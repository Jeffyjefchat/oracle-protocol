# Oracle Protocol

> A trust layer for AI agents — so they deliver correct information instead of hallucinating alone.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-125%20passing-brightgreen)]()
[![PyPI](https://img.shields.io/pypi/v/oracle-mempalace)](https://pypi.org/project/oracle-mempalace/)

Every LLM hallucinates independently. Oracle Protocol fixes that by treating AI agents as participants in a knowledge network — agents that give correct answers earn reputation and tokens, agents that hallucinate lose both. The network self-corrects toward accurate answers over time.

**What's inside:**
- **Federation** — agents share verified knowledge across nodes via HMAC-signed protocol messages
- **Trust & reputation** — good agents rise, bad agents get throttled (Sybil-resistant)
- **Token incentives** — useful contributions earn tokens, hallucinations cost tokens
- **Conflict resolution** — when agents disagree, the network resolves it (5 strategies)
- **Standard schema** — one universal claim format (`StandardClaim` v1.0) across all backends
- **Quality auto-tuning** — feedback-driven policy updates per node
- **Private-first** — raw conversations never leave the node

**22 modules. 125 tests. Zero required dependencies. One-liner API.**

## Install

```bash
# From PyPI
pip install oracle-mempalace

# For development
git clone https://github.com/Jeffyjefchat/oracle-protocol.git
cd oracle-protocol
pip install -e ".[dev]"
```

## Quick start (5 seconds)

```python
from oracle_memory import OracleAgent

agent = OracleAgent("my-agent")
agent.remember("Python was created by Guido van Rossum in 1991")
agent.remember("Flask is a lightweight WSGI web framework")

results = agent.recall("who created Python?")
print(results)  # ['Python was created by Guido van Rossum in 1991']

agent.thumbs_up()   # positive feedback → improves future retrieval
print(agent.stats)  # token balance, quality metrics, claim count
```

That's it. One object, five methods: `remember()`, `recall()`, `forget()`, `thumbs_up()`, `thumbs_down()`.

For framework integrations:

```python
# LangChain drop-in
from oracle_memory.integrations import LangChainMemory
memory = LangChainMemory(agent_name="my-chain")

# LlamaIndex drop-in
from oracle_memory.integrations import LlamaIndexMemory
memory = LlamaIndexMemory(agent_name="llama-agent")

# AutoGen drop-in
from oracle_memory.integrations import AutoGenMemoryBackend
backend = AutoGenMemoryBackend(agent_name="coder")
```

## Why this exists — the social LLM problem

Every LLM hallucinates alone. RAG gives an agent its own documents, but when that agent is wrong, nothing corrects it. There's no feedback loop. No reputation. No consequence for bad answers.

This library treats AI agents like participants in a social network:

- **Agents that give correct information earn reputation and tokens** — they get amplified
- **Agents that hallucinate lose reputation** — their confidence gets capped and their claims get deprioritized
- **When agents disagree, the network resolves it** — by confidence, reputation, consensus, recency, or manual review
- **Correct knowledge propagates; bad knowledge doesn't** — federation spreads verified facts, trust scoring blocks noise

The result: instead of each LLM independently guessing, the network self-corrects toward accurate answers over time.

| Feature | LLMem | memX | Mem0 | **Oracle Protocol** |
|---------|-------|------|------|---------------------|
| Per-user private memory | ✅ | ❌ | ✅ | ✅ |
| Public/general facts | ❌ | ❌ | ❌ | ✅ |
| Multi-node federation | ❌ | ✅ | ❌ | ✅ |
| Wire protocol (HMAC-signed) | ❌ | ❌ | ❌ | ✅ |
| Quality auto-tuning | ❌ | ❌ | ❌ | ✅ |
| Token incentive layer | ❌ | ❌ | ❌ | ✅ |
| Reputation + Sybil resistance | ❌ | ❌ | ❌ | ✅ |
| Conflict resolution | ❌ | ❌ | ❌ | ✅ |
| Standard memory format | ❌ | ❌ | ❌ | ✅ |
| Provenance tracking | ❌ | ❌ | ❌ | ✅ |
| Hallucination propagation defense | ❌ | ❌ | ❌ | ✅ |
| No raw conversation storage | ❌ | ✅ | ❌ | ✅ |

## Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Node A    │      │   Node B    │      │   Node C    │
│ (your app)  │      │ (partner)   │      │ (mobile)    │
│             │      │             │      │             │
│ ┌─────────┐ │      │ ┌─────────┐ │      │ ┌─────────┐ │
│ │ Service │ │      │ │ Service │ │      │ │ Service │ │
│ │ + Store │ │      │ │ + Store │ │      │ │ + Store │ │
│ │ +Quality│ │      │ │ +Quality│ │      │ │ +Quality│ │
│ └────┬────┘ │      │ └────┬────┘ │      │ └────┬────┘ │
│      │      │      │      │      │      │      │      │
└──────┼──────┘      └──────┼──────┘      └──────┼──────┘
       │                    │                     │
       └────────────┬───────┴─────────────────────┘
                    │
           ┌────────▼────────┐
           │  Orchestrator   │
           │  ┌────────────┐ │
           │  │ Federation │ │
           │  │  Registry  │ │
           │  ├────────────┤ │
           │  │  Control   │ │
           │  │   Plane    │ │
           │  ├────────────┤ │
           │  │  Policy    │ │
           │  │  Engine    │ │
           │  └────────────┘ │
           └─────────────────┘
```

## Package layout

| Module | Purpose |
|--------|---------|
| `oracle_memory.models` | Memory claims and palace coordinates |
| `oracle_memory.extractor` | Extraction rules for prompts and documents |
| `oracle_memory.store` | Abstract store interface + in-memory reference impl |
| `oracle_memory.service` | High-level orchestration for ingestion and retrieval |
| `oracle_memory.protocol` | HMAC-signed wire protocol for node ↔ orchestrator |
| `oracle_memory.control_plane` | Orchestrator, retrieval policies, auto-tuning |
| `oracle_memory.quality` | Quality event tracking and metric aggregation |
| `oracle_memory.federation` | Multi-node registry and public claim exchange |
| `oracle_memory.trust` | Reputation engine, Sybil resistance, provenance tracking |
| `oracle_memory.conflict` | Conflict detection and resolution between claims |
| `oracle_memory.schema` | Standard memory format — universal claim schema v1.0 |
| `oracle_memory.tokens` | Token incentive ledger — rewards, penalties, leaderboard |
| `oracle_memory.palace_adapter` | Optional adapter for external palace storage backends |
| `oracle_memory.easy` | **One-liner API** — `OracleAgent` with 5 methods |
| `oracle_memory.crypto` | Security hardening — key rotation, replay protection |
| `oracle_memory.scaling` | Consistent hash ring, backpressure, TTL, shard routing |
| `oracle_memory.benchmark` | Benchmark suite — shared vs isolated memory comparison |
| `oracle_memory.integrations` | Drop-in adapters for LangChain, LlamaIndex, AutoGen |

## Quick start

### Single-node (your app)

```python
from oracle_memory import OracleMemoryService, InMemoryMemoryStore

store = InMemoryMemoryStore()
service = OracleMemoryService(store=store, node_id="my-app")

# Ingest a conversation (extracts facts, never stores raw text)
service.ingest_conversation_text(
    user_id="user-1",
    text="I am building a Flask OAuth app and I prefer local models.",
    conversation_id="conv-42",
)

# Ingest a document
service.ingest_document_text(
    user_id="user-1",
    title="roadmap.txt",
    text="The project uses Flask, SQLite, and local-first memory.",
    visibility="public",
)

# Build context for an LLM prompt (respects retrieval policy)
context = service.build_context(user_id="user-1")
for line in context:
    print(line)

# Record user feedback to improve future retrieval
service.record_feedback(user_id="user-1", conversation_id="conv-42", positive=True)
```

### Multi-node with orchestrator

```python
from oracle_memory import (
    Orchestrator, FederationRegistry, FederationClient,
    OracleMemoryService, InMemoryMemoryStore,
)

# --- Orchestrator side ---
orch = Orchestrator(secret="shared-secret")
registry = FederationRegistry()

# --- Node side ---
client = FederationClient(node_id="node-a", secret="shared-secret")
store = InMemoryMemoryStore()
service = OracleMemoryService(store=store, node_id="node-a", federation=client)

# Register with orchestrator
reg_msg = client.build_register_message({"supports": ["text", "pdf"]})
node_record = orch.register_node("node-a", reg_msg.payload.get("capabilities"))

# Orchestrator pushes tuned policy to node
policy_msg = orch.push_policy_to_node("node-a", min_confidence=0.5)

# Node ingests and public claims queue for federation
service.ingest_conversation_text("user-1", "Python is great for prototyping.", "conv-1")

# Flush queued public claims to orchestrator
for msg in client.flush_pending():
    claim_data = msg.payload
    # ... send to orchestrator endpoint ...
```

### Quality auto-tuning loop

```python
# Node collects quality metrics and reports to orchestrator
metrics = service.get_quality_metrics()
report = orch.report_quality("node-a", "user-1", metrics)
# Orchestrator auto-tunes the node's retrieval policy based on metrics
```

## Protocol

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

## Core concepts

- **Claims** — normalized extracted facts (not raw text)
- **StandardClaim** — universal memory format (schema v1.0) compatible with Mem0, Memori, and custom backends
- **Visibility** — `private` (user-only) or `public` (shared general facts)
- **Palace coordinates** — `wing/hall/room` for organizing memory
- **Retrieval policy** — tunable parameters for how memory is ranked and mixed
- **Quality tracking** — hits, misses, hallucinations, corrections, satisfaction
- **Auto-tuning** — orchestrator adjusts policies based on quality signals
- **Reputation** — nodes earn trust; bad actors get throttled (Sybil resistance)
- **Provenance** — every claim tracks origin node, confirmations, disputes
- **Conflict resolution** — contradicting claims get detected and resolved
- **Tokens** — reward useful contributions, penalize hallucinations

## Benchmark: shared memory vs isolated RAG

```python
from oracle_memory.benchmark import run_benchmark
result = run_benchmark()
print(result.summary())
```

```
============================================================
BENCHMARK: Shared Memory vs Isolated RAG
============================================================
[Isolated (no sharing)] accuracy=50.0% avg_recall=0.05ms ingest=0.80ms (5/10 correct)
[Shared (oracle-memory)] accuracy=100.0% avg_recall=0.03ms ingest=0.60ms (10/10 correct)
Improvement: +100.0% accuracy
============================================================
```

## Security

```python
from oracle_memory import SecureTransport, ProtocolMessage

# Key rotation + replay protection in one object
transport = SecureTransport(initial_secret="my-secret-v1")

msg = ProtocolMessage(message_type="memory_claim", node_id="node-a")
transport.prepare(msg)        # signs with current key
assert transport.accept(msg)   # verifies signature + checks replay
assert not transport.accept(msg)  # replay rejected!

transport.rotate_key("my-secret-v2")  # old messages still verify
```

## Scaling

```python
from oracle_memory import ShardRouter

router = ShardRouter(replication_factor=3)
router.add_node("node-a")
router.add_node("node-b")
router.add_node("node-c")

info = router.register_claim("claim-123", ttl_seconds=86400)
print(info)  # {shard_nodes: ["node-b", "node-c", "node-a"], expires_at: ...}
```

## Roadmap

1. Real embeddings / vector retrieval (ChromaDB, pgvector)
2. HTTP transport for protocol messages
3. SQLite and Postgres store backends
4. Dashboard for quality metrics and token leaderboard
5. Bridge to crypto tokens (ERC-20 / Cosmos)
6. MCP (Model Context Protocol) transport adapter
7. Governance / voting mechanisms for claim disputes
8. GDPR compliance hooks (right to erasure, data export)
9. Streaming / real-time sync via WebSocket transport
10. Formal protocol specification (RFC-style)

## What problem this solves

Every AI assistant hallucinates independently. Ask three agents the same question and you might get three different wrong answers, because none of them have a way to verify, share, or correct knowledge socially.

This library is the social infrastructure that's missing. It makes LLM interactions self-correcting:

- One agent learns a fact → every agent in the network benefits
- An agent that consistently provides wrong answers → loses reputation, gets filtered out
- Two agents contradict each other → the system resolves it with evidence, not randomness

Here is the gap analysis and what we solve:

| Gap identified | Why it's hard | Our solution |
|---|---|---|
| 🧪 Memory quality unsolved | Hallucination propagation, conflicting truths | `quality.py` + `trust.py` — quality tracking auto-tunes policy; reputation caps confidence from untrusted nodes |
| 🔐 Privacy vs sharing conflict | Personal memory is sensitive | `private`/`public` visibility on every claim; private memory never leaves the node |
| 💸 Token incentives are tricky | Valuation, spam, Sybil resistance | `tokens.py` — reward accepted claims, penalize hallucinations; `trust.py` — rate limiting + reputation gating |
| ⚙️ No standard memory format | Different systems use different formats | `schema.py` — `StandardClaim` v1.0 with adapters from Mem0, semantic triples, and custom sources |
| 🌐 No shared memory graph | Each system is isolated | `federation.py` — nodes register, exchange public claims, query cross-node |
| 🤝 No trust/attribution layer | Who contributed what? | `trust.py` — `ClaimProvenance` tracks origin, confirmations, disputes, retrievals |
| ⚔️ Conflicting truths | Two nodes disagree | `conflict.py` — detect contradictions, resolve by confidence/reputation/consensus/recency |

This library is the **social layer between isolated LLMs and collective intelligence**.
It sits on top of any local memory store and adds:
- A wire protocol for agents to communicate like participants in a network
- A trust and reputation system so good agents rise and bad agents get filtered
- Token incentives that reward correct contributions and penalize hallucinations
- Federation so verified knowledge spreads — not noise
- Conflict resolution so disagreements get settled with evidence
- Private-first design: raw conversations never leave the node

### Who this is for

- Developers building **LLM-powered apps** that need agents to give correct answers
- Teams running **multiple AI agents** that should share verified knowledge, not duplicate hallucinations
- Anyone building **social AI systems** where agents interact, build reputation, and self-correct
- Projects that use **RAG or retrieval-augmented generation** and want cross-node trust + sync

## How it compares

| Project | What it does | What's missing |
|---------|-------------|----------------|
| [Unibase](https://unibase.io/) | Blockchain AI memory layer (UB token) | Web3-only; requires blockchain; no local-first option; no quality auto-tuning |
| [MemoryGr.id](https://memorygr.id/) | Open-source AI society memory | Individual + collective memory for agents; no token incentives, no wire protocol |
| [Distributed Knowledge (OpenMined)](https://openmined.org/) | Federated LLM network, Ollama-compatible | Privacy-focused federation; no structured memory schema, no reputation system |
| [Panini](https://arxiv.org/) | Structured Memory via GSW (question-answer networks) | Research concept; write-time compute for RAG; no sharing protocol or tokens |
| [LLM Wiki](https://github.com/) | Local LLM → auto-generated wiki | Document ingestion pipeline; single-user, no federation or incentives |
| [SingularityNET](https://singularitynet.io/) | Decentralized AI marketplace | Token economy for services, not memory |
| [Fetch.ai](https://fetch.ai/) | Autonomous agent framework | Agent infra, no shared memory layer |
| [Ocean Protocol](https://oceanprotocol.com/) | Data marketplace with tokens | Data sharing, not LLM memory |
| [Allora Network](https://allora.network/) | Collective intelligence via consensus | Scoring agent outputs; no persistent memory |
| [Recall Network](https://recall.network/) | Agent competition + ranking | Agent economy, not structured memory sync |
| [LLMem](https://llmem.com/) | Cross-LLM memory sync | "Dropbox for AI" — not tokenized, not a network |
| [memX](https://github.com/) | Multi-agent real-time shared memory | CRDT coordination, no knowledge economy |
| [Mem0](https://mem0.ai/) | Extracted facts for LLMs | Single-user, no federation, no tokens |
| [LangChain](https://langchain.com/) / [LlamaIndex](https://llamaindex.ai/) | RAG + persistent storage | Framework-level; no multi-node federation or incentives |
| [AutoGen](https://github.com/microsoft/autogen) / [CrewAI](https://crewai.com/) | Multi-agent toolkits | Shared memory within a run; no persistent cross-node network |
| [KBLAM](https://arxiv.org/) | Knowledge tokens injected into attention | Research paper; injects KV pairs, no sharing protocol |
| Moltbook / OpenClaw | Agent memory marketplace concept | Reddit-like social layer; not a structured memory protocol |
| [NodeGoAI](https://nodegoai.com/) | Distributed GPU compute | Infra layer only, no knowledge sharing |

**None of these** combine all layers:

| Layer | This lib | Others |
|-------|----------|--------|
| Local structured memory | ✅ Built-in + pluggable backends | Partial (Mem0) |
| Standard memory format | ✅ `StandardClaim` v1.0 | ❌ No shared schema |
| Federation protocol | ✅ HMAC-signed messages | ❌ No cross-node protocol |
| Token incentives | ✅ Reward/penalty ledger | ❌ Experimental at best |
| Trust + reputation | ✅ Sybil resistance, rate limiting | ❌ Not addressed |
| Conflict resolution | ✅ 5 strategies | ❌ Not addressed |
| Provenance tracking | ✅ Origin, confirmations, disputes | ❌ Not addressed |
| Hallucination defense | ✅ Confidence capped to reputation | ❌ Not addressed |
| Quality auto-tuning | ✅ Feedback-driven policy updates | ❌ Not addressed |

## Keywords

`social LLM` · `social AI agents` · `agent trust` · `agent reputation` ·
`collective knowledge` · `global sharing` · `token network` · `LLM memory` ·
`oracle protocol` · `federation protocol` · `shared memory graph` · `agent memory` ·
`decentralized AI memory` · `knowledge exchange` · `collective intelligence` ·
`AI orchestrator` · `quality auto-tuning` · `RAG` · `retrieval augmented generation` ·
`context sharing` · `private-first memory` · `multi-agent knowledge` ·
`distributed LLM memory` · `conversational AI memory` · `token incentive` ·
`Sybil resistance` · `hallucination defense` · `conflict resolution` ·
`claim provenance` · `reputation system` · `standard memory format` ·
`knowledge graph` · `Mem0 alternative` · `LLMem alternative` · `memX alternative` ·
`SingularityNET memory` · `Allora memory` · `Recall Network memory` ·
`shared intelligence` · `collective context field` · `memory fragments as assets` ·
`knowledge tokens` · `KBLAM` · `LangChain memory` · `LlamaIndex memory` ·
`AutoGen shared memory` · `CrewAI memory` · `multi-agent memory` ·
`persistent agent memory` · `knowledge marketplace` · `episodic memory LLM` ·
`continual learning` · `Moltbook` · `OpenClaw` · `vector database` ·
`P2P knowledge sharing` · `decentralized inference` · `agent swarm memory` ·
`MemOS` · `memory infrastructure` · `key rotation` · `replay protection` ·
`consistent hashing` · `backpressure` · `claim TTL` · `shard routing` ·
`LangChain plugin` · `LlamaIndex plugin` · `AutoGen memory backend` ·
`one-liner API` · `drop-in memory` · `benchmark suite` · `shared vs isolated` ·
`memory coordination layer` · `social trust layer` · `self-correcting AI` ·
`correct AI answers` · `anti-hallucination network` · `social LLM interactions`

## Links

- **PyPI:** https://pypi.org/project/oracle-mempalace/
- **GitHub:** https://github.com/Jeffyjefchat/oracle-protocol
- **Live demo & app:** https://gpt-mind.gcapay.club/
- **Developer forum:** https://gpt-mind.gcapay.club/forum
- **Blog:** https://gpt-mind.gcapay.club/blog
