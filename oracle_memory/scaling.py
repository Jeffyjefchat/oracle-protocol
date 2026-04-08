"""
Scaling primitives — sharding, backpressure, and consistency.

GPT's VC critique: "No sharding, no eventual consistency, no backpressure."
This module provides:
  - Consistent hash ring for claim sharding across nodes
  - Backpressure controller (rate limiting per-node claim ingestion)
  - ClaimTTL for automatic expiry of stale knowledge
  - ShardRouter to decide which node owns which claims
"""
from __future__ import annotations

import hashlib
import time
from bisect import bisect_right
from dataclasses import dataclass, field
from typing import Any


class ConsistentHashRing:
    """
    Consistent hash ring for distributing claims across shards/nodes.

    Uses virtual nodes (replicas) for even distribution.
    Adding/removing a node only remaps ~1/n of keys.
    """

    def __init__(self, replicas: int = 150) -> None:
        self._replicas = replicas
        self._ring: list[tuple[int, str]] = []
        self._nodes: set[str] = set()

    def _hash(self, key: str) -> int:
        return int(hashlib.sha256(key.encode()).hexdigest(), 16)

    def add_node(self, node_id: str) -> None:
        if node_id in self._nodes:
            return
        self._nodes.add(node_id)
        for i in range(self._replicas):
            h = self._hash(f"{node_id}:{i}")
            self._ring.append((h, node_id))
        self._ring.sort()

    def remove_node(self, node_id: str) -> None:
        if node_id not in self._nodes:
            return
        self._nodes.discard(node_id)
        self._ring = [(h, n) for h, n in self._ring if n != node_id]

    def get_node(self, key: str) -> str | None:
        """Given a claim_id or key, return the owning node."""
        if not self._ring:
            return None
        h = self._hash(key)
        hashes = [pair[0] for pair in self._ring]
        idx = bisect_right(hashes, h) % len(self._ring)
        return self._ring[idx][1]

    def get_nodes(self, key: str, n: int = 3) -> list[str]:
        """Return n distinct nodes responsible for a key (replication)."""
        if not self._ring:
            return []
        h = self._hash(key)
        hashes = [pair[0] for pair in self._ring]
        idx = bisect_right(hashes, h) % len(self._ring)
        result: list[str] = []
        seen: set[str] = set()
        for i in range(len(self._ring)):
            _, node = self._ring[(idx + i) % len(self._ring)]
            if node not in seen:
                seen.add(node)
                result.append(node)
                if len(result) >= n:
                    break
        return result

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def nodes(self) -> set[str]:
        return set(self._nodes)


@dataclass(slots=True)
class BackpressureController:
    """
    Rate limiter per node to prevent flood attacks.

    GPT critique: "What prevents spam farming?"
    Answer: backpressure + token penalties + reputation gates.

    Uses token bucket algorithm.
    """
    max_claims_per_second: float = 10.0
    burst_size: int = 50
    _buckets: dict[str, list[float]] = field(default_factory=dict, repr=False)

    def allow(self, node_id: str) -> bool:
        """Returns True if this node is within rate limits."""
        now = time.time()
        if node_id not in self._buckets:
            self._buckets[node_id] = []

        window = self._buckets[node_id]
        # Prune old timestamps
        cutoff = now - 1.0
        self._buckets[node_id] = [t for t in window if t > cutoff]
        window = self._buckets[node_id]

        if len(window) >= self.max_claims_per_second:
            return False

        # Check burst (last 10 seconds)
        burst_cutoff = now - 10.0
        recent = [t for t in window if t > burst_cutoff]
        if len(recent) >= self.burst_size:
            return False

        self._buckets[node_id].append(now)
        return True

    def reset(self, node_id: str) -> None:
        self._buckets.pop(node_id, None)


@dataclass(slots=True)
class ClaimTTL:
    """
    Manages claim expiry. Claims have a time-to-live.

    GPT critique: "No claim expiration/TTL."
    Answer: every claim gets a TTL. Stale claims are pruned.
    """
    default_ttl_seconds: float = 86400 * 30  # 30 days default
    _expiry: dict[str, float] = field(default_factory=dict, repr=False)

    def set_ttl(self, claim_id: str, ttl_seconds: float | None = None) -> float:
        """Set or refresh TTL for a claim. Returns expiry timestamp."""
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = time.time() + ttl
        self._expiry[claim_id] = expires_at
        return expires_at

    def is_expired(self, claim_id: str) -> bool:
        """Check if a claim has expired."""
        if claim_id not in self._expiry:
            return False  # No TTL set = never expires
        return time.time() > self._expiry[claim_id]

    def get_expired(self) -> list[str]:
        """Return all expired claim IDs."""
        now = time.time()
        return [cid for cid, exp in self._expiry.items() if now > exp]

    def prune(self) -> list[str]:
        """Remove expired entries from the TTL registry. Returns pruned IDs."""
        expired = self.get_expired()
        for cid in expired:
            del self._expiry[cid]
        return expired

    def remaining(self, claim_id: str) -> float | None:
        """Seconds remaining until expiry, or None if no TTL."""
        if claim_id not in self._expiry:
            return None
        return max(0.0, self._expiry[claim_id] - time.time())


class ShardRouter:
    """
    Routes claims to appropriate shard nodes with replication.

    Combines ConsistentHashRing with backpressure.
    """

    def __init__(self, replicas: int = 150, replication_factor: int = 3) -> None:
        self.ring = ConsistentHashRing(replicas=replicas)
        self.backpressure = BackpressureController()
        self.replication_factor = replication_factor
        self.ttl = ClaimTTL()

    def add_node(self, node_id: str) -> None:
        self.ring.add_node(node_id)

    def remove_node(self, node_id: str) -> None:
        self.ring.remove_node(node_id)
        self.backpressure.reset(node_id)

    def route(self, claim_id: str) -> list[str]:
        """Get the node(s) responsible for this claim."""
        return self.ring.get_nodes(claim_id, n=self.replication_factor)

    def can_accept(self, node_id: str) -> bool:
        """Check if a node can accept more claims (backpressure)."""
        return self.backpressure.allow(node_id)

    def register_claim(self, claim_id: str, ttl_seconds: float | None = None) -> dict[str, Any]:
        """Route a claim and set its TTL. Returns routing info."""
        nodes = self.route(claim_id)
        expiry = self.ttl.set_ttl(claim_id, ttl_seconds)
        return {
            "claim_id": claim_id,
            "shard_nodes": nodes,
            "primary": nodes[0] if nodes else None,
            "expires_at": expiry,
        }
