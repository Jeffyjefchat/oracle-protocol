from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .control_plane import RetrievalPolicy
from .extractor import compact_context_lines, extract_claims_from_conversation, extract_claims_from_document
from .federation import FederationClient
from .models import MemoryClaim
from .quality import QualityTracker
from .store import MemoryStore, bulk_save


@dataclass(slots=True)
class OracleMemoryService:
    """
    High-level service that ties together local storage, federation,
    quality tracking, and policy-driven retrieval.
    """
    store: MemoryStore
    node_id: str = ""
    quality: QualityTracker = field(default_factory=QualityTracker)
    federation: FederationClient | None = None
    _policy: RetrievalPolicy = field(default_factory=RetrievalPolicy)

    def apply_policy(self, policy: RetrievalPolicy) -> None:
        self._policy = policy

    def ingest_conversation_text(self, user_id: str, text: str,
                                 conversation_id: str = "") -> list[MemoryClaim]:
        claims = extract_claims_from_conversation(user_id=user_id, text=text)
        saved = bulk_save(self.store, claims)
        # Publish public claims to federation
        if self.federation:
            for claim in saved:
                self.federation.queue_claim(claim)
        # Track quality: if we saved claims, that's a sign of useful extraction
        if saved and conversation_id:
            self.quality.record_hit(
                user_id=user_id,
                conversation_id=conversation_id,
                claim_ids=[c.claim_id for c in saved],
                node_id=self.node_id,
            )
        return saved

    def ingest_document_text(self, user_id: str, title: str, text: str,
                             visibility: str = "public") -> list[MemoryClaim]:
        claims = extract_claims_from_document(user_id=user_id, title=title, text=text, visibility=visibility)
        saved = bulk_save(self.store, claims)
        if self.federation:
            for claim in saved:
                self.federation.queue_claim(claim)
        return saved

    def build_context(self, user_id: str, include_public: bool = True,
                      include_private: bool = True) -> list[str]:
        """Build memory context lines respecting active retrieval policy."""
        policy = self._policy
        context_lines: list[str] = []
        if include_private:
            private_claims = self.store.list_claims(
                user_id=user_id, visibility="private",
                limit=policy.max_private_claims,
            )
            # Filter by confidence threshold
            private_claims = [c for c in private_claims if c.confidence >= policy.min_confidence]
            if private_claims:
                context_lines.append("Private memory: " + " | ".join(
                    compact_context_lines(private_claims, limit=policy.max_private_claims)))
        if include_public and policy.inject_public_general:
            public_claims = self.store.list_claims(
                user_id=user_id, visibility="public",
                limit=policy.max_public_claims,
            )
            public_claims = [c for c in public_claims if c.confidence >= policy.min_confidence]
            if public_claims:
                context_lines.append("Public/general memory: " + " | ".join(
                    compact_context_lines(public_claims, limit=policy.max_public_claims)))
        return context_lines

    def search(self, user_id: str, query: str, visibility: str | None = None,
               limit: int = 10) -> list[MemoryClaim]:
        return self.store.search_claims(user_id=user_id, query=query, visibility=visibility, limit=limit)

    def record_feedback(self, user_id: str, conversation_id: str,
                        positive: bool, claim_ids: list[str] | None = None) -> None:
        if positive:
            self.quality.record_positive(user_id, conversation_id,
                                         claim_ids=claim_ids, node_id=self.node_id)
        else:
            self.quality.record_correction(user_id, conversation_id,
                                           node_id=self.node_id)

    def get_quality_metrics(self) -> dict[str, float]:
        if self.node_id:
            return self.quality.metrics_for_node(self.node_id)
        return self.quality.global_metrics()
