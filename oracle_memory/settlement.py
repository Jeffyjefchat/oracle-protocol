"""
Unified settlement engine — the ONE path for all reward/penalty flows.

Principles enforced:
- Two-phase verdict: propose_verdict() → finalize_verdict().
- Finality before payment: _apply_verdict refuses non-final verdicts.
- Pre-settlement hooks: inspect/veto a verdict before it settles.
- Post-settlement hooks: react after settlement (blockchain bridge, etc).
- Single interface: all reward/penalty flows route through here.
- Event log: every settlement is recorded in QualityTracker.
"""
from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .conflict import Conflict, ConflictResolver, ResolutionStrategy, Verdict
from .models import MemoryClaim
from .quality import QualityTracker
from .tokens import TokenLedger
from .trust import ReputationEngine


class SettlementEngine:
    """
    Single gateway for all token/reputation mutations.

    Two-phase flow:
      1. propose_verdict()  — determines winner, creates pending Verdict,
                              fires pre-settlement hooks (can inspect/veto).
      2. finalize_verdict()  — marks final, applies tokens+rep, fires
                              post-settlement hooks.

    settle_conflict() is the convenience wrapper that does both steps
    in one call (immediate-finality mode, backward compatible).
    """

    def __init__(
        self,
        resolver: ConflictResolver,
        ledger: TokenLedger,
        reputation: ReputationEngine,
        quality: QualityTracker | None = None,
    ) -> None:
        self._resolver = resolver
        self._ledger = ledger
        self._reputation = reputation
        self._quality = quality
        self._verdicts: list[Verdict] = []
        self._pending: dict[str, Verdict] = {}  # verdict_id → pending Verdict
        self._pre_hooks: list[Callable[[Verdict], bool]] = []
        self._post_hooks: list[Callable[[Verdict], None]] = []

    # ── Hook registration ──

    def register_hook(self, callback: Callable[[Verdict], None]) -> None:
        """Register a post-settlement callback (blockchain bridge, etc)."""
        self._post_hooks.append(callback)

    def register_pre_hook(self, callback: Callable[[Verdict], bool]) -> None:
        """Register a pre-settlement hook.

        Callback receives the pending (non-final) Verdict.
        Return True to allow finalization, False to veto.
        """
        self._pre_hooks.append(callback)

    # ── Two-phase flow ──

    def propose_verdict(
        self,
        conflict: Conflict,
        claim_a: MemoryClaim,
        claim_b: MemoryClaim,
        node_a: str,
        node_b: str,
        reputation_a: float = 0.5,
        reputation_b: float = 0.5,
        confirmations_a: int = 0,
        confirmations_b: int = 0,
        strategy: ResolutionStrategy | None = None,
    ) -> Verdict | None:
        """
        Phase 1: determine winner, create a PENDING verdict.

        The verdict is NOT final — no tokens or reputation change yet.
        Pre-settlement hooks fire here so external systems can inspect.
        Returns None for MANUAL strategy.
        """
        winner_claim_id = self._resolver.resolve(
            conflict, claim_a, claim_b,
            reputation_a=reputation_a, reputation_b=reputation_b,
            confirmations_a=confirmations_a, confirmations_b=confirmations_b,
            strategy=strategy,
        )
        if not winner_claim_id:
            return None

        if winner_claim_id == claim_a.claim_id:
            winner_node, loser_node = node_a, node_b
        else:
            winner_node, loser_node = node_b, node_a

        reward = self._ledger._config.reward_claim_accepted
        penalty = self._ledger._config.penalty_dispute_lost

        verdict = Verdict.create(
            conflict=conflict,
            winner_node=winner_node,
            loser_node=loser_node,
            reward=reward,
            penalty=penalty,
            auto_finalize=False,  # pending — not final yet
        )

        self._pending[verdict.verdict_id] = verdict
        return verdict

    def finalize_verdict(self, verdict: Verdict) -> bool:
        """
        Phase 2: finalize a pending verdict and apply settlement.

        Runs pre-hooks first — if any returns False, finalization is
        vetoed and the verdict stays pending.
        Returns True if settled, False if vetoed or already final.
        """
        if verdict.is_final:
            return False  # already settled

        # Pre-settlement hooks: any veto blocks finalization
        for hook in self._pre_hooks:
            if not hook(verdict):
                return False  # vetoed

        # Mark final (irreversible)
        verdict.finalize()

        # Apply consequences
        self._apply_verdict(verdict)

        # Remove from pending
        self._pending.pop(verdict.verdict_id, None)

        return True

    # ── Convenience: immediate-finality mode (backward compatible) ──

    def settle_conflict(
        self,
        conflict: Conflict,
        claim_a: MemoryClaim,
        claim_b: MemoryClaim,
        node_a: str,
        node_b: str,
        reputation_a: float = 0.5,
        reputation_b: float = 0.5,
        confirmations_a: int = 0,
        confirmations_b: int = 0,
        strategy: ResolutionStrategy | None = None,
    ) -> Verdict | None:
        """
        One-shot: propose + finalize in a single call.

        This is the original immediate-finality API. Use propose_verdict()
        + finalize_verdict() when you need delayed settlement.
        """
        verdict = self.propose_verdict(
            conflict, claim_a, claim_b,
            node_a=node_a, node_b=node_b,
            reputation_a=reputation_a, reputation_b=reputation_b,
            confirmations_a=confirmations_a, confirmations_b=confirmations_b,
            strategy=strategy,
        )
        if verdict is None:
            return None

        settled = self.finalize_verdict(verdict)
        if not settled:
            return None  # vetoed by pre-hook

        return verdict

    # ── Feedback settlement (thumbs up/down) ──

    def settle_feedback(
        self,
        node_id: str,
        claim_ids: list[str],
        positive: bool,
        user_id: str = "",
        conversation_id: str = "",
    ) -> float:
        """
        Settle a feedback event through the single path.

        Returns the token amount applied.
        """
        if positive:
            rep = self._reputation.get_node_reputation(node_id)
            # Reward
            amount = 0.0
            for cid in claim_ids:
                amount += self._ledger.reward_positive_feedback(
                    node_id, cid, reputation=rep.score,
                )
            # Reputation update
            self._reputation.on_positive_feedback(node_id, claim_ids)
            # Quality log
            if self._quality:
                self._quality.record_positive(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    claim_ids=claim_ids,
                    node_id=node_id,
                )
            return amount
        else:
            # Penalty
            amount = self._ledger.penalize_correction(node_id)
            self._reputation.on_correction(node_id)
            if self._quality:
                self._quality.record_correction(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    node_id=node_id,
                )
            return amount

    # ── Internal ──

    def _apply_verdict(self, verdict: Verdict) -> None:
        """Apply all consequences of a finalized verdict.

        Raises ValueError if the verdict is not final — this is the
        finality gate that prevents premature settlement.
        """
        if not verdict.is_final:
            raise ValueError(
                f"Cannot settle non-final verdict {verdict.verdict_id}. "
                "Call finalize_verdict() first."
            )

        # Tokens: reward winner
        self._ledger.get_balance(verdict.winner_id).credit(
            verdict.reward_amount,
            "verdict_winner",
            verdict.verdict_id,
        )
        # Tokens: penalize loser
        self._ledger.get_balance(verdict.loser_id).debit(
            verdict.penalty_amount,
            "verdict_loser",
            verdict.verdict_id,
        )

        # Reputation: boost winner, dock loser
        winner_rep = self._reputation.get_node_reputation(verdict.winner_id)
        winner_rep.claims_accepted += 1
        winner_rep.score = min(winner_rep.score + 0.02, 1.0)
        winner_rep.last_updated = time.time()

        loser_rep = self._reputation.get_node_reputation(verdict.loser_id)
        loser_rep.claims_rejected += 1
        loser_rep.score = max(loser_rep.score - 0.03, 0.0)
        loser_rep.last_updated = time.time()

        # Quality log
        if self._quality:
            self._quality.record_verdict(
                verdict_id=verdict.verdict_id,
                conflict_id=verdict.conflict_id,
                winner_node=verdict.winner_id,
                loser_node=verdict.loser_id,
            )

        # Store verdict
        self._verdicts.append(verdict)

        # Fire post-settlement hooks (blockchain bridge, external systems)
        for hook in self._post_hooks:
            hook(verdict)

    # ── Query ──

    @property
    def all_verdicts(self) -> list[Verdict]:
        return list(self._verdicts)

    @property
    def pending_verdicts(self) -> list[Verdict]:
        return list(self._pending.values())

    def get_verdict(self, verdict_id: str) -> Verdict | None:
        # Check finalized first, then pending
        for v in self._verdicts:
            if v.verdict_id == verdict_id:
                return v
        return self._pending.get(verdict_id)
