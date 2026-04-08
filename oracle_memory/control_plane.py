"""
Orchestrator control plane — the competitive edge layer.

The orchestrator is your site's authority over how memory is retrieved,
ranked, mixed, and fed into conversations. Every node (app instance)
checks in, receives policies, and reports quality metrics back.

This is where your platform beats a vanilla MemPalace install:
- smarter retrieval ranking tuned from real user feedback
- fresher memory injection based on global event signals
- conversation quality targets enforced per-node
- coordinated deduplication and conflict resolution
- cross-user public memory enrichment
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .protocol import (
    ProtocolMessage,
    make_policy_update,
    make_quality_report,
)


@dataclass(slots=True)
class RetrievalPolicy:
    """Controls how a node ranks and mixes memory for conversations."""
    max_private_claims: int = 8
    max_public_claims: int = 6
    prefer_recent_hours: int = 72
    min_confidence: float = 0.4
    boost_document_memory: float = 1.2
    boost_goal_memory: float = 1.1
    inject_public_general: bool = True
    freshness_weight: float = 0.3
    relevance_weight: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_private_claims": self.max_private_claims,
            "max_public_claims": self.max_public_claims,
            "prefer_recent_hours": self.prefer_recent_hours,
            "min_confidence": self.min_confidence,
            "boost_document_memory": self.boost_document_memory,
            "boost_goal_memory": self.boost_goal_memory,
            "inject_public_general": self.inject_public_general,
            "freshness_weight": self.freshness_weight,
            "relevance_weight": self.relevance_weight,
        }


@dataclass(slots=True)
class QualityTarget:
    """Minimum quality thresholds pushed to nodes."""
    min_retrieval_hit_rate: float = 0.6
    max_hallucination_rate: float = 0.05
    max_fallback_rate: float = 0.15
    target_user_satisfaction: float = 0.8


@dataclass(slots=True)
class NodeRecord:
    node_id: str
    capabilities: dict[str, Any] = field(default_factory=dict)
    last_heartbeat: float = 0.0
    quality_scores: dict[str, float] = field(default_factory=dict)
    active_policy: RetrievalPolicy = field(default_factory=RetrievalPolicy)

    @property
    def is_alive(self) -> bool:
        return (time.time() - self.last_heartbeat) < 300  # 5 min timeout


class Orchestrator:
    """
    Central coordinator that nodes check into.

    Your site runs this. It holds the global policy, collects quality
    metrics, and pushes tuned retrieval rules back to nodes. This is
    your proprietary advantage — better policies = better conversations.
    """

    def __init__(self, secret: str = "") -> None:
        self._secret = secret
        self._nodes: dict[str, NodeRecord] = {}
        self._default_policy = RetrievalPolicy()
        self._quality_target = QualityTarget()
        self._global_events: list[dict[str, Any]] = []

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def alive_nodes(self) -> list[NodeRecord]:
        return [node for node in self._nodes.values() if node.is_alive]

    def register_node(self, node_id: str, capabilities: dict[str, Any] | None = None) -> NodeRecord:
        if node_id in self._nodes:
            record = self._nodes[node_id]
            record.last_heartbeat = time.time()
            record.capabilities = capabilities or record.capabilities
            return record
        record = NodeRecord(
            node_id=node_id,
            capabilities=capabilities or {},
            last_heartbeat=time.time(),
            active_policy=RetrievalPolicy(**self._default_policy.to_dict()),
        )
        self._nodes[node_id] = record
        return record

    def heartbeat(self, node_id: str, stats: dict[str, Any] | None = None) -> NodeRecord | None:
        record = self._nodes.get(node_id)
        if not record:
            return None
        record.last_heartbeat = time.time()
        if stats:
            record.quality_scores.update(stats)
        return record

    def get_policy_for_node(self, node_id: str) -> RetrievalPolicy:
        record = self._nodes.get(node_id)
        if record:
            return record.active_policy
        return self._default_policy

    def update_default_policy(self, **kwargs: Any) -> RetrievalPolicy:
        for key, value in kwargs.items():
            if hasattr(self._default_policy, key):
                setattr(self._default_policy, key, value)
        return self._default_policy

    def push_policy_to_node(self, node_id: str, **overrides: Any) -> ProtocolMessage | None:
        record = self._nodes.get(node_id)
        if not record:
            return None
        policy_dict = self._default_policy.to_dict()
        policy_dict.update(overrides)
        record.active_policy = RetrievalPolicy(**policy_dict)
        msg = make_policy_update(node_id, policy_dict)
        if self._secret:
            msg.sign(self._secret)
        return msg

    def push_policy_to_all(self, **overrides: Any) -> list[ProtocolMessage]:
        messages = []
        for node_id in self._nodes:
            msg = self.push_policy_to_node(node_id, **overrides)
            if msg:
                messages.append(msg)
        return messages

    def report_quality(self, node_id: str, user_id: str, metrics: dict[str, Any]) -> ProtocolMessage:
        record = self._nodes.get(node_id)
        if record:
            record.quality_scores.update(metrics)
            self._auto_tune_policy(record, metrics)
        return make_quality_report(node_id, user_id, metrics)

    def add_global_event(self, event: dict[str, Any]) -> None:
        """Inject a global event (news, release, announcement) that all nodes can access."""
        event.setdefault("timestamp", time.time())
        self._global_events.append(event)
        if len(self._global_events) > 200:
            self._global_events = self._global_events[-200:]

    def get_recent_global_events(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._global_events[-limit:]

    def _auto_tune_policy(self, record: NodeRecord, metrics: dict[str, Any]) -> None:
        """
        Automatically adjust a node's retrieval policy based on quality signals.
        This is the core competitive advantage: your orchestrator learns from
        real feedback and tunes retrieval better over time.
        """
        hit_rate = metrics.get("retrieval_hit_rate", 1.0)
        hallucination_rate = metrics.get("hallucination_rate", 0.0)
        fallback_rate = metrics.get("fallback_rate", 0.0)
        satisfaction = metrics.get("user_satisfaction", 1.0)

        policy = record.active_policy

        # If retrieval is missing too often, widen the window and boost confidence floor
        if hit_rate < self._quality_target.min_retrieval_hit_rate:
            policy.prefer_recent_hours = min(policy.prefer_recent_hours + 24, 720)
            policy.min_confidence = max(policy.min_confidence - 0.05, 0.1)
            policy.max_private_claims = min(policy.max_private_claims + 2, 20)

        # If hallucinations are high, tighten confidence and reduce injection
        if hallucination_rate > self._quality_target.max_hallucination_rate:
            policy.min_confidence = min(policy.min_confidence + 0.1, 0.9)
            policy.max_public_claims = max(policy.max_public_claims - 1, 2)

        # If fallback rate is high, boost document and goal memory
        if fallback_rate > self._quality_target.max_fallback_rate:
            policy.boost_document_memory = min(policy.boost_document_memory + 0.1, 2.0)
            policy.boost_goal_memory = min(policy.boost_goal_memory + 0.1, 2.0)

        # If user satisfaction is low, lean heavier on relevance over freshness
        if satisfaction < self._quality_target.target_user_satisfaction:
            policy.relevance_weight = min(policy.relevance_weight + 0.05, 0.95)
            policy.freshness_weight = max(policy.freshness_weight - 0.05, 0.05)
