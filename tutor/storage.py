import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


SCHEMA = """
CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    locale TEXT NOT NULL CHECK (locale IN ('zh-Hans', 'en'))
);
INSERT OR IGNORE INTO preferences VALUES (1, 'zh-Hans');
CREATE TABLE IF NOT EXISTS courses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    outline_id TEXT REFERENCES outlines(id),
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id),
    filename TEXT NOT NULL,
    digest TEXT NOT NULL,
    replaces_id TEXT REFERENCES materials(id),
    status TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pages (
    material_id TEXT NOT NULL REFERENCES materials(id),
    number INTEGER NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (material_id, number)
);
CREATE TABLE IF NOT EXISTS outlines (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id),
    material_ids TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id),
    key TEXT NOT NULL,
    UNIQUE (course_id, key)
);
CREATE TABLE IF NOT EXISTS topic_versions (
    outline_id TEXT NOT NULL REFERENCES outlines(id),
    topic_id TEXT NOT NULL REFERENCES topics(id),
    parent_id TEXT REFERENCES topics(id),
    position INTEGER NOT NULL,
    locale TEXT NOT NULL,
    content TEXT NOT NULL,
    PRIMARY KEY (outline_id, topic_id)
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id),
    outline_id TEXT NOT NULL REFERENCES outlines(id),
    topic_id TEXT REFERENCES topics(id),
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    locale TEXT,
    text TEXT NOT NULL,
    sources TEXT NOT NULL,
    kind TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS gaps (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    topic_id TEXT NOT NULL REFERENCES topics(id),
    key TEXT NOT NULL,
    locale TEXT NOT NULL,
    description TEXT NOT NULL,
    trigger_id TEXT NOT NULL REFERENCES messages(id),
    status TEXT NOT NULL,
    reason TEXT,
    attempt_id TEXT REFERENCES attempts(id),
    updated TEXT NOT NULL,
    UNIQUE (session_id, key)
);
CREATE TABLE IF NOT EXISTS checks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    topic_id TEXT REFERENCES topics(id),
    gap_id TEXT REFERENCES gaps(id),
    purpose TEXT NOT NULL,
    status TEXT NOT NULL,
    locale TEXT NOT NULL,
    body TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_check ON checks(session_id) WHERE status = 'open';
CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    check_id TEXT NOT NULL UNIQUE REFERENCES checks(id),
    answer TEXT NOT NULL,
    reason TEXT NOT NULL,
    locale TEXT NOT NULL,
    result TEXT,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    course_id TEXT NOT NULL REFERENCES courses(id),
    kind TEXT NOT NULL,
    request_id TEXT NOT NULL,
    locale TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    result TEXT,
    error TEXT,
    created TEXT NOT NULL,
    UNIQUE (course_id, kind, request_id)
);
CREATE INDEX IF NOT EXISTS jobs_by_status ON jobs(status, created);
CREATE INDEX IF NOT EXISTS sessions_by_course ON sessions(course_id, updated);
CREATE INDEX IF NOT EXISTS messages_by_session ON messages(session_id, seq);
CREATE INDEX IF NOT EXISTS gaps_by_topic ON gaps(topic_id, status);
CREATE TABLE IF NOT EXISTS translations (
    source_locale TEXT NOT NULL,
    target_locale TEXT NOT NULL,
    source TEXT NOT NULL,
    translation TEXT NOT NULL,
    PRIMARY KEY (source_locale, target_locale, source)
);
"""


def new_id() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.files = self.directory / "uploads"
        self.files.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "tutor.sqlite3"
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self, *, write: bool = False):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            with db:
                yield db
        finally:
            db.close()

    def material_file(self, material_id: str) -> Path:
        return self.files / f"{material_id}.pdf"
