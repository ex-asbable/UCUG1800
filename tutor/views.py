import json
from collections import Counter

from .contracts import Question
from .jobs import lookup, public_job
from .materials import topic_version


class Views:
    def __init__(self, service):
        self.store = service.store
        self.localizer = service.localizer
        self.locale = service.locale

    def materials(self, course_id):
        with self.store.connect() as db:
            course = lookup(db, "courses", course_id)
            materials = []
            for row in db.execute("SELECT * FROM materials WHERE course_id = ? ORDER BY created", (course_id,)):
                pages = db.execute(
                    "SELECT number, status FROM pages WHERE material_id = ? ORDER BY number", (row["id"],),
                ).fetchall()
                materials.append({
                    "id": row["id"], "filename": row["filename"], "status": row["status"],
                    "active": bool(row["active"]), "pageCount": len(pages),
                    "unreadablePages": [page["number"] for page in pages if page["status"] != "readable"],
                })
            jobs = [
                public_job(row) for row in db.execute(
                    """SELECT * FROM jobs WHERE course_id = ? AND status <> 'ready'
                       ORDER BY created DESC LIMIT 30""", (course_id,),
                )
            ]
        return {
            "course": {"id": course["id"], "name": course["name"], "outlineId": course["outline_id"]},
            "materials": materials, "jobs": jobs,
        }

    def topic_list(self, course_id):
        translations = []
        with self.store.connect() as db:
            course = lookup(db, "courses", course_id)
            locale = self.locale(db)
            statuses = self.topic_statuses(db, course_id)
            topics = [
                self.topic_view(row, translations, statuses.get(row["topic_id"], "unassessed"))
                for row in db.execute(
                    "SELECT * FROM topic_versions WHERE outline_id = ? ORDER BY position", (course["outline_id"],),
                )
            ]
        self.localizer.render(translations, locale)
        return {"outlineId": course["outline_id"], "locale": locale, "topics": topics}

    @staticmethod
    def topic_statuses(db, course_id):
        priority = {"review_needed": 4, "pending": 3, "resolved": 2, "not_confirmed": 1}
        statuses = {}
        for row in db.execute(
            """SELECT g.topic_id, g.status FROM gaps g JOIN topics t ON t.id = g.topic_id WHERE t.course_id = ?""",
            (course_id,),
        ):
            if priority[row["status"]] > priority.get(statuses.get(row["topic_id"]), 0):
                statuses[row["topic_id"]] = row["status"]
        return statuses

    @staticmethod
    def topic_view(row, translations, status=None):
        topic = {
            "id": row["topic_id"], "parentId": row["parent_id"], "position": row["position"],
            **json.loads(row["content"]),
        }
        if status:
            topic["status"] = status
        translations.extend((topic, key, row["locale"]) for key in ("title", "explanation", "opening"))
        return topic

    def sessions(self, course_id):
        translations = []
        with self.store.connect() as db:
            lookup(db, "courses", course_id)
            locale = self.locale(db)
            sessions = []
            for row in db.execute("SELECT * FROM sessions WHERE course_id = ? ORDER BY updated DESC", (course_id,)):
                item = {"id": row["id"], "topicId": row["topic_id"], "updated": row["updated"], "title": None}
                topic = topic_version(db, row["outline_id"], row["topic_id"])
                if topic:
                    item["title"] = json.loads(topic["content"])["title"]
                    translations.append((item, "title", topic["locale"]))
                else:
                    message = db.execute(
                        "SELECT text FROM messages WHERE session_id = ? AND role = 'student' ORDER BY seq LIMIT 1", (row["id"],),
                    ).fetchone()
                    item["title"] = message["text"][:100] if message else None
                sessions.append(item)
        self.localizer.render(translations, locale)
        return {"locale": locale, "sessions": sessions}

    def session(self, session_id):
        translations = []
        with self.store.connect() as db:
            row = lookup(db, "sessions", session_id)
            locale = self.locale(db)
            check = db.execute(
                """SELECT id, status FROM checks WHERE session_id = ? AND status <> 'abandoned'
                   ORDER BY created DESC LIMIT 1""", (session_id,),
            ).fetchone()
            locked = check and check["status"] in ("open", "submitted")
            topic = topic_version(db, row["outline_id"], row["topic_id"]) if not locked else None
            messages = []
            gaps = []
            if not locked:
                for message in db.execute(
                    "SELECT * FROM messages WHERE session_id = ? AND kind <> 'check_evidence' ORDER BY seq", (session_id,),
                ):
                    item = {
                        "id": message["id"], "role": message["role"], "text": message["text"],
                        "sources": json.loads(message["sources"]),
                    }
                    messages.append(item)
                    if message["role"] == "tutor":
                        translations.append((item, "text", message["locale"]))
                gaps.extend(
                    self.gap_view(gap, translations)
                    for gap in db.execute(
                        """SELECT g.*, m.text AS trigger FROM gaps g JOIN messages m ON m.id = g.trigger_id
                           WHERE g.session_id = ? ORDER BY g.updated DESC""", (session_id,),
                    )
                )
            data = {
                "id": session_id, "courseId": row["course_id"], "outlineId": row["outline_id"],
                "topicId": row["topic_id"], "topic": self.topic_view(topic, translations) if topic else None,
                "locale": locale, "messages": messages, "gaps": gaps, "check": dict(check) if check else None,
                "jobs": [
                    public_job(job) for job in db.execute(
                        """SELECT * FROM jobs WHERE json_extract(payload, '$.sessionId') = ?
                           AND status <> 'ready' ORDER BY created DESC""", (session_id,),
                    )
                ],
            }
        self.localizer.render(translations, locale)
        return data

    @staticmethod
    def gap_view(row, translations):
        item = {
            "id": row["id"], "topicId": row["topic_id"], "sessionId": row["session_id"],
            "description": row["description"], "status": row["status"], "reason": row["reason"],
            "trigger": row["trigger"],
        }
        translations.append((item, "description", row["locale"]))
        return item

    def get_check(self, check_id):
        translations = []
        with self.store.connect() as db:
            row = lookup(db, "checks", check_id)
            locale = self.locale(db)
            question = Question.model_validate_json(row["body"])
            item = {
                "id": check_id, "locale": locale, "sessionId": row["session_id"], "status": row["status"],
                "format": question.format, "prompt": question.prompt, "requiresReason": question.requiresReason,
                "options": [option.model_dump(include={"id", "text"}) for option in question.options],
                "fields": [field.model_dump(include={"id", "label"}) for field in question.fields],
            }
            translations.append((item, "prompt", row["locale"]))
            translations.extend((option, "text", row["locale"]) for option in item["options"])
            translations.extend((field, "label", row["locale"]) for field in item["fields"])
            attempt = db.execute("SELECT * FROM attempts WHERE check_id = ?", (check_id,)).fetchone()
            if attempt:
                item["attempt"] = {
                    "id": attempt["id"], "answer": json.loads(attempt["answer"]), "reason": attempt["reason"],
                    "result": json.loads(attempt["result"]) if attempt["result"] else None,
                }
                if item["attempt"]["result"]:
                    item["solution"] = question.solution
                    item["sources"] = [source.model_dump() for source in question.sources]
                    translations.append((item, "solution", row["locale"]))
                    translations.append((item["attempt"]["result"], "feedback", attempt["locale"]))
        self.localizer.render(translations, locale)
        return item

    def review(self, course_id):
        translations = []
        with self.store.connect() as db:
            course = lookup(db, "courses", course_id)
            locale = self.locale(db)
            rows = db.execute(
                """SELECT g.*, m.text AS trigger, s.outline_id, a.result AS evaluation, a.check_id AS check_id
                   FROM gaps g JOIN messages m ON m.id = g.trigger_id JOIN sessions s ON s.id = g.session_id
                   LEFT JOIN attempts a ON a.id = g.attempt_id
                   WHERE s.course_id = ? AND g.status = 'review_needed' ORDER BY g.updated DESC""", (course_id,),
            ).fetchall()
            counts = Counter(row["topic_id"] for row in rows)
            topics = {}
            for row in rows:
                group = topics.get(row["topic_id"])
                if group is None:
                    topic = topic_version(db, course["outline_id"], row["topic_id"]) or topic_version(
                        db, row["outline_id"], row["topic_id"],
                    )
                    group = {
                        "topic": self.topic_view(topic, translations), "count": counts[row["topic_id"]], "gaps": [],
                    }
                    topics[row["topic_id"]] = group
                gap = self.gap_view(row, translations)
                gap["checkId"] = row["check_id"]
                gap["evidence"] = json.loads(row["evaluation"]).get("evidence") if row["evaluation"] else None
                group["gaps"].append(gap)
        self.localizer.render(translations, locale)
        return {
            "locale": locale,
            "topics": sorted(topics.values(), key=lambda group: (-group["count"], group["topic"]["position"])),
        }
