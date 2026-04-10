"""
SQLite-backed persistent memory store — zero external dependencies.

v2.0.0 feature: claims survive restarts. Uses Python's built-in sqlite3.

Usage:
    from oracle_memory import SQLiteStore, OracleAgent

    store = SQLiteStore("my_memory.db")          # file-based
    store = SQLiteStore(":memory:")               # in-memory (test mode)
    agent = OracleAgent("my-agent", store=store)  # persistent agent
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable

from .models import MemoryClaim, PalaceCoordinate
from .store import MemoryStore, _STOP_WORDS

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id     TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    memory_type  TEXT NOT NULL DEFAULT 'general',
    content      TEXT NOT NULL,
    visibility   TEXT NOT NULL DEFAULT 'private',
    title        TEXT,
    source_kind  TEXT DEFAULT 'conversation',
    source_ref   TEXT,
    confidence   REAL DEFAULT 0.6,
    coord_wing   TEXT,
    coord_hall   TEXT,
    coord_room   TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_claims_user     ON claims (user_id);",
    "CREATE INDEX IF NOT EXISTS idx_claims_vis      ON claims (user_id, visibility);",
    "CREATE INDEX IF NOT EXISTS idx_claims_type     ON claims (user_id, memory_type);",
    "CREATE INDEX IF NOT EXISTS idx_claims_updated  ON claims (updated_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_claims_content  ON claims (content);",
]


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase words, stripping punctuation and stop-words."""
    return [w for w in re.findall(r"[a-z0-9]+", text.lower())
            if w not in _STOP_WORDS and len(w) > 1]


def _tf(terms: list[str]) -> dict[str, float]:
    counts = Counter(terms)
    total = len(terms) or 1
    return {t: c / total for t, c in counts.items()}


def _idf(term: str, doc_count: int, docs_with_term: int) -> float:
    return math.log((doc_count + 1) / (docs_with_term + 1)) + 1.0


def _row_to_claim(row: sqlite3.Row | tuple) -> MemoryClaim:
    """Convert a database row to a MemoryClaim."""
    if isinstance(row, sqlite3.Row):
        d = dict(row)
    else:
        # positional columns match SELECT order
        cols = [
            "claim_id", "user_id", "memory_type", "content", "visibility",
            "title", "source_kind", "source_ref", "confidence",
            "coord_wing", "coord_hall", "coord_room", "created_at", "updated_at",
        ]
        d = dict(zip(cols, row))

    coord = None
    if d.get("coord_wing"):
        coord = PalaceCoordinate(
            wing=d["coord_wing"],
            hall=d.get("coord_hall") or "",
            room=d.get("coord_room") or "",
        )
    return MemoryClaim(
        user_id=d["user_id"],
        memory_type=d["memory_type"],
        content=d["content"],
        visibility=d["visibility"],
        title=d.get("title"),
        source_kind=d.get("source_kind") or "conversation",
        source_ref=d.get("source_ref"),
        confidence=d.get("confidence") or 0.6,
        coordinate=coord,
        claim_id=d["claim_id"],
        created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
        updated_at=datetime.fromisoformat(d["updated_at"]) if isinstance(d["updated_at"], str) else d["updated_at"],
    )


class SQLiteStore(MemoryStore):
    """
    Persistent memory store backed by SQLite.

    Thread-safe: each thread gets its own connection via thread-local storage.
    Supports file-based (`"path/to/db.sqlite"`) or in-memory (`":memory:"`).
    """

    def __init__(self, db_path: str = "oracle_memory.db") -> None:
        self._db_path = db_path
        self._local = threading.local()
        # Create the table on the main thread
        conn = self._get_conn()
        conn.execute(_CREATE_TABLE)
        for idx_sql in _CREATE_INDEXES:
            conn.execute(idx_sql)
        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local connection (created once per thread)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        """Close the current thread's connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # ── MemoryStore interface ──

    def save_claim(self, claim: MemoryClaim) -> MemoryClaim:
        conn = self._get_conn()
        # Check for existing duplicate (same user, type, visibility, content)
        row = conn.execute(
            "SELECT claim_id FROM claims "
            "WHERE user_id = ? AND memory_type = ? AND visibility = ? AND LOWER(content) = LOWER(?)",
            (claim.user_id, claim.memory_type, claim.visibility, claim.content),
        ).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        if row:
            conn.execute("UPDATE claims SET updated_at = ? WHERE claim_id = ?", (now, row["claim_id"]))
            conn.commit()
            claim.claim_id = row["claim_id"]
            claim.updated_at = datetime.fromisoformat(now)
            return claim

        coord = claim.coordinate
        conn.execute(
            "INSERT INTO claims "
            "(claim_id, user_id, memory_type, content, visibility, title, "
            " source_kind, source_ref, confidence, "
            " coord_wing, coord_hall, coord_room, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                claim.claim_id, claim.user_id, claim.memory_type, claim.content,
                claim.visibility, claim.title, claim.source_kind, claim.source_ref,
                claim.confidence,
                coord.wing if coord else None,
                coord.hall if coord else None,
                coord.room if coord else None,
                claim.created_at.isoformat(),
                now,
            ),
        )
        conn.commit()
        return claim

    def list_claims(self, user_id: str, visibility: str | None = None,
                    limit: int = 20) -> list[MemoryClaim]:
        conn = self._get_conn()
        if visibility:
            rows = conn.execute(
                "SELECT * FROM claims WHERE user_id = ? AND visibility = ? "
                "ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                (user_id, visibility, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM claims WHERE user_id = ? "
                "ORDER BY updated_at DESC, created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [_row_to_claim(r) for r in rows]

    def search_claims(self, user_id: str, query: str, visibility: str | None = None,
                      limit: int = 10, min_relevance: float = 0.1) -> list[MemoryClaim]:
        """TF-IDF search over persisted claims (same algorithm as InMemoryMemoryStore)."""
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        claims = self.list_claims(user_id=user_id, visibility=visibility, limit=500)
        if not claims:
            return []

        claim_tokens = [_tokenize(f"{c.title or ''} {c.content}") for c in claims]
        doc_count = len(claims)
        term_doc_counts: Counter = Counter()
        for tokens in claim_tokens:
            term_doc_counts.update(set(tokens))

        query_tf = _tf(query_terms)
        scored: list[tuple[float, MemoryClaim]] = []
        for idx, claim in enumerate(claims):
            doc_tokens = claim_tokens[idx]
            if not doc_tokens:
                continue
            doc_tf = _tf(doc_tokens)
            dot = query_norm = doc_norm = 0.0
            for term in set(query_tf) | set(doc_tf):
                idf_val = _idf(term, doc_count, term_doc_counts.get(term, 0))
                q_w = query_tf.get(term, 0.0) * idf_val
                d_w = doc_tf.get(term, 0.0) * idf_val
                dot += q_w * d_w
                query_norm += q_w * q_w
                doc_norm += d_w * d_w
            if query_norm == 0 or doc_norm == 0:
                continue
            cosine = dot / (math.sqrt(query_norm) * math.sqrt(doc_norm))
            if cosine >= min_relevance:
                scored.append((cosine, claim))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:limit]]

    # ── Extended API (v2) ──

    def delete_claim(self, claim_id: str) -> bool:
        """Delete a single claim by ID. Returns True if deleted."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM claims WHERE claim_id = ?", (claim_id,))
        conn.commit()
        return cursor.rowcount > 0

    def delete_user_data(self, user_id: str) -> int:
        """GDPR: delete all claims for a user. Returns count deleted."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM claims WHERE user_id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount

    def export_user_data(self, user_id: str) -> list[dict]:
        """GDPR: export all claims for a user as JSON-serializable dicts."""
        claims = self.list_claims(user_id=user_id, limit=100000)
        return [
            {
                "claim_id": c.claim_id,
                "user_id": c.user_id,
                "memory_type": c.memory_type,
                "content": c.content,
                "visibility": c.visibility,
                "title": c.title,
                "source_kind": c.source_kind,
                "confidence": c.confidence,
                "created_at": c.created_at.isoformat() if isinstance(c.created_at, datetime) else str(c.created_at),
                "updated_at": c.updated_at.isoformat() if isinstance(c.updated_at, datetime) else str(c.updated_at),
            }
            for c in claims
        ]

    def count_claims(self, user_id: str | None = None) -> int:
        """Count claims, optionally filtered by user."""
        conn = self._get_conn()
        if user_id:
            row = conn.execute("SELECT COUNT(*) FROM claims WHERE user_id = ?", (user_id,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM claims").fetchone()
        return row[0] if row else 0
