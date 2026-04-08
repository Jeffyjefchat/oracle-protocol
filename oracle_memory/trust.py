"""
Trust and reputation — Sybil resistance, spam filtering, provenance tracking.

Addresses the key weakness every AI identifies:
"Who do you trust in a shared memory network?"

Each node and each claim accumulates reputation.
Bad actors get throttled. Good contributors get amplified.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NodeReputation:
    """Reputation record for a federated node."""
    node_id: str
    score: float = 0.5          # 0.0 = untrusted, 1.0 = fully trusted
    claims_accepted: int = 0
    claims_rejected: int = 0
    hallucinations_reported: int = 0
    corrections_reported: int = 0
    positive_feedback: int = 0
    last_updated: float = field(default_factory=time.time)

    @property
    def acceptance_rate(self) -> float:
        total = self.claims_accepted + self.claims_rejected
        return self.claims_accepted / total if total else 0.0

    @property
    def is_trusted(self) -> bool:
        return self.score >= 0.3

    @property
    def is_premium(self) -> bool:
        return self.score >= 0.8 and self.claims_accepted >= 10


@dataclass(slots=True)
class ClaimProvenance:
    """Tracks where a claim came from and how it's been validated."""
    claim_id: str
    origin_node_id: str
    origin_user_id: str
    created_at: float = field(default_factory=time.time)
    confirmations: int = 0      # other nodes confirmed this claim
    disputes: int = 0           # other nodes disputed this claim
    retrievals: int = 0         # how many times this was retrieved and used
    last_retrieved: float = 0.0
    superseded_by: str | None = None  # claim_id of newer replacement

    @property
    def trust_score(self) -> float:
        """Compute trust score from confirmations vs disputes."""
        total = self.confirmations + self.disputes
        if total == 0:
            return 0.5  # neutral — unvalidated
        base = self.confirmations / total
        # Bonus for being frequently retrieved (useful)
        usage_bonus = min(self.retrievals * 0.01, 0.2)
        return min(base + usage_bonus, 1.0)

    @property
    def is_disputed(self) -> bool:
        return self.disputes > self.confirmations

    @property
    def is_superseded(self) -> bool:
        return self.superseded_by is not None


class ReputationEngine:
    """
    Central reputation tracker for nodes and claims.

    Defenses:
    - Sybil resistance: new nodes start at 0.5, must earn reputation
    - Spam resistance: nodes with low acceptance rate get throttled
    - Hallucination propagation: claims from low-rep nodes get lower confidence
    - Provenance: every claim tracks origin, confirmations, disputes
    """

    def __init__(self) -> None:
        self._node_rep: dict[str, NodeReputation] = {}
        self._claim_prov: dict[str, ClaimProvenance] = {}
        self._rate_limits: dict[str, list[float]] = {}  # node_id -> timestamps

    def get_node_reputation(self, node_id: str) -> NodeReputation:
        if node_id not in self._node_rep:
            self._node_rep[node_id] = NodeReputation(node_id=node_id)
        return self._node_rep[node_id]

    def get_claim_provenance(self, claim_id: str) -> ClaimProvenance | None:
        return self._claim_prov.get(claim_id)

    # ── Rate limiting (spam resistance) ──

    def check_rate_limit(self, node_id: str, max_per_minute: int = 30) -> bool:
        """Returns True if the node is within rate limits."""
        now = time.time()
        timestamps = self._rate_limits.get(node_id, [])
        # Prune old timestamps
        timestamps = [t for t in timestamps if now - t < 60]
        self._rate_limits[node_id] = timestamps
        return len(timestamps) < max_per_minute

    def record_activity(self, node_id: str) -> None:
        """Record a node's activity for rate limiting."""
        if node_id not in self._rate_limits:
            self._rate_limits[node_id] = []
        self._rate_limits[node_id].append(time.time())

    # ── Claim acceptance gate ──

    def should_accept_claim(self, node_id: str, confidence: float) -> tuple[bool, str]:
        """
        Gate check: should the orchestrator accept a claim from this node?

        Returns (accepted, reason).
        """
        rep = self.get_node_reputation(node_id)

        if not self.check_rate_limit(node_id):
            return False, "rate_limited"

        if not rep.is_trusted:
            return False, "untrusted_node"

        # Low-rep nodes can't push high-confidence claims
        if rep.score < 0.5 and confidence > 0.8:
            return False, "confidence_exceeds_reputation"

        self.record_activity(node_id)
        return True, "accepted"

    # ── Reputation updates ──

    def on_claim_accepted(self, node_id: str, claim_id: str, user_id: str) -> None:
        rep = self.get_node_reputation(node_id)
        rep.claims_accepted += 1
        rep.score = min(rep.score + 0.01, 1.0)
        rep.last_updated = time.time()
        self._claim_prov[claim_id] = ClaimProvenance(
            claim_id=claim_id,
            origin_node_id=node_id,
            origin_user_id=user_id,
        )

    def on_claim_rejected(self, node_id: str, claim_id: str) -> None:
        rep = self.get_node_reputation(node_id)
        rep.claims_rejected += 1
        rep.score = max(rep.score - 0.02, 0.0)
        rep.last_updated = time.time()

    def on_hallucination(self, node_id: str, claim_ids: list[str]) -> None:
        """Penalize node and mark claims as disputed."""
        rep = self.get_node_reputation(node_id)
        rep.hallucinations_reported += 1
        rep.score = max(rep.score - 0.05, 0.0)
        rep.last_updated = time.time()
        for cid in claim_ids:
            prov = self._claim_prov.get(cid)
            if prov:
                prov.disputes += 1

    def on_correction(self, node_id: str) -> None:
        rep = self.get_node_reputation(node_id)
        rep.corrections_reported += 1
        rep.score = max(rep.score - 0.02, 0.0)
        rep.last_updated = time.time()

    def on_positive_feedback(self, node_id: str, claim_ids: list[str]) -> None:
        rep = self.get_node_reputation(node_id)
        rep.positive_feedback += 1
        rep.score = min(rep.score + 0.02, 1.0)
        rep.last_updated = time.time()
        for cid in claim_ids:
            prov = self._claim_prov.get(cid)
            if prov:
                prov.confirmations += 1

    def on_claim_retrieved(self, claim_id: str) -> None:
        prov = self._claim_prov.get(claim_id)
        if prov:
            prov.retrievals += 1
            prov.last_retrieved = time.time()

    def confirm_claim(self, claim_id: str, confirming_node_id: str) -> None:
        """Another node confirms a claim is accurate."""
        prov = self._claim_prov.get(claim_id)
        if prov and prov.origin_node_id != confirming_node_id:
            prov.confirmations += 1

    def dispute_claim(self, claim_id: str, disputing_node_id: str) -> None:
        """Another node disputes a claim."""
        prov = self._claim_prov.get(claim_id)
        if prov and prov.origin_node_id != disputing_node_id:
            prov.disputes += 1

    def supersede_claim(self, old_claim_id: str, new_claim_id: str) -> None:
        """Mark an old claim as replaced by a newer one."""
        prov = self._claim_prov.get(old_claim_id)
        if prov:
            prov.superseded_by = new_claim_id

    # ── Confidence adjustment ──

    def adjust_confidence(self, node_id: str, raw_confidence: float) -> float:
        """
        Adjust a claim's confidence based on the node's reputation.

        Hallucination propagation defense: claims from untrusted nodes
        get their confidence capped, so they rank lower in retrieval.
        """
        rep = self.get_node_reputation(node_id)
        # Cap confidence to node's reputation score
        return min(raw_confidence, rep.score)

    # ── Aggregates ──

    def trusted_nodes(self) -> list[NodeReputation]:
        return [r for r in self._node_rep.values() if r.is_trusted]

    def disputed_claims(self) -> list[ClaimProvenance]:
        return [p for p in self._claim_prov.values() if p.is_disputed]

    def top_claims(self, limit: int = 20) -> list[ClaimProvenance]:
        claims = sorted(self._claim_prov.values(),
                        key=lambda p: p.trust_score, reverse=True)
        return claims[:limit]
