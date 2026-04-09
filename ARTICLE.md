# A Shared Memory Layer for AI Agents

*22 modules. 125 tests. Zero dependencies. Now on PyPI.*

`oracle-memory` is an open-source Python library for persistent, shared AI agent memory. Agents remember facts across sessions, share knowledge across nodes through a federation protocol, and earn tokens for useful contributions.

```bash
pip install oracle-mempalace
```

**GitHub:** https://github.com/Jeffyjefchat/oracle-protocol
**PyPI:** https://pypi.org/project/oracle-mempalace/

---

## The problem

AI agents forget everything between sessions. RAG gives them retrieval — but only locally. If you run multiple agents, or work across machines, each one starts from scratch. There's no standard way for agents to share what they've learned with each other.

oracle-memory adds the missing layer: persistent memory that federates across nodes, with trust scoring so bad data doesn't propagate.

## Five lines to get started

```python
from oracle_memory import OracleAgent

agent = OracleAgent("my-agent")
agent.remember("Python was created by Guido van Rossum in 1991")
results = agent.recall("who created Python?")
agent.thumbs_up()
```

Five methods. One object. That's the interface.

## What's under the hood

22 modules handle the rest:

- **Memory** — Facts extracted from conversations, stored as claims. Private by default, optionally shared. Content-hashed to prevent duplicates.
- **Federation** — Nodes register with an orchestrator. Public claims sync via HMAC-signed protocol messages.
- **Trust & reputation** — Nodes earn reputation over time. Hallucination sources get penalized. Rate limiting prevents spam.
- **Token incentives** — Useful knowledge earns tokens. Bad contributions cost tokens. A leaderboard tracks contributors. No blockchain — the ledger is in the orchestrator.
- **Conflict resolution** — When nodes disagree, five strategies resolve it: confidence, reputation, recency, consensus, or manual review. Confirmations are detected separately from contradictions.
- **Settlement engine** — Sealed ledger boundary with verdict serialization. Winners earn tokens, losers pay.
- **Scaling** — Consistent hash ring for sharding. Backpressure control. TTL-based expiry.
- **Security** — Key rotation, replay protection, message expiry windows.
- **Framework adapters** — Drop-in integration with LangChain, LlamaIndex, and AutoGen.

## What makes it different

Most memory tools solve one piece. Mem0 extracts facts but doesn't federate. LangChain and LlamaIndex handle retrieval but not cross-node sharing. AutoGen and CrewAI coordinate agents but memory doesn't persist.

oracle-memory combines all of these — structured memory, federation protocol, token incentives, trust scoring, conflict resolution, quality tracking, and a standard claim schema — in one library with zero external dependencies. The README includes a comparison against 19 alternatives.

## Benchmark

```
Isolated (no sharing): 50% accuracy
Shared (oracle-memory): 100% accuracy
```

The shared agent answers questions correctly because the knowledge exists somewhere in the network — even if that specific node never saw it.

## Install

```bash
pip install oracle-mempalace
```

```python
from oracle_memory import OracleAgent

agent = OracleAgent("my-first-agent")
agent.remember("your knowledge here")
print(agent.recall("your query"))
print(agent.stats)
```

125 tests. Zero external dependencies. Python 3.9+.

## FAQ

**How is oracle-memory different from Mem0?**
Mem0 extracts and stores facts for a single user. oracle-memory does that too, but adds multi-node federation, token incentives, trust scoring, conflict resolution, and a standard claim schema so agents can share knowledge across a network.

**Does it require a database?**
No. The default store is in-memory. You can plug in any backend by implementing the MemoryStore interface.

**Can I use it with LangChain / LlamaIndex / AutoGen?**
Yes. Drop-in adapters are included for all three. One import and your existing agent has persistent shared memory.

## Links

- **PyPI:** https://pypi.org/project/oracle-mempalace/
- **Source:** https://github.com/Jeffyjefchat/oracle-protocol
- **Live demo:** https://gpt-mind.gcapay.club/

---

*oracle-memory is a collective knowledge sharing system for AI agents — persistent memory, federated knowledge exchange, and token-based incentives in a single Python package.*
