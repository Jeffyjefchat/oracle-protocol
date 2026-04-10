# Oracle Protocol

> **Your agents disagree. Oracle Protocol decides who's right — and makes it count.**

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-204%20passing-brightgreen)]()
[![PyPI](https://img.shields.io/pypi/v/oracle-mempalace)](https://pypi.org/project/oracle-mempalace/)

Most AI systems give answers.
Oracle Protocol lets **multiple agents challenge each other**,
resolve conflicts, and **apply real consequences**.

---

## ⚖️ What it does

- Detects contradictions between agents
- Resolves disputes using structured logic
- Produces a **verdict** (who's right, who's wrong)
- Applies consequences:
  - ✅ Correct agents gain tokens + reputation
  - ❌ Incorrect agents lose trust

---

## 🔁 The core flow

```
claim → conflict → verdict → finalize → settle
```

This is not just scoring.
This is a **system for resolving truth between agents**.

---

## 🧩 How it works

```
Agent A ── claims ──┐
                    │
Agent B ── disputes ─┼──→  Conflict Detector
                    │
Agent C ── claims ──┘
                    ↓
             Resolution Engine
              (5 strategies)
                    ↓
                 Verdict
            (who is correct)
                    ↓
              Finalization
          (inspectable, vetable)
                    ↓
               Settlement
          (tokens + reputation)
```

---

## ⚡ Example

```python
agent_a: "BTC is $70,000"   (confidence: 80%, reputation: 45%)
agent_b: "BTC is $65,000"   (confidence: 60%, reputation: 30%)

# conflict detected automatically
# system resolves using reputation + confidence

→ agent_a wins
→ +5 tokens, reputation increases

→ agent_b loses
→ reputation decreases

# Correct agents are reinforced.
# Incorrect agents lose trust.
# Over time, the system learns who to believe.
```

---

## 🎮 Multi-Agent Conflict Demo

```bash
pip install oracle-mempalace
python -m oracle_memory.demo_conflict
```

What happens:

- 3 agents submit conflicting claims
- 3 contradictions are detected
- Verdicts are proposed and finalized (two-phase)
- Tokens and reputation are updated

Example outcome:

```
verified-source:  +5.0 tokens   reputation 90% → 94%  ⭐ premium
research-lab:     -1.0 tokens   reputation 60% → 57%
news-bot:         -1.0 tokens   reputation 30% → 27%  ❌ untrusted
```

This shows the full system in action.

---

## 🧠 When should you use this?

Use Oracle Protocol when:

- Multiple AI agents **disagree on facts**
- You need a system to **decide what is correct**
- You want **trust to evolve over time**
- You're building **multi-agent systems**
- You need **automatic validation of AI outputs**

Instead of trusting one model, you let agents **compete and converge on truth**.

---

## 🚀 Quick start

```python
from oracle_memory import OracleAgent

agent = OracleAgent("my-agent")
agent.remember("Python was created by Guido van Rossum in 1991")
results = agent.recall("who created Python?")
agent.thumbs_up()
```

Five methods. One object: `remember()`, `recall()`, `forget()`, `thumbs_up()`, `thumbs_down()`.

## Install

```bash
pip install oracle-mempalace
```

```bash
# For development
git clone https://github.com/Jeffyjefchat/oracle-protocol.git
cd oracle-protocol
pip install -e ".[dev]"
```

## CLI

```bash
oracle ask "Who created Python?"       # confidence-scored answers
oracle verify "Flask uses Jinja2"      # cross-reference against known claims
oracle remember "new fact"             # ingest a claim
oracle trends                          # knowledge distribution overview
oracle stats                           # oracle health metrics
oracle export --output backup.json     # portable JSON export
oracle forget "outdated fact"          # remove a claim
oracle demo                            # interactive walkthrough
```

### oracle ask

```bash
$ oracle ask "who created Python?"

  Oracle says  (2 results, 0.01s)
  ────────────────────────────────
  1. Python was created by Guido van Rossum in 1991
     Confidence: ████████████░░░░░░░░ 60% (MEDIUM)

  2. Flask is a micro web framework for Python
     Confidence: ████████████░░░░░░░░ 60% (MEDIUM)
```

### oracle verify

```bash
$ oracle verify "Python was created by Guido van Rossum"

  Verdict: LIKELY TRUE
  Combined confidence: ████████████████░░░░ 78% (HIGH)

  Supporting evidence (1):
    ✓ Python was created by Guido van Rossum in 1991
      confidence=60%  relevance=83%
```

## The conflict resolution pipeline (deep dive)

Every other feature exists to support this flow.

```
┌──────────────┐     ┌───────────────────┐     ┌──────────────────┐
│  Agents      │     │  ConflictDetector  │     │ ConflictResolver │
│  submit      │────>│  finds conflicts   │────>│ picks winner     │
│  claims      │     │  (overlap/contra.) │     │ (5 strategies)   │
└──────────────┘     └───────────────────┘     └────────┬─────────┘
                                                        │
                     ┌───────────────────┐              │
                     │  Consequences     │     ┌────────v─────────┐
                     │  tokens settled   │<────│ SettlementEngine │
                     │  reputation moved │     │ propose → finalize│
                     │  verdict is final │     │ (two-phase, hooks)│
                     └───────────────────┘     └──────────────────┘
```

**Resolution strategies:** `CONFIDENCE_WINS` · `REPUTATION_WINS` · `NEWER_WINS` · `CONSENSUS` · `MANUAL`

**Two-phase verdicts:** `propose_verdict()` returns a pending verdict you can inspect and veto. `finalize_verdict()` makes it irreversible and settles tokens + reputation. Or use `settle_conflict()` for one-shot mode.

**Pre/post hooks:** Register callbacks that can veto verdicts before finalization or react after settlement.

```python
from oracle_memory import (
    ConflictDetector, ConflictResolver, SettlementEngine,
    ResolutionStrategy, TokenLedger, ReputationEngine, QualityTracker,
)

detector = ConflictDetector()
resolver = ConflictResolver(default_strategy=ResolutionStrategy.REPUTATION_WINS)
engine = SettlementEngine(resolver=resolver, ledger=TokenLedger(),
                          reputation=ReputationEngine(), quality=QualityTracker())

# Detect
conflict = detector.check_pair(claim_a, claim_b)

# Two-phase resolve
verdict = engine.propose_verdict(conflict, claim_a, claim_b, "node-a", "node-b", 0.6, 0.9)
# inspect verdict, run business logic, optionally veto...
engine.finalize_verdict(verdict)  # tokens and reputation are settled
```

## Persistent storage

```python
from oracle_memory import OracleAgent, SQLiteStore

store = SQLiteStore("memory.db")           # survives restarts
agent = OracleAgent("my-agent", store=store)
agent.remember("Python was created by Guido van Rossum in 1991")
# restart your app — the claim is still there
```

## GDPR compliance

```python
from oracle_memory import GDPRController, SQLiteStore

store = SQLiteStore("memory.db")
gdpr = GDPRController(store)
gdpr.record_consent("user-42", "memory_storage")
data = gdpr.export_user_data("user-42")   # Article 20 portability
gdpr.erase_user_data("user-42")            # Article 17 right to erasure
```

## Federation

Nodes register with an orchestrator. Public claims sync via HMAC-signed protocol messages. Knowledge spreads across the network — but only if the source is trusted.

```
+-------------+      +-------------+      +-------------+
|   Node A    |      |   Node B    |      |   Node C    |
| (your app)  |      | (partner)   |      | (mobile)    |
|  Service    |      |  Service    |      |  Service    |
|  + Store    |      |  + Store    |      |  + Store    |
+------+------+      +------+------+      +------+------+
       |                    |                     |
       +----------+---------+---------------------+
                  |
          +-------v--------+
          |  Orchestrator  |
          |  Federation    |
          |  Settlement    |
          |  Token Ledger  |
          +----------------+
```

## Framework integrations

```python
from oracle_memory.integrations import LangChainMemory    # LangChain
from oracle_memory.integrations import LlamaIndexMemory    # LlamaIndex
from oracle_memory.integrations import AutoGenMemoryBackend # AutoGen
```

## What's under the hood

| Layer | What it does |
|-------|-------------|
| **Memory & storage** | Claims stored with confidence scoring. SQLite (WAL, thread-safe) or in-memory. Content-hashed deduplication. |
| **Federation & protocol** | Multi-node sync via HMAC-SHA256 signed messages. HTTP transport included. |
| **Trust & reputation** | Nodes earn reputation over time. Hallucination sources get penalized. Sybil-resistant. |
| **Token incentives** | Useful knowledge earns tokens. Bad contributions cost tokens. No blockchain — pure accounting. |
| **Conflict resolution** | 5 strategies. Confirmations detected separately from contradictions. |
| **Settlement engine** | Two-phase verdicts (propose → finalize). Pre/post hooks. Sealed ledger boundary. |
| **Quality auto-tuning** | Feedback-driven policy updates per node. |
| **Scaling** | Consistent hash ring, backpressure, TTL-based expiry, shard routing. |
| **Security** | Key rotation, replay protection, message expiry windows. |
| **GDPR** | Consent management, data export (Art. 20), right to erasure (Art. 17), audit log. |
| **CLI** | `oracle ask`, `verify`, `trends`, `remember`, `demo` — the product layer. |

## Package layout (28 modules)

| Module | Purpose |
|--------|---------|
| `oracle_memory.easy` | **One-liner API** — `OracleAgent` with 5 methods |
| `oracle_memory.cli` | CLI: `oracle ask`, `verify`, `trends`, `demo` |
| `oracle_memory.demo_conflict` | **v2.2** — Multi-agent conflict resolution demo |
| `oracle_memory.models` | Memory claims and palace coordinates |
| `oracle_memory.store` | Abstract store interface + in-memory impl |
| `oracle_memory.sqlite_store` | SQLite persistent store (WAL, thread-safe) |
| `oracle_memory.service` | High-level orchestration for ingestion and retrieval |
| `oracle_memory.extractor` | Extraction rules for prompts and documents |
| `oracle_memory.protocol` | HMAC-signed wire protocol for node ↔ orchestrator |
| `oracle_memory.control_plane` | Orchestrator, retrieval policies, auto-tuning |
| `oracle_memory.quality` | Quality event tracking and metric aggregation |
| `oracle_memory.federation` | Multi-node registry and public claim exchange |
| `oracle_memory.trust` | Reputation engine, Sybil resistance, provenance |
| `oracle_memory.conflict` | Conflict detection + resolution (5 strategies) |
| `oracle_memory.settlement` | Verdict engine with sealed ledger boundary |
| `oracle_memory.schema` | Standard memory format — `StandardClaim` v1.0 |
| `oracle_memory.tokens` | Token incentive ledger — rewards, penalties, leaderboard |
| `oracle_memory.palace_adapter` | Optional adapter for external storage backends |
| `oracle_memory.crypto` | Key rotation, replay protection |
| `oracle_memory.scaling` | Hash ring, backpressure, TTL, shard routing |
| `oracle_memory.monitor` | Network statistics dashboard |
| `oracle_memory.benchmark` | Benchmark suite — shared vs isolated comparison |
| `oracle_memory.http_transport` | HTTP transport client + server handler |
| `oracle_memory.gdpr` | GDPR compliance (consent, erasure, export, audit) |
| `oracle_memory.integrations` | Drop-in adapters for LangChain, LlamaIndex, AutoGen |

## Protocol messages

All node ↔ orchestrator messages use `ProtocolMessage` with HMAC-SHA256 signing:

| Message type | Direction | Purpose |
|---|---|---|
| `register_node` | Node → Orch | Join the federation |
| `heartbeat` | Node → Orch | Keepalive + stats |
| `memory_claim` | Node → Orch | Publish public claim |
| `retrieval_request` | Node → Orch | Query public claims |
| `retrieval_response` | Orch → Node | Return matching claims |
| `policy_update` | Orch → Node | Push tuned retrieval policy |
| `quality_report` | Node → Orch | Submit quality metrics |
| `conversation_feedback` | Node → Orch | User feedback signal |
| `conflict_notice` | Orch → Node | Conflicting claim alert |

## Benchmark

```
Isolated (no sharing): 50% accuracy  (5/10 correct)
Shared (oracle-memory): 100% accuracy (10/10 correct)
```

The shared agent answers correctly because knowledge exists somewhere in the network — even if that specific node never saw it.

## Security

```python
from oracle_memory import SecureTransport, ProtocolMessage

transport = SecureTransport(initial_secret="my-secret-v1")
msg = ProtocolMessage(message_type="memory_claim", node_id="node-a")
transport.prepare(msg)         # signs with current key
assert transport.accept(msg)    # verifies + checks replay
assert not transport.accept(msg) # replay rejected
transport.rotate_key("my-secret-v2")  # old messages still verify
```

## How it compares

| Feature | Mem0 | LLMem | memX | LangChain | **Oracle Protocol** |
|---------|------|-------|------|-----------|---------------------|
| Private memory | Yes | Yes | No | Yes | Yes |
| Public shared facts | No | No | No | No | **Yes** |
| Multi-node federation | No | No | Yes | No | **Yes** |
| Wire protocol (HMAC) | No | No | No | No | **Yes** |
| Token incentives | No | No | No | No | **Yes** |
| Reputation + Sybil resistance | No | No | No | No | **Yes** |
| **Conflict resolution + verdicts** | No | No | No | No | **Yes** |
| **Two-phase settlement** | No | No | No | No | **Yes** |
| Quality auto-tuning | No | No | No | No | **Yes** |
| Provenance tracking | No | No | No | No | **Yes** |
| CLI tool | No | No | No | No | **Yes** |
| GDPR compliance | No | No | No | No | **Yes** |

## What's new in v2.2.0

- **Multi-agent conflict demo** — `python -m oracle_memory.demo_conflict`. Three agents disagree, the protocol resolves it live. Shows the full pipeline: detection → two-phase verdict → token/reputation settlement.
- **README rewrite** — Leads with the killer feature (conflict resolution with consequences), not generic memory.

## What's new in v2.1.0

- **CLI** — `oracle ask`, `oracle verify`, `oracle remember`, `oracle trends`, `oracle stats`, `oracle export`, `oracle forget`, `oracle demo`. The user-facing product layer.
- **`__main__` support** — `python -m oracle_memory demo` works.
- **`[project.scripts]` entry point** — `pip install oracle-mempalace` gives you the `oracle` command globally.
- **204 tests** — 35 new CLI tests, all passing with zero warnings.

## What's new in v2.0.0

- **SQLite persistent store** — WAL journal mode, thread-safe, TF-IDF search.
- **HTTP transport** — Network-ready federation using stdlib `urllib`.
- **GDPR compliance** — Consent management, data export, right to erasure, audit log.
- **169 tests** — 39 new tests for v2 features.

## Roadmap

1. Real embeddings / vector retrieval (ChromaDB, pgvector)
2. ~~SQLite store backend~~ ✅ v2.0.0
3. ~~HTTP transport for protocol messages~~ ✅ v2.0.0
4. Dashboard for quality metrics and token leaderboard
5. MCP (Model Context Protocol) transport adapter
6. Bridge to crypto tokens (ERC-20 / Cosmos)
7. Governance / voting for claim disputes
8. ~~GDPR compliance hooks~~ ✅ v2.0.0
9. WebSocket real-time sync
10. Formal protocol specification (RFC-style)
11. Postgres store backend
12. ~~Multi-agent conflict demo~~ ✅ v2.2.0

## FAQ

**What makes this different from Mem0 / LangChain memory?**
Those systems store facts for a single user. Oracle Protocol lets multiple agents **challenge each other's claims** and automatically determines who is right — with token and reputation consequences. It's a protocol, not just storage.

**Does it require a database?**
No. The default store is in-memory. For persistence, use `SQLiteStore("memory.db")` — no external database needed.

**Can I use it with LangChain / LlamaIndex / AutoGen?**
Yes. Drop-in adapters included. One import and your agent has persistent shared memory with conflict resolution.

**How does conflict resolution work?**
When two claims contradict, `ConflictDetector` flags it. `ConflictResolver` picks a winner using one of 5 strategies. `SettlementEngine` proposes a verdict (inspectable, vetable), then finalizes it — settling tokens and reputation. The verdict is a portable JSON object.

## Links

- **PyPI:** https://pypi.org/project/oracle-mempalace/
- **GitHub:** https://github.com/Jeffyjefchat/oracle-protocol
- **Live demo:** https://gpt-mind.gcapay.club/
- **Forum:** https://gpt-mind.gcapay.club/forum
- **Blog:** https://gpt-mind.gcapay.club/blog

---

## 🧠 What this is

Oracle Protocol is not just an AI tool.
It's a **truth resolution layer for multi-agent systems**.

**28 modules. 204+ tests. Zero required dependencies.**

*Claims are challenged. Verdicts are rendered. Truth has consequences.*
