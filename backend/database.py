from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BACKEND_DIR / "jd_agent_workbench.sqlite3"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_created
                ON messages(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_session_created
                ON tool_calls(session_id, created_at);
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def create_session(db_path: str | Path, title: str | None = None) -> dict[str, Any]:
    session_id = new_id("ses")
    timestamp = now_iso()
    session_title = (title or "新会话").strip() or "新会话"
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO sessions(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, session_title, timestamp, timestamp),
        )
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row_to_dict(row)


def list_sessions(db_path: str | Path) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC, created_at DESC"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_session(db_path: str | Path, session_id: str) -> dict[str, Any] | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return row_to_dict(row) if row else None


def delete_session(db_path: str | Path, session_id: str) -> bool:
    with get_connection(db_path) as conn:
        cursor = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cursor.rowcount > 0


def add_message(db_path: str | Path, session_id: str, role: str, content: str) -> dict[str, Any]:
    message_id = new_id("msg")
    timestamp = now_iso()
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO messages(id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (message_id, session_id, role, content, timestamp),
        )
        conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (timestamp, session_id))
        row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    return row_to_dict(row)


def add_tool_call(
    db_path: str | Path,
    session_id: str,
    message_id: str,
    tool_name: str,
    result_json: str,
) -> dict[str, Any]:
    call_id = new_id("tool")
    timestamp = now_iso()
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO tool_calls(id, session_id, message_id, tool_name, result_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (call_id, session_id, message_id, tool_name, result_json, timestamp),
        )
        row = conn.execute("SELECT * FROM tool_calls WHERE id = ?", (call_id,)).fetchone()
    return row_to_dict(row)


def get_session_detail(db_path: str | Path, session_id: str) -> dict[str, Any] | None:
    session = get_session(db_path, session_id)
    if not session:
        return None
    with get_connection(db_path) as conn:
        messages = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        tool_calls = conn.execute(
            "SELECT * FROM tool_calls WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
    return {
        "session": session,
        "messages": [row_to_dict(row) for row in messages],
        "tool_calls": [row_to_dict(row) for row in tool_calls],
    }


def recent_messages(db_path: str | Path, session_id: str, limit: int = 6) -> list[dict[str, str]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [row_to_dict(row) for row in reversed(rows)]


def recent_tool_calls(db_path: str | Path, session_id: str, limit: int = 6) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM tool_calls
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
    return [row_to_dict(row) for row in reversed(rows)]
