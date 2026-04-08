"""
Federation layer — multi-node coordination and public memory exchange.

Each app instance running oracle-memory is a "node" in the federation.
Nodes register with the orchestrator, exchange public memory claims,
and receive policy updates. Private memory never leaves the node.

Federation flow:
1. Node starts → registers with orchestrator (node_id, capabilities)
2. Orchestrator replies with active RetrievalPolicy
3. Node periodically sends heartbeat + quality metrics
4. Node publishes public memory claims to orchestrator
5. Other nodes can query the orchestrator for public claims
6. Orchestrator pushes policy updates when quality targets shift
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .models import MemoryClaim
from .protocol import (
    ProtocolMessage,
    make_heartbeat,
    make_memory_claim,
    make_register,
    make_retrieval_request,
)


@dataclass(slots=True)
class FederatedNode:
    """Represents a remote node as seen from the federation registry."""
    node_id: str
    endpoint: str = ""
    capabilities: dict[str, Any] = field(default_factory=dict)
    last_seen: float = 0.0
    public_claim_count: int = 0

    @property
    def is_reachable(self) -> bool:
        return (time.time() - self.last_seen) < 300


class FederationRegistry:
    """
    Tracks all known nodes and their public memory claims.

    Runs on the orchestrator side. Nodes push public claims here;
    other nodes query here for cross-user enrichment.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, FederatedNode] = {}
        self._public_claims: list[MemoryClaim] = []

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def register(self, node_id: str, endpoint: str = "",
                 capabilities: dict[str, Any] | None = None) -> FederatedNode:
        if node_id in self._nodes:
            node = self._nodes[node_id]
            node.last_seen = time.time()
            node.endpoint = endpoint or node.endpoint
            node.capabilities = capabilities or node.capabilities
            return node
        node = FederatedNode(
            node_id=node_id,
            endpoint=endpoint,
            capabilities=capabilities or {},
            last_seen=time.time(),
        )
        self._nodes[node_id] = node
        return node

    def heartbeat(self, node_id: str) -> FederatedNode | None:
        node = self._nodes.get(node_id)
        if node:
            node.last_seen = time.time()
        return node

    def alive_nodes(self) -> list[FederatedNode]:
        return [n for n in self._nodes.values() if n.is_reachable]

    def accept_public_claim(self, claim: MemoryClaim, node_id: str) -> bool:
        """Accept a public claim from a node. Rejects private claims."""
        if claim.visibility != "public":
            return False
        # Deduplicate by content hash
        for existing in self._public_claims:
            if existing.content == claim.content and existing.user_id == claim.user_id:
                return False
        self._public_claims.append(claim)
        node = self._nodes.get(node_id)
        if node:
            node.public_claim_count += 1
        return True

    def query_public_claims(self, keywords: list[str] | None = None,
                            memory_type: str = "",
                            limit: int = 20) -> list[MemoryClaim]:
        results = self._public_claims
        if memory_type:
            results = [c for c in results if c.memory_type == memory_type]
        if keywords:
            kw_lower = [k.lower() for k in keywords]
            results = [
                c for c in results
                if any(k in c.content.lower() for k in kw_lower)
            ]
        results.sort(key=lambda c: c.created_at, reverse=True)
        return results[:limit]

    def get_public_claims_for_user(self, user_id: str, limit: int = 20) -> list[MemoryClaim]:
        claims = [c for c in self._public_claims if c.user_id == user_id]
        claims.sort(key=lambda c: c.created_at, reverse=True)
        return claims[:limit]


class FederationClient:
    """
    Node-side federation client. Each app instance uses this to
    communicate with the orchestrator.
    """

    def __init__(self, node_id: str, secret: str = "") -> None:
        self.node_id = node_id
        self._secret = secret
        self._pending_claims: list[ProtocolMessage] = []
        self._pending_heartbeats: list[ProtocolMessage] = []

    def build_register_message(self, capabilities: dict[str, Any] | None = None) -> ProtocolMessage:
        msg = make_register(self.node_id, capabilities or {})
        if self._secret:
            msg.sign(self._secret)
        return msg

    def build_heartbeat_message(self, active_users: int = 0,
                                memory_count: int = 0) -> ProtocolMessage:
        msg = make_heartbeat(self.node_id, {"active_users": active_users, "memory_count": memory_count})
        if self._secret:
            msg.sign(self._secret)
        return msg

    def build_claim_message(self, claim: MemoryClaim) -> ProtocolMessage | None:
        """Build a protocol message for a public claim. Returns None for private claims."""
        if claim.visibility != "public":
            return None
        msg = make_memory_claim(
            node_id=self.node_id,
            user_id=claim.user_id,
            claim={
                "claim_id": claim.claim_id,
                "memory_type": claim.memory_type,
                "content": claim.content,
                "confidence": claim.confidence,
            },
            scope="public",
        )
        if self._secret:
            msg.sign(self._secret)
        return msg

    def build_retrieval_request(self, user_id: str, query: str,
                                scope: str = "public") -> ProtocolMessage:
        msg = make_retrieval_request(self.node_id, user_id, query, scope)
        if self._secret:
            msg.sign(self._secret)
        return msg

    def queue_claim(self, claim: MemoryClaim) -> bool:
        msg = self.build_claim_message(claim)
        if msg:
            self._pending_claims.append(msg)
            return True
        return False

    def flush_pending(self) -> list[ProtocolMessage]:
        """Return all pending messages and clear the queue."""
        pending = self._pending_claims + self._pending_heartbeats
        self._pending_claims.clear()
        self._pending_heartbeats.clear()
        return pending
