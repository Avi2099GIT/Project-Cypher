# cloud/api/assistant/memory/semantic.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import os
import json
import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
import math

logger = logging.getLogger(__name__)

try:
    import openai  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    openai = None  # type: ignore[assignment]
    logger.warning("OpenAI library not available; semantic embeddings will not work.")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _device_id(device: Dict[str, Any]) -> str:
    return str(device.get("device_id") or device.get("id") or "local-dev")


@contextmanager
def _safe_cursor(conn: sqlite3.Connection):
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
# Config
# -------------------------------------------------------------------


@dataclass
class SemanticConfig:
    db_path: str = os.getenv("CYPHER_MEMORY_DB", "cypher_memory.sqlite")
    embedding_model: str = os.getenv("CYPHER_EMBED_MODEL", "text-embedding-3-small")
    max_items_per_device: int = int(os.getenv("CYPHER_SEMANTIC_MAX_ITEMS", "2000"))


# -------------------------------------------------------------------
# Embedding helpers
# -------------------------------------------------------------------


class EmbeddingProvider:
    """
    Simple wrapper over OpenAI embeddings.
    """

    def __init__(self, config: SemanticConfig) -> None:
        self.config = config

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if openai is None:
            raise RuntimeError("OpenAI library not installed; cannot compute embeddings.")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY missing; cannot compute embeddings.")

        client = openai.OpenAI(api_key=api_key)
        resp = client.embeddings.create(
            model=self.config.embedding_model,
            input=texts,
        )
        return [d.embedding for d in resp.data]  # type: ignore[attr-defined]


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# -------------------------------------------------------------------
# Semantic Memory Service
# -------------------------------------------------------------------


class SemanticMemoryService:
    """
    Semantic memory for Cypher.

    Table: semantic_items
      - device_id TEXT
      - id        INTEGER PK
      - kind      TEXT         (e.g., 'fact', 'preference', 'note', 'pattern')
      - text      TEXT
      - embedding TEXT         (JSON list of floats)
      - metadata  TEXT         (JSON dict)
      - created_at TEXT
    """

    def __init__(self, config: Optional[SemanticConfig] = None) -> None:
        self.config = config or SemanticConfig()
        self._conn: Optional[sqlite3.Connection] = None
        self._embedder = EmbeddingProvider(self.config)
        self._init_db()

    def _init_db(self) -> None:
        try:
            path = self.config.db_path
            logger.info("Initializing semantic memory DB at %s", path)
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
                    CREATE TABLE IF NOT EXISTS semantic_items (
                        device_id   TEXT NOT NULL,
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind        TEXT NOT NULL,
                        text        TEXT NOT NULL,
                        embedding   TEXT NOT NULL,
                        metadata    TEXT,
                        created_at  TEXT NOT NULL
                    )
                    """
                )
            logger.info("Semantic memory table ready.")
        except Exception as e:
            logger.exception("Failed to initialize semantic memory DB: %s", e)
            self._conn = None

    @property
    def available(self) -> bool:
        return self._conn is not None

    # ------------------------- Public API -------------------------

    def add_item(
        self,
        device: Dict[str, Any],
        kind: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """
        Store a semantic item and its embedding.

        Returns DB id or None if failed.
        """
        device_id = _device_id(device)
        ts = _now_iso()
        metadata = metadata or {}

        if not self._conn:
            logger.warning("Semantic memory unavailable (no DB).")
            return None

        try:
            vec = self._embedder.embed_texts([text])[0]
        except Exception as e:
            logger.exception("Failed to compute embedding: %s", e)
            return None

        emb_json = json.dumps(vec)
        meta_json = json.dumps(metadata, ensure_ascii=False)

        try:
            with _safe_cursor(self._conn) as cur:
                cur.execute(
                    """
                    INSERT INTO semantic_items(device_id, kind, text, embedding, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (device_id, kind, text, emb_json, meta_json, ts),
                )
                item_id = cur.lastrowid

                # Optional: cap per-device size with a simple eviction strategy
                cur.execute(
                    """
                    SELECT id FROM semantic_items
                    WHERE device_id = ?
                    ORDER BY id DESC
                    LIMIT -1 OFFSET ?
                    """,
                    (device_id, self.config.max_items_per_device),
                )
                rows = cur.fetchall()
                stale_ids = [r[0] for r in rows]
                if stale_ids:
                    cur.execute(
                        f"DELETE FROM semantic_items WHERE id IN ({','.join('?' for _ in stale_ids)})",
                        stale_ids,
                    )

            return int(item_id)
        except Exception as e:
            logger.exception("Failed to insert semantic item: %s", e)
            return None

    def search(
        self,
        device: Dict[str, Any],
        query: str,
        kind: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over a device's items.

        Returns: list of {id, kind, text, score, metadata, created_at}
        ordered by descending score.
        """
        device_id = _device_id(device)

        if not self._conn:
            logger.warning("Semantic memory unavailable (no DB).")
            return []

        try:
            q_vec = self._embedder.embed_texts([query])[0]
        except Exception as e:
            logger.exception("Failed to compute query embedding: %s", e)
            return []

        try:
            with _safe_cursor(self._conn) as cur:
                if kind:
                    cur.execute(
                        """
                        SELECT id, kind, text, embedding, metadata, created_at
                        FROM semantic_items
                        WHERE device_id = ? AND kind = ?
                        """,
                        (device_id, kind),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, kind, text, embedding, metadata, created_at
                        FROM semantic_items
                        WHERE device_id = ?
                        """,
                        (device_id,),
                    )
                rows = cur.fetchall()
        except Exception as e:
            logger.exception("Failed to fetch semantic items: %s", e)
            return []

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for r in rows:
            try:
                emb = json.loads(r[3])
                score = _cosine(q_vec, emb)
            except Exception:
                score = 0.0

            try:
                meta = json.loads(r[4]) if r[4] else {}
            except Exception:
                meta = {"_raw_meta": r[4]}

            scored.append(
                (
                    score,
                    {
                        "id": r[0],
                        "kind": r[1],
                        "text": r[2],
                        "metadata": meta,
                        "created_at": r[5],
                        "score": score,
                    },
                )
            )

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for score, item in scored[:top_k] if score > 0.0]


# Global singleton
semantic_memory = SemanticMemoryService()
