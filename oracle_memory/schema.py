"""
Standard Memory Format — the universal schema for knowledge exchange.

ChatGPT says: "No shared schema → no shared economy."
This module defines one. Every claim, regardless of source, gets
normalized into this format before entering the network.

Compatible with:
- Palace coordinates (wings/halls/rooms)
- Mem0 (extracted facts → claims)
- Memori (semantic triples → claim + provenance)
- MCP (Model Context Protocol → transport)
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "1.0.0"

# ── Canonical memory types ──
# Every system maps to one of these
CANONICAL_TYPES = {
    "identity",      # who the user is
    "goal",          # what they want to achieve
    "interest",      # topics they care about
    "general",       # shared public facts
    "document",      # extracted from files
    "decision",      # choices made
    "event",         # things that happened
    "preference",    # likes/dislikes
    "relationship",  # connections between entities
    "procedure",     # how to do something
}


@dataclass(slots=True)
class StandardClaim:
    """
    The universal memory unit. Every claim in the network
    conforms to this schema.
    """
    # Required
    claim_id: str
    content: str
    memory_type: str             # one of CANONICAL_TYPES
    visibility: Literal["private", "public"] = "private"

    # Identity
    user_id: str = ""
    source_node_id: str = ""
    source_kind: str = "conversation"  # conversation, document, api, agent

    # Confidence and trust
    confidence: float = 0.6
    trust_score: float = 0.5     # from reputation engine
    confirmations: int = 0
    disputes: int = 0

    # Location in palace coordinate space (optional)
    wing: str = ""
    hall: str = ""
    room: str = ""

    # Provenance
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    origin_hash: str = ""        # SHA-256 of original source text
    supersedes: str = ""         # claim_id this replaces
    schema_version: str = SCHEMA_VERSION

    def content_hash(self) -> str:
        """Deterministic hash for deduplication."""
        key = f"{self.user_id}:{self.memory_type}:{self.content}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StandardClaim:
        # Drop unknown fields for forward compatibility
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json(cls, raw: str) -> StandardClaim:
        return cls.from_dict(json.loads(raw))


def validate_claim(claim: StandardClaim) -> list[str]:
    """Validate a claim against the standard schema. Returns list of errors."""
    errors: list[str] = []
    if not claim.claim_id:
        errors.append("claim_id is required")
    if not claim.content:
        errors.append("content is required")
    if claim.memory_type not in CANONICAL_TYPES:
        errors.append(f"unknown memory_type: {claim.memory_type}")
    if not 0.0 <= claim.confidence <= 1.0:
        errors.append(f"confidence must be 0.0-1.0, got {claim.confidence}")
    if claim.visibility not in ("private", "public"):
        errors.append(f"visibility must be private or public, got {claim.visibility}")
    return errors


# ── Adapters from other formats ──

def from_palace_memory(entry: dict[str, Any], user_id: str = "",
                       node_id: str = "") -> StandardClaim:
    """Convert a palace memory entry to StandardClaim."""
    return StandardClaim(
        claim_id=entry.get("id", ""),
        content=entry.get("text", entry.get("content", "")),
        memory_type=_map_palace_type(entry.get("hall", "")),
        visibility="private",
        user_id=user_id,
        source_node_id=node_id,
        source_kind="palace",
        confidence=entry.get("score", 0.6),
        wing=entry.get("wing", ""),
        hall=entry.get("hall", ""),
        room=entry.get("room", ""),
    )

# Backward-compat alias
from_mempalace_memory = from_palace_memory


def from_mem0_fact(fact: dict[str, Any], user_id: str = "",
                   node_id: str = "") -> StandardClaim:
    """Convert a Mem0 extracted fact to StandardClaim."""
    return StandardClaim(
        claim_id=fact.get("id", ""),
        content=fact.get("text", fact.get("fact", "")),
        memory_type="general",
        visibility="private",
        user_id=user_id,
        source_node_id=node_id,
        source_kind="mem0",
        confidence=fact.get("confidence", 0.6),
    )


def from_semantic_triple(subject: str, predicate: str, obj: str,
                         user_id: str = "", node_id: str = "") -> StandardClaim:
    """Convert a semantic triple (Memori-style) to StandardClaim."""
    content = f"{subject} {predicate} {obj}"
    return StandardClaim(
        claim_id="",
        content=content,
        memory_type=_map_predicate_to_type(predicate),
        visibility="public",
        user_id=user_id,
        source_node_id=node_id,
        source_kind="semantic_triple",
    )


def _map_palace_type(hall: str) -> str:
    """Map palace hall names to canonical types."""
    mapping = {
        "facts": "general",
        "events": "event",
        "discoveries": "interest",
        "preferences": "preference",
        "advice": "procedure",
        "decisions": "decision",
        "relationships": "relationship",
        "goals": "goal",
        "identity": "identity",
    }
    return mapping.get(hall.lower(), "general")


def _map_predicate_to_type(predicate: str) -> str:
    """Map semantic predicates to canonical types."""
    pred = predicate.lower()
    if any(w in pred for w in ("is", "was", "are")):
        return "identity"
    if any(w in pred for w in ("wants", "goal", "plans")):
        return "goal"
    if any(w in pred for w in ("likes", "prefers", "enjoys")):
        return "preference"
    if any(w in pred for w in ("knows", "learned", "discovered")):
        return "interest"
    if any(w in pred for w in ("decided", "chose", "selected")):
        return "decision"
    return "general"
