import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .contracts import Locale, ModelCatalogRequest, ModelEffortsRequest, QuestionFormat, RuntimeSettings
from .jobs import AppError, lookup, public_job
from .model_catalog import list_models, model_efforts
from .models import ModelError, Provider
from .service import TutorService
from .storage import Store, new_id, now
from .views import Views


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "dist"
FILE_LIMIT = 30 * 1024 * 1024
ApiId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9_-]{1,80}$")]
UserText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]
FieldValue = Annotated[str, StringConstraints(max_length=2500)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Preference(Input):
    locale: Locale


class CourseInput(Input):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class StartInput(Input):
    requestId: ApiId
    topicId: ApiId | None = None
    question: UserText | None = None

    @model_validator(mode="after")
    def require_target(self):
        if not (self.topicId or self.question):
            raise ValueError("Select a topic or ask a question")
        return self


class MessageInput(Input):
    requestId: ApiId
    text: UserText


class CheckInput(Input):
    requestId: ApiId
    format: QuestionFormat | None = None
    purpose: Literal["practice", "confirm", "review"] = "practice"
    gapId: ApiId | None = None

    @model_validator(mode="after")
    def require_gap_for_diagnosis(self):
        if bool(self.gapId) != (self.purpose != "practice"):
            raise ValueError("A gap ID is required for confirmation and review")
        return self


class AttemptInput(Input):
    requestId: ApiId
    answer: ApiId | Annotated[dict[ApiId, FieldValue], Field(min_length=1, max_length=6)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""


def error_response(code, status):
    return JSONResponse(
        {"error": {"code": code, "params": {}, "recoveryActions": []}}, status_code=status,
    )


def create_app(data_directory: Path | None = None, provider=None):
    @asynccontextmanager
    async def lifespan(application):
        directory = data_directory or Path(os.getenv("AI_TUTOR_DATA_DIR", str(ROOT / ".data")))
        service = TutorService(Store(directory), provider or Provider())
        application.state.service = service
        application.state.views = Views(service)
        service.worker.start()
        try:
            yield
        finally:
            service.worker.close()

    app = FastAPI(title="AI Tutor", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            own_origin = f"{request.url.scheme}://{request.headers.get('host')}"
            if (origin is not None and origin != own_origin) or request.headers.get("sec-fetch-site") == "cross-site":
                return error_response("request_origin", 403)
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > FILE_LIMIT + 256_000:
                return error_response("file_too_large", 413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(_request, error):
        return error_response(error.code, error.status)

    @app.exception_handler(ModelError)
    async def handle_model_error(_request, error):
        return error_response(error.code, 503)

    @app.exception_handler(RequestValidationError)
    async def handle_bad_input(_request, _error):
        return error_response("invalid_input", 422)

    api = APIRouter(prefix="/api/v1")

    def service(request):
        return request.app.state.service

    def views(request):
        return request.app.state.views

    @api.get("/preferences")
    def preferences(request: Request):
        tutor = service(request)
        with tutor.store.connect() as db:
            return {"locale": tutor.locale(db)}

    @api.patch("/preferences")
    def change_preferences(body: Preference, request: Request):
        with service(request).store.connect(write=True) as db:
            db.execute("UPDATE preferences SET locale = ? WHERE id = 1", (body.locale,))
        return {"locale": body.locale}

    @api.get("/runtime/status")
    def runtime(request: Request):
        return service(request).provider.status()

    @api.patch("/runtime/settings")
    def configure_runtime(body: RuntimeSettings, request: Request):
        return service(request).configure_runtime(body)

    @api.post("/runtime/models")
    def runtime_models(body: ModelCatalogRequest, request: Request):
        return list_models(service(request).provider, body)

    @api.post("/runtime/model-efforts")
    def runtime_model_efforts(body: ModelEffortsRequest, request: Request):
        return model_efforts(service(request).provider, body)

    @api.get("/courses")
    def courses(request: Request):
        with service(request).store.connect() as db:
            return {"courses": [
                {"id": row["id"], "name": row["name"], "outlineId": row["outline_id"]}
                for row in db.execute("SELECT * FROM courses ORDER BY created DESC")
            ]}

    @api.post("/courses", status_code=201)
    def add_course(body: CourseInput, request: Request):
        identifier = new_id()
        with service(request).store.connect(write=True) as db:
            db.execute("INSERT INTO courses (id, name, created) VALUES (?, ?, ?)", (identifier, body.name, now()))
        return {"id": identifier, "name": body.name, "outlineId": None}

    @api.get("/courses/{course_id}/materials")
    def materials(course_id: ApiId, request: Request):
        return views(request).materials(course_id)

    @api.post("/courses/{course_id}/materials", status_code=202)
    def upload(
        course_id: ApiId, request: Request, file: Annotated[UploadFile, File()],
        requestId: Annotated[ApiId, Form()], replacesId: Annotated[ApiId | None, Form()] = None,
    ):
        try:
            contents = file.file.read(FILE_LIMIT + 1)
            if len(contents) > FILE_LIMIT:
                raise AppError("file_too_large", 413)
            material, job = service(request).import_material(course_id, file.filename or "", contents, requestId, replacesId)
            return {"materialId": material, "jobId": job}
        finally:
            file.file.close()

    @api.get("/courses/{course_id}/jobs/{job_id}")
    def get_job(course_id: ApiId, job_id: ApiId, request: Request):
        with service(request).store.connect() as db:
            return public_job(lookup(db, "jobs", job_id, course_id))

    @api.post("/courses/{course_id}/jobs/{job_id}/retry", status_code=202)
    def retry_job(course_id: ApiId, job_id: ApiId, request: Request):
        service(request).retry(course_id, job_id)
        return {"jobId": job_id}

    @api.get("/courses/{course_id}/topics")
    def topics(course_id: ApiId, request: Request):
        return views(request).topic_list(course_id)

    @api.get("/courses/{course_id}/materials/{material_id}/units/{number}")
    def unit(course_id: ApiId, material_id: ApiId, number: int, request: Request):
        with service(request).store.connect() as db:
            material = lookup(db, "materials", material_id, course_id)
            page = db.execute(
                "SELECT * FROM pages WHERE material_id = ? AND number = ?", (material_id, number),
            ).fetchone()
            if not page:
                raise AppError("not_found", 404)
        return {
            "materialId": material_id, "page": number, "filename": material["filename"],
            "text": page["text"], "status": page["status"],
            "url": f"/api/v1/courses/{course_id}/materials/{material_id}/pdf#page={number}",
        }

    @api.get("/courses/{course_id}/materials/{material_id}/pdf")
    def original(course_id: ApiId, material_id: ApiId, request: Request):
        tutor = service(request)
        with tutor.store.connect() as db:
            material = lookup(db, "materials", material_id, course_id)
        if not (file := tutor.store.material_file(material_id)).is_file():
            raise AppError("not_found", 404)
        return FileResponse(file, media_type="application/pdf", filename=material["filename"], content_disposition_type="inline")

    @api.get("/courses/{course_id}/sessions")
    def sessions(course_id: ApiId, request: Request):
        return views(request).sessions(course_id)

    @api.post("/courses/{course_id}/sessions", status_code=202)
    def open_session(course_id: ApiId, body: StartInput, request: Request):
        session, job = service(request).start_session(course_id, body.topicId, body.question, body.requestId)
        return {"sessionId": session, "jobId": job}

    @api.get("/sessions/{session_id}")
    def session(session_id: ApiId, request: Request):
        return views(request).session(session_id)

    @api.post("/sessions/{session_id}/messages", status_code=202)
    def send(session_id: ApiId, body: MessageInput, request: Request):
        return {"jobId": service(request).send_message(session_id, body.text, body.requestId)}

    @api.post("/sessions/{session_id}/checks", status_code=202)
    def checks(session_id: ApiId, body: CheckInput, request: Request):
        return {
            "jobId": service(request).request_check(session_id, body.gapId, body.purpose, body.format, body.requestId),
        }

    @api.get("/checks/{check_id}")
    def check(check_id: ApiId, request: Request):
        return views(request).get_check(check_id)

    @api.post("/checks/{check_id}/leave")
    def leave_check(check_id: ApiId, request: Request):
        service(request).leave_check(check_id)
        return {"status": "abandoned"}

    @api.post("/checks/{check_id}/attempts", status_code=202)
    def submit(check_id: ApiId, body: AttemptInput, request: Request):
        attempt, job = service(request).submit(check_id, body.answer, body.reason, body.requestId)
        return {"attemptId": attempt, "jobId": job}

    @api.get("/courses/{course_id}/review")
    def review(course_id: ApiId, request: Request):
        return views(request).review(course_id)

    app.include_router(api)
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets", check_dir=False), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        file = FRONTEND / "index.html"
        return FileResponse(file) if file.is_file() else error_response("frontend_not_built", 503)

    return app


app = create_app()
