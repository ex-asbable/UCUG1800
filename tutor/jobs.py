import json
import logging
import sqlite3
import threading
from dataclasses import dataclass

from .models import ModelError
from .storage import Store, encode, new_id, now


log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, code: str, status: int = 400):
        super().__init__(code)
        self.code = code
        self.status = status


def lookup(db, table: str, identifier: str, course_id: str | None = None):
    if table not in {"courses", "materials", "outlines", "jobs", "sessions", "gaps", "checks"}:
        raise ValueError(table)
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (identifier,)).fetchone()
    if not row or (course_id is not None and row["course_id"] != course_id):
        raise AppError("not_found", 404)
    return row


def find_job(db, course_id: str, kind: str, request_id: str, payload: dict):
    row = db.execute(
        "SELECT * FROM jobs WHERE course_id = ? AND kind = ? AND request_id = ?",
        (course_id, kind, request_id),
    ).fetchone()
    if row and json.loads(row["payload"]).get("input") != payload:
        raise AppError("request_conflict", 409)
    return row


def create_job(db, kind: str, course_id: str, request_id: str, locale: str, payload: dict) -> str:
    job_id = new_id()
    db.execute(
        """INSERT INTO jobs (id, course_id, kind, request_id, locale, payload, status, stage, created)
           VALUES (?, ?, ?, ?, ?, ?, 'queued', 'queued', ?)""",
        (job_id, course_id, kind, request_id, locale, encode(payload), now()),
    )
    return job_id


def public_job(row):
    return {
        "jobId": row["id"], "courseId": row["course_id"], "kind": row["kind"], "locale": row["locale"],
        "status": row["status"], "stage": row["stage"], "error": row["error"],
        "result": json.loads(row["result"]) if row["result"] else None,
        "recoveryActions": ["retry"] if row["status"] == "failed" else [],
    }


@dataclass(frozen=True)
class Job:
    id: str
    course: str
    kind: str
    locale: str
    payload: dict


def complete(db, job: Job, result: dict):
    db.execute(
        "UPDATE jobs SET status = 'ready', stage = 'ready', result = ? WHERE id = ?",
        (encode(result), job.id),
    )


class JobWorker:
    def __init__(self, store: Store, run):
        self.store = store
        self.run = run
        self.stop = threading.Event()
        self.changed = threading.Event()
        self.thread = None

    def start(self):
        with self.store.connect(write=True) as db:
            db.execute("UPDATE jobs SET status = 'queued', stage = 'queued' WHERE status = 'running'")
        self.stop.clear()
        self.thread = threading.Thread(target=self._loop, name="tutor-jobs", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.changed.set()
        self.thread.join(timeout=2)

    def notify(self):
        self.changed.set()

    def _claim(self):
        with self.store.connect(write=True) as db:
            row = db.execute("SELECT * FROM jobs WHERE status = 'queued' ORDER BY created, id LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status = 'running', stage = 'generating' WHERE id = ?", (row["id"],))
            return Job(row["id"], row["course_id"], row["kind"], row["locale"], json.loads(row["payload"]))

    def _loop(self):
        while not self.stop.is_set():
            try:
                job = self._claim()
            except sqlite3.Error:
                log.exception("Could not claim a Tutor job")
                self.stop.wait(1)
                continue
            if job is None:
                self.changed.wait(0.4)
                self.changed.clear()
                continue
            try:
                self.run(job)
            except (AppError, ModelError) as error:
                log.info("Task %s (%s) failed: %s", job.id, job.kind, error.code)
                self._fail(job, error.code)
            except Exception:
                log.exception("Task %s (%s) failed", job.id, job.kind)
                self._fail(job, "internal_error")

    def _fail(self, job: Job, code: str):
        with self.store.connect(write=True) as db:
            db.execute("UPDATE jobs SET status = 'failed', error = ? WHERE id = ?", (code, job.id))
            if job.kind == "import":
                db.execute("UPDATE materials SET status = 'failed' WHERE id = ?", (job.payload["materialId"],))
            elif job.kind == "folder":
                db.execute(
                    """UPDATE materials SET status = 'failed'
                       WHERE id IN (SELECT value FROM json_each(?)) AND status IN ('queued', 'parsing', 'generating')""",
                    (encode(job.payload["materialIds"]),),
                )
