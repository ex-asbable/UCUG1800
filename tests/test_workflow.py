import io
import json
import os
import re
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tutor.grading import match_tex
from tutor.contracts import TopicSelection
from tutor.main import create_app
from tutor.materials import read_pdf
from tutor.models import ModelError, Provider


BASE = "/api/v1"


def pdf_bytes(*texts):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        if not text:
            continue
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 730 Td ({text}) Tj ET".encode())
        page.replace_contents(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class FixtureProvider:
    """Predictable teaching outputs so tests can isolate persistence and rules."""

    def __init__(self):
        self.questions = 0
        self.fail_evaluation = False
        self.invalid_citation = False

    def status(self):
        return {"provider": "api", "ready": True, "error": None}

    def generate(self, task, _instructions, data, schema):
        locale = data["locale"]
        en = locale == "en"
        pages = data.get("pages", [])
        sources = [{key: page[key] for key in ("materialId", "page")} for page in pages[:1]]
        if task in ("outline", "merge_outline"):
            result = {"topics": [{
                "key": "hypothesis_testing", "parentKey": None,
                "title": "Hypothesis testing" if en else "假设检验",
                "coverage": "supported", "explanation": "Compare $p$ and $\\alpha$." if en else "比较 $p$ 和 $\\alpha$。",
                "opening": "How would you begin?" if en else "你会从哪一步开始？",
                "sources": sources if not self.invalid_citation else [{"materialId": "other", "page": 500}],
            }]}
        elif task == "select_topic":
            result = {"topicKey": "hypothesis_testing"}
        elif task == "dialogue":
            raw = data["latestStudentMessage"]
            result = {
                "topicKey": "hypothesis_testing",
                "message": "What does failing to reject tell you?" if en else "未拒绝原假设时，你能判断它为真吗？",
                "sources": sources, "hypothesis": {
                    "key": "non_rejection", "description": "Confuses failure to reject with proof." if en else "把未拒绝误认为证明原假设成立。",
                    "evidence": "证明原假设成立",
                } if "证明原假设成立" in raw else None,
            }
        elif task == "question":
            self.questions += 1
            kind = data["format"]
            number = str(self.questions)
            prompt = {
                "choice": "Select the error type in scenario " + number + ".",
                "text": "Explain the conclusion in scenario " + number + " when $p=0.08$.",
                "tex": "Enter the power for scenario " + number + " when $\\beta=0.2$.",
            }[kind] if en else "第" + number + "种情境。给定 $p=0.08$，写出结论。"
            options = [
                {"id": identifier, "text": label, "diagnostic": "none"}
                for identifier, label in (("a", "Type I error"), ("b", "Type II error"), ("c", "No error"))
            ] if kind == "choice" else []
            result = {
                "format": kind, "prompt": prompt,
                "options": options,
                "fields": [] if options else [{
                    "id": "x", "label": "Answer" if en else "答案",
                    "accepted": ["0.8", r"\frac{4}{5}"] if kind == "tex" else ["do not reject", "未拒绝"],
                }],
                "correctOptionId": "a" if options else None,
                "requiresReason": bool(data["gap"]), "rubric": "Use the decision rule." if en else "根据判定规则。",
                "solution": "Compare the p-value to the significance level." if en else "比较 p 值与显著性水平。",
                "sources": sources,
            }
        elif task == "audit_question":
            result = {"valid": True}
        elif task == "evaluate":
            if self.fail_evaluation:
                self.fail_evaluation = False
                raise ModelError("model_timeout")
            evidence = data["reason"]
            correct = "证据不足" in evidence
            result = {
                "correctness": data["objectiveCorrectness"] or ("correct" if correct else "incorrect"),
                "evidenceType": "demonstrated" if correct else "same_gap", "evidence": evidence,
                "feedback": "Compare the evidence with the null." if en else "比较显著性水平，结论是证据不足以拒绝。",
                "otherHypothesis": None,
            }
        elif task == "translate":
            translations = {
                "假设检验": "Hypothesis testing",
                "比较 [[TUTOR_MATH_0]] 和 [[TUTOR_MATH_1]]。": "Compare [[TUTOR_MATH_0]] and [[TUTOR_MATH_1]].",
                "你会从哪一步开始？": "How would you begin?",
                "答案": "Answer",
            }
            result = {"texts": [
                translations.get(text, "Course content " + " ".join(re.findall(r"\[\[TUTOR_MATH_\d+\]\]", text)))
                if en else "课程内容 " + " ".join(re.findall(r"\[\[TUTOR_MATH_\d+\]\]", text))
                for text in data["texts"]
            ]}
        else:
            raise AssertionError(task)
        return schema.model_validate({"locale": locale, **result})


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.provider = FixtureProvider()
        self.client = TestClient(
            create_app(Path(self.directory.name), self.provider), base_url="http://127.0.0.1",
        )
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.course = self.call("POST", "/courses", {"name": "Applied Statistics"})["id"]

    def call(self, method, path, body=None, status=None):
        response = self.client.request(method, BASE + path, json=body)
        if status is None:
            self.assertTrue(response.is_success, response.text)
        else:
            self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def upload(self, contents, request_id=None, replaces=None):
        data = {"requestId": request_id or uuid4().hex}
        if replaces:
            data["replacesId"] = replaces
        result = self.client.post(BASE + f"/courses/{self.course}/materials", data=data,
                                  files={"file": ("Hypothesis.pdf", contents, "application/pdf")})
        self.assertEqual(result.status_code, 202, result.text)
        return result.json()

    def wait(self, job, expected="ready"):
        path = f"/courses/{self.course}/jobs/{job}"
        end = time.monotonic() + 12
        while time.monotonic() < end:
            result = self.call("GET", path)
            if result["status"] in ("ready", "failed"):
                self.assertEqual(result["status"], expected, result)
                return result
            time.sleep(0.03)
        self.fail(f"Job did not finish: {job}")

    def prepare(self):
        uploaded = self.upload(pdf_bytes("Failing to reject is insufficient evidence.", ""))
        self.wait(uploaded["jobId"])
        return uploaded, self.call("GET", f"/courses/{self.course}/topics")["topics"][0]

    def open_session(self, topic):
        start = self.call("POST", f"/courses/{self.course}/sessions", {
            "topicId": topic["id"], "requestId": uuid4().hex,
        })
        self.wait(start["jobId"])
        return f"/sessions/{start['sessionId']}"

    def open_check(self, session, kind, gap=None, purpose="practice"):
        job = self.call("POST", session + "/checks", {
            "requestId": uuid4().hex, "format": kind, "gapId": gap, "purpose": purpose,
        })
        return self.wait(job["jobId"])["result"]["checkId"]

    def test_pdf_import_isolation_replacement_and_stable_ids(self):
        data = pdf_bytes("Failing to reject is insufficient evidence.", "")
        uploaded = self.upload(data, "same-upload")
        self.assertEqual(self.upload(data, "same-upload"), uploaded)
        self.wait(uploaded["jobId"])
        path = f"/courses/{self.course}"
        original = uploaded["materialId"]
        self.assertEqual(self.call("GET", path + "/materials")["materials"][0]["unreadablePages"], [2])
        self.assertTrue(self.call("GET", path + f"/materials/{original}/units/1")["url"].endswith("#page=1"))
        self.assertIn("insufficient evidence", self.call("GET", path + f"/materials/{original}/units/1")["text"])
        topic = self.call("GET", path + "/topics")["topics"][0]
        session = self.open_session(topic)
        other = self.call("POST", "/courses", {"name": "Other"})["id"]
        self.call("GET", f"/courses/{other}/materials/{original}/units/1", status=404)
        replaced = self.upload(pdf_bytes("New evidence and updated notes."), replaces=original)
        self.wait(replaced["jobId"])
        self.assertEqual(self.call("GET", path + "/topics")["topics"][0]["id"], topic["id"])
        self.assertEqual(self.call("GET", session)["topic"]["sources"][0]["materialId"], original)
        self.assertEqual(self.call("GET", path + "/materials")["materials"][0]["status"], "superseded")
        self.provider.invalid_citation = True
        failed = self.upload(pdf_bytes("Invalid generated citation."))
        self.assertEqual(self.wait(failed["jobId"], "failed")["error"], "invalid_citation")
        self.assertEqual(self.call("GET", path + "/topics")["topics"][0]["sources"][0]["materialId"], replaced["materialId"])

    def test_independent_check_retry_language_and_review(self):
        _, topic = self.prepare()
        session = self.open_session(topic)
        raw = "因为 p 大于 0.05，所以证明原假设成立"
        message = self.call("POST", session + "/messages", {"text": raw, "requestId": "one-message"})
        self.assertEqual(message, self.call("POST", session + "/messages", {"text": raw, "requestId": "one-message"}))
        self.wait(message["jobId"])
        state = self.call("GET", session)
        gap = state["gaps"][0]["id"]
        self.assertEqual(state["gaps"][0]["status"], "pending")

        check = self.open_check(session, "text", gap, "confirm")
        path = f"/checks/{check}"
        prompt = self.call("GET", path)
        self.assertNotIn("solution", prompt)
        self.assertNotIn("sources", prompt)
        self.assertEqual(set(prompt["fields"][0]), {"id", "label"})
        self.assertEqual(self.call("GET", session)["messages"], [])
        self.call("PATCH", "/preferences", {"locale": "en"})
        translated = self.call("GET", path)
        self.assertEqual(translated["locale"], "en")
        self.assertEqual(translated["id"], prompt["id"])
        self.assertEqual(translated["fields"][0]["id"], prompt["fields"][0]["id"])
        self.assertIn("$p=0.08$", translated["prompt"])

        self.provider.fail_evaluation = True
        body = {"requestId": "attempt", "answer": {"x": "成立"}, "reason": "证明原假设成立"}
        submitted = self.call("POST", path + "/attempts", body)
        self.assertEqual(self.wait(submitted["jobId"], "failed")["error"], "model_timeout")
        self.assertEqual(self.call("GET", path)["attempt"]["answer"], body["answer"])
        self.assertIsNone(self.call("GET", path)["attempt"]["result"])
        self.assertEqual(self.call("POST", path + "/attempts", body), submitted)
        self.call("POST", path + "/attempts", {**body, "requestId": "duplicate"}, status=409)
        self.call("POST", f"/courses/{self.course}/jobs/{submitted['jobId']}/retry")
        self.wait(submitted["jobId"])
        self.assertEqual(self.call("GET", path)["attempt"]["result"]["gapStatus"], "review_needed")
        review_path = f"/courses/{self.course}/review"
        self.assertEqual(self.call("GET", review_path)["topics"][0]["gaps"][0]["evidence"], body["reason"])
        self.assertIn("solution", self.call("GET", path))

        with TestClient(create_app(Path(self.directory.name), self.provider), base_url="http://127.0.0.1") as client:
            self.assertEqual(client.get(BASE + "/preferences").json()["locale"], "en")
            self.assertEqual(client.get(BASE + review_path).json()["topics"][0]["gaps"][0]["id"], gap)
            self.assertEqual(client.get(BASE + path).json()["attempt"]["id"], submitted["attemptId"])
        check = self.open_check(session, "text", gap, "review")
        result = self.call("POST", f"/checks/{check}/attempts", {
            "requestId": "review-attempt", "answer": {"x": "do not reject"}, "reason": "证据不足以拒绝",
        })
        self.wait(result["jobId"])
        self.assertEqual(self.call("GET", review_path)["topics"], [])

    def test_choice_and_tex_public_contract_and_resume(self):
        _, topic = self.prepare()
        session = self.open_session(topic)
        self.call("PATCH", "/preferences", {"locale": "en"})
        check = self.open_check(session, "choice")
        view = self.call("GET", f"/checks/{check}")
        self.assertEqual(set(view["options"][0]), {"id", "text"})
        self.call("POST", f"/checks/{check}/leave")
        self.call("POST", f"/checks/{check}/attempts", {"requestId": "left", "answer": "a"}, status=409)
        next_check = self.open_check(session, "choice")
        self.assertNotEqual(next_check, check)
        job = self.call("POST", f"/checks/{next_check}/attempts", {"requestId": "choice", "answer": "a"})
        self.wait(job["jobId"])
        self.assertEqual(self.call("GET", f"/checks/{next_check}")["attempt"]["result"]["correctness"], "correct")
        tex = self.open_check(session, "tex")
        job = self.call("POST", f"/checks/{tex}/attempts", {"requestId": "tex", "answer": {"x": "1-0.2"}})
        self.wait(job["jobId"])
        self.assertEqual(self.call("GET", f"/checks/{tex}")["attempt"]["result"]["correctness"], "correct")

    def test_origin_is_local(self):
        response = self.client.post(BASE + "/courses", headers={"Origin": "https://example.invalid"}, json={"name": "x"})
        self.assertEqual(response.status_code, 403)

    @unittest.skipUnless(os.getenv("AI_TUTOR_TEST_PDF"), "Set AI_TUTOR_TEST_PDF to the provided course PDF")
    def test_actual_course_pdf(self):
        file = Path(os.environ["AI_TUTOR_TEST_PDF"])
        pages = read_pdf(file)
        self.assertEqual(len(pages), 125)
        self.assertIn("insufficient evidence", pages[15][1])
        self.assertNotIn("proportions_ztest", pages[124][1])
        print(f"\nVerified {file.name} page locations.")
        uploaded = self.upload(file.read_bytes())
        self.wait(uploaded["jobId"])
        data = self.call("GET", f"/courses/{self.course}/materials/{uploaded['materialId']}/units/32")
        self.assertEqual(data["page"], 32)
        self.assertIn("Type II Error", data["text"])
        self.assertEqual(len(PdfReader(io.BytesIO(self.client.get(data["url"].split("#")[0]).content)).pages), 125)


class TexTests(unittest.TestCase):
    def test_equivalence(self):
        self.assertTrue(match_tex(r"\frac{4}{5}", ["0.8"]))
        self.assertTrue(match_tex("(x+2)(x+3)", ["x^2+5x+6"]))
        self.assertTrue(match_tex("2x=8", ["x-4=0"]))
        self.assertFalse(match_tex("0.2", ["0.8"]))
        self.assertIsNone(match_tex(r"\sqrt{2}", ["0.8"]))
        self.assertIsNone(match_tex("1/x", ["0.8"]))


class ModelAdapterTests(unittest.TestCase):
    def test_responses_api_contract(self):
        payload = {
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": '{"locale":"en","topicKey":"p_value"}'},
            ]}],
        }
        with patch.dict(os.environ, {
            "AI_TUTOR_PROVIDER": "api", "AI_TUTOR_API_MODEL": "local-test-model",
            "AI_TUTOR_API_KEY": "test-key", "AI_TUTOR_API_BASE_URL": "https://example.invalid/v1",
        }), patch("tutor.models.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(payload).encode()
            result = Provider().generate("select_topic", "Select a topic.", {"locale": "en"}, TopicSelection)
            request = opener.return_value.open.call_args.args[0]
        self.assertEqual(result.topicKey, "p_value")
        self.assertEqual(request.full_url, "https://example.invalid/v1/responses")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        submitted = json.loads(request.data)
        self.assertFalse(submitted["store"])
        self.assertTrue(submitted["text"]["format"]["strict"])
        self.assertEqual(submitted["text"]["format"]["schema"], TopicSelection.model_json_schema())
