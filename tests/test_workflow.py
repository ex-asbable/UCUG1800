import io
import json
import os
import re
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from uuid import uuid4
from zipfile import ZipFile
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tutor.grading import match_tex
from tutor.contracts import TopicSelection
from tutor.main import create_app
from tutor.materials import read_pdf
from tutor.models import ModelError, Provider, discover_codex


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
        self.outline_calls = 0
        self.guide_calls = 0
        self.fail_evaluation = False
        self.invalid_citation = False
        self.visual_calls = []
        self.reject_visual_page = None
        self.outline_pages = []

    def status(self):
        return {"provider": "api", "ready": True, "error": None}

    def generate(self, task, _instructions, data, schema, *, images=()):
        locale = data["locale"]
        en = locale == "en"
        pages = data.get("pages", [])
        sources = [{key: page[key] for key in ("materialId", "page")} for page in pages[:1]]
        if task == "describe_visuals":
            if not images or any(not image.startswith(b"\xff\xd8") for image in images):
                raise AssertionError("Expected JPEG attachments")
            self.visual_calls.append(data["page"])
            if data["page"] == self.reject_visual_page:
                raise ModelError("multimodal_required")
            result = {"description": "图中比较了检验统计量。"}
        elif task in ("outline", "merge_outline"):
            self.outline_calls += 1
            self.outline_pages = pages
            result = {"topics": [{
                "key": "hypothesis_testing", "parentKey": None,
                "title": "Hypothesis testing" if en else "假设检验",
                "coverage": "supported", "explanation": "Compare $p$ and $\\alpha$." if en else "比较 $p$ 和 $\\alpha$。",
                "opening": "How would you begin?" if en else "你会从哪一步开始？",
                "sources": sources if not self.invalid_citation else [{"materialId": "other", "page": 500}],
            }]}
        elif task == "review_guide":
            self.guide_calls += 1
            heading = "Hypothesis testing" if en else "假设检验"
            result = {
                "markdown": f"# {heading}\n\n$$\np < \\alpha\n$$",
                "sources": sources if not self.invalid_citation else [{"materialId": "other", "page": 500}],
            }
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

    def test_folder_import_keeps_originals_and_builds_one_outline(self):
        diagram = io.BytesIO()
        Image.new("RGB", (80, 80), "red").save(diagram, "PNG")
        word_file = io.BytesIO()
        with ZipFile(word_file, "w") as archive:
            archive.writestr("word/document.xml", """
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                  <w:body><w:p><w:r><w:t>Decision rules</w:t><w:drawing>
                    <a:blip r:embed="rId2" />
                  </w:drawing></w:r></w:p></w:body>
                </w:document>
            """)
            archive.writestr("word/_rels/document.xml.rels", """
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
                    Target="media/image.png" />
                </Relationships>
            """)
            archive.writestr("word/media/image.png", diagram.getvalue())
        slides = io.BytesIO()
        with ZipFile(slides, "w") as archive:
            archive.writestr("ppt/presentation.xml", """
                <p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                  <p:sldIdLst><p:sldId id="256" r:id="rId1" /></p:sldIdLst>
                </p:presentation>
            """)
            archive.writestr("ppt/_rels/presentation.xml.rels", """
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                  <Relationship Id="rId1" Target="slides/slide2.xml" />
                </Relationships>
            """)
            archive.writestr("ppt/slides/slide2.xml", """
                <p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
                  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
                  <a:p><a:r><a:t>Type II error</a:t></a:r></a:p>
                  <a:blip r:embed="rId3" />
                </p:sld>
            """)
            archive.writestr("ppt/slides/_rels/slide2.xml.rels", """
                <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
                    Target="../media/image.png" />
                </Relationships>
            """)
            archive.writestr("ppt/media/image.png", diagram.getvalue())
        path = f"/courses/{self.course}/materials"
        entries = [
            ("files", ("week-1/sample.pdf", pdf_bytes("Compare p with alpha."))),
            ("files", ("week-1/nested/lecture.docx", word_file.getvalue())),
            ("files", ("week-1/nested/notes.md", b"# Review\n\nCompare $p$ with alpha.")),
            ("files", ("week-1/slides.pptx", slides.getvalue())),
            ("files", ("week-1/diagram.png", diagram.getvalue())),
            ("files", ("week-1/broken.png", b"invalid image")),
            ("files", ("week-1/broken.pdf", b"corrupt PDF")),
            ("files", ("week-1/../invalid.txt", b"invalid")),
        ]

        def upload_folder():
            response = self.client.post(BASE + path + "/folder", data={"requestId": "folder"}, files=entries)
            self.assertEqual(response.status_code, 202, response.text)
            return response.json()

        result = upload_folder()
        self.assertEqual(upload_folder(), result)
        self.assertEqual(result["issues"], [{"filename": "week-1/../invalid.txt", "code": "invalid_material_name"}])
        self.wait(result["jobId"])
        materials = self.call("GET", path)["materials"]
        self.assertEqual([item["status"] for item in materials],
                         ["ready", "ready", "ready", "ready", "ready", "attached", "attached"])
        self.assertEqual(self.provider.outline_calls, 1)
        for offset, text in ((1, "Decision rules"), (2, "# Review"), (3, "Type II error")):
            unit = self.call("GET", path + f"/{materials[offset]['id']}/units/1")
            self.assertIn(text, unit["text"])
            self.assertFalse(unit["isPdf"])
        original = self.client.get(BASE + path + f"/{materials[4]['id']}/original")
        self.assertEqual(original.content, diagram.getvalue())
        self.assertIn("attachment", original.headers["content-disposition"])
        self.assertFalse(materials[0]["requiresMultimodal"])
        for offset, number in ((1, 2), (3, 1), (4, 1)):
            self.assertTrue(materials[offset]["requiresMultimodal"])
            unit = self.call("GET", path + f"/{materials[offset]['id']}/units/{number}")
            self.assertIn("检验统计量", unit["visualDescription"])

    def test_scanned_pdf_retries_with_saved_visual_pages(self):
        scan = io.BytesIO()
        image = Image.new("RGB", (150, 150), "white")
        image.save(scan, "PDF", save_all=True, append_images=[image])
        self.provider.reject_visual_page = 2
        uploaded = self.upload(scan.getvalue())
        job_id = uploaded["jobId"]
        self.assertEqual(self.wait(job_id, "failed")["error"], "multimodal_required")
        course = f"/courses/{self.course}"
        material = self.call("GET", course + "/materials")["materials"][0]
        self.assertTrue(material["requiresMultimodal"])
        self.assertEqual(self.provider.outline_calls, 0)
        self.provider.reject_visual_page = None
        self.call("POST", course + f"/jobs/{job_id}/retry")
        self.wait(job_id)
        self.assertEqual(self.provider.visual_calls, [1, 2, 2])
        self.assertEqual([page["page"] for page in self.provider.outline_pages], [1, 2])
        self.assertTrue(all(page["visualDescription"] for page in self.provider.outline_pages))
        unit = self.call("GET", course + f"/materials/{material['id']}/units/2")
        self.assertEqual(unit["text"], "")
        self.assertEqual(unit["status"], "readable")
        self.assertTrue(unit["url"].endswith("#page=2"))

    def test_review_guide_retries_citations_and_reuses_version_and_locale(self):
        uploaded = self.upload(pdf_bytes("Compare p with alpha."))
        outline = self.wait(uploaded["jobId"])["result"]["outlineId"]
        course_path = f"/courses/{self.course}"
        topic = self.call("GET", course_path + "/topics")["topics"][0]
        path = course_path + f"/topics/{topic['id']}/guide"
        body = {"outlineId": outline}
        self.provider.invalid_citation = True
        job_id = self.call("POST", path, body)["jobId"]
        self.assertEqual(self.wait(job_id, "failed")["error"], "invalid_citation")
        self.provider.invalid_citation = False
        self.call("POST", course_path + f"/jobs/{job_id}/retry")
        result = self.wait(job_id)["result"]
        self.assertIn("$$\np < \\alpha\n$$", result["markdown"])
        self.assertEqual(result["sources"], [{"materialId": uploaded["materialId"], "page": 1}])
        self.assertEqual(self.call("POST", path, body)["jobId"], job_id)
        self.assertEqual(self.call("GET", course_path + "/sessions")["sessions"], [])
        self.assertEqual(self.provider.guide_calls, 2)
        self.call("PATCH", "/preferences", {"locale": "en"})
        english = self.call("POST", path, body)["jobId"]
        self.assertNotEqual(english, job_id)
        self.assertIn("Hypothesis testing", self.wait(english)["result"]["markdown"])

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
            "AI_TUTOR_API_REASONING_EFFORT": "",
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
            self.assertNotIn("reasoning", submitted)
            Provider().generate("select_topic", "Select a topic.", {"locale": "en"}, TopicSelection,
                                images=(b"image",))
            content = json.loads(opener.return_value.open.call_args.args[0].data)["input"][0]["content"]
            self.assertEqual(content[0]["type"], "input_text")
            self.assertEqual(content[1]["image_url"], "data:image/jpeg;base64,aW1hZ2U=")
            opener.return_value.open.side_effect = HTTPError(
                request.full_url, 400, "Bad Request", {},
                io.BytesIO(b'{"error":{"message":"This model does not support image input."}}'),
            )
            with self.assertRaises(ModelError) as error:
                Provider().generate("select_topic", "Select a topic.", {"locale": "en"}, TopicSelection,
                                    images=(b"image",))
            self.assertEqual(error.exception.code, "multimodal_required")

    def test_responses_api_sends_effort_and_reports_unsupported_level(self):
        details = io.BytesIO(b'{"error":{"param":"reasoning.effort","message":"Unsupported value"}}')
        rejected = HTTPError("https://example.invalid/v1/responses", 400, "Bad Request", {}, details)
        with patch.dict(os.environ, {
            "AI_TUTOR_PROVIDER": "api", "AI_TUTOR_API_MODEL": "configured-api-model",
            "AI_TUTOR_API_KEY": "test-key", "AI_TUTOR_API_BASE_URL": "https://example.invalid/v1",
            "AI_TUTOR_API_REASONING_EFFORT": "high",
        }), patch("tutor.models.build_opener") as opener:
            opener.return_value.open.side_effect = rejected
            with self.assertRaises(ModelError) as error:
                Provider().generate("select_topic", "Select a topic.", {"locale": "en"}, TopicSelection)
            request = opener.return_value.open.call_args.args[0]
        self.assertEqual(error.exception.code, "reasoning_effort_unsupported")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "configured-api-model")
        self.assertEqual(body["reasoning"], {"effort": "high"})

    def test_codex_cli_applies_model_and_reasoning_only_when_configured(self):
        def complete(command, **kwargs):
            (kwargs["cwd"] / "result.json").write_text('{"locale":"en","topicKey":"p_value"}', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "", "")

        with patch.dict(os.environ, {
            "AI_TUTOR_PROVIDER": "codex_cli", "AI_TUTOR_CODEX_MODEL": "gpt-custom-codex",
            "AI_TUTOR_CODEX_REASONING_EFFORT": "xhigh",
        }), patch("tutor.models.discover_codex", return_value="codex.exe"), patch.object(
            Provider, "_cli_status", return_value=None,
        ), patch("tutor.models.subprocess.run", side_effect=complete) as run:
            Provider().generate("select_topic", "Select a topic.", {"locale": "en"}, TopicSelection)
            command = run.call_args.args[0]
            self.assertIn("--model=gpt-custom-codex", command)
            setting = command.index('model_reasoning_effort="xhigh"')
            self.assertEqual(command[setting - 1], "-c")
            self.assertEqual(command[-1], "-")
            with patch.dict(os.environ, {"AI_TUTOR_CODEX_MODEL": "", "AI_TUTOR_CODEX_REASONING_EFFORT": ""}):
                Provider().generate("select_topic", "Select a topic.", {"locale": "en"}, TopicSelection)
            self.assertFalse(any("reasoning_effort" in arg or arg.startswith("--model") for arg in run.call_args.args[0]))

    def test_cli_status_distinguishes_missing_executable_and_launch_failure(self):
        with patch.dict(os.environ, {"AI_TUTOR_PROVIDER": "codex_cli", "AI_TUTOR_CODEX_BIN": "C:/custom/codex.exe"}):
            provider = Provider()
        with patch("tutor.models.discover_codex", return_value=None):
            self.assertEqual(provider.status()["error"], "cli_path")
        with patch("tutor.models.discover_codex", return_value="codex.exe"):
            provider = Provider(provider.settings)
            with patch("tutor.models.subprocess.run", side_effect=OSError("permission denied")):
                self.assertEqual(provider.status()["error"], "cli_launch_failed")
            with patch("tutor.models.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 8)):
                self.assertEqual(provider.status()["error"], "cli_status_timeout")

    def test_api_catalog_uses_draft_endpoint_and_model_capabilities(self):
        def respond(request, **_):
            self.assertEqual(request.get_header("Authorization"), "Bearer draft-key")
            if request.full_url == "https://draft.invalid/api/v1/models":
                return io.BytesIO(json.dumps({"data": [
                    {"id": "draft-text", "supported_reasoning_efforts": ["minimal", "high"]},
                    {"id": "verify", "display_name": "Verify"},
                ]}).encode())
            if request.full_url == "https://draft.invalid/api/v1/models/verify":
                return io.BytesIO(b'{"id":"verify"}')
            self.assertEqual(request.full_url, "https://draft.invalid/api/v1/responses/input_tokens")
            payload = json.loads(request.data)
            self.assertEqual(payload["model"], "verify")
            if payload.get("reasoning", {}).get("effort") in (None, "none", "xhigh"):
                return io.BytesIO(b'{"object":"response.input_tokens","input_tokens":1}')
            raise HTTPError(request.full_url, 400, "Unsupported reasoning effort", {}, io.BytesIO())

        with patch("tutor.model_catalog.build_opener") as opener, TemporaryDirectory() as directory, TestClient(
            create_app(Path(directory)), base_url="http://127.0.0.1",
        ) as client:
            opener.return_value.open.side_effect = respond
            draft = {"provider": "api", "apiBaseUrl": "https://draft.invalid/api/v1/responses", "apiKey": "draft-key"}
            response = client.post(BASE + "/runtime/models", json=draft)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertNotIn("draft-key", response.text)
            listed = response.json()["models"]
            self.assertEqual([model["id"] for model in listed], ["draft-text", "verify"])
            self.assertEqual(listed[0]["reasoningEfforts"], ["minimal", "high"])
            self.assertIsNone(listed[1]["reasoningEfforts"])
            details = client.post(BASE + "/runtime/model-efforts", json={**draft, "model": "verify"})
            self.assertEqual(details.status_code, 200, details.text)
            self.assertEqual(details.json()["reasoningEfforts"], ["none", "xhigh"])

    def test_api_without_token_count_shows_default_only(self):
        with patch("tutor.model_catalog.build_opener") as opener, TemporaryDirectory() as directory, TestClient(
            create_app(Path(directory)), base_url="http://127.0.0.1",
        ) as client:
            opener.return_value.open.side_effect = [
                io.BytesIO(b'{"id":"basic"}'),
                HTTPError("https://api.invalid/v1/responses/input_tokens", 404, "Not found", {}, io.BytesIO()),
            ]
            response = client.post(BASE + "/runtime/model-efforts", json={
                "provider": "api", "apiBaseUrl": "https://api.invalid/v1", "apiKey": "test-key", "model": "basic",
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertIsNone(response.json()["reasoningEfforts"])
            self.assertEqual(opener.return_value.open.call_count, 2)

    @unittest.skipUnless(os.name == "nt", "Windows app package discovery")
    def test_codex_desktop_installation_without_path_entry(self):
        bundled = r"C:\Program Files\WindowsApps\OpenAI.Codex\app\resources\codex.exe"
        with patch("tutor.models.shutil.which", side_effect=[None, bundled]) as which, patch(
            "tutor.models.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0, bundled + "\r\n", ""),
        ):
            self.assertEqual(discover_codex(None), bundled)
        self.assertEqual(which.call_args.args, (bundled,))

    @unittest.skipUnless(os.name == "nt", "Windows PATH and desktop installation selection")
    def test_old_path_cli_does_not_override_newer_desktop_cli(self):
        old_cli = r"C:\npm\codex.cmd"
        desktop_cli = r"C:\Program Files\WindowsApps\OpenAI.Codex\app\resources\codex.exe"
        versions = {old_cli: "0.151.0", desktop_cli: "0.171.0-alpha.13"}

        def release(command, **kwargs):
            self.assertNotIn("AI_TUTOR_API_KEY", kwargs["env"])
            return subprocess.CompletedProcess(command, 0, "codex-cli " + versions[command[0]], "")

        with patch("tutor.models.shutil.which", return_value=old_cli), patch(
            "tutor.models._desktop_codex", return_value=desktop_cli,
        ) as desktop, patch("tutor.models.subprocess.run", side_effect=release), patch.dict(
            os.environ, {"AI_TUTOR_CODEX_BIN": "", "AI_TUTOR_API_KEY": "test-only"},
        ), patch.object(Provider, "_cli_status", return_value=None):
            provider = Provider()
            self.assertEqual(provider.codex_executable(), desktop_cli)
            self.assertEqual(provider.codex_version, "0.171.0-alpha.13")
            self.assertEqual(provider.codex_executable(), desktop_cli)
            desktop.assert_called_once()
            versions[old_cli] = "0.171.0"
            self.assertEqual(discover_codex(None), old_cli)
            self.assertEqual(discover_codex(old_cli), old_cli)
            self.assertEqual(desktop.call_count, 2)

    def test_runtime_can_switch_backends_without_exposing_key(self):
        cli = subprocess.CompletedProcess([], 0, "Logged in using ChatGPT", "")
        with patch.dict(os.environ, {
            "AI_TUTOR_PROVIDER": "codex_cli", "AI_TUTOR_API_MODEL": "", "AI_TUTOR_API_KEY": "",
            "OPENAI_API_KEY": "", "AI_TUTOR_API_BASE_URL": "https://api.openai.com/v1",
            "AI_TUTOR_API_REASONING_EFFORT": "", "AI_TUTOR_CODEX_MODEL": "", "AI_TUTOR_CODEX_REASONING_EFFORT": "",
        }), patch("tutor.models.discover_codex", return_value="codex.exe"), patch(
            "tutor.models.subprocess.run", return_value=cli,
        ), TemporaryDirectory() as directory, TestClient(
            create_app(Path(directory)), base_url="http://127.0.0.1",
        ) as client:
            runtime = BASE + "/runtime/status"
            settings = BASE + "/runtime/settings"
            self.assertEqual(client.get(runtime).json()["provider"], "codex_cli")
            codex = client.patch(settings, json={
                "provider": "codex_cli", "codexModel": "configured-codex", "codexReasoningEffort": "xhigh",
            })
            self.assertEqual(codex.status_code, 200, codex.text)
            self.assertEqual(codex.json()["codexReasoningEffort"], "xhigh")
            payload = {
                "provider": "api", "apiModel": "example-model",
                "apiReasoningEffort": "high",
                "apiBaseUrl": "https://example.invalid/v1/responses/",
            }
            response = client.patch(settings, json=payload)
            self.assertEqual(response.json()["error"]["code"], "api_key_required")
            self.assertEqual(client.get(runtime).json()["provider"], "codex_cli")
            secret = "sample-in-memory-key"
            switched = client.patch(settings, json={**payload, "apiKey": secret})
            self.assertEqual(switched.status_code, 200, switched.text)
            self.assertNotIn(secret, switched.text)
            self.assertEqual(switched.json()["apiBaseUrl"], "https://example.invalid/v1")
            self.assertEqual(switched.json()["apiReasoningEffort"], "high")
            self.assertEqual(switched.json()["codexModel"], "configured-codex")
            self.assertEqual(client.get(runtime).json()["provider"], "api")
            wrong_origin = client.patch(settings, json={**payload, "apiBaseUrl": "https://other.invalid/v1"})
            self.assertEqual(wrong_origin.json()["error"]["code"], "api_key_required")
            self.assertEqual(client.get(runtime).json()["apiBaseUrl"], "https://example.invalid/v1")
            self.assertFalse(client.patch(settings, json={
                **payload, "apiBaseUrl": "https://user:pass@example.invalid/v1",
            }).is_success)
            codex = client.patch(settings, json={"provider": "codex_cli"}).json()
            self.assertEqual(codex["provider"], "codex_cli")
            self.assertEqual(codex["codexReasoningEffort"], "xhigh")
            api = client.patch(settings, json={"provider": "api", "apiModel": "another-model"}).json()
            self.assertTrue(api["ready"])
            self.assertEqual(api["apiReasoningEffort"], "high")
            reset = client.patch(settings, json={"provider": "api", "apiReasoningEffort": None}).json()
            self.assertIsNone(reset["apiReasoningEffort"])
            self.assertEqual(reset["apiModel"], "another-model")
            self.assertEqual(client.patch(settings, json={"provider": "api", "apiReasoningEffort": "ultra"}).status_code, 422)
            self.assertNotIn(secret, Path(directory, "tutor.sqlite3").read_bytes().decode("latin1"))
