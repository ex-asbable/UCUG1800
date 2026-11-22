import hashlib
import json
import re
from threading import Lock
from pathlib import PurePosixPath

from .contracts import Dialogue, Evaluation, Hypothesis, Question, QuestionAudit, RuntimeSettings, TopicSelection
from .grading import UnsupportedMath, match_tex, normalize_text, tex_value
from .jobs import AppError, Job, JobWorker, complete, create_job, find_job, lookup
from .localization import Localizer
from .materials import (
    KEY, build_outline, outline_pages, publish_outline, read_pdf, readable_pages,
    select_pages, source_ids, topic_version, validate_sources,
)
from .models import ModelError, validate_language
from .storage import Store, encode, new_id, now


DIALOGUE_RULES = """Guide the learner one step at a time. If only a question was supplied,
ask how they would start, which topic it relates to, or what they have tried. Based on
their reasoning ask a focused question, or give one targeted hint or brief example.
Only propose a hypothesis for a specific misunderstanding with supporting evidence in
the student's latest message. Its evidence must be a verbatim substring of that message.
Use a consistent English snake_case key from known hypotheses when the concept matches.
Never diagnose mastery from a first attempt. Return topicKey from the supplied course
topics if the connection is clear. Ask for material or clarification when necessary.
Ground explanatory claims in the supplied excerpts and cite those excerpts."""

QUESTION_RULES = """Produce exactly one new short independent question in the requested
format. It must be self-contained and present a new example testing the specified topic
and, when present, the specific suspected gap. Do not give hints or put the answer in
the prompt or labels. Use a short rubric describing both correct reasoning and what
evidence distinguishes this gap from another error. Use distinct short IDs. For
choice, provide 3 to 5 options, exactly one correctOptionId, and empty fields. A
distractor is same_gap only when uniquely diagnostic. The correct option has diagnostic
none. For text or tex, provide fields with accepted answers and a null correctOptionId
and no options. For tex use only rational numbers, fractions, polynomials of low
degree, or a single-variable linear equation; accepted entries must all be equivalent
within a field. When checking a gap, require a short explanation from the student.
Provide an independent solution and genuine course citations. Use different contexts
and values from previous questions or guided examples."""

EVALUATION_RULES = """Assess the student's submitted answer against the question and
rubric. If objectiveCorrectness is given, do not override it. For a gap, mark same_gap
only if the independent answer or reason repeats the exact misconception. Use
demonstrated only when the student gives the key reasoning and their answer is correct.
Use other_error for a different identifiable error, and insufficient for truncated,
contradictory or ambiguous evidence. In evidence quote an exact short substring of the
student's submission or return an empty string for insufficient evidence. The feedback
should explain the decision in the requested locale. For a different specific gap,
provide otherHypothesis supported by an exact substring of the student's submission."""


class TutorService:
    def __init__(self, store: Store, provider):
        self.store = store
        self.provider = provider
        self.localizer = Localizer(store, provider)
        self.worker = JobWorker(store, self.run)
        self.runtime_lock = Lock()

    def configure_runtime(self, settings: RuntimeSettings):
        with self.runtime_lock:
            try:
                candidate = self.provider.configured(settings)
            except ModelError as error:
                raise AppError(error.code, 422) from error
            status = candidate.status()
            if not status["ready"]:
                raise AppError(status["error"], 422)
            with self.store.connect(write=True) as db:
                if db.execute("SELECT 1 FROM jobs WHERE status IN ('queued', 'running') LIMIT 1").fetchone():
                    raise AppError("runtime_busy", 409)
                self.provider = candidate
                self.localizer.provider = candidate
            return status

    @staticmethod
    def locale(db):
        return db.execute("SELECT locale FROM preferences WHERE id = 1").fetchone()[0]

    def import_material(self, course_id, filename, file_bytes, request_id, replaces):
        filename = PurePosixPath(filename.replace("\\", "/")).name
        if not filename or not filename.lower().endswith(".pdf"):
            raise AppError("unsupported_format", 415)
        if len(filename) > 240 or not re.match(br"%PDF-\d\.\d", file_bytes.lstrip()[:8]):
            raise AppError("invalid_pdf", 422)
        digest = hashlib.sha256(file_bytes).hexdigest()
        input_data = {"filename": filename, "digest": digest, "replacesId": replaces}
        target = None
        try:
            with self.store.connect(write=True) as db:
                lookup(db, "courses", course_id)
                if old := find_job(db, course_id, "import", request_id, input_data):
                    return json.loads(old["payload"])["materialId"], old["id"]
                if replaces and not lookup(db, "materials", replaces, course_id)["active"]:
                    raise AppError("stale_material", 409)
                material_id = new_id()
                target = self.store.material_file(material_id)
                target.write_bytes(file_bytes)
                db.execute(
                    """INSERT INTO materials (id, course_id, filename, digest, replaces_id, status, created)
                       VALUES (?, ?, ?, ?, ?, 'queued', ?)""",
                    (material_id, course_id, filename, digest, replaces, now()),
                )
                job_id = create_job(
                    db, "import", course_id, request_id, self.locale(db),
                    {"input": input_data, "materialId": material_id},
                )
        except Exception:
            if target:
                target.unlink(missing_ok=True)
            raise
        self.worker.notify()
        return material_id, job_id

    def start_session(self, course_id, topic_id, question, request_id):
        input_data = {"topicId": topic_id, "question": question}
        with self.store.connect(write=True) as db:
            course = lookup(db, "courses", course_id)
            if job := find_job(db, course_id, "start", request_id, input_data):
                return json.loads(job["payload"])["sessionId"], job["id"]
            outline_id = course["outline_id"]
            if not outline_id:
                raise AppError("course_not_ready", 409)
            if topic_id:
                topic = topic_version(db, outline_id, topic_id)
                if not topic:
                    raise AppError("not_found", 404)
                if json.loads(topic["content"])["coverage"] == "missing":
                    raise AppError("missing_material", 409)
            session_id = new_id()
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)", (session_id, course_id, outline_id, topic_id, now()))
            message_id = self.save_message(db, session_id, "student", question) if question else None
            job_id = create_job(
                db, "start", course_id, request_id, self.locale(db),
                {"input": input_data, "sessionId": session_id, "messageId": message_id},
            )
        self.worker.notify()
        return session_id, job_id

    def send_message(self, session_id, text, request_id):
        input_data = {"sessionId": session_id, "text": text}
        with self.store.connect(write=True) as db:
            session = lookup(db, "sessions", session_id)
            course_id = session["course_id"]
            if job := find_job(db, course_id, "dialogue", request_id, input_data):
                return job["id"]
            self.assert_no_check(db, session_id)
            self.assert_no_job(db, session_id, ("start", "dialogue", "question"))
            self.assert_no_failed_dialogue(db, session_id)
            message_id = self.save_message(db, session_id, "student", text)
            job_id = create_job(
                db, "dialogue", course_id, request_id, self.locale(db),
                {"input": input_data, "sessionId": session_id, "messageId": message_id},
            )
        self.worker.notify()
        return job_id

    @staticmethod
    def save_message(db, session_id, role, text, locale=None, sources=None, kind="dialogue"):
        identifier = new_id()
        db.execute(
            "INSERT INTO messages (id, session_id, role, locale, text, sources, kind, created) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (identifier, session_id, role, locale, text, encode(sources or []), kind, now()),
        )
        db.execute("UPDATE sessions SET updated = ? WHERE id = ?", (now(), session_id))
        return identifier

    @staticmethod
    def assert_no_job(db, session_id, kinds):
        jobs = db.execute(
            """SELECT kind FROM jobs WHERE status IN ('queued', 'running') AND json_extract(payload, '$.sessionId') = ?""",
            (session_id,),
        )
        if any(job["kind"] in kinds for job in jobs):
            raise AppError("task_in_progress", 409)

    @staticmethod
    def assert_no_failed_dialogue(db, session_id):
        if db.execute(
            """SELECT 1 FROM jobs WHERE status = 'failed' AND kind IN ('start', 'dialogue')
               AND json_extract(payload, '$.sessionId') = ? LIMIT 1""", (session_id,),
        ).fetchone():
            raise AppError("retry_previous", 409)

    @staticmethod
    def assert_no_check(db, session_id):
        if db.execute("SELECT 1 FROM checks WHERE session_id = ? AND status = 'open'", (session_id,)).fetchone():
            raise AppError("independent_check_open", 409)
        if db.execute(
            """SELECT 1 FROM attempts a JOIN checks c ON c.id = a.check_id
               WHERE c.session_id = ? AND a.result IS NULL""", (session_id,),
        ).fetchone():
            raise AppError("answer_pending", 409)

    def request_check(self, session_id, gap_id, purpose, preferred_format, request_id):
        input_data = {"sessionId": session_id, "gapId": gap_id, "purpose": purpose, "format": preferred_format}
        with self.store.connect(write=True) as db:
            session = lookup(db, "sessions", session_id)
            course_id = session["course_id"]
            if job := find_job(db, course_id, "question", request_id, input_data):
                return job["id"]
            self.assert_no_check(db, session_id)
            self.assert_no_job(db, session_id, ("start", "question", "dialogue"))
            self.assert_no_failed_dialogue(db, session_id)
            if gap_id:
                gap = lookup(db, "gaps", gap_id)
                if gap["session_id"] != session_id:
                    raise AppError("not_found", 404)
                required = "review_needed" if purpose == "review" else "pending"
                if gap["status"] != required:
                    raise AppError("gap_changed", 409)
            elif not session["topic_id"]:
                raise AppError("topic_needed", 409)
            job_id = create_job(
                db, "question", course_id, request_id, self.locale(db),
                {"input": input_data, "sessionId": session_id},
            )
        self.worker.notify()
        return job_id

    def leave_check(self, check_id):
        with self.store.connect(write=True) as db:
            check = lookup(db, "checks", check_id)
            if check["status"] not in ("open", "abandoned"):
                raise AppError("check_closed", 409)
            db.execute("UPDATE checks SET status = 'abandoned' WHERE id = ?", (check_id,))

    def submit(self, check_id, answer, reason, request_id):
        input_data = {"checkId": check_id, "answer": answer, "reason": reason}
        with self.store.connect(write=True) as db:
            check = lookup(db, "checks", check_id)
            session = lookup(db, "sessions", check["session_id"])
            course_id = session["course_id"]
            if job := find_job(db, course_id, "evaluate", request_id, input_data):
                return json.loads(job["payload"])["attemptId"], job["id"]
            if check["status"] != "open":
                raise AppError("check_closed", 409)
            question = Question.model_validate_json(check["body"])
            self.validate_answer(question, answer)
            attempt_id = new_id()
            locale = self.locale(db)
            db.execute(
                "INSERT INTO attempts (id, check_id, answer, reason, locale, created) VALUES (?, ?, ?, ?, ?, ?)",
                (attempt_id, check_id, encode(answer), reason, locale, now()),
            )
            db.execute("UPDATE checks SET status = 'submitted' WHERE id = ?", (check_id,))
            job_id = create_job(
                db, "evaluate", course_id, request_id, locale,
                {"input": input_data, "sessionId": session["id"], "attemptId": attempt_id},
            )
        self.worker.notify()
        return attempt_id, job_id

    @staticmethod
    def validate_answer(question: Question, answer):
        if question.format == "choice":
            if not isinstance(answer, str) or answer not in {item.id for item in question.options}:
                raise AppError("invalid_answer", 422)
        elif not isinstance(answer, dict) or set(answer) != {item.id for item in question.fields}:
            raise AppError("invalid_answer", 422)
        elif not any(value.strip() for value in answer.values()):
            raise AppError("invalid_answer", 422)

    def retry(self, course_id, job_id):
        with self.store.connect(write=True) as db:
            row = lookup(db, "jobs", job_id, course_id)
            if row["status"] == "failed":
                payload = json.loads(row["payload"])
                if row["kind"] in ("start", "dialogue", "question"):
                    self.assert_no_check(db, payload["sessionId"])
                    self.assert_no_job(db, payload["sessionId"], ("start", "dialogue", "question"))
                if row["kind"] == "question":
                    self.assert_no_failed_dialogue(db, payload["sessionId"])
                db.execute("UPDATE jobs SET status = 'queued', stage = 'queued', error = NULL WHERE id = ?", (job_id,))
                if row["kind"] == "import":
                    db.execute(
                        "UPDATE materials SET status = 'queued' WHERE id = ?", (payload["materialId"],),
                    )
        self.worker.notify()

    def run(self, job: Job):
        if job.kind == "import":
            self.run_import(job)
        elif job.kind in ("start", "dialogue"):
            self.run_dialogue(job)
        elif job.kind == "question":
            self.run_question(job)
        elif job.kind == "evaluate":
            self.run_evaluation(job)

    def run_import(self, job: Job):
        material_id = job.payload["materialId"]
        with self.store.connect(write=True) as db:
            material = lookup(db, "materials", material_id, job.course)
            if material["replaces_id"] and not lookup(db, "materials", material["replaces_id"], job.course)["active"]:
                raise AppError("stale_material", 409)
            db.execute("UPDATE jobs SET stage = 'parsing' WHERE id = ?", (job.id,))
            db.execute("UPDATE materials SET status = 'parsing' WHERE id = ?", (material_id,))
            parsed = db.execute("SELECT count(*) FROM pages WHERE material_id = ?", (material_id,)).fetchone()[0]
        if not parsed:
            pages = read_pdf(self.store.material_file(material_id))
            with self.store.connect(write=True) as db:
                db.executemany("INSERT INTO pages VALUES (?, ?, ?, ?)", [(material_id, *page) for page in pages])
        with self.store.connect(write=True) as db:
            if not readable_pages(db, [material_id]):
                raise AppError("no_readable_text", 422)
            db.execute("UPDATE jobs SET stage = 'generating' WHERE id = ?", (job.id,))
            db.execute("UPDATE materials SET status = 'generating' WHERE id = ?", (material_id,))
            course = lookup(db, "courses", job.course)
            active = [
                row["id"] for row in db.execute(
                    "SELECT id FROM materials WHERE course_id = ? AND active = 1 ORDER BY created", (job.course,),
                )
            ]
            if material["replaces_id"]:
                active[active.index(material["replaces_id"])] = material_id
            else:
                active.append(material_id)
            pages = readable_pages(db, active)
            old_topics = [
                {"key": row["key"], "title": json.loads(row["content"])["title"]}
                for row in db.execute(
                    """SELECT t.key, tv.content FROM topic_versions tv JOIN topics t ON t.id = tv.topic_id
                       WHERE tv.outline_id = ? ORDER BY tv.position""", (course["outline_id"],),
                )
            ]
        topics = build_outline(self.provider, name=course["name"], pages=pages, old_topics=old_topics, locale=job.locale)
        with self.store.connect(write=True) as db:
            if material["replaces_id"]:
                db.execute("UPDATE materials SET active = 0, status = 'superseded' WHERE id = ?", (material["replaces_id"],))
            db.execute("UPDATE materials SET active = 1, status = 'ready' WHERE id = ?", (material_id,))
            outline_id = publish_outline(db, job.course, active, topics, job.locale)
            complete(db, job, {"materialId": material_id, "outlineId": outline_id})

    def conversation_context(self, db, session, query):
        topic = topic_version(db, session["outline_id"], session["topic_id"])
        content = json.loads(topic["content"]) if topic else {}
        pages = outline_pages(db, session["outline_id"])
        return topic, content, select_pages(pages, f"{content.get('title', '')} {query}", content.get("sources"))

    def run_dialogue(self, job: Job):
        session_id = job.payload["sessionId"]
        message_id = job.payload["messageId"]
        with self.store.connect() as db:
            session = lookup(db, "sessions", session_id, job.course)
            rows = db.execute(
                """SELECT id, role, text FROM
                   (SELECT id, role, text, seq FROM messages WHERE session_id = ? ORDER BY seq DESC LIMIT 12)
                   ORDER BY seq""", (session_id,),
            ).fetchall()
            topics = [
                {
                    "id": row["topic_id"], "key": row["key"], "title": json.loads(row["content"])["title"],
                    "coverage": json.loads(row["content"])["coverage"],
                }
                for row in db.execute(
                    """SELECT tv.*, t.key FROM topic_versions tv JOIN topics t ON t.id = tv.topic_id
                       WHERE tv.outline_id = ? ORDER BY tv.position""", (session["outline_id"],),
                )
            ]
            gaps = [
                dict(row) for row in db.execute("SELECT key, description FROM gaps WHERE session_id = ?", (session_id,))
            ]
        latest = next((row["text"] for row in rows if row["id"] == message_id), "")
        topic_id = session["topic_id"]
        if not topic_id and latest:
            prediction = self.provider.generate(
                "select_topic",
                "Choose a topic key from the outline when the student question is clearly related, otherwise return null.",
                {"locale": job.locale, "question": latest, "topics": [{"key": row["key"], "title": row["title"]} for row in topics]},
                TopicSelection,
            )
            topic_id = next((
                row["id"] for row in topics if row["key"] == prediction.topicKey and row["coverage"] != "missing"
            ), None)
        with self.store.connect() as db:
            topic, content, pages = self.conversation_context(db, {**dict(session), "topic_id": topic_id}, latest)
        if not message_id and topic:
            with self.store.connect(write=True) as db:
                self.save_message(db, session_id, "tutor", content["opening"], topic["locale"], content["sources"])
                complete(db, job, {"sessionId": session_id})
            return
        result = self.provider.generate(
            "dialogue", DIALOGUE_RULES,
            {
                "locale": job.locale, "latestStudentMessage": latest,
                "messages": [{"role": row["role"], "text": row["text"][:2500]} for row in rows],
                "topics": [{"key": row["key"], "title": row["title"], "coverage": row["coverage"]} for row in topics],
                "currentTopic": topic["key"] if topic else None, "knownHypotheses": gaps, "pages": pages,
            }, Dialogue,
        )
        if not result.message.strip() or len(result.message) > 7000:
            raise ModelError("invalid_model_output")
        validate_sources(result.sources, source_ids(pages))
        validate_language([result.message, result.hypothesis.description if result.hypothesis else ""], job.locale)
        if not topic_id:
            topic_id = next((
                row["id"] for row in topics if row["key"] == result.topicKey and row["coverage"] != "missing"
            ), None)
        refs = [source.model_dump() for source in result.sources]
        with self.store.connect(write=True) as db:
            if topic_id and not session["topic_id"]:
                db.execute("UPDATE sessions SET topic_id = ? WHERE id = ?", (topic_id, session_id))
            self.save_message(db, session_id, "tutor", result.message, job.locale, refs)
            if result.hypothesis and topic_id and message_id:
                self.save_gap(db, session_id, topic_id, message_id, latest, result.hypothesis, job.locale)
            complete(db, job, {"sessionId": session_id})

    @staticmethod
    def save_gap(db, session_id, topic_id, message_id, student_text, hypothesis: Hypothesis, locale):
        evidence = hypothesis.evidence.strip()
        if not KEY.fullmatch(hypothesis.key) or not hypothesis.description.strip() or not evidence or evidence not in student_text:
            raise ModelError("invalid_evidence")
        row = db.execute("SELECT id, status FROM gaps WHERE session_id = ? AND key = ?", (session_id, hypothesis.key)).fetchone()
        if not row:
            db.execute(
                """INSERT INTO gaps (id, session_id, topic_id, key, locale, description, trigger_id, status, updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (new_id(), session_id, topic_id, hypothesis.key, locale, hypothesis.description, message_id, now()),
            )
        elif row["status"] in ("not_confirmed", "resolved"):
            db.execute(
                "UPDATE gaps SET trigger_id = ?, status = 'pending', reason = NULL, attempt_id = NULL, updated = ? WHERE id = ?",
                (message_id, now(), row["id"]),
            )

    def run_question(self, job: Job):
        inputs = job.payload["input"]
        session_id = inputs["sessionId"]
        with self.store.connect() as db:
            session = lookup(db, "sessions", session_id, job.course)
            gap = lookup(db, "gaps", inputs["gapId"]) if inputs["gapId"] else None
            required = "review_needed" if inputs["purpose"] == "review" else "pending"
            if gap and gap["status"] != required:
                raise AppError("gap_changed", 409)
            description = gap["description"] if gap else ""
            topic, content, pages = self.conversation_context(db, session, description)
            recent_prompts = [
                json.loads(row["body"])["prompt"]
                for row in db.execute(
                    "SELECT body FROM checks WHERE session_id = ? ORDER BY created DESC LIMIT 20", (session_id,),
                )
            ]
            guided = [
                row["text"][:1000]
                for row in db.execute(
                    """SELECT text FROM messages WHERE session_id = ? AND role = 'tutor'
                       ORDER BY seq DESC LIMIT 5""", (session_id,),
                )
            ]
        if not topic or not pages:
            raise AppError("topic_needed", 409)
        format_name = inputs["format"] or ("text" if gap else "choice")
        data = {
            "locale": job.locale, "format": format_name, "topic": content["title"],
            "gap": description, "purpose": inputs["purpose"],
            "previousQuestions": recent_prompts, "guidedExamples": guided, "pages": pages,
        }
        question = self.provider.generate("question", QUESTION_RULES, data, Question)
        self.validate_question(question, format_name, gap is not None, pages, recent_prompts)
        audit = self.provider.generate(
            "audit_question",
            "Independently solve the question and verify the rubric and answer. Return valid only if the question "
            "is self-contained, answer is correct, no hint is disclosed, options are unambiguous, supporting "
            "sources are relevant, and it uses a fresh scenario that tests the requested gap when present.",
            {"locale": job.locale, "question": question.model_dump(), "topic": content["title"],
             "gap": description, "pages": pages, "previousQuestions": recent_prompts},
            QuestionAudit,
        )
        if not audit.valid:
            raise ModelError("question_unverified")
        with self.store.connect(write=True) as db:
            self.assert_no_check(db, session_id)
            check_id = new_id()
            db.execute(
                "INSERT INTO checks VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)",
                (
                    check_id, session_id, session["topic_id"], inputs["gapId"], inputs["purpose"],
                    job.locale, question.model_dump_json(), now(),
                ),
            )
            complete(db, job, {"checkId": check_id, "sessionId": session_id})

    @staticmethod
    def validate_question(question, format_name, requires_reason, pages, recent_prompts):
        if (
            question.format != format_name or (requires_reason and not question.requiresReason)
            or not all(part.strip() for part in (question.prompt, question.rubric, question.solution))
            or len(question.prompt) > 4200 or len(question.rubric) > 4200 or len(question.solution) > 4200
        ):
            raise ModelError("invalid_model_output")
        if normalize_text(question.prompt) in {normalize_text(old) for old in recent_prompts}:
            raise ModelError("repeated_question")
        validate_sources(question.sources, source_ids(pages), required=True)
        if question.format == "choice":
            ids = {item.id for item in question.options}
            labels = {normalize_text(item.text) for item in question.options}
            if (
                not 3 <= len(ids) <= 5 or len(ids) != len(question.options) or len(labels) != len(ids)
                or "" in labels or question.fields or question.correctOptionId not in ids
                or any(item.id == question.correctOptionId and item.diagnostic != "none" for item in question.options)
            ):
                raise ModelError("invalid_model_output")
        else:
            ids = {item.id for item in question.fields}
            if (
                not 1 <= len(ids) <= 6 or len(ids) != len(question.fields)
                or question.options or question.correctOptionId is not None
                or any(not field.label.strip() or not 1 <= len(field.accepted) <= 12
                       or any(not answer.strip() for answer in field.accepted) for field in question.fields)
            ):
                raise ModelError("invalid_model_output")
            if question.format == "tex":
                try:
                    for field in question.fields:
                        reference = tex_value(field.accepted[0])
                        if any(tex_value(value) != reference for value in field.accepted[1:]):
                            raise UnsupportedMath()
                except (UnsupportedMath, ValueError, ZeroDivisionError) as error:
                    raise ModelError("invalid_model_output") from error
        if not all(re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", identifier) for identifier in ids):
            raise ModelError("invalid_model_output")
        validate_language(
            [question.prompt, question.solution, *(option.text for option in question.options),
             *(field.label for field in question.fields)], question.locale,
        )

    @staticmethod
    def grade_objectively(question, answer):
        if question.format == "choice":
            return "correct" if answer == question.correctOptionId else "incorrect"
        if question.format == "tex":
            matches = [match_tex(answer[field.id], field.accepted) for field in question.fields]
            if False in matches:
                return "incorrect"
            return "uncertain" if None in matches else "correct"
        if all(normalize_text(answer[field.id]) in {normalize_text(value) for value in field.accepted}
               for field in question.fields):
            return "correct"
        return None

    def evaluate_answer(self, job, question, answer, reason, gap, pages):
        objective = self.grade_objectively(question, answer)
        reason = reason.strip()
        raw = "\n".join([answer] if isinstance(answer, str) else answer.values())
        raw = f"{raw}\n{reason}".strip()
        selected = next((option for option in question.options if option.id == answer), None)
        if objective == "uncertain":
            return objective, "insufficient", raw, None, "unsupported_tex", None
        if question.requiresReason and not reason:
            return objective or "uncertain", "insufficient", raw, None, "reason_needed", None
        if objective is not None and not gap and not question.requiresReason and not reason:
            return objective, "demonstrated" if objective == "correct" else "insufficient", raw, None, objective, None
        evaluation = self.provider.generate(
            "evaluate", EVALUATION_RULES,
            {
                "locale": job.locale, "question": question.model_dump(),
                "objectiveCorrectness": objective, "gap": gap["description"] if gap else None,
                "answer": answer, "reason": reason, "selectedOption": selected.text if selected else None,
                "verbatimStudentSubmission": raw, "pages": pages,
            },
            Evaluation,
        )
        evidence = evaluation.evidence.strip()
        if (not evaluation.feedback.strip() or len(evaluation.feedback) > 5400
                or (evaluation.evidenceType != "insufficient" and not evidence)
                or (evidence and evidence not in raw)):
            raise ModelError("invalid_evidence")
        validate_language([evaluation.feedback], job.locale)
        correctness = objective or evaluation.correctness
        evidence_type = evaluation.evidenceType
        if objective and evaluation.correctness != objective:
            raise ModelError("invalid_model_output")
        if correctness == "uncertain" or (evidence_type == "demonstrated" and correctness != "correct"):
            evidence_type = "insufficient"
        if evidence_type == "same_gap" and not gap:
            evidence_type = "insufficient"
        return correctness, evidence_type, evidence, evaluation.feedback, None, evaluation.otherHypothesis

    def run_evaluation(self, job: Job):
        with self.store.connect() as db:
            session = lookup(db, "sessions", job.payload["sessionId"], job.course)
            check = lookup(db, "checks", job.payload["input"]["checkId"])
            attempt = db.execute("SELECT * FROM attempts WHERE id = ?", (job.payload["attemptId"],)).fetchone()
            gap = lookup(db, "gaps", check["gap_id"]) if check["gap_id"] else None
            question = Question.model_validate_json(check["body"])
            pages = select_pages(
                outline_pages(db, session["outline_id"]), question.prompt,
                [source.model_dump() for source in question.sources],
            )
        answer = json.loads(attempt["answer"])
        reason = attempt["reason"]
        correctness, evidence_type, evidence, feedback, code, other = self.evaluate_answer(
            job, question, answer, reason, gap, pages,
        )
        result = {
            "correctness": correctness, "evidence": evidence, "feedback": feedback, "feedbackCode": code,
            "gapStatus": gap["status"] if gap else None, "evidenceType": evidence_type,
        }
        with self.store.connect(write=True) as db:
            if gap:
                status, pending_reason = self.transition(gap["status"], check["purpose"], result, code)
                result["gapStatus"] = status
                if status != gap["status"] or status == "pending":
                    db.execute(
                        "UPDATE gaps SET status = ?, reason = ?, attempt_id = ?, updated = ? WHERE id = ?",
                        (status, pending_reason, attempt["id"], now(), gap["id"]),
                    )
            if other and evidence_type == "other_error" and session["topic_id"] and (not gap or other.key != gap["key"]):
                raw = "\n".join([answer] if isinstance(answer, str) else answer.values()) + "\n" + reason
                message_id = self.save_message(db, session["id"], "student", raw.strip(), kind="check_evidence")
                self.save_gap(db, session["id"], session["topic_id"], message_id, raw, other, job.locale)
            db.execute("UPDATE attempts SET result = ? WHERE id = ?", (encode(result), attempt["id"]))
            db.execute("UPDATE checks SET status = 'graded' WHERE id = ?", (check["id"],))
            db.execute("UPDATE sessions SET updated = ? WHERE id = ?", (now(), session["id"]))
            complete(db, job, {"checkId": check["id"], "attemptId": attempt["id"], "sessionId": session["id"]})

    @staticmethod
    def transition(previous, purpose, result, code):
        kind = result["evidenceType"]
        if purpose == "review":
            return ("resolved", None) if kind == "demonstrated" else (previous, None)
        if previous != "pending":
            return previous, None
        if kind == "same_gap":
            return "review_needed", None
        if kind in ("demonstrated", "other_error"):
            return "not_confirmed", None
        return "pending", code or "insufficient_evidence"
