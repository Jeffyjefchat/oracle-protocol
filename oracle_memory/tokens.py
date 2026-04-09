"""
Token incentive layer — reward useful knowledge, punish garbage.

This is the skeleton for "memory fragments as assets."
No blockchain dependency — the accounting runs in the orchestrator.
You can wire it to a real token later (ERC-20, Cosmos, etc).

Incentive design:
- Contribution reward: node submits a claim that gets confirmed
- Retrieval reward: node's claim is retrieved and rated positively
- Hallucination penalty: node's claim causes a hallucination
- Staleness penalty: old claims that get superseded
- Quality bonus: nodes maintaining high reputation earn multiplier
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


# ── Reward/penalty configuration ──

@dataclass(slots=True)
class TokenConfig:
    """Tunable incentive parameters."""
    reward_claim_accepted: float = 1.0       # tokens for accepted claim
    reward_claim_confirmed: float = 0.5      # tokens when another node confirms
    reward_claim_retrieved: float = 0.1      # tokens per retrieval
    reward_positive_feedback: float = 2.0    # tokens for user thumbs-up
    penalty_hallucination: float = -5.0      # tokens for hallucination
    penalty_correction: float = -2.0         # tokens for user correction
    penalty_spam_rejected: float = -1.0      # tokens for rejected spam
    penalty_dispute_lost: float = -3.0       # tokens when dispute resolved against
    quality_multiplier_threshold: float = 0.8  # reputation above this gets bonus
    quality_multiplier: float = 1.5          # bonus multiplier for premium nodes


@dataclass
class TokenBalance:
    """A node's token balance and transaction history.

    Balance is read-only from outside — all mutations go through
    credit() and debit() to enforce the settlement path.
    """
    node_id: str
    _balance: float = field(default=0.0, repr=False)
    total_earned: float = 0.0
    total_penalized: float = 0.0
    transactions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def balance(self) -> float:
        return self._balance

    def credit(self, amount: float, reason: str, ref: str = "") -> None:
        self._balance += amount
        self.total_earned += amount
        self.transactions.append({
            "type": "credit",
            "amount": amount,
            "reason": reason,
            "ref": ref,
            "timestamp": time.time(),
        })

    def debit(self, amount: float, reason: str, ref: str = "") -> None:
        """Debit (penalty). Balance can go negative."""
        self._balance += amount  # amount is negative
        self.total_penalized += abs(amount)
        self.transactions.append({
            "type": "debit",
            "amount": amount,
            "reason": reason,
            "ref": ref,
            "timestamp": time.time(),
        })

    def recent_transactions(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.transactions[-limit:]


class TokenLedger:
    """
    Central ledger tracking all token balances across the network.

    Runs in the orchestrator. Each node earns/loses tokens based on
    the quality of their memory contributions.
    """

    def __init__(self, config: TokenConfig | None = None) -> None:
        self._config = config or TokenConfig()
        self._balances: dict[str, TokenBalance] = {}

    def get_balance(self, node_id: str) -> TokenBalance:
        if node_id not in self._balances:
            self._balances[node_id] = TokenBalance(node_id=node_id)
        return self._balances[node_id]

    def _multiplier(self, reputation: float) -> float:
        if reputation >= self._config.quality_multiplier_threshold:
            return self._config.quality_multiplier
        return 1.0

    # ── Reward events ──

    def reward_claim_accepted(self, node_id: str, claim_id: str,
                              reputation: float = 0.5) -> float:
        amount = self._config.reward_claim_accepted * self._multiplier(reputation)
        self.get_balance(node_id).credit(amount, "claim_accepted", claim_id)
        return amount

    def reward_claim_confirmed(self, node_id: str, claim_id: str,
                               reputation: float = 0.5) -> float:
        amount = self._config.reward_claim_confirmed * self._multiplier(reputation)
        self.get_balance(node_id).credit(amount, "claim_confirmed", claim_id)
        return amount

    def reward_claim_retrieved(self, node_id: str, claim_id: str) -> float:
        amount = self._config.reward_claim_retrieved
        self.get_balance(node_id).credit(amount, "claim_retrieved", claim_id)
        return amount

    def reward_positive_feedback(self, node_id: str, claim_id: str,
                                 reputation: float = 0.5) -> float:
        amount = self._config.reward_positive_feedback * self._multiplier(reputation)
        self.get_balance(node_id).credit(amount, "positive_feedback", claim_id)
        return amount

    # ── Penalty events ──

    def penalize_hallucination(self, node_id: str, claim_id: str) -> float:
        amount = self._config.penalty_hallucination
        self.get_balance(node_id).debit(amount, "hallucination", claim_id)
        return amount

    def penalize_correction(self, node_id: str) -> float:
        amount = self._config.penalty_correction
        self.get_balance(node_id).debit(amount, "user_correction")
        return amount

    def penalize_spam(self, node_id: str) -> float:
        amount = self._config.penalty_spam_rejected
        self.get_balance(node_id).debit(amount, "spam_rejected")
        return amount

    def penalize_dispute_lost(self, node_id: str, claim_id: str) -> float:
        amount = self._config.penalty_dispute_lost
        self.get_balance(node_id).debit(amount, "dispute_lost", claim_id)
        return amount

    # ── Leaderboard ──

    def leaderboard(self, limit: int = 10) -> list[TokenBalance]:
        balances = sorted(self._balances.values(),
                          key=lambda b: b.balance, reverse=True)
        return balances[:limit]

    def total_supply(self) -> float:
        """Total tokens in circulation (earned minus penalized)."""
        return sum(b.balance for b in self._balances.values())

    def network_stats(self) -> dict[str, Any]:
        return {
            "total_nodes": len(self._balances),
            "total_supply": self.total_supply(),
            "total_earned": sum(b.total_earned for b in self._balances.values()),
            "total_penalized": sum(b.total_penalized for b in self._balances.values()),
        }
