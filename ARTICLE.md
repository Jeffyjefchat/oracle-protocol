# I Built a Social Trust Layer for AI Agents — So They Deliver Correct Information Instead of Hallucinating Alone

**TL;DR:** I built `oracle-memory`, a Python library that turns isolated AI agents into a self-correcting social network. Agents share verified knowledge, build reputation, and get penalized for bad information. The network converges toward correct answers. 22 modules, 122 tests, zero dependencies.

```bash
pip install oracle-mempalace
```

GitHub: https://github.com/Jeffyjefchat/collective-knowledge-global-sharing-token-network-mempalace
PyPI: https://pypi.org/project/oracle-mempalace/
Live demo: https://gpt-mind.gcapay.club/

---

## The Problem Every AI Developer Hits

AI agents guess alone and get things wrong. Ask three agents the same question — you might get three different wrong answers. Each one hallucinates independently because there's no feedback loop, no reputation, no consequence for bad answers.

You add RAG. Now the agent retrieves its own documents. But a hallucinating agent looks exactly the same as a reliable one. There's no trust layer. No way for agents to verify each other.

I looked for a library that treats agents as social participants — where reputation matters and correct knowledge spreads while bad knowledge gets filtered out. Here's what I found:

- **Mem0** — extracts facts, but single-user, no sharing
- **LangChain / LlamaIndex** — great RAG frameworks, but no multi-node federation
- **AutoGen / CrewAI** — multi-agent, but memory dies when the session ends
- **MemPalace** — structured local memory, but no networking
- **SingularityNET / Fetch.ai** — token economies for AI services, but not for memory
- **Ocean Protocol** — data marketplace, but not LLM memory

None of them make agents self-correct socially. None combine trust scoring + federation + token incentives + conflict resolution + a standard schema into a system where the network converges toward correct answers. So I built it.

## What oracle-memory Does

```python
from oracle_memory import OracleAgent

agent = OracleAgent("my-agent")
agent.remember("Python was created by Guido van Rossum in 1991")
results = agent.recall("who created Python?")
agent.thumbs_up()  # feedback improves future retrieval
```

That's the simple API. Under the hood, 22 modules handle:

**Memory:** Private + public claims per user. Facts are extracted, not raw conversations. Content-hashed for deduplication.

**Federation:** Agents register with an orchestrator. Verified claims sync across the network via HMAC-signed protocol messages. Nine message types cover registration, heartbeat, claims, retrieval, policy updates, quality reports, feedback, and conflict notices.

**Trust:** Every agent earns reputation. Agents that give correct information rise. Hallucination sources get penalized and deprioritized. Rate limiting prevents spam. Claims from untrusted agents get confidence-capped.

**Tokens:** Contributing useful knowledge earns tokens. Hallucinations cost tokens. A leaderboard tracks the best contributors. No blockchain required — the ledger runs in the orchestrator. You can wire it to a real token later.

**Conflict Resolution:** When two nodes disagree ("Python is best" vs "Rust is best"), five resolution strategies handle it: confidence wins, reputation wins, newer wins, consensus, or manual review.

**Scaling:** Consistent hash ring shards claims across nodes. Backpressure prevents floods. Claims have TTL and expire automatically.

**Security:** Key rotation, replay attack protection, message expiry windows. Not just HMAC baseline — production-grade transport security.

**Framework Integrations:** Drop-in adapters for LangChain, LlamaIndex, and AutoGen. One import, plug it in, your agent has persistent shared memory.

## The Benchmark

```
============================================================
BENCHMARK: Shared Memory vs Isolated RAG
============================================================
[Isolated (no sharing)] accuracy=50.0%
[Shared (oracle-memory)] accuracy=100.0%
Improvement: +100.0% accuracy
============================================================
```

When agents share verified knowledge through a trust network, they answer questions the isolated agent can't — because correct knowledge surfaces through reputation scoring, even when a specific agent never saw the original information.

## Who This Is For

- **AI developers** who want agents that deliver correct answers, not just recall their own documents
- **Teams running multiple agents** that should verify each other's knowledge instead of duplicating hallucinations
- **Anyone building social AI systems** where agents interact, build reputation, and self-correct
- **Projects using RAG** that want trust + cross-node knowledge sync
- **Researchers** studying federated AI memory, social LLM interactions, and token incentive design

## How It Compares to 19 Alternatives

I compared oracle-memory against MemPalace, Unibase, MemoryGr.id, OpenMined, Panini, LLM Wiki, SingularityNET, Fetch.ai, Ocean Protocol, Allora Network, Recall Network, LLMem, memX, Mem0, LangChain, LlamaIndex, AutoGen, CrewAI, KBLAM, Moltbook, OpenClaw, and NodeGoAI.

**None combine all layers:** structured memory + standard schema + federation protocol + token incentives + trust/reputation + conflict resolution + quality auto-tuning + provenance tracking + hallucination defense.

The full comparison table is in the [README](README.md).

## Try It

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

See it running live: https://gpt-mind.gcapay.club/

---

**Tags:** social LLM, social AI agents, agent trust, collective knowledge, LLM memory, token network, federated AI memory, persistent agent memory, shared memory graph, oracle-memory, Mem0 alternative, LangChain memory plugin, LlamaIndex memory, AutoGen memory backend, multi-agent memory, knowledge exchange protocol, decentralized AI memory, RAG federation, retrieval augmented generation, collective intelligence, social trust layer, self-correcting AI, anti-hallucination network, social LLM interactions, correct AI answers, reputation system, hallucination defense, conflict resolution, standard memory format, claim provenance
