"""Tests for settlement engine, Verdict, and architectural principles."""
import time

from oracle_memory.models import MemoryClaim
from oracle_memory.conflict import (
    Conflict, ConflictDetector, ConflictResolver, ResolutionStrategy, Verdict,
)
from oracle_memory.tokens import TokenLedger, TokenConfig, TokenBalance
from oracle_memory.trust import ReputationEngine
from oracle_memory.quality import QualityTracker
from oracle_memory.settlement import SettlementEngine
from oracle_memory.easy import OracleAgent


# ── Verdict dataclass ───────────────────────────────────────────────────

def test_verdict_create():
    conflict = Conflict(
        conflict_id="conflict-1",
        claim_a_id="ca1", claim_b_id="cb1",
        reason="contradicts",
    )
    conflict.resolve("ca1", "confidence_wins")
    verdict = Verdict.create(
        conflict=conflict,
        winner_node="node-a",
        loser_node="node-b",
        reward=1.0,
        penalty=-3.0,
    )
    assert verdict.verdict_id.startswith("verdict-")
    assert verdict.conflict_id == "conflict-1"
    assert verdict.winner_id == "node-a"
    assert verdict.loser_id == "node-b"
    assert verdict.winner_claim_id == "ca1"
    assert verdict.loser_claim_id == "cb1"
    assert verdict.reward_amount == 1.0
    assert verdict.penalty_amount == -3.0
    assert verdict.strategy == "confidence_wins"
    assert verdict.reason == "contradicts"
    assert verdict.is_final is True
    assert verdict.finalized_at > 0


def test_verdict_has_stable_ids():
    """Principle 4: every verdict has a unique, stable ID."""
    conflict = Conflict(
        conflict_id="conflict-99",
        claim_a_id="ca1", claim_b_id="cb1",
        reason="test",
    )
    conflict.resolve("ca1", "confidence_wins")
    v1 = Verdict.create(conflict, "n1", "n2")
    v2 = Verdict.create(conflict, "n1", "n2")
    assert v1.verdict_id != v2.verdict_id  # unique each time


# ── TokenBalance read-only balance ──────────────────────────────────────

def test_token_balance_read_only():
    """Principle 1: balance is read-only, mutations only through credit/debit."""
    tb = TokenBalance(node_id="n1")
    assert tb.balance == 0.0
    tb.credit(5.0, "test")
    assert tb.balance == 5.0
    tb.debit(-2.0, "test")
    assert tb.balance == 3.0
    # balance is a property — setting it raises AttributeError
    try:
        tb.balance = 999.0
        assert False, "Should not be able to set balance directly"
    except AttributeError:
        pass  # expected


# ── Settlement engine: conflict flow ────────────────────────────────────

def _make_test_claims():
    """Helper: two contradicting claims."""
    claim_a = MemoryClaim(
        user_id="u1", memory_type="fact",
        content="Python was created in 1989",
        title="Python Origin",
        confidence=0.9,
    )
    claim_b = MemoryClaim(
        user_id="u1", memory_type="fact",
        content="Python was created in 1991",
        title="Python Origin",
        confidence=0.7,
    )
    return claim_a, claim_b


def test_settle_conflict_produces_verdict():
    """Principle 3: resolve() produces a Verdict object."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    quality = QualityTracker()
    engine = SettlementEngine(resolver, ledger, rep, quality)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)
    assert conflict is not None

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    assert verdict is not None
    assert verdict.winner_id == "node-a"  # higher confidence
    assert verdict.loser_id == "node-b"
    assert verdict.reward_amount > 0
    assert verdict.penalty_amount < 0


def test_settle_conflict_finality_gate():
    """Principle 5: tokens and reputation change ONLY after verdict."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    quality = QualityTracker()
    engine = SettlementEngine(resolver, ledger, rep, quality)

    # Before settlement: balances are zero, reputation is default
    assert ledger.get_balance("node-a").balance == 0.0
    assert ledger.get_balance("node-b").balance == 0.0
    assert rep.get_node_reputation("node-a").score == 0.5
    assert rep.get_node_reputation("node-b").score == 0.5

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )

    # After settlement: winner rewarded, loser penalized
    assert ledger.get_balance("node-a").balance > 0
    assert ledger.get_balance("node-b").balance < 0
    assert rep.get_node_reputation("node-a").score > 0.5
    assert rep.get_node_reputation("node-b").score < 0.5


def test_settle_conflict_fires_hooks():
    """Principle 7: post-settlement hooks fire after settlement."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    hook_calls = []
    engine.register_hook(lambda v: hook_calls.append(("hook-1", v)))
    engine.register_hook(lambda v: hook_calls.append(("hook-2", v)))

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )

    # Both hooks fired in order
    assert len(hook_calls) == 2
    assert hook_calls[0][0] == "hook-1"
    assert hook_calls[0][1].verdict_id == verdict.verdict_id
    assert hook_calls[1][0] == "hook-2"
    assert hook_calls[1][1].verdict_id == verdict.verdict_id


def test_settle_conflict_logs_verdict_event():
    """Principle 6: verdict_finalized appears in quality event stream."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    quality = QualityTracker(window_seconds=9999)
    engine = SettlementEngine(resolver, ledger, rep, quality)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )

    events = [e for e in quality._events if e.event_type == "verdict_finalized"]
    assert len(events) == 1
    assert verdict.verdict_id in events[0].detail


def test_settle_manual_returns_none():
    """MANUAL strategy returns None — no auto-verdict."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
        strategy=ResolutionStrategy.MANUAL,
    )
    assert verdict is None


# ── Settlement engine: feedback flow ────────────────────────────────────

def test_settle_feedback_positive():
    """Principle 2: thumbs-up goes through single settlement path."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    quality = QualityTracker(window_seconds=9999)
    engine = SettlementEngine(resolver, ledger, rep, quality)

    amount = engine.settle_feedback(
        node_id="n1",
        claim_ids=["c1", "c2"],
        positive=True,
        user_id="u1",
        conversation_id="conv-1",
    )
    assert amount > 0
    assert ledger.get_balance("n1").balance > 0
    assert rep.get_node_reputation("n1").score > 0.5


def test_settle_feedback_negative():
    """Principle 2: thumbs-down goes through single settlement path."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    quality = QualityTracker(window_seconds=9999)
    engine = SettlementEngine(resolver, ledger, rep, quality)

    amount = engine.settle_feedback(
        node_id="n1",
        claim_ids=["c1"],
        positive=False,
        user_id="u1",
        conversation_id="conv-1",
    )
    assert amount < 0
    assert ledger.get_balance("n1").balance < 0
    assert rep.get_node_reputation("n1").score < 0.5


# ── OracleAgent integration ────────────────────────────────────────────

def test_oracle_agent_uses_settlement():
    """Easy API (thumbs_up/down) routes through settlement engine."""
    agent = OracleAgent("test-agent")
    agent.remember("Guido van Rossum created Python")
    agent.recall("who created Python?")
    agent.thumbs_up()
    # Settlement engine should have updated the ledger
    assert agent._ledger.get_balance("test-agent").balance > 0
    # Settlement engine exists on the agent
    assert hasattr(agent, "_settlement")
    assert isinstance(agent._settlement, SettlementEngine)


# ── Verdict query ───────────────────────────────────────────────────────

def test_settlement_stores_and_queries_verdicts():
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    assert len(engine.all_verdicts) == 1
    assert engine.get_verdict(verdict.verdict_id) is not None
    assert engine.get_verdict("nonexistent") is None


# ── Two-phase verdict flow ──────────────────────────────────────────────

def test_verdict_pending_state():
    """Verdict can exist in a non-final (pending) state."""
    conflict = Conflict(
        conflict_id="conflict-1",
        claim_a_id="ca1", claim_b_id="cb1",
        reason="contradicts",
    )
    conflict.resolve("ca1", "confidence_wins")
    verdict = Verdict.create(
        conflict=conflict,
        winner_node="node-a",
        loser_node="node-b",
        auto_finalize=False,
    )
    assert verdict.is_final is False
    assert verdict.finalized_at == 0.0

    verdict.finalize()
    assert verdict.is_final is True
    assert verdict.finalized_at > 0


def test_finalize_is_idempotent():
    """Calling finalize() twice doesn't change the timestamp."""
    conflict = Conflict(
        conflict_id="c1", claim_a_id="a", claim_b_id="b", reason="test",
    )
    conflict.resolve("a", "confidence_wins")
    verdict = Verdict.create(conflict, "n1", "n2", auto_finalize=False)
    verdict.finalize()
    ts = verdict.finalized_at
    verdict.finalize()  # second call
    assert verdict.finalized_at == ts  # unchanged


def test_propose_creates_pending_verdict():
    """propose_verdict() returns a non-final verdict."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.propose_verdict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    assert verdict is not None
    assert verdict.is_final is False
    assert verdict.winner_id == "node-a"
    # No tokens or rep should have changed
    assert ledger.get_balance("node-a").balance == 0.0
    assert ledger.get_balance("node-b").balance == 0.0
    assert rep.get_node_reputation("node-a").score == 0.5
    # Should be in pending list
    assert len(engine.pending_verdicts) == 1
    assert engine.get_verdict(verdict.verdict_id) is verdict


def test_finalize_verdict_applies_settlement():
    """finalize_verdict() marks final and applies tokens+rep."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    quality = QualityTracker(window_seconds=9999)
    engine = SettlementEngine(resolver, ledger, rep, quality)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.propose_verdict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )

    settled = engine.finalize_verdict(verdict)
    assert settled is True
    assert verdict.is_final is True
    assert verdict.finalized_at > 0
    # Tokens applied
    assert ledger.get_balance("node-a").balance > 0
    assert ledger.get_balance("node-b").balance < 0
    # Rep applied
    assert rep.get_node_reputation("node-a").score > 0.5
    assert rep.get_node_reputation("node-b").score < 0.5
    # Moved from pending to finalized
    assert len(engine.pending_verdicts) == 0
    assert len(engine.all_verdicts) == 1
    # Quality event logged
    events = [e for e in quality._events if e.event_type == "verdict_finalized"]
    assert len(events) == 1


def test_finalize_already_final_returns_false():
    """Cannot finalize an already-final verdict."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    # Already final from settle_conflict
    assert engine.finalize_verdict(verdict) is False


def test_apply_verdict_rejects_non_final():
    """_apply_verdict raises ValueError on non-final verdict."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    conflict = Conflict(
        conflict_id="c1", claim_a_id="a", claim_b_id="b", reason="test",
    )
    conflict.resolve("a", "confidence_wins")
    verdict = Verdict.create(conflict, "n1", "n2", auto_finalize=False)

    try:
        engine._apply_verdict(verdict)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "non-final" in str(e).lower()


def test_pre_hook_can_veto():
    """Pre-settlement hook returning False blocks finalization."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    # Register a hook that vetoes everything
    engine.register_pre_hook(lambda v: False)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.propose_verdict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    assert verdict is not None

    settled = engine.finalize_verdict(verdict)
    assert settled is False
    assert verdict.is_final is False
    # No tokens changed
    assert ledger.get_balance("node-a").balance == 0.0
    # Still pending
    assert len(engine.pending_verdicts) == 1


def test_pre_hook_allows_when_true():
    """Pre-settlement hook returning True allows finalization."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    inspected = []
    def inspect_and_allow(v):
        inspected.append(v)
        return True

    engine.register_pre_hook(inspect_and_allow)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)


    verdict = engine.propose_verdict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    settled = engine.finalize_verdict(verdict)
    assert settled is True
    assert len(inspected) == 1
    assert inspected[0].verdict_id == verdict.verdict_id


def test_settle_conflict_vetoed_by_pre_hook():
    """settle_conflict() returns None when pre-hook vetoes."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    engine.register_pre_hook(lambda v: False)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    assert verdict is None
    assert ledger.get_balance("node-a").balance == 0.0


def test_post_hooks_fire_after_finalize():
    """Post-settlement hooks fire only after finalize, not propose."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    post_calls = []
    engine.register_hook(lambda v: post_calls.append(v))

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.propose_verdict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    assert len(post_calls) == 0  # not yet

    engine.finalize_verdict(verdict)
    assert len(post_calls) == 1
    assert post_calls[0].is_final is True


# ── Verdict serialization (v0.4.0) ─────────────────────────────────────

def test_verdict_to_dict():
    """to_dict produces canonical wire format with nested amounts."""
    conflict = Conflict(
        conflict_id="c-ser", claim_a_id="ca", claim_b_id="cb", reason="test",
    )
    conflict.resolve("ca", "confidence_wins")
    verdict = Verdict.create(conflict, "alice", "bob", reward=1.0, penalty=-3.0)

    d = verdict.to_dict()
    assert d["schema_version"] == "1.0"
    assert d["verdict_id"] == verdict.verdict_id
    assert d["conflict_id"] == "c-ser"
    assert d["winner_id"] == "alice"
    assert d["loser_id"] == "bob"
    assert d["amounts"]["reward"] == 1.0
    assert d["amounts"]["penalty"] == -3.0
    assert d["strategy"] == "confidence_wins"
    assert d["reason"] == "test"
    assert d["is_final"] is True
    assert d["finalized_at"] > 0


def test_verdict_from_dict_roundtrip():
    """to_dict → from_dict preserves all fields."""
    conflict = Conflict(
        conflict_id="c-rt", claim_a_id="x", claim_b_id="y", reason="dup",
    )
    conflict.resolve("x", "newer_wins")
    original = Verdict.create(conflict, "node-1", "node-2", reward=2.0, penalty=-1.5)

    rebuilt = Verdict.from_dict(original.to_dict())

    assert rebuilt.verdict_id == original.verdict_id
    assert rebuilt.conflict_id == original.conflict_id
    assert rebuilt.winner_id == original.winner_id
    assert rebuilt.loser_id == original.loser_id
    assert rebuilt.winner_claim_id == original.winner_claim_id
    assert rebuilt.loser_claim_id == original.loser_claim_id
    assert rebuilt.reward_amount == original.reward_amount
    assert rebuilt.penalty_amount == original.penalty_amount
    assert rebuilt.strategy == original.strategy
    assert rebuilt.reason == original.reason
    assert rebuilt.is_final == original.is_final
    assert rebuilt.finalized_at == original.finalized_at


def test_verdict_from_dict_handles_flat_amounts():
    """from_dict accepts the legacy flat reward_amount/penalty_amount keys."""
    data = {
        "verdict_id": "verdict-legacy",
        "conflict_id": "c-legacy",
        "winner_id": "w",
        "loser_id": "l",
        "reward_amount": 5.0,
        "penalty_amount": -2.0,
        "is_final": True,
        "finalized_at": 100.0,
    }
    v = Verdict.from_dict(data)
    assert v.reward_amount == 5.0
    assert v.penalty_amount == -2.0


# ── Public ledger boundary (v0.4.0) ────────────────────────────────────

def test_ledger_verdict_amounts():
    """verdict_amounts() returns (reward, penalty) from config."""
    ledger = TokenLedger()
    reward, penalty = ledger.verdict_amounts()
    assert reward == 1.0   # TokenConfig default
    assert penalty == -3.0  # TokenConfig default


def test_ledger_settle_winner():
    """settle_winner() credits the correct amount."""
    ledger = TokenLedger()
    amount = ledger.settle_winner("winner-node", "verdict-1")
    assert amount == 1.0  # default config, default reputation
    assert ledger.get_balance("winner-node").balance == 1.0
    txn = ledger.get_balance("winner-node").transactions[-1]
    assert txn["reason"] == "verdict_winner"
    assert txn["ref"] == "verdict-1"


def test_ledger_settle_winner_custom_amount():
    """settle_winner() uses explicit amount when provided."""
    ledger = TokenLedger()
    amount = ledger.settle_winner("w", "v-1", amount=7.5)
    assert amount == 7.5
    assert ledger.get_balance("w").balance == 7.5


def test_ledger_settle_loser():
    """settle_loser() debits the correct amount."""
    ledger = TokenLedger()
    amount = ledger.settle_loser("loser-node", "verdict-2")
    assert amount == -3.0  # default config
    assert ledger.get_balance("loser-node").balance == -3.0
    txn = ledger.get_balance("loser-node").transactions[-1]
    assert txn["reason"] == "verdict_loser"
    assert txn["ref"] == "verdict-2"


def test_settle_conflict_uses_public_ledger_api():
    """Full settle_conflict flow uses settle_winner/settle_loser under the hood."""
    resolver = ConflictResolver()
    ledger = TokenLedger()
    rep = ReputationEngine()
    engine = SettlementEngine(resolver, ledger, rep)

    claim_a, claim_b = _make_test_claims()
    detector = ConflictDetector()
    conflict = detector.check_pair(claim_a, claim_b)

    verdict = engine.settle_conflict(
        conflict, claim_a, claim_b,
        node_a="node-a", node_b="node-b",
    )
    assert verdict is not None
    assert verdict.is_final is True

    # Winner got credited via settle_winner
    winner_bal = ledger.get_balance(verdict.winner_id)
    assert winner_bal.balance > 0
    assert winner_bal.transactions[-1]["reason"] == "verdict_winner"

    # Loser got debited via settle_loser
    loser_bal = ledger.get_balance(verdict.loser_id)
    assert loser_bal.balance < 0
    assert loser_bal.transactions[-1]["reason"] == "verdict_loser"
