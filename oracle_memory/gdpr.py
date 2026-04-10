"""
GDPR compliance hooks — right to erasure, data export, consent tracking.

v2.0.0 feature: privacy-by-design compliance for European AI regulations.

Usage:
    from oracle_memory import OracleAgent, SQLiteStore
    from oracle_memory.gdpr import GDPRController

    store = SQLiteStore("memory.db")
    agent = OracleAgent("my-agent", store=store)
    gdpr = GDPRController(store)

    # User requests their data
    export = gdpr.export_user_data("user-42")

    # User requests deletion (right to erasure)
    result = gdpr.erase_user_data("user-42")

    # Check consent status
    gdpr.record_consent("user-42", purpose="memory_storage")
    assert gdpr.has_consent("user-42", purpose="memory_storage")
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from .store import MemoryStore


@dataclass(slots=True)
class ConsentRecord:
    """Tracks what a user has consented to."""
    user_id: str
    purpose: str
    granted: bool = True
    timestamp: float = field(default_factory=time.time)
    ip_hash: str = ""  # hashed, never raw IP


@dataclass(slots=True)
class ErasureResult:
    """Result of a right-to-erasure operation."""
    user_id: str
    claims_deleted: int = 0
    consent_records_cleared: int = 0
    success: bool = True
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "claims_deleted": self.claims_deleted,
            "consent_records_cleared": self.consent_records_cleared,
            "success": self.success,
            "timestamp": self.timestamp,
        }


class GDPRController:
    """
    GDPR compliance controller for oracle-memory stores.

    Provides:
    - Right to erasure (Article 17)
    - Data portability / export (Article 20)
    - Consent management (Article 7)
    - Audit log for compliance evidence
    """

    def __init__(self, store: MemoryStore) -> None:
        self._store = store
        self._consent: dict[str, dict[str, ConsentRecord]] = {}  # user_id -> purpose -> record
        self._audit_log: list[dict[str, Any]] = []

    def _log(self, action: str, user_id: str, details: dict[str, Any] | None = None) -> None:
        entry = {
            "action": action,
            "user_id": user_id,
            "timestamp": time.time(),
            **(details or {}),
        }
        self._audit_log.append(entry)

    # ── Consent management (Article 7) ──

    def record_consent(self, user_id: str, purpose: str, granted: bool = True,
                       ip_hash: str = "") -> ConsentRecord:
        """Record user consent for a specific processing purpose."""
        record = ConsentRecord(
            user_id=user_id, purpose=purpose, granted=granted, ip_hash=ip_hash,
        )
        self._consent.setdefault(user_id, {})[purpose] = record
        self._log("consent_recorded", user_id, {"purpose": purpose, "granted": granted})
        return record

    def revoke_consent(self, user_id: str, purpose: str) -> bool:
        """Revoke previously granted consent."""
        user_consents = self._consent.get(user_id, {})
        if purpose in user_consents:
            user_consents[purpose].granted = False
            self._log("consent_revoked", user_id, {"purpose": purpose})
            return True
        return False

    def has_consent(self, user_id: str, purpose: str) -> bool:
        """Check if user has active consent for a purpose."""
        record = self._consent.get(user_id, {}).get(purpose)
        return record is not None and record.granted

    def list_consents(self, user_id: str) -> list[dict[str, Any]]:
        """List all consent records for a user."""
        return [
            {"purpose": r.purpose, "granted": r.granted, "timestamp": r.timestamp}
            for r in self._consent.get(user_id, {}).values()
        ]

    # ── Data export (Article 20 — portability) ──

    def export_user_data(self, user_id: str) -> dict[str, Any]:
        """Export all user data in a portable JSON format."""
        # Use the store's export method if available (SQLiteStore has it)
        if hasattr(self._store, "export_user_data"):
            claims = self._store.export_user_data(user_id)
        else:
            raw_claims = self._store.list_claims(user_id=user_id, limit=100000)
            claims = [
                {
                    "claim_id": c.claim_id,
                    "content": c.content,
                    "memory_type": c.memory_type,
                    "visibility": c.visibility,
                    "confidence": c.confidence,
                    "created_at": str(c.created_at),
                    "updated_at": str(c.updated_at),
                }
                for c in raw_claims
            ]

        consents = self.list_consents(user_id)
        export = {
            "user_id": user_id,
            "exported_at": time.time(),
            "claims": claims,
            "consents": consents,
            "total_claims": len(claims),
        }
        self._log("data_exported", user_id, {"claim_count": len(claims)})
        return export

    # ── Right to erasure (Article 17) ──

    def erase_user_data(self, user_id: str) -> ErasureResult:
        """Delete all user data — GDPR right to erasure."""
        claims_deleted = 0
        # Use store's bulk delete if available (SQLiteStore)
        if hasattr(self._store, "delete_user_data"):
            claims_deleted = self._store.delete_user_data(user_id)
        else:
            # Fallback: delete one-by-one for InMemoryMemoryStore
            all_claims = self._store.list_claims(user_id=user_id, limit=100000)
            if hasattr(self._store, "_claims"):
                before = len(self._store._claims)
                self._store._claims = [
                    c for c in self._store._claims if c.user_id != user_id
                ]
                claims_deleted = before - len(self._store._claims)
            elif hasattr(self._store, "delete_claim"):
                for c in all_claims:
                    if self._store.delete_claim(c.claim_id):
                        claims_deleted += 1

        # Clear consent records
        consent_count = len(self._consent.pop(user_id, {}))

        result = ErasureResult(
            user_id=user_id,
            claims_deleted=claims_deleted,
            consent_records_cleared=consent_count,
        )
        self._log("data_erased", user_id, result.to_dict())
        return result

    # ── Audit log ──

    def get_audit_log(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """Get audit log entries, optionally filtered by user."""
        if user_id:
            return [e for e in self._audit_log if e.get("user_id") == user_id]
        return list(self._audit_log)
