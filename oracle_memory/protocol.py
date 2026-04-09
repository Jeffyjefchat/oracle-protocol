"""
Oracle Memory Protocol — message types and schemas for node coordination.

This is the wire format between nodes (apps using the library) and the
orchestrator (your site). Adds quality scoring, retrieval policies,
and coordinated memory exchange.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

PROTOCOL_VERSION = "0.1.0"

MessageType = Literal[
    "register_node",
    "heartbeat",
    "memory_claim",
    "retrieval_request",
    "retrieval_response",
    "policy_update",
    "quality_report",
    "conversation_feedback",
    "conflict_notice",
]

Scope = Literal["private", "project", "public"]


@dataclass(slots=True)
class ProtocolMessage:
    message_type: MessageType
    node_id: str
    user_id: str | None = None
    conversation_id: str | None = None
    scope: Scope = "private"
    payload: dict[str, Any] = field(default_factory=dict)
    protocol_version: str = PROTOCOL_VERSION
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    signature: str | None = None
    trace_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProtocolMessage:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def sign(self, secret: str) -> str:
        """Compute HMAC-SHA256 signature over canonical payload."""
        canonical = json.dumps(
            {"message_id": self.message_id, "timestamp": self.timestamp, "payload": self.payload},
            sort_keys=True,
            default=str,
        )
        self.signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return self.signature

    def verify(self, secret: str) -> bool:
        expected = hmac.new(
            secret.encode(),
            json.dumps(
                {"message_id": self.message_id, "timestamp": self.timestamp, "payload": self.payload},
                sort_keys=True,
                default=str,
            ).encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(self.signature or "", expected)


# --- Convenience builders ---

def make_register(node_id: str, capabilities: dict[str, Any] | None = None) -> ProtocolMessage:
    return ProtocolMessage(
        message_type="register_node",
        node_id=node_id,
        scope="public",
        payload={
            "capabilities": capabilities or {},
            "protocol_version": PROTOCOL_VERSION,
        },
    )


def make_heartbeat(node_id: str, stats: dict[str, Any] | None = None) -> ProtocolMessage:
    return ProtocolMessage(
        message_type="heartbeat",
        node_id=node_id,
        scope="public",
        payload={"stats": stats or {}},
    )


def make_memory_claim(node_id: str, user_id: str, claim: dict[str, Any], scope: Scope = "private") -> ProtocolMessage:
    return ProtocolMessage(
        message_type="memory_claim",
        node_id=node_id,
        user_id=user_id,
        scope=scope,
        payload={"claim": claim},
    )


def make_retrieval_request(node_id: str, user_id: str, query: str, scope: Scope = "private", limit: int = 10) -> ProtocolMessage:
    return ProtocolMessage(
        message_type="retrieval_request",
        node_id=node_id,
        user_id=user_id,
        scope=scope,
        payload={"query": query, "limit": limit},
    )


def make_policy_update(node_id: str, policies: dict[str, Any]) -> ProtocolMessage:
    return ProtocolMessage(
        message_type="policy_update",
        node_id=node_id,
        scope="public",
        payload={"policies": policies},
    )


def make_quality_report(node_id: str, user_id: str, metrics: dict[str, Any]) -> ProtocolMessage:
    return ProtocolMessage(
        message_type="quality_report",
        node_id=node_id,
        user_id=user_id,
        scope="private",
        payload={"metrics": metrics},
    )


def make_conversation_feedback(node_id: str, user_id: str, conversation_id: str, feedback: dict[str, Any]) -> ProtocolMessage:
    return ProtocolMessage(
        message_type="conversation_feedback",
        node_id=node_id,
        user_id=user_id,
        conversation_id=conversation_id,
        scope="private",
        payload={"feedback": feedback},
    )
