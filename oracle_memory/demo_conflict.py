"""
Multi-agent conflict resolution demo — shows Oracle Protocol's killer feature.

    python -m oracle_memory.demo_conflict

Three agents disagree about a fact. The protocol detects the conflict,
resolves it using reputation + confidence scoring, issues a verdict,
and settles consequences (tokens + reputation). One source of truth emerges.

This is what makes Oracle Protocol different from every other memory system:
claims can be challenged, and outcomes have consequences.
"""
from __future__ import annotations

import sys

from .conflict import ConflictDetector, ConflictResolver, ResolutionStrategy
from .easy import OracleAgent
from .models import MemoryClaim
from .quality import QualityTracker
from .settlement import SettlementEngine
from .store import InMemoryMemoryStore
from .tokens import TokenLedger, TokenConfig
from .trust import ReputationEngine


def _bar(score: float, width: int = 15) -> str:
    filled = int(score * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def run_demo() -> int:
    print()
    print("  \u2550" * 62)
    print("  Oracle Protocol — Multi-Agent Conflict Resolution Demo")
    print("  \u2550" * 62)
    print()

    # ── Setup: shared infrastructure ──
    quality = QualityTracker()
    ledger = TokenLedger(config=TokenConfig())
    reputation = ReputationEngine()
    resolver = ConflictResolver(default_strategy=ResolutionStrategy.REPUTATION_WINS)
    detector = ConflictDetector()
    settlement = SettlementEngine(
        resolver=resolver,
        ledger=ledger,
        reputation=reputation,
        quality=quality,
    )

    # Register a post-settlement hook (shows the hook system works)
    verdicts_log: list[str] = []
    settlement.register_hook(lambda v: verdicts_log.append(v.verdict_id))

    # ── Three agents with different stores ──
    store_a = InMemoryMemoryStore()
    store_b = InMemoryMemoryStore()
    store_c = InMemoryMemoryStore()

    agent_a = OracleAgent("research-lab", user_id="researcher", store=store_a)
    agent_b = OracleAgent("news-bot", user_id="researcher", store=store_b)
    agent_c = OracleAgent("verified-source", user_id="researcher", store=store_c)

    # Give the verified source higher reputation
    rep_a = reputation.get_node_reputation("research-lab")
    rep_a.score = 0.6
    rep_a.claims_accepted = 5

    rep_b = reputation.get_node_reputation("news-bot")
    rep_b.score = 0.3
    rep_b.claims_accepted = 1

    rep_c = reputation.get_node_reputation("verified-source")
    rep_c.score = 0.9
    rep_c.claims_accepted = 25
    rep_c.positive_feedback = 18

    # Seed token balances
    ledger.reward_positive_feedback("research-lab", "seed", reputation=0.6)
    ledger.reward_positive_feedback("news-bot", "seed", reputation=0.3)
    ledger.reward_positive_feedback("verified-source", "seed", reputation=0.9)

    print("  STEP 1: Three agents, three conflicting claims")
    print("  " + "\u2500" * 58)
    print()

    # ── Agent A claims one thing ──
    claim_a = MemoryClaim(
        user_id="researcher",
        memory_type="general",
        content="GPT-5 was released in March 2026 with 10 trillion parameters",
        visibility="public",
        confidence=0.7,
        source_kind="research-paper",
        title="GPT-5 release",
    )
    store_a.save_claim(claim_a)

    # ── Agent B claims something different ──
    claim_b = MemoryClaim(
        user_id="researcher",
        memory_type="general",
        content="GPT-5 was released in January 2026 with 5 trillion parameters",
        visibility="public",
        confidence=0.5,
        source_kind="news-article",
        title="GPT-5 release",
    )
    store_b.save_claim(claim_b)

    # ── Agent C has the verified truth ──
    claim_c = MemoryClaim(
        user_id="researcher",
        memory_type="general",
        content="GPT-5 was released in February 2026 with 8 trillion parameters",
        visibility="public",
        confidence=0.95,
        source_kind="official-announcement",
        title="GPT-5 release",
    )
    store_c.save_claim(claim_c)

    agents_claims = [
        ("research-lab",    claim_a, rep_a),
        ("news-bot",        claim_b, rep_b),
        ("verified-source", claim_c, rep_c),
    ]

    for name, claim, rep in agents_claims:
        print(f"  Agent: {name}")
        print(f"    Claim:      \"{claim.content}\"")
        print(f"    Source:     {claim.source_kind}")
        print(f"    Confidence: {_bar(claim.confidence)} {claim.confidence:.0%}")
        print(f"    Reputation: {_bar(rep.score)} {rep.score:.0%}")
        print()

    # ── Step 2: Detect conflicts ──
    print("  STEP 2: Conflict detection")
    print("  " + "\u2500" * 58)
    print()

    conflict_ab = detector.check_pair(claim_a, claim_b)
    conflict_ac = detector.check_pair(claim_a, claim_c)
    conflict_bc = detector.check_pair(claim_b, claim_c)

    conflicts = [c for c in [conflict_ab, conflict_ac, conflict_bc] if c is not None]
    print(f"  Detected {len(conflicts)} conflict{'s' if len(conflicts) != 1 else ''}:")
    for c in conflicts:
        print(f"    \u26a0 {c.claim_a_id[:12]}... vs {c.claim_b_id[:12]}...")
        print(f"      Reason: {c.reason}")
    print()

    # ── Step 3: Propose verdicts (two-phase) ──
    print("  STEP 3: Two-phase resolution (propose \u2192 finalize)")
    print("  " + "\u2500" * 58)
    print()

    # Resolve A vs C (research-lab vs verified-source)
    if conflict_ac:
        print("  Phase 1: Proposing verdict (research-lab vs verified-source)...")
        verdict_ac = settlement.propose_verdict(
            conflict=conflict_ac,
            claim_a=claim_a, claim_b=claim_c,
            node_a="research-lab", node_b="verified-source",
            reputation_a=rep_a.score, reputation_b=rep_c.score,
        )
        if verdict_ac:
            print(f"    Verdict ID:  {verdict_ac.verdict_id}")
            print(f"    Winner:      {verdict_ac.winner_id}")
            print(f"    Loser:       {verdict_ac.loser_id}")
            print(f"    Strategy:    {verdict_ac.strategy}")
            print(f"    Is final:    {verdict_ac.is_final}  \u2190 not yet!")
            print(f"    Reward:      +{verdict_ac.reward_amount:.1f} tokens")
            print(f"    Penalty:     -{verdict_ac.penalty_amount:.1f} tokens")
            print()

            print("  Phase 2: Finalizing verdict...")
            settled = settlement.finalize_verdict(verdict_ac)
            print(f"    Finalized:   {settled}")
            print(f"    Is final:    {verdict_ac.is_final}  \u2190 irreversible")
            print(f"    Finalized at: {verdict_ac.finalized_at:.0f} (unix timestamp)")
            print()

    # Resolve B vs C (news-bot vs verified-source)
    if conflict_bc:
        print("  Resolving: news-bot vs verified-source...")
        verdict_bc = settlement.settle_conflict(
            conflict=conflict_bc,
            claim_a=claim_b, claim_b=claim_c,
            node_a="news-bot", node_b="verified-source",
            reputation_a=rep_b.score, reputation_b=rep_c.score,
        )
        if verdict_bc:
            print(f"    Winner: {verdict_bc.winner_id} (one-shot mode)")
            print()

    # ── Step 4: Show consequences ──
    print("  STEP 4: Consequences (tokens + reputation)")
    print("  " + "\u2500" * 58)
    print()

    for name in ["research-lab", "news-bot", "verified-source"]:
        rep = reputation.get_node_reputation(name)
        bal = ledger.get_balance(name)
        token_str = f"{bal.balance:.1f}" if bal else "0.0"
        trusted = "\u2705 trusted" if rep.is_trusted else "\u274c untrusted"
        premium = " \u2b50 premium" if rep.is_premium else ""
        print(f"  {name}:")
        print(f"    Reputation:  {_bar(rep.score)} {rep.score:.0%}  ({trusted}{premium})")
        print(f"    Tokens:      {token_str}")
        print(f"    Accepted:    {rep.claims_accepted}  |  Rejected: {rep.claims_rejected}")
        print()

    # ── Step 5: The winner ──
    print("  STEP 5: One source of truth emerges")
    print("  " + "\u2500" * 58)
    print()
    print(f"  \u2714 Winner: verified-source")
    print(f"  \u2714 Truth:  \"{claim_c.content}\"")
    print(f"  \u2714 Source: {claim_c.source_kind} (confidence {claim_c.confidence:.0%})")
    print()

    # ── Verdict serialization ──
    print("  STEP 6: Verdict is portable (JSON-serializable)")
    print("  " + "\u2500" * 58)
    print()
    if verdict_ac:
        d = verdict_ac.to_dict()
        for key in ["verdict_id", "winner_id", "loser_id", "strategy", "is_final"]:
            print(f"    {key}: {d[key]}")
        print(f"    amounts: reward={d['amounts']['reward']:.1f}, penalty={d['amounts']['penalty']:.1f}")
    print()

    # ── Summary ──
    print("  " + "\u2550" * 62)
    print("  What just happened:")
    print()
    print("    1. Three agents submitted conflicting claims about the same topic")
    print("    2. ConflictDetector found the contradictions automatically")
    print("    3. SettlementEngine proposed verdicts (inspectable, vetable)")
    print("    4. Verdicts were finalized \u2014 tokens and reputation were settled")
    print("    5. The verified source won, bad sources lost tokens")
    print("    6. Verdicts are portable JSON \u2014 ready for federation")
    print()
    print("  This is what makes Oracle Protocol different:")
    print("    Claims can be challenged. Outcomes have consequences.")
    print()
    print("  " + "\u2550" * 62)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(run_demo())
