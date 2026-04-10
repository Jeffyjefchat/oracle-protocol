# Oracle Protocol

> Ask Oracle anything and get a confidence-scored answer.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-204%20passing-brightgreen)]()
[![PyPI](https://img.shields.io/pypi/v/oracle-mempalace)](https://pypi.org/project/oracle-mempalace/)

AI agents forget everything between sessions. RAG gives them retrieval — but only locally. If you run multiple agents, or work across machines, each one starts from scratch.

Oracle Protocol adds the missing layer: persistent memory that federates across nodes, with trust scoring so bad data doesn't propagate.

**27 modules. 204 tests. Zero required dependencies.**

## 10-second demo

```bash
pip install oracle-mempalace
oracle demo
```

```
Oracle Protocol v2.1.0 — Live Demo
═══════════════════════════════════
Step 1: Teaching the oracle...
  + Python was created by Guido van Rossum in 1991
  + Flask is a micro web framework for Python
  + Trust scoring prevents bad data from spreading
  → Stored 10 claims (8 public, 2 private)

Step 2: Querying the oracle...
  Q: who created Python?
  A: Python was created by Guido van Rossum in 1991
  → 👍 Feedback recorded

Step 3: Oracle statistics
  Total claims: 10
  Token balance: 10.0
```

## CLI

```bash
oracle ask "Who created Python?"
oracle verify "Flask uses Jinja2 templates"
oracle remember "Python 3.12 added f-string improvements"
oracle trends
oracle stats
oracle export --output backup.json
oracle forget "outdated fact"
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

  Verifying: "Python was created by Guido van Rossum"
  ────────────────────────────────
  Verdict: LIKELY TRUE
  Combined confidence: ████████████████░░░░ 78% (HIGH)

  Supporting evidence (1):
    ✓ Python was created by Guido van Rossum in 1991
      confidence=60%  relevance=83%
```

### oracle trends

```bash
$ oracle trends

  Oracle Knowledge Trends
  ────────────────────────────────
  Total claims: 38
  Categories:   5
  Sources:      conversation(12), document(26)

  EVENT (15 claims, 10 high-confidence)
    ██████████ 80%  AI agents forget everything...
    ████████░░ 60%  Federation allows knowledge...
  ...

  Top verified claims:
    1. HMAC-SHA256 is used for message signing
       confidence: ████████████████████ 95% (HIGH)
```

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

## Quick start (Python API)

```python
from oracle_memory import OracleAgent

agent = OracleAgent("my-agent")
agent.remember("Python was created by Guido van Rossum in 1991")
results = agent.recall("who created Python?")
agent.thumbs_up()
```

Five methods. One object. That's the interface: `remember()`, `recall()`, `forget()`, `thumbs_up()`, `thumbs_down()`.

### Persistent storage (v2)

```python
from oracle_memory import OracleAgent, SQLiteStore

store = SQLiteStore("memory.db")           # survives restarts
agent = OracleAgent("my-agent", store=store)
agent.remember("Python was created by Guido van Rossum in 1991")
# restart your app — the claim is still there
```

### GDPR compliance (v2)

```python
from oracle_memory import GDPRController, SQLiteStore

store = SQLiteStore("memory.db")
gdpr = GDPRController(store)
gdpr.record_consent("user-42", "memory_storage")
data = gdpr.export_user_data("user-42")   # Article 20 portability
gdpr.erase_user_data("user-42")            # Article 17 right to erasure
```

## What's under the hood

- **Memory** — Facts stored as claims. Private by default, optionally shared. Content-hashed to prevent duplicates.
- **Persistent storage (v2)** — SQLite-backed store. Claims survive restarts. WAL mode, thread-safe, zero dependencies.
- **Federation** — Nodes register with an orchestrator. Public claims sync via HMAC-signed protocol messages.
- **HTTP transport (v2)** — Network-ready federation over stdlib `urllib`. Client + server handler included.
- **Trust & reputation** — Nodes earn reputation over time. Hallucination sources get penalized. Sybil-resistant.
- **Token incentives** — Useful knowledge earns tokens. Bad contributions cost tokens. No blockchain — the ledger is in the orchestrator.
- **Conflict resolution** — When nodes disagree, five strategies resolve it: confidence, reputation, recency, consensus, or manual review. Confirmations detected separately from contradictions.
- **Settlement engine** — Sealed ledger boundary with verdict serialization. Winners earn, losers pay.
- **Quality auto-tuning** — Feedback-driven policy updates per node.
- **Scaling** — Consistent hash ring, backpressure, TTL-based expiry.
- **Security** — Key rotation, replay protection, message expiry windows.
- **GDPR compliance (v2)** — Consent management, data export (Art. 20), right to erasure (Art. 17), audit log.
- **CLI (v2.1)** — `oracle ask`, `oracle verify`, `oracle trends`, `oracle remember`, `oracle demo`. The user-facing product layer.
- **Framework adapters** — Drop-in for LangChain, LlamaIndex, AutoGen.

## Framework integrations

```python
from oracle_memory.integrations import LangChainMemory    # LangChain
from oracle_memory.integrations import LlamaIndexMemory    # LlamaIndex
from oracle_memory.integrations import AutoGenMemoryBackend # AutoGen
```

## Architecture

```
+-------------+      +-------------+      +-------------+
|   Node A    |      |   Node B    |      |   Node C    |
| (your app)  |      | (partner)   |      | (mobile)    |
|  Service    |      |  Service    |      |  Service    |
|  + Store    |      |  + Store    |      |  + Store    |
|  + Quality  |      |  + Quality  |      |  + Quality  |
+------+------+      +------+------+      +------+------+
       |                    |                     |
       +----------+---------+---------------------+
                  |
          +-------v--------+
          |  Orchestrator  |
          |  Federation    |
          |  Control Plane |
          |  Policy Engine |
          +----------------+
```

## Package layout

| Module | Purpose |
|--------|---------|
| `oracle_memory.cli` | **v2.1** — CLI: `oracle ask`, `verify`, `trends`, `demo` |
| `oracle_memory.easy` | **One-liner API** — `OracleAgent` with 5 methods |
| `oracle_memory.models` | Memory claims and palace coordinates |
| `oracle_memory.store` | Abstract store interface + in-memory impl |
| `oracle_memory.sqlite_store` | **v2** — SQLite persistent store (WAL, thread-safe) |
| `oracle_memory.service` | High-level orchestration for ingestion and retrieval |
| `oracle_memory.extractor` | Extraction rules for prompts and documents |
| `oracle_memory.protocol` | HMAC-signed wire protocol for node <-> orchestrator |
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
| `oracle_memory.http_transport` | **v2** — HTTP transport client + server handler |
| `oracle_memory.gdpr` | **v2** — GDPR compliance (consent, erasure, export, audit) |
| `oracle_memory.integrations` | Drop-in adapters for LangChain, LlamaIndex, AutoGen |

## Protocol

All node <-> orchestrator messages use `ProtocolMessage` with HMAC-SHA256 signing:

| Message type | Direction | Purpose |
|---|---|---|
| `register_node` | Node -> Orch | Join the federation |
| `heartbeat` | Node -> Orch | Keepalive + stats |
| `memory_claim` | Node -> Orch | Publish public claim |
| `retrieval_request` | Node -> Orch | Query public claims |
| `retrieval_response` | Orch -> Node | Return matching claims |
| `policy_update` | Orch -> Node | Push tuned retrieval policy |
| `quality_report` | Node -> Orch | Submit quality metrics |
| `conversation_feedback` | Node -> Orch | User feedback signal |
| `conflict_notice` | Orch -> Node | Conflicting claim alert |

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
| Conflict resolution | No | No | No | No | **Yes** |
| Quality auto-tuning | No | No | No | No | **Yes** |
| Standard claim format | No | No | No | No | **Yes** |
| Provenance tracking | No | No | No | No | **Yes** |
| CLI tool | No | No | No | No | **Yes** |

## What's new in v2.1.0

- **CLI** — `oracle ask`, `oracle verify`, `oracle remember`, `oracle trends`, `oracle stats`, `oracle export`, `oracle forget`, `oracle demo`. Confidence-scored answers from the command line. The user-facing product layer.
- **`__main__` support** — `python -m oracle_memory demo` works now.
- **`[project.scripts]` entry point** — `pip install oracle-mempalace` gives you the `oracle` command globally.
- **204 tests** — 35 new CLI tests, all passing with zero warnings.

## What's new in v2.0.0

- **SQLite persistent store** — Drop-in replacement for `InMemoryMemoryStore`. Claims survive restarts. WAL journal mode, thread-safe via thread-local connections, TF-IDF search, extended API (`delete_claim`, `delete_user_data`, `export_user_data`, `count_claims`).
- **HTTP transport** — Network-ready federation using stdlib `urllib`. Client class (`send`, `fetch_claims`, `register`, `heartbeat`, `publish_claim`) + server-side `handle_protocol_request()` with HMAC signature verification.
- **GDPR compliance** — `GDPRController` with consent management (Article 7), data export (Article 20), right to erasure (Article 17), and full audit log. Works with both in-memory and SQLite stores.
- **Deprecation fixes** — All `datetime.utcnow()` replaced with timezone-aware `datetime.now(timezone.utc)`.
- **169 tests** — 39 new tests for v2 features, all passing with zero warnings.

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

## FAQ

**Does it require a database?**
No. The default store is in-memory. For persistence, use `SQLiteStore("memory.db")` — no external database needed. You can also plug in any backend by implementing the `MemoryStore` interface.

**How is it different from Mem0?**
Mem0 extracts facts for a single user. Oracle Protocol adds federation, tokens, trust scoring, conflict resolution, and a standard schema so agents share knowledge across a network.

**Can I use it with LangChain / LlamaIndex / AutoGen?**
Yes. Drop-in adapters included. One import and your agent has persistent shared memory.

## Links

- **PyPI:** https://pypi.org/project/oracle-mempalace/
- **GitHub:** https://github.com/Jeffyjefchat/oracle-protocol
- **Live demo:** https://gpt-mind.gcapay.club/
- **Forum:** https://gpt-mind.gcapay.club/forum
- **Blog:** https://gpt-mind.gcapay.club/blog

---

*Oracle Protocol is a collective knowledge layer for AI agents — persistent memory, federated exchange, trust scoring, and token incentives in a single Python package.*
