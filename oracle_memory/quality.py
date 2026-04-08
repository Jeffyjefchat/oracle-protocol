"""
Quality scoring and feedback collection.

Collects signals from conversations and uses them to score memory
retrieval quality. The orchestrator uses these scores to auto-tune
retrieval policies for each node.

Signal types:
- retrieval_hit: user question matched a stored memory claim
- retrieval_miss: user question had no matching memory
- hallucination: answer contradicted stored facts
- user_correction: user explicitly corrected the AI
- positive_feedback: user confirmed answer was helpful
- topic_drift: conversation veered away from retrieved context
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QualityEvent:
    """A single quality signal from a conversation turn."""
    event_type: str
    user_id: str
    conversation_id: str
    node_id: str = ""
    claim_ids: list[str] = field(default_factory=list)
    score: float = 1.0
    detail: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "node_id": self.node_id,
            "claim_ids": self.claim_ids,
            "score": self.score,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


class QualityTracker:
    """
    Collects quality events and computes aggregate metrics per node/user.

    Metrics are fed to the orchestrator's auto-tuning loop.
    """

    def __init__(self, window_seconds: int = 3600) -> None:
        self._events: list[QualityEvent] = []
        self._window = window_seconds

    def record(self, event: QualityEvent) -> None:
        self._events.append(event)
        self._prune()

    def record_hit(self, user_id: str, conversation_id: str, claim_ids: list[str],
                   node_id: str = "") -> QualityEvent:
        ev = QualityEvent("retrieval_hit", user_id, conversation_id,
                          node_id=node_id, claim_ids=claim_ids, score=1.0)
        self.record(ev)
        return ev

    def record_miss(self, user_id: str, conversation_id: str,
                    node_id: str = "", detail: str = "") -> QualityEvent:
        ev = QualityEvent("retrieval_miss", user_id, conversation_id,
                          node_id=node_id, score=0.0, detail=detail)
        self.record(ev)
        return ev

    def record_hallucination(self, user_id: str, conversation_id: str,
                             claim_ids: list[str], node_id: str = "",
                             detail: str = "") -> QualityEvent:
        ev = QualityEvent("hallucination", user_id, conversation_id,
                          node_id=node_id, claim_ids=claim_ids, score=-1.0,
                          detail=detail)
        self.record(ev)
        return ev

    def record_correction(self, user_id: str, conversation_id: str,
                          node_id: str = "", detail: str = "") -> QualityEvent:
        ev = QualityEvent("user_correction", user_id, conversation_id,
                          node_id=node_id, score=-0.5, detail=detail)
        self.record(ev)
        return ev

    def record_positive(self, user_id: str, conversation_id: str,
                        claim_ids: list[str] | None = None,
                        node_id: str = "") -> QualityEvent:
        ev = QualityEvent("positive_feedback", user_id, conversation_id,
                          node_id=node_id, claim_ids=claim_ids or [], score=1.0)
        self.record(ev)
        return ev

    def record_drift(self, user_id: str, conversation_id: str,
                     node_id: str = "", detail: str = "") -> QualityEvent:
        ev = QualityEvent("topic_drift", user_id, conversation_id,
                          node_id=node_id, score=-0.3, detail=detail)
        self.record(ev)
        return ev

    def metrics_for_node(self, node_id: str) -> dict[str, float]:
        events = [e for e in self._events if e.node_id == node_id]
        return self._compute_metrics(events)

    def metrics_for_user(self, user_id: str) -> dict[str, float]:
        events = [e for e in self._events if e.user_id == user_id]
        return self._compute_metrics(events)

    def global_metrics(self) -> dict[str, float]:
        return self._compute_metrics(self._events)

    def _compute_metrics(self, events: list[QualityEvent]) -> dict[str, float]:
        if not events:
            return {
                "retrieval_hit_rate": 0.0,
                "hallucination_rate": 0.0,
                "fallback_rate": 0.0,
                "user_satisfaction": 0.0,
                "total_events": 0,
            }

        total = len(events)
        hits = sum(1 for e in events if e.event_type == "retrieval_hit")
        misses = sum(1 for e in events if e.event_type == "retrieval_miss")
        hallucinations = sum(1 for e in events if e.event_type == "hallucination")
        positives = sum(1 for e in events if e.event_type == "positive_feedback")
        corrections = sum(1 for e in events if e.event_type == "user_correction")

        retrieval_total = hits + misses
        feedback_total = positives + corrections + hallucinations

        return {
            "retrieval_hit_rate": hits / retrieval_total if retrieval_total else 0.0,
            "hallucination_rate": hallucinations / total,
            "fallback_rate": misses / total,
            "user_satisfaction": positives / feedback_total if feedback_total else 0.0,
            "total_events": total,
        }

    def _prune(self) -> None:
        cutoff = time.time() - self._window
        self._events = [e for e in self._events if e.timestamp >= cutoff]
