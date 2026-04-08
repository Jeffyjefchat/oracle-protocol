"""
Easy API — the one-liner developer experience.

GPT's VC critique: "13 modules = cognitive overload."
This module answers: "Drop-in memory that improves your agent over time."

    from oracle_memory import OracleAgent
    agent = OracleAgent("my-agent")
    agent.remember("Python was created by Guido van Rossum")
    context = agent.recall("who created Python?")
    agent.thumbs_up()  # positive feedback loop
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import MemoryClaim
from .service import OracleMemoryService
from .store import InMemoryMemoryStore, MemoryStore
from .quality import QualityTracker
from .tokens import TokenLedger, TokenConfig


@dataclass
class OracleAgent:
    """
    One-object API for oracle-memory.

    Wraps all 13 modules behind 5 methods:
      remember(), recall(), forget(), thumbs_up(), thumbs_down()
    """

    name: str
    user_id: str = "default"
    store: MemoryStore | None = None
    _service: OracleMemoryService = field(init=False, repr=False)
    _ledger: TokenLedger = field(init=False, repr=False)
    _last_query: str = field(init=False, default="", repr=False)
    _last_claim_ids: list[str] = field(init=False, default_factory=list, repr=False)
    _conversation_id: str = field(init=False, default="default", repr=False)

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryMemoryStore()
        self._service = OracleMemoryService(
            store=self.store,
            node_id=self.name,
            quality=QualityTracker(),
        )
        self._ledger = TokenLedger(config=TokenConfig())

    # ── Core API (5 methods) ──

    def remember(self, text: str, visibility: str = "private") -> list[MemoryClaim]:
        """Store knowledge. Returns extracted claims."""
        claims = self._service.ingest_conversation_text(
            user_id=self.user_id,
            text=text,
            conversation_id=self._conversation_id,
        )
        # Override visibility if requested
        for c in claims:
            c.visibility = visibility
        self._last_claim_ids = [c.claim_id for c in claims]
        return claims

    def recall(self, query: str, limit: int = 5) -> list[str]:
        """Search memory. Returns context strings ready for LLM injection."""
        self._last_query = query
        claims = self._service.search(
            user_id=self.user_id,
            query=query,
            limit=limit,
        )
        self._last_claim_ids = [c.claim_id for c in claims]
        return [c.content for c in claims]

    def forget(self, query: str) -> int:
        """Remove claims matching query. Returns count removed."""
        claims = self._service.search(
            user_id=self.user_id,
            query=query,
            limit=100,
        )
        # Remove from store's internal list (InMemoryMemoryStore)
        removed = 0
        if hasattr(self.store, '_claims'):
            for claim in claims:
                try:
                    self.store._claims.remove(claim)
                    removed += 1
                except ValueError:
                    pass
        return removed

    def thumbs_up(self) -> None:
        """Positive feedback on last recall."""
        self._service.record_feedback(
            user_id=self.user_id,
            conversation_id=self._conversation_id,
            positive=True,
            claim_ids=self._last_claim_ids,
        )
        for cid in self._last_claim_ids:
            self._ledger.reward_positive_feedback(self.name, cid)

    def thumbs_down(self) -> None:
        """Negative feedback on last recall."""
        self._service.record_feedback(
            user_id=self.user_id,
            conversation_id=self._conversation_id,
            positive=False,
            claim_ids=self._last_claim_ids,
        )
        self._ledger.penalize_correction(self.name)

    # ── Convenience ──

    @property
    def stats(self) -> dict[str, Any]:
        """Quick overview of this agent's memory state."""
        metrics = self._service.get_quality_metrics()
        balance = self._ledger.get_balance(self.name)
        all_claims = self.store.list_claims(user_id=self.user_id, limit=10000)
        return {
            "name": self.name,
            "total_claims": len(all_claims),
            "token_balance": balance.balance if balance else 0.0,
            "quality": metrics,
        }

    def context_for_llm(self) -> str:
        """Build a ready-to-inject context block for an LLM prompt."""
        lines = self._service.build_context(
            user_id=self.user_id,
            include_public=True,
            include_private=True,
        )
        return "\n".join(lines) if lines else ""
