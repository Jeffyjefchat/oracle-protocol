"""Network statistics monitor for Collective Knowledge Global Sharing Token Network.

Aggregates metrics from all oracle-protocol subsystems into a single dashboard
view. Provides both a snapshot API and a simple HTTP handler for protected access.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .quality import QualityTracker
from .trust import ReputationEngine
from .tokens import TokenLedger
from .federation import FederationRegistry
from .scaling import ClaimTTL
from .conflict import ConflictDetector


@dataclass
class NetworkSnapshot:
    """Point-in-time snapshot of the entire oracle-protocol network."""
    timestamp: str
    # Claims
    total_claims: int = 0
    public_claims: int = 0
    private_claims: int = 0
    expired_claims: int = 0
    # Agents / Nodes
    total_nodes: int = 0
    alive_nodes: int = 0
    trusted_nodes: int = 0
    # Quality
    global_hit_rate: float = 0.0
    global_hallucination_rate: float = 0.0
    global_satisfaction: float = 0.0
    total_quality_events: int = 0
    # Tokens
    total_tokens_earned: float = 0.0
    total_tokens_penalized: float = 0.0
    net_token_supply: float = 0.0
    top_contributors: list[dict[str, Any]] = field(default_factory=list)
    # Federation
    federation_public_claims: int = 0
    federation_nodes: list[dict[str, Any]] = field(default_factory=list)
    # Conflicts
    total_conflicts: int = 0
    unresolved_conflicts: int = 0
    resolved_conflicts: int = 0
    # TTL
    ttl_default_days: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "claims": {
                "total": self.total_claims,
                "public": self.public_claims,
                "private": self.private_claims,
                "expired": self.expired_claims,
            },
            "nodes": {
                "total": self.total_nodes,
                "alive": self.alive_nodes,
                "trusted": self.trusted_nodes,
            },
            "quality": {
                "hit_rate": round(self.global_hit_rate, 4),
                "hallucination_rate": round(self.global_hallucination_rate, 4),
                "user_satisfaction": round(self.global_satisfaction, 4),
                "total_events": self.total_quality_events,
            },
            "tokens": {
                "total_earned": round(self.total_tokens_earned, 2),
                "total_penalized": round(self.total_tokens_penalized, 2),
                "net_supply": round(self.net_token_supply, 2),
                "top_contributors": self.top_contributors,
            },
            "federation": {
                "public_claims": self.federation_public_claims,
                "nodes": self.federation_nodes,
            },
            "conflicts": {
                "total": self.total_conflicts,
                "unresolved": self.unresolved_conflicts,
                "resolved": self.resolved_conflicts,
            },
            "ttl": {
                "default_days": round(self.ttl_default_days, 1),
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class NetworkMonitor:
    """Aggregates all oracle-protocol subsystems into a single stats view.

    Usage:
        monitor = NetworkMonitor(
            quality_tracker=qt,
            reputation_engine=rep,
            token_ledger=ledger,
            federation_registry=fed,
            conflict_detector=cd,
            claim_ttl=ttl,
        )
        snapshot = monitor.snapshot()
        print(snapshot.to_json())
    """

    def __init__(
        self,
        quality_tracker: QualityTracker | None = None,
        reputation_engine: ReputationEngine | None = None,
        token_ledger: TokenLedger | None = None,
        federation_registry: FederationRegistry | None = None,
        conflict_detector: ConflictDetector | None = None,
        claim_ttl: ClaimTTL | None = None,
    ) -> None:
        self._quality = quality_tracker
        self._reputation = reputation_engine
        self._tokens = token_ledger
        self._federation = federation_registry
        self._conflict = conflict_detector
        self._ttl = claim_ttl
        self._history: list[NetworkSnapshot] = []

    def snapshot(self) -> NetworkSnapshot:
        """Gather a point-in-time snapshot of all network metrics."""
        snap = NetworkSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Quality metrics
        if self._quality:
            metrics = self._quality.global_metrics()
            snap.global_hit_rate = metrics.get("retrieval_hit_rate", 0.0)
            snap.global_hallucination_rate = metrics.get("hallucination_rate", 0.0)
            snap.global_satisfaction = metrics.get("user_satisfaction", 0.0)
            snap.total_quality_events = metrics.get("total_events", 0)

        # Reputation / trust
        if self._reputation:
            all_nodes = list(self._reputation._node_rep.keys())
            snap.total_nodes = len(all_nodes)
            snap.trusted_nodes = sum(
                1 for nid in all_nodes
                if self._reputation.get_node_reputation(nid).is_trusted
            )
            # Count claims from provenance
            snap.total_claims = len(self._reputation._claim_prov)

        # Token economy
        if self._tokens:
            stats = self._tokens.network_stats()
            snap.total_tokens_earned = stats.get("total_earned", 0.0)
            snap.total_tokens_penalized = stats.get("total_penalized", 0.0)
            snap.net_token_supply = stats.get("net_supply", snap.total_tokens_earned + snap.total_tokens_penalized)
            if not snap.total_nodes:
                snap.total_nodes = stats.get("total_nodes", 0)
            # Top contributors
            board = self._tokens.leaderboard(limit=10)
            snap.top_contributors = [
                {
                    "node_id": b.node_id,
                    "balance": round(b.balance, 2),
                    "earned": round(b.total_earned, 2),
                    "penalized": round(b.total_penalized, 2),
                }
                for b in board
            ]

        # Federation
        if self._federation:
            alive = self._federation.alive_nodes()
            snap.alive_nodes = len(alive)
            snap.federation_nodes = [
                {
                    "node_id": n.node_id,
                    "endpoint": n.endpoint,
                    "public_claims": n.public_claim_count,
                    "reachable": n.is_reachable,
                }
                for n in alive
            ]
            # Count public claims across federation
            all_pub = self._federation.query_public_claims(keywords=[], limit=10000)
            snap.federation_public_claims = len(all_pub)
            snap.public_claims = len(all_pub)

        # Conflicts
        if self._conflict:
            all_conflicts = self._conflict.all_conflicts
            snap.total_conflicts = len(all_conflicts)
            snap.resolved_conflicts = sum(1 for c in all_conflicts if c.resolved)
            snap.unresolved_conflicts = snap.total_conflicts - snap.resolved_conflicts

        # TTL
        if self._ttl:
            snap.ttl_default_days = self._ttl.default_ttl_seconds / 86400.0
            expired = self._ttl.get_expired()
            snap.expired_claims = len(expired)

        self._history.append(snap)
        return snap

    @property
    def history(self) -> list[NetworkSnapshot]:
        """All previously taken snapshots (for trend analysis)."""
        return list(self._history)

    def trend(self, field: str, last_n: int = 20) -> list[dict[str, Any]]:
        """Return time-series data for a specific metric.

        field can be: 'total_claims', 'alive_nodes', 'global_hit_rate',
        'global_hallucination_rate', 'net_token_supply', etc.
        """
        points = []
        for snap in self._history[-last_n:]:
            value = getattr(snap, field, None)
            if value is not None:
                points.append({"timestamp": snap.timestamp, "value": value})
        return points


# ── Password-protected stats handler ────────────────────────────────────

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def check_monitor_auth(username: str, password: str,
                       expected_user: str, expected_pass_hash: str) -> bool:
    """Constant-time comparison of monitor credentials."""
    user_ok = hmac.compare_digest(username, expected_user)
    pass_ok = hmac.compare_digest(_hash_password(password), expected_pass_hash)
    return user_ok and pass_ok


def render_monitor_html(snapshot: NetworkSnapshot) -> str:
    """Render a self-contained HTML dashboard for network statistics."""
    d = snapshot.to_dict()
    contributors_rows = ""
    for c in d["tokens"]["top_contributors"][:10]:
        contributors_rows += (
            f'<tr><td>{c["node_id"]}</td><td>{c["balance"]}</td>'
            f'<td>{c["earned"]}</td><td>{c["penalized"]}</td></tr>'
        )
    fed_rows = ""
    for n in d["federation"]["nodes"]:
        status = "alive" if n["reachable"] else "offline"
        fed_rows += (
            f'<tr><td>{n["node_id"]}</td><td>{n["endpoint"]}</td>'
            f'<td>{n["public_claims"]}</td><td>{status}</td></tr>'
        )
    conflict_bar_resolved = d["conflicts"]["resolved"]
    conflict_bar_unresolved = d["conflicts"]["unresolved"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oracle Protocol Network Monitor</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 20px; }}
  h1 {{ color: #58a6ff; margin-bottom: 8px; font-size: 1.6em; }}
  .subtitle {{ color: #8b949e; margin-bottom: 24px; font-size: 0.9em; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }}
  .card h3 {{ color: #58a6ff; font-size: 0.85em; text-transform: uppercase; margin-bottom: 8px; }}
  .big-number {{ font-size: 2em; font-weight: 700; color: #f0f6fc; }}
  .label {{ font-size: 0.8em; color: #8b949e; margin-top: 4px; }}
  .quality-bar {{ height: 8px; border-radius: 4px; background: #21262d; margin-top: 6px; overflow: hidden; }}
  .quality-fill {{ height: 100%; border-radius: 4px; }}
  .fill-green {{ background: #3fb950; }}
  .fill-red {{ background: #f85149; }}
  .fill-blue {{ background: #58a6ff; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th {{ text-align: left; color: #8b949e; font-size: 0.75em; text-transform: uppercase;
       padding: 6px 8px; border-bottom: 1px solid #30363d; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #21262d; font-size: 0.9em; }}
  .section {{ margin-bottom: 24px; }}
  .section h2 {{ color: #c9d1d9; font-size: 1.1em; margin-bottom: 12px;
                 border-bottom: 1px solid #30363d; padding-bottom: 6px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.75em; font-weight: 600; }}
  .badge-green {{ background: #238636; color: #fff; }}
  .badge-red {{ background: #da3633; color: #fff; }}
  .badge-yellow {{ background: #9e6a03; color: #fff; }}
  .timestamp {{ color: #484f58; font-size: 0.75em; text-align: right; margin-top: 20px; }}
</style>
</head>
<body>
<h1>Collective Knowledge Network Monitor</h1>
<p class="subtitle">Oracle Protocol — Real-time network statistics</p>

<div class="grid">
  <div class="card">
    <h3>Total Claims</h3>
    <div class="big-number">{d['claims']['total']}</div>
    <div class="label">Public: {d['claims']['public']} &middot; Expired: {d['claims']['expired']}</div>
  </div>
  <div class="card">
    <h3>Active Nodes</h3>
    <div class="big-number">{d['nodes']['alive']}/{d['nodes']['total']}</div>
    <div class="label">Trusted: {d['nodes']['trusted']}</div>
  </div>
  <div class="card">
    <h3>Hit Rate</h3>
    <div class="big-number">{d['quality']['hit_rate']:.0%}</div>
    <div class="quality-bar"><div class="quality-fill fill-green" style="width:{d['quality']['hit_rate']*100:.0f}%"></div></div>
    <div class="label">{d['quality']['total_events']} events tracked</div>
  </div>
  <div class="card">
    <h3>Hallucination Rate</h3>
    <div class="big-number">{d['quality']['hallucination_rate']:.1%}</div>
    <div class="quality-bar"><div class="quality-fill fill-red" style="width:{d['quality']['hallucination_rate']*100:.0f}%"></div></div>
  </div>
  <div class="card">
    <h3>User Satisfaction</h3>
    <div class="big-number">{d['quality']['user_satisfaction']:.0%}</div>
    <div class="quality-bar"><div class="quality-fill fill-blue" style="width:{d['quality']['user_satisfaction']*100:.0f}%"></div></div>
  </div>
  <div class="card">
    <h3>Token Economy</h3>
    <div class="big-number">{d['tokens']['net_supply']:.1f}</div>
    <div class="label">Earned: {d['tokens']['total_earned']:.1f} &middot; Penalized: {d['tokens']['total_penalized']:.1f}</div>
  </div>
  <div class="card">
    <h3>Conflicts</h3>
    <div class="big-number">{d['conflicts']['total']}</div>
    <div class="label">
      <span class="badge badge-green">{conflict_bar_resolved} resolved</span>
      <span class="badge badge-red">{conflict_bar_unresolved} open</span>
    </div>
  </div>
  <div class="card">
    <h3>Claim TTL</h3>
    <div class="big-number">{d['ttl']['default_days']:.0f}d</div>
    <div class="label">Expired: {d['claims']['expired']}</div>
  </div>
</div>

<div class="section">
  <h2>Top Contributors</h2>
  <table>
    <tr><th>Node</th><th>Balance</th><th>Earned</th><th>Penalized</th></tr>
    {contributors_rows if contributors_rows else '<tr><td colspan="4" style="color:#484f58">No contributors yet</td></tr>'}
  </table>
</div>

<div class="section">
  <h2>Federation Nodes</h2>
  <table>
    <tr><th>Node</th><th>Endpoint</th><th>Public Claims</th><th>Status</th></tr>
    {fed_rows if fed_rows else '<tr><td colspan="4" style="color:#484f58">No federation nodes registered</td></tr>'}
  </table>
</div>

<div class="timestamp">Snapshot: {d['timestamp']}</div>
</body>
</html>"""
