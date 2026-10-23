"""SQLite registry: documents, extraction errors, activity feed and evaluation runs."""

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    pages INTEGER,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    entity_count INTEGER NOT NULL DEFAULT 0,
    relation_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extraction_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    chunk_id TEXT,
    message TEXT NOT NULL,
    raw_response TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    summary_json TEXT
);
CREATE TABLE IF NOT EXISTS eval_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    record_json TEXT NOT NULL
);
"""

COUNT_FIELDS = {"pages", "chunk_count", "entity_count", "relation_count"}


class DocumentRow(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    status: str
    error: str | None = None
    pages: int | None = None
    chunk_count: int = 0
    entity_count: int = 0
    relation_count: int = 0
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Registry:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # Documents

    def upsert_document(self, id: str, filename: str, content_type: str, size_bytes: int) -> DocumentRow:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, content_type, size_bytes, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'uploaded', ?, ?) ON CONFLICT(id) DO NOTHING",
                (id, filename, content_type, size_bytes, now, now),
            )
        return self.get_document(id)

    def get_document(self, id: str) -> DocumentRow | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (id,)).fetchone()
        return DocumentRow(**dict(row)) if row else None

    def list_documents(self) -> list[DocumentRow]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM documents ORDER BY created_at, filename").fetchall()
        return [DocumentRow(**dict(r)) for r in rows]

    def set_status(self, id: str, status: str, error: str | None = None, **counts) -> None:
        unknown = set(counts) - COUNT_FIELDS
        if unknown:
            raise ValueError(f"unknown document fields: {sorted(unknown)}")
        assignments = ["status = ?", "error = ?", "updated_at = ?"] + [f"{k} = ?" for k in counts]
        values = [status, error, _now(), *counts.values(), id]
        with self._connect() as conn:
            conn.execute(f"UPDATE documents SET {', '.join(assignments)} WHERE id = ?", values)

    def delete_document(self, id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (id,))
            conn.execute("DELETE FROM extraction_errors WHERE document_id = ?", (id,))

    # Extraction errors

    def add_extraction_error(self, document_id: str, chunk_id: str | None, message: str, raw: str | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO extraction_errors (document_id, chunk_id, message, raw_response, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (document_id, chunk_id, message, raw, _now()),
            )

    def clear_extraction_errors(self, document_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM extraction_errors WHERE document_id = ?", (document_id,))

    def list_extraction_errors(self, document_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chunk_id, message, raw_response, created_at FROM extraction_errors"
                " WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # Activity

    def log_activity(self, kind: str, message: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO activity (kind, message, created_at) VALUES (?, ?, ?)", (kind, message, _now())
            )

    def recent_activity(self, limit: int = 20) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT kind, message, created_at FROM activity ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # Evaluation

    def create_eval_run(self, config: dict) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO eval_runs (id, created_at, status, config_json) VALUES (?, ?, 'running', ?)",
                (run_id, _now(), json.dumps(config)),
            )
        return run_id

    def finish_eval_run(self, run_id: str, status: str, summary: dict | None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE eval_runs SET status = ?, summary_json = ? WHERE id = ?",
                (status, json.dumps(summary) if summary is not None else None, run_id),
            )

    def add_eval_result(self, run_id: str, question_id: str, mode: str, record: dict) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO eval_results (run_id, question_id, mode, record_json) VALUES (?, ?, ?, ?)",
                (run_id, question_id, mode, json.dumps(record, default=str)),
            )

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "status": row["status"],
            "config": json.loads(row["config_json"]),
            "summary": json.loads(row["summary_json"]) if row["summary_json"] else None,
        }

    def get_eval_run(self, run_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (run_id,)).fetchone()
        return self._run_dict(row) if row else None

    def latest_eval_run(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM eval_runs ORDER BY created_at DESC, rowid DESC LIMIT 1").fetchone()
        return self._run_dict(row) if row else None

    def list_eval_runs(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM eval_runs ORDER BY created_at DESC, rowid DESC").fetchall()
        return [self._run_dict(r) for r in rows]

    def eval_results(self, run_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT question_id, mode, record_json FROM eval_results WHERE run_id = ? ORDER BY id", (run_id,)
            ).fetchall()
        return [{"question_id": r["question_id"], "mode": r["mode"], "record": json.loads(r["record_json"])} for r in rows]
