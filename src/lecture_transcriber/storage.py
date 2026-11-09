from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ("media", "temp"):
            path = self.root / name
            path.mkdir(exist_ok=True)
            self.path(name)
        with self.db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("이 앱보다 새로운 데이터입니다. 앱 버전을 확인하세요.")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS courses (
                    id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS glossary_terms (
                    id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
                    term TEXT NOT NULL, aliases_json TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(course_id,term));
                CREATE TABLE IF NOT EXISTS lectures (
                    id TEXT PRIMARY KEY, course_id TEXT REFERENCES courses(id),
                    title TEXT NOT NULL, lecture_date TEXT NOT NULL,
                    original_filename TEXT NOT NULL, source_relpath TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL, source_bytes INTEGER NOT NULL CHECK(source_bytes>0),
                    duration_ms INTEGER NOT NULL CHECK(duration_ms>0),
                    lifecycle TEXT NOT NULL DEFAULT 'active',
                    revision INTEGER NOT NULL DEFAULT 1,
                    transcript_revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS imports (
                    idempotency_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
                    lecture_id TEXT NOT NULL REFERENCES lectures(id) ON DELETE CASCADE,
                    created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS lectures_date ON lectures(lecture_date,id);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.root / "app.sqlite3", timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def path(self, relative):
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ValueError("관리 폴더를 벗어난 경로입니다.")
        # resolve() also follows Windows junctions and symlinks.
        return target
