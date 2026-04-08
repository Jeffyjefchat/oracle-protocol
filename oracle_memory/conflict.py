"""
Conflict resolution — handles contradicting claims across the network.

When two nodes submit claims that contradict each other, the orchestrator
must decide which one wins. This module provides the resolution logic.

Strategies:
- confidence_wins: higher confidence claim wins
- reputation_wins: claim from higher-reputation node wins
- newer_wins: most recent claim supersedes older
- consensus: claim with more confirmations wins
- manual: flag for human review
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import MemoryClaim


class ResolutionStrategy(Enum):
    CONFIDENCE_WINS = "confidence_wins"
    REPUTATION_WINS = "reputation_wins"
    NEWER_WINS = "newer_wins"
    CONSENSUS = "consensus"
    MANUAL = "manual"


@dataclass(slots=True)
class Conflict:
    """A detected conflict between two claims."""
    conflict_id: str
    claim_a_id: str
    claim_b_id: str
    reason: str  # e.g. "contradicts", "duplicate_diverged", "stale_update"
    detected_at: float = field(default_factory=time.time)
    resolved: bool = False
    winner_id: str | None = None
    strategy_used: str | None = None

    def resolve(self, winner_id: str, strategy: str) -> None:
        self.resolved = True
        self.winner_id = winner_id
        self.strategy_used = strategy


class ConflictDetector:
    """
    Detects conflicts between claims in the federation.

    Two claims conflict when:
    - Same user + same memory_type + same topic but different content
    - Same content from different nodes with different confidence
    - A newer claim contradicts an older established one
    """

    def __init__(self) -> None:
        self._conflicts: list[Conflict] = []
        self._conflict_counter = 0

    @property
    def unresolved(self) -> list[Conflict]:
        return [c for c in self._conflicts if not c.resolved]

    @property
    def all_conflicts(self) -> list[Conflict]:
        return list(self._conflicts)

    def check_pair(self, claim_a: MemoryClaim, claim_b: MemoryClaim) -> Conflict | None:
        """Check if two claims conflict."""
        # Same user, same type, but different content = potential conflict
        if (claim_a.user_id == claim_b.user_id
                and claim_a.memory_type == claim_b.memory_type
                and claim_a.content != claim_b.content
                and claim_a.claim_id != claim_b.claim_id):
            # Check for title-level overlap (same topic, different facts)
            if claim_a.title and claim_b.title and claim_a.title == claim_b.title:
                return self._register_conflict(
                    claim_a.claim_id, claim_b.claim_id, "contradicts"
                )
            # Check for keyword overlap in content (rough heuristic)
            words_a = set(claim_a.content.lower().split())
            words_b = set(claim_b.content.lower().split())
            overlap = words_a & words_b
            if len(overlap) > 3 and len(overlap) / max(len(words_a), len(words_b)) > 0.4:
                return self._register_conflict(
                    claim_a.claim_id, claim_b.claim_id, "duplicate_diverged"
                )
        return None

    def check_against_existing(self, new_claim: MemoryClaim,
                               existing_claims: list[MemoryClaim]) -> list[Conflict]:
        """Check a new claim against all existing ones."""
        conflicts = []
        for existing in existing_claims:
            conflict = self.check_pair(new_claim, existing)
            if conflict:
                conflicts.append(conflict)
        return conflicts

    def _register_conflict(self, claim_a_id: str, claim_b_id: str,
                           reason: str) -> Conflict:
        # Don't re-register the same pair
        for existing in self._conflicts:
            ids = {existing.claim_a_id, existing.claim_b_id}
            if claim_a_id in ids and claim_b_id in ids:
                return existing
        self._conflict_counter += 1
        conflict = Conflict(
            conflict_id=f"conflict-{self._conflict_counter}",
            claim_a_id=claim_a_id,
            claim_b_id=claim_b_id,
            reason=reason,
        )
        self._conflicts.append(conflict)
        return conflict


class ConflictResolver:
    """
    Resolves conflicts using configurable strategies.
    """

    def __init__(self, default_strategy: ResolutionStrategy = ResolutionStrategy.CONFIDENCE_WINS) -> None:
        self._default = default_strategy

    def resolve(self, conflict: Conflict,
                claim_a: MemoryClaim, claim_b: MemoryClaim,
                reputation_a: float = 0.5, reputation_b: float = 0.5,
                confirmations_a: int = 0, confirmations_b: int = 0,
                strategy: ResolutionStrategy | None = None) -> str:
        """Resolve a conflict and return the winner's claim_id."""
        strat = strategy or self._default

        if strat == ResolutionStrategy.CONFIDENCE_WINS:
            winner = claim_a.claim_id if claim_a.confidence >= claim_b.confidence else claim_b.claim_id
        elif strat == ResolutionStrategy.REPUTATION_WINS:
            winner = claim_a.claim_id if reputation_a >= reputation_b else claim_b.claim_id
        elif strat == ResolutionStrategy.NEWER_WINS:
            winner = claim_a.claim_id if claim_a.created_at >= claim_b.created_at else claim_b.claim_id
        elif strat == ResolutionStrategy.CONSENSUS:
            winner = claim_a.claim_id if confirmations_a >= confirmations_b else claim_b.claim_id
        elif strat == ResolutionStrategy.MANUAL:
            # Flag for review, don't auto-resolve
            return ""
        else:
            winner = claim_a.claim_id

        conflict.resolve(winner, strat.value)
        return winner
