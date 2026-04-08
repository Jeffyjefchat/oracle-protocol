# Oracle Memory Lib

A private-first extracted-memory library with a built-in coordination protocol.
Each user gets private memory. Extracted facts (not raw conversations) are the
default storage layer. Nodes federate through an orchestrator that auto-tunes
retrieval quality — your competitive edge over vanilla memory systems.

## Why this exists

| Feature | Vanilla MemPalace | Oracle Memory |
|---------|-------------------|---------------|
| Per-user private memory | ✅ | ✅ |
| Public/general facts | ❌ | ✅ |
| Multi-node federation | ❌ | ✅ |
| Wire protocol (HMAC-signed) | ❌ | ✅ |
| Quality-driven auto-tuning | ❌ | ✅ |
| Orchestrator control plane | ❌ | ✅ |
| No raw conversation storage | ❌ | ✅ |

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
| `oracle_memory.quality` | Quality event tracking an metric aggregation |
| `oracle_memory.federation` | Multi-node registry and public claim exchange |
| `oracle_memory.mempalace_adapter` | Adapter boundary for future MemPalace integration |

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
- **Visibility** — `private` (user-only) or `public` (shared general facts)
- **Palace coordinates** — `wing/hall/room` for organizing memory
- **Retrieval policy** — tunable parameters for how memory is ranked and mixed
- **Quality tracking** — hits, misses, hallucinations, corrections, satisfaction
- **Auto-tuning** — orchestrator adjusts policies based on quality signals

## Roadmap

1. Real embeddings / vector retrieval (ChromaDB, pgvector)
2. MemPalace adapter implementation
3. SQLite and Postgres store backends
4. HTTP transport for protocol messages
5. Conflict detection and claim invalidation
6. Dashboard for quality metrics visualization
