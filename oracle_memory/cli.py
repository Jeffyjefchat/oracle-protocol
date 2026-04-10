"""
Oracle CLI — the user-facing product layer.

    oracle ask "What are the top AI trends?"
    oracle verify "Python was created by Guido van Rossum"
    oracle trends
    oracle remember "Flask uses Jinja2 templates"
    oracle stats
    oracle demo
    oracle export --user default
    oracle forget "outdated claim"

This is the "why should I use this today?" layer built on top of the
v2 infrastructure (SQLiteStore, trust, quality, federation).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
from pathlib import Path

from .easy import OracleAgent
from .models import MemoryClaim
from .sqlite_store import SQLiteStore
from .store import InMemoryMemoryStore
from .version import CURRENT_VERSION


# ── Defaults ─────────────────────────────────────────────────────────────

_DEFAULT_DB = os.environ.get("ORACLE_DB", "oracle_memory.db")
_DEFAULT_USER = os.environ.get("ORACLE_USER", "default")
_CONFIDENCE_BAR = "█"
_CONFIDENCE_EMPTY = "░"


# ── Helpers ──────────────────────────────────────────────────────────────

def _db_path() -> str:
    """Resolve the database path. Use :memory: for tests or if explicitly set."""
    return _DEFAULT_DB


def _make_agent(db: str | None = None, user: str | None = None) -> OracleAgent:
    """Create an OracleAgent with persistent SQLite storage."""
    db = db or _db_path()
    user = user or _DEFAULT_USER
    store = SQLiteStore(db)
    return OracleAgent(name="oracle-cli", user_id=user, store=store)


def _confidence_bar(score: float, width: int = 20) -> str:
    """Render a confidence score as a visual bar."""
    filled = int(score * width)
    return _CONFIDENCE_BAR * filled + _CONFIDENCE_EMPTY * (width - filled)


def _format_confidence(score: float) -> str:
    """Format confidence as colored percentage + bar."""
    pct = score * 100
    bar = _confidence_bar(score)
    if pct >= 70:
        label = "HIGH"
    elif pct >= 40:
        label = "MEDIUM"
    else:
        label = "LOW"
    return f"{bar} {pct:.0f}% ({label})"


def _wrap(text: str, indent: str = "  ", width: int = 76) -> str:
    return textwrap.fill(text, width=width, initial_indent=indent, subsequent_indent=indent)


# ── Commands ─────────────────────────────────────────────────────────────

def cmd_ask(args: argparse.Namespace) -> int:
    """Search the oracle's memory for an answer."""
    query = " ".join(args.question)
    if not query.strip():
        print("Usage: oracle ask \"your question here\"")
        return 1

    agent = _make_agent(args.db, args.user)
    start = time.time()
    results = agent.store.search_claims(
        user_id=agent.user_id, query=query, limit=args.limit or 5
    )
    elapsed = time.time() - start

    if not results:
        # Try public claims too
        results = agent.store.search_claims(
            user_id=agent.user_id, query=query, visibility="public", limit=args.limit or 5
        )

    print()
    if not results:
        print("  Oracle has no knowledge matching that query.")
        print(f"  Try: oracle remember \"<some fact>\" to teach it first.")
        print()
        return 0

    print(f"  Oracle says  ({len(results)} result{'s' if len(results) != 1 else ''}, {elapsed:.2f}s)")
    print(f"  {'─' * 60}")
    print()

    for i, claim in enumerate(results, 1):
        print(f"  {i}. {claim.content}")
        print(f"     Confidence: {_format_confidence(claim.confidence)}")
        meta_parts = [f"type={claim.memory_type}"]
        if claim.source_kind != "conversation":
            meta_parts.append(f"source={claim.source_kind}")
        if claim.title:
            meta_parts.append(f"title={claim.title}")
        print(f"     [{', '.join(meta_parts)}]")
        print()

    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Verify a claim against the oracle's knowledge base."""
    statement = " ".join(args.statement)
    if not statement.strip():
        print("Usage: oracle verify \"statement to check\"")
        return 1

    agent = _make_agent(args.db, args.user)

    # Search for related claims
    related = agent.store.search_claims(
        user_id=agent.user_id, query=statement, limit=10
    )

    print()
    print(f"  Verifying: \"{statement}\"")
    print(f"  {'─' * 60}")
    print()

    if not related:
        print("  Verdict: UNKNOWN")
        print("  No matching knowledge found in the oracle.")
        print()
        print("  The oracle has no data to confirm or deny this claim.")
        print(f"  Teach it: oracle remember \"{statement}\"")
        print()
        return 0

    # Score: how well does existing knowledge support this?
    supporting = []
    contradicting = []

    for claim in related:
        # Simple heuristic: if the claim content substantially overlaps
        # with the statement, it's supporting. If confidence is low, it's weak.
        stmt_words = set(statement.lower().split())
        claim_words = set(claim.content.lower().split())
        overlap = len(stmt_words & claim_words) / max(len(stmt_words | claim_words), 1)

        if overlap > 0.15:
            supporting.append((claim, overlap))
        else:
            contradicting.append((claim, overlap))

    # Calculate aggregate confidence
    if supporting:
        avg_conf = sum(c.confidence for c, _ in supporting) / len(supporting)
        avg_overlap = sum(o for _, o in supporting) / len(supporting)
        combined = (avg_conf * 0.6 + avg_overlap * 0.4)
    else:
        combined = 0.0

    if combined >= 0.6:
        verdict = "LIKELY TRUE"
    elif combined >= 0.3:
        verdict = "PLAUSIBLE"
    elif supporting:
        verdict = "WEAK SUPPORT"
    else:
        verdict = "UNVERIFIED"

    print(f"  Verdict: {verdict}")
    print(f"  Combined confidence: {_format_confidence(combined)}")
    print()

    if supporting:
        print(f"  Supporting evidence ({len(supporting)}):")
        for claim, overlap in supporting:
            print(f"    ✓ {claim.content}")
            print(f"      confidence={claim.confidence:.0%}  relevance={overlap:.0%}")
        print()

    if contradicting:
        print(f"  Weak/unrelated matches ({len(contradicting)}):")
        for claim, overlap in contradicting[:3]:
            print(f"    ? {claim.content}")
        print()

    return 0


def cmd_remember(args: argparse.Namespace) -> int:
    """Teach the oracle a new fact."""
    text = " ".join(args.text)
    if not text.strip():
        print("Usage: oracle remember \"fact to remember\"")
        return 1

    agent = _make_agent(args.db, args.user)
    visibility = "public" if args.public else "private"
    claims = agent.remember(text, visibility=visibility)

    print()
    print(f"  Oracle remembered {len(claims)} claim{'s' if len(claims) != 1 else ''}:")
    for claim in claims:
        print(f"    • {claim.content}")
        print(f"      [{claim.memory_type}, {claim.visibility}, confidence={claim.confidence:.0%}]")
    print()
    return 0


def cmd_forget(args: argparse.Namespace) -> int:
    """Remove claims matching a query."""
    query = " ".join(args.query)
    if not query.strip():
        print("Usage: oracle forget \"query to match\"")
        return 1

    agent = _make_agent(args.db, args.user)
    removed = agent.forget(query)

    print()
    if removed:
        print(f"  Removed {removed} claim{'s' if removed != 1 else ''}.")
    else:
        print("  No matching claims found to remove.")
    print()
    return 0


def cmd_trends(args: argparse.Namespace) -> int:
    """Show top claims and knowledge trends."""
    agent = _make_agent(args.db, args.user)

    # Get all claims
    all_claims = agent.store.list_claims(user_id=agent.user_id, limit=1000)

    print()
    if not all_claims:
        print("  Oracle is empty. Teach it something:")
        print("    oracle remember \"Python was created by Guido van Rossum in 1991\"")
        print("    oracle remember \"Flask is a micro web framework\"")
        print()
        return 0

    # Group by type
    by_type: dict[str, list[MemoryClaim]] = {}
    for claim in all_claims:
        by_type.setdefault(claim.memory_type, []).append(claim)

    # Sort each group by confidence
    for claims in by_type.values():
        claims.sort(key=lambda c: c.confidence, reverse=True)

    # Count sources  
    sources: dict[str, int] = {}
    for claim in all_claims:
        sources[claim.source_kind] = sources.get(claim.source_kind, 0) + 1

    print(f"  Oracle Knowledge Trends")
    print(f"  {'─' * 60}")
    print(f"  Total claims: {len(all_claims)}")
    print(f"  Categories:   {len(by_type)}")
    print(f"  Sources:      {', '.join(f'{k}({v})' for k, v in sorted(sources.items()))}")
    print()

    # Top claims per category
    for mtype, claims in sorted(by_type.items(), key=lambda x: -len(x[1])):
        high_conf = [c for c in claims if c.confidence >= 0.7]
        print(f"  {mtype.upper()} ({len(claims)} claims, {len(high_conf)} high-confidence)")
        for claim in claims[:3]:
            print(f"    {_confidence_bar(claim.confidence, 10)} {claim.confidence:.0%}  {claim.content[:70]}")
        if len(claims) > 3:
            print(f"    ... and {len(claims) - 3} more")
        print()

    # Most confident claims overall
    top = sorted(all_claims, key=lambda c: c.confidence, reverse=True)[:5]
    print(f"  Top verified claims:")
    for i, claim in enumerate(top, 1):
        print(f"    {i}. {claim.content[:70]}")
        print(f"       confidence: {_format_confidence(claim.confidence)}")
    print()

    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show oracle statistics."""
    agent = _make_agent(args.db, args.user)
    s = agent.stats

    # Count by visibility
    all_claims = agent.store.list_claims(user_id=agent.user_id, limit=10000)
    public = sum(1 for c in all_claims if c.visibility == "public")
    private = sum(1 for c in all_claims if c.visibility == "private")

    # Count by source
    sources: dict[str, int] = {}
    for claim in all_claims:
        sources[claim.source_kind] = sources.get(claim.source_kind, 0) + 1

    # Average confidence
    avg_conf = sum(c.confidence for c in all_claims) / len(all_claims) if all_claims else 0.0

    db = args.db or _db_path()
    db_size = ""
    if db != ":memory:" and Path(db).exists():
        size_bytes = Path(db).stat().st_size
        if size_bytes < 1024:
            db_size = f" ({size_bytes} B)"
        elif size_bytes < 1048576:
            db_size = f" ({size_bytes / 1024:.1f} KB)"
        else:
            db_size = f" ({size_bytes / 1048576:.1f} MB)"

    print()
    print(f"  Oracle Protocol v{CURRENT_VERSION}")
    print(f"  {'─' * 60}")
    print(f"  Database:    {db}{db_size}")
    print(f"  User:        {agent.user_id}")
    print(f"  Claims:      {s['total_claims']} total ({public} public, {private} private)")
    print(f"  Avg conf:    {_format_confidence(avg_conf)}")
    print(f"  Tokens:      {s['token_balance']:.1f}")
    print(f"  Sources:     {', '.join(f'{k}({v})' for k, v in sorted(sources.items())) or 'none'}")
    print()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export all claims as JSON."""
    agent = _make_agent(args.db, args.user)
    all_claims = agent.store.list_claims(user_id=agent.user_id, limit=100000)

    data = {
        "oracle_version": CURRENT_VERSION,
        "user_id": agent.user_id,
        "claim_count": len(all_claims),
        "claims": [
            {
                "claim_id": c.claim_id,
                "content": c.content,
                "memory_type": c.memory_type,
                "visibility": c.visibility,
                "confidence": c.confidence,
                "source_kind": c.source_kind,
                "source_ref": c.source_ref,
                "title": c.title,
                "created_at": str(c.created_at),
                "updated_at": str(c.updated_at),
            }
            for c in all_claims
        ],
    }

    output = json.dumps(data, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"  Exported {len(all_claims)} claims to {args.output}")
    else:
        print(output)

    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Run an interactive demo showing the oracle in action."""
    print()
    print(f"  Oracle Protocol v{CURRENT_VERSION} — Live Demo")
    print(f"  {'═' * 60}")
    print()

    # Use in-memory store for demo so we don't pollute user's DB
    store = InMemoryMemoryStore()
    agent = OracleAgent(name="demo-agent", user_id="demo", store=store)

    facts = [
        ("Python was created by Guido van Rossum in 1991", "public"),
        ("Flask is a micro web framework for Python", "public"),
        ("SQLite is a self-contained SQL database engine", "public"),
        ("The oracle protocol uses HMAC-SHA256 for message signing", "public"),
        ("AI agents forget everything between sessions without persistent memory", "public"),
        ("RAG gives agents retrieval but only locally", "public"),
        ("Federation allows knowledge to propagate across nodes", "public"),
        ("Trust scoring prevents bad data from spreading", "public"),
        ("I like building distributed systems", "private"),
        ("My goal is to create a shared knowledge network for AI", "private"),
    ]

    print("  Step 1: Teaching the oracle...")
    print()
    for text, vis in facts:
        agent.remember(text, visibility=vis)
        print(f"    + {text}")
    print()
    print(f"    → Stored {len(facts)} claims ({sum(1 for _, v in facts if v == 'public')} public, "
          f"{sum(1 for _, v in facts if v == 'private')} private)")
    print()

    queries = [
        "who created Python?",
        "what is Flask?",
        "how does oracle protocol work?",
        "what prevents bad data?",
    ]

    print("  Step 2: Querying the oracle...")
    print()
    for query in queries:
        results = agent.recall(query, limit=2)
        print(f"    Q: {query}")
        if results:
            for r in results:
                print(f"    A: {r}")
            agent.thumbs_up()
            print(f"    → 👍 Feedback recorded")
        else:
            print(f"    A: (no results)")
        print()

    s = agent.stats
    print("  Step 3: Oracle statistics")
    print()
    print(f"    Total claims:  {s['total_claims']}")
    print(f"    Token balance: {s['token_balance']:.1f}")
    print()
    print(f"  {'═' * 60}")
    print(f"  Demo complete. To use with persistent storage:")
    print()
    print(f"    oracle remember \"your fact here\"")
    print(f"    oracle ask \"your question\"")
    print(f"    oracle verify \"claim to check\"")
    print(f"    oracle trends")
    print()
    return 0


# ── Argument parser ──────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oracle",
        description="Oracle Protocol — ask, verify, and manage a confidence-scored knowledge base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              oracle ask "Who created Python?"
              oracle verify "Flask uses Jinja2"
              oracle remember "Python 3.12 added f-string improvements"
              oracle trends
              oracle demo
              oracle stats
              oracle export --output backup.json
        """),
    )
    parser.add_argument("--version", action="version", version=f"oracle-protocol {CURRENT_VERSION}")
    parser.add_argument("--db", default=None, help=f"SQLite database path (default: {_DEFAULT_DB})")
    parser.add_argument("--user", default=None, help=f"User ID (default: {_DEFAULT_USER})")

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # ask
    p_ask = sub.add_parser("ask", help="Ask the oracle a question")
    p_ask.add_argument("question", nargs="+", help="Your question")
    p_ask.add_argument("--limit", type=int, default=5, help="Max results")

    # verify
    p_verify = sub.add_parser("verify", help="Verify a claim against oracle knowledge")
    p_verify.add_argument("statement", nargs="+", help="Statement to verify")

    # remember
    p_remember = sub.add_parser("remember", help="Teach the oracle a new fact")
    p_remember.add_argument("text", nargs="+", help="Fact to remember")
    p_remember.add_argument("--public", action="store_true", help="Make claim public")

    # forget
    p_forget = sub.add_parser("forget", help="Remove claims matching a query")
    p_forget.add_argument("query", nargs="+", help="Query to match claims for removal")

    # trends
    sub.add_parser("trends", help="Show knowledge trends and top claims")

    # stats
    sub.add_parser("stats", help="Show oracle statistics")

    # export
    p_export = sub.add_parser("export", help="Export all claims as JSON")
    p_export.add_argument("--output", "-o", help="Output file (default: stdout)")

    # demo
    sub.add_parser("demo", help="Run an interactive demo")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "ask": cmd_ask,
        "verify": cmd_verify,
        "remember": cmd_remember,
        "forget": cmd_forget,
        "trends": cmd_trends,
        "stats": cmd_stats,
        "export": cmd_export,
        "demo": cmd_demo,
    }

    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        return 1

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
