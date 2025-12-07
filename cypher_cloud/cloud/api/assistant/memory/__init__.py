from __future__ import annotations

import os
import json
import sqlite3
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _device_id(device: Dict[str, Any]) -> str:
    return str(device.get("device_id") or device.get("id") or "local-dev")


@contextmanager
def _safe_cursor(conn: sqlite3.Connection):
    """
    Context manager that yields a cursor and rolls back on error.
    """
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# -------------------------------------------------------------------
# Memory Service (SQLite-backed with in-memory fallback)
# -------------------------------------------------------------------


@dataclass
class MemoryConfig:
    db_path: str = os.getenv("CYPHER_MEMORY_DB", "cypher_memory.sqlite")


class MemoryService:
    """
    Cypher Memory V2

    Per-device, structured memory with three main areas:

      1) Notes       → simple text notes (backward compatible with existing tools)
      2) Tasks       → per-device todo items
      3) Episodes    → conversational / event history

    Tables:

      notes(device_id TEXT, id INTEGER PK, content TEXT, created_at TEXT)
      tasks(device_id TEXT, id INTEGER PK, text TEXT, done INTEGER, created_at TEXT, completed_at TEXT)
      episodes(device_id TEXT, id INTEGER PK, role TEXT, content TEXT, meta TEXT, created_at TEXT)

    If SQLite cannot be used (e.g. filesystem issues), it falls back to
    a basic in-memory store so Cypher keeps working (just less durable).
    """

    def __init__(self, config: Optional[MemoryConfig] = None) -> None:
        self.config = config or MemoryConfig()
        self._conn: Optional[sqlite3.Connection] = None
        self._fallback: Dict[str, Any] = {
            "notes": {},      # device_id -> List[Dict]
            "tasks": {},      # device_id -> List[Dict]
            "episodes": {},   # device_id -> List[Dict]
        }
        self._init_db()

    # ------------------------ DB init ------------------------

    def _init_db(self) -> None:
        try:
            path = self.config.db_path
            logger.info("Initializing Cypher memory DB at %s", path)
            self._conn = sqlite3.connect(
                path,
                check_same_thread=False,
                isolation_level=None,
            )
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")

            with _safe_cursor(self._conn) as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notes (
                        device_id   TEXT NOT NULL,
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        content     TEXT NOT NULL,
                        created_at  TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        device_id    TEXT NOT NULL,
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        text         TEXT NOT NULL,
                        done         INTEGER NOT NULL DEFAULT 0,
                        created_at   TEXT NOT NULL,
                        completed_at TEXT
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS episodes (
                        device_id  TEXT NOT NULL,
                        id         INTEGER PRIMARY KEY AUTOINCREMENT,
                        role       TEXT NOT NULL,
                        content    TEXT NOT NULL,
                        meta       TEXT,
                        created_at TEXT NOT NULL
                    )
                    """
                )

            logger.info("Cypher memory DB initialized successfully.")
        except Exception as e:
            logger.exception("Failed to initialize memory DB, using in-memory fallback: %s", e)
            self._conn = None

    # ------------------------ Internal helpers ------------------------

    @property
    def has_persistent_store(self) -> bool:
        return self._conn is not None

    # ------------------------------------------------------------------
    # NOTES API (backward compatible with notes_tool)
    # ------------------------------------------------------------------

    def add_note(self, device: Dict[str, Any], content: str) -> None:
        device_id = _device_id(device)
        ts = _now_iso()

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute(
                        "INSERT INTO notes(device_id, content, created_at) VALUES (?, ?, ?)",
                        (device_id, content, ts),
                    )
                return
            except Exception:
                logger.exception("Failed to insert note into DB, falling back to memory.")

        # Fallback: in-memory
        notes = self._fallback["notes"].setdefault(device_id, [])
        notes.append({"content": content, "created_at": ts})

    def get_notes(self, device: Dict[str, Any]) -> List[str]:
        device_id = _device_id(device)

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute(
                        "SELECT content FROM notes WHERE device_id = ? ORDER BY id DESC LIMIT 100",
                        (device_id,),
                    )
                    rows = cur.fetchall()
                return [r[0] for r in rows]
            except Exception:
                logger.exception("Failed to fetch notes from DB, falling back to memory.")

        notes = self._fallback["notes"].get(device_id, [])
        return [n["content"] for n in reversed(notes[-100:])]

    def clear_notes(self, device: Dict[str, Any]) -> None:
        device_id = _device_id(device)

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute("DELETE FROM notes WHERE device_id = ?", (device_id,))
                return
            except Exception:
                logger.exception("Failed to clear notes from DB, falling back to memory.")

        self._fallback["notes"][device_id] = []

    # ------------------------------------------------------------------
    # TASKS API (backward compatible with tasks_tool)
    # ------------------------------------------------------------------

    def add_task(self, device: Dict[str, Any], text: str) -> Dict[str, Any]:
        device_id = _device_id(device)
        ts = _now_iso()

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute(
                        "INSERT INTO tasks(device_id, text, done, created_at) VALUES (?, ?, 0, ?)",
                        (device_id, text, ts),
                    )
                    task_id = cur.lastrowid
                return {
                    "id": task_id,
                    "text": text,
                    "done": False,
                    "created_at": ts,
                    "completed_at": None,
                }
            except Exception:
                logger.exception("Failed to insert task into DB, falling back to memory.")

        tasks = self._fallback["tasks"].setdefault(device_id, [])
        task_id = len(tasks) + 1
        task = {
            "id": task_id,
            "text": text,
            "done": False,
            "created_at": ts,
            "completed_at": None,
        }
        tasks.append(task)
        return task

    def list_tasks(self, device: Dict[str, Any]) -> List[Dict[str, Any]]:
        device_id = _device_id(device)

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute(
                        """
                        SELECT id, text, done, created_at, completed_at
                        FROM tasks
                        WHERE device_id = ?
                        ORDER BY id ASC
                        """,
                        (device_id,),
                    )
                    rows = cur.fetchall()
                return [
                    {
                        "id": r[0],
                        "text": r[1],
                        "done": bool(r[2]),
                        "created_at": r[3],
                        "completed_at": r[4],
                    }
                    for r in rows
                ]
            except Exception:
                logger.exception("Failed to list tasks from DB, falling back to memory.")

        return list(self._fallback["tasks"].get(device_id, []))

    def complete_task(self, device: Dict[str, Any], task_id: int) -> bool:
        device_id = _device_id(device)
        ts = _now_iso()

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute(
                        """
                        UPDATE tasks
                        SET done = 1, completed_at = ?
                        WHERE device_id = ? AND id = ?
                        """,
                        (ts, device_id, task_id),
                    )
                    return cur.rowcount > 0
            except Exception:
                logger.exception("Failed to complete task in DB, falling back to memory.")

        tasks = self._fallback["tasks"].get(device_id, [])
        for t in tasks:
            if t["id"] == task_id:
                t["done"] = True
                t["completed_at"] = ts
                return True
        return False

    def clear_tasks(self, device: Dict[str, Any]) -> None:
        device_id = _device_id(device)

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute("DELETE FROM tasks WHERE device_id = ?", (device_id,))
                return
            except Exception:
                logger.exception("Failed to clear tasks from DB, falling back to memory.")

        self._fallback["tasks"][device_id] = []

    # ------------------------------------------------------------------
    # EPISODIC MEMORY API (new)
    # ------------------------------------------------------------------

    def store_episode(
        self,
        device: Dict[str, Any],
        role: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Store a single conversational / behavioral episode.

        role:
          - 'user'
          - 'assistant'
          - 'system'
          - 'tool'
          - etc.
        """
        device_id = _device_id(device)
        ts = _now_iso()
        meta_json = json.dumps(meta or {}, ensure_ascii=False)

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute(
                        """
                        INSERT INTO episodes(device_id, role, content, meta, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (device_id, role, content, meta_json, ts),
                    )
                return
            except Exception:
                logger.exception("Failed to store episode in DB, falling back to memory.")

        eps = self._fallback["episodes"].setdefault(device_id, [])
        eps.append(
            {
                "role": role,
                "content": content,
                "meta": meta or {},
                "created_at": ts,
            }
        )

    def get_recent_episodes(
        self,
        device: Dict[str, Any],
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Return most recent episodes for a device (for context / debugging).
        """
        device_id = _device_id(device)

        if self._conn:
            try:
                with _safe_cursor(self._conn) as cur:
                    cur.execute(
                        """
                        SELECT role, content, meta, created_at
                        FROM episodes
                        WHERE device_id = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (device_id, limit),
                    )
                    rows = cur.fetchall()
                episodes: List[Dict[str, Any]] = []
                for r in rows:
                    meta = {}
                    if r[2]:
                        try:
                            meta = json.loads(r[2])
                        except Exception:
                            meta = {"_raw_meta": r[2]}
                    episodes.append(
                        {
                            "role": r[0],
                            "content": r[1],
                            "meta": meta,
                            "created_at": r[3],
                        }
                    )
                return episodes
            except Exception:
                logger.exception("Failed to fetch episodes from DB, falling back to memory.")

        eps = self._fallback["episodes"].get(device_id, [])
        return list(reversed(eps[-limit:]))


# Global singleton (used by tools & brain)
memory_service = MemoryService()
