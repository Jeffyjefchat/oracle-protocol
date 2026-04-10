"""
Easy API — the one-liner developer experience.

GPT's VC critique: "13 modules = cognitive overload."
This module answers: "Drop-in memory that improves your agent over time."

    from oracle_memory import OracleAgent
    agent = OracleAgent("my-agent")
    agent.remember("Python was created by Guido van Rossum")
    context = agent.recall("who created Python?")
    agent.thumbs_up()  # positive feedback loop

Federated mode (auto-registers, heartbeats, fetches policy):

    from oracle_memory import OracleAgent, Orchestrator
    orch = Orchestrator(secret="shared-secret")
    agent = OracleAgent("my-agent", orchestrator=orch, secret="shared-secret")
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .models import MemoryClaim
from .service import OracleMemoryService
from .store import InMemoryMemoryStore, MemoryStore
from .quality import QualityTracker
from .tokens import TokenLedger, TokenConfig
from .trust import ReputationEngine
from .conflict import ConflictResolver
from .settlement import SettlementEngine
from .federation import FederationClient
from .control_plane import Orchestrator, RetrievalPolicy


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
    orchestrator: Orchestrator | None = None
    secret: str = ""
    heartbeat_interval: float = 60.0
    _service: OracleMemoryService = field(init=False, repr=False)
    _ledger: TokenLedger = field(init=False, repr=False)
    _settlement: SettlementEngine = field(init=False, repr=False)
    _federation: FederationClient | None = field(init=False, default=None, repr=False)
    _heartbeat_thread: threading.Thread | None = field(init=False, default=None, repr=False)
    _heartbeat_stop: threading.Event = field(init=False, repr=False, default_factory=threading.Event)
    _last_query: str = field(init=False, default="", repr=False)
    _last_claim_ids: list[str] = field(init=False, default_factory=list, repr=False)
    _conversation_id: str = field(init=False, default="default", repr=False)

    def __post_init__(self) -> None:
        if self.store is None:
            self.store = InMemoryMemoryStore()
        quality = QualityTracker()

        # Set up federation client if orchestrator provided
        federation: FederationClient | None = None
        if self.orchestrator is not None:
            federation = FederationClient(node_id=self.name, secret=self.secret)
            self._federation = federation
            # Register with orchestrator
            self._register_with_orchestrator()

        self._service = OracleMemoryService(
            store=self.store,
            node_id=self.name,
            quality=quality,
            federation=federation,
        )
        self._ledger = TokenLedger(config=TokenConfig())
        self._settlement = SettlementEngine(
            resolver=ConflictResolver(),
            ledger=self._ledger,
            reputation=ReputationEngine(),
            quality=quality,
        )

        # Start heartbeat loop if federated
        if self.orchestrator is not None:
            self._start_heartbeat()

    def _register_with_orchestrator(self) -> None:
        """Register this node with the orchestrator and fetch retrieval policy."""
        assert self.orchestrator is not None
        assert self._federation is not None
        # Build and send HMAC-signed register message
        msg = self._federation.build_register_message()
        if self.secret:
            self.orchestrator._secret = self.orchestrator._secret or self.secret
        # Register and receive policy
        self.orchestrator.register_node(self.name, msg.payload.get("capabilities", {}))

    def _start_heartbeat(self) -> None:
        """Start a daemon thread that sends periodic heartbeats."""
        self._heartbeat_stop.clear()

        def _heartbeat_loop() -> None:
            while not self._heartbeat_stop.is_set():
                self._heartbeat_stop.wait(self.heartbeat_interval)
                if self._heartbeat_stop.is_set():
                    break
                if self.orchestrator and self._federation:
                    stats = {
                        "active_users": 1,
                        "memory_count": len(
                            self.store.list_claims(user_id=self.user_id, limit=10000)
                        ) if self.store else 0,
                    }
                    self._federation.build_heartbeat_message(**stats)
                    self.orchestrator.heartbeat(self.name, stats)
                    # Fetch latest policy
                    policy = self.orchestrator.get_policy_for_node(self.name)
                    if policy:
                        self._service.apply_policy(policy)

        self._heartbeat_thread = threading.Thread(
            target=_heartbeat_loop, daemon=True, name=f"oracle-heartbeat-{self.name}"
        )
        self._heartbeat_thread.start()

    def shutdown(self) -> None:
        """Stop the heartbeat loop. Safe to call multiple times."""
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5)
            self._heartbeat_thread = None

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
        """Positive feedback on last recall — routed through settlement."""
        self._service.record_feedback(
            user_id=self.user_id,
            conversation_id=self._conversation_id,
            positive=True,
            claim_ids=self._last_claim_ids,
        )
        self._settlement.settle_feedback(
            node_id=self.name,
            claim_ids=self._last_claim_ids,
            positive=True,
            user_id=self.user_id,
            conversation_id=self._conversation_id,
        )

    def thumbs_down(self) -> None:
        """Negative feedback on last recall — routed through settlement."""
        self._service.record_feedback(
            user_id=self.user_id,
            conversation_id=self._conversation_id,
            positive=False,
            claim_ids=self._last_claim_ids,
        )
        self._settlement.settle_feedback(
            node_id=self.name,
            claim_ids=self._last_claim_ids,
            positive=False,
            user_id=self.user_id,
            conversation_id=self._conversation_id,
        )

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
