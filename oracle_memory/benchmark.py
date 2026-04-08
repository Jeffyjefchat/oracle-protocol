"""
Benchmark suite — prove shared memory > isolated RAG.

GPT's VC critique: "Proof that shared memory > isolated RAG."
This module provides a reproducible benchmark harness.

Usage:
    from oracle_memory.benchmark import run_benchmark
    results = run_benchmark()
    print(results.summary())
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .easy import OracleAgent
from .store import InMemoryMemoryStore


# ── Test knowledge corpus ──

KNOWLEDGE_CORPUS = [
    "Python was created by Guido van Rossum in 1991",
    "The capital of Norway is Oslo",
    "Flask is a lightweight WSGI web framework in Python",
    "SQLAlchemy is the Python SQL toolkit and ORM",
    "Docker containers share the host OS kernel",
    "Kubernetes orchestrates container deployments",
    "Redis is an in-memory data structure store",
    "PostgreSQL supports JSONB for document storage",
    "OAuth 2.0 is an authorization framework, not authentication",
    "HMAC uses a secret key for message authentication",
    "Git was created by Linus Torvalds in 2005",
    "REST APIs should be stateless",
    "WebSocket enables full-duplex communication",
    "TLS 1.3 removed RSA key exchange",
    "Consistent hashing distributes data evenly across nodes",
    "The CAP theorem states you can have at most 2 of 3: consistency, availability, partition tolerance",
    "Bloom filters test set membership with possible false positives",
    "B-trees are optimized for systems that read and write large blocks of data",
    "HTTP/2 uses multiplexing to send multiple requests over one connection",
    "JSON Web Tokens encode claims as a JSON object signed with HMAC or RSA",
]

QUERIES = [
    ("who created Python?", "Guido van Rossum"),
    ("capital of Norway", "Oslo"),
    ("what is Flask?", "web framework"),
    ("SQL toolkit for Python", "SQLAlchemy"),
    ("container orchestration", "Kubernetes"),
    ("in-memory data store", "Redis"),
    ("authorization framework", "OAuth"),
    ("message authentication", "HMAC"),
    ("who created git?", "Linus Torvalds"),
    ("set membership test", "Bloom filter"),
]


@dataclass
class BenchmarkResult:
    """Results from a single benchmark run."""
    name: str
    total_queries: int = 0
    correct_recalls: int = 0
    total_recall_time_ms: float = 0.0
    total_ingest_time_ms: float = 0.0
    details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct_recalls / self.total_queries if self.total_queries else 0.0

    @property
    def avg_recall_ms(self) -> float:
        return self.total_recall_time_ms / self.total_queries if self.total_queries else 0.0

    def summary(self) -> str:
        return (
            f"[{self.name}] accuracy={self.accuracy:.1%} "
            f"avg_recall={self.avg_recall_ms:.2f}ms "
            f"ingest={self.total_ingest_time_ms:.2f}ms "
            f"({self.correct_recalls}/{self.total_queries} correct)"
        )


@dataclass
class ComparisonResult:
    """Side-by-side benchmark comparison."""
    isolated: BenchmarkResult
    shared: BenchmarkResult
    improvement_pct: float = 0.0

    def __post_init__(self) -> None:
        if self.isolated.accuracy > 0:
            self.improvement_pct = (
                (self.shared.accuracy - self.isolated.accuracy)
                / self.isolated.accuracy * 100
            )

    def summary(self) -> str:
        lines = [
            "=" * 60,
            "BENCHMARK: Shared Memory vs Isolated RAG",
            "=" * 60,
            self.isolated.summary(),
            self.shared.summary(),
            f"Improvement: {self.improvement_pct:+.1f}% accuracy",
            "=" * 60,
        ]
        return "\n".join(lines)


def _bench_isolated(corpus: list[str], queries: list[tuple[str, str]]) -> BenchmarkResult:
    """Benchmark: each agent has ONLY its own knowledge (no sharing)."""
    result = BenchmarkResult(name="Isolated (no sharing)")

    # Agent A knows first half, Agent B knows second half
    mid = len(corpus) // 2
    agent_a = OracleAgent("agent-a", user_id="a")
    agent_b = OracleAgent("agent-b", user_id="b")

    t0 = time.perf_counter()
    for fact in corpus[:mid]:
        agent_a.remember(fact)
    for fact in corpus[mid:]:
        agent_b.remember(fact)
    ingest_ms = (time.perf_counter() - t0) * 1000

    result.total_ingest_time_ms = ingest_ms
    result.total_queries = len(queries)

    for query, expected in queries:
        t0 = time.perf_counter()
        # Each agent can only search its own memory
        results_a = agent_a.recall(query)
        results_b = agent_b.recall(query)
        recall_ms = (time.perf_counter() - t0) * 1000
        result.total_recall_time_ms += recall_ms

        combined = " ".join(results_a + results_b).lower()
        hit = expected.lower() in combined
        if hit:
            result.correct_recalls += 1
        result.details.append({
            "query": query, "expected": expected,
            "hit": hit, "recall_ms": recall_ms,
        })

    return result


def _bench_shared(corpus: list[str], queries: list[tuple[str, str]]) -> BenchmarkResult:
    """Benchmark: agents share a common memory store (federation simulated)."""
    result = BenchmarkResult(name="Shared (oracle-memory)")

    # Both agents share the same store
    shared_store = InMemoryMemoryStore()
    agent_a = OracleAgent("agent-a", user_id="shared", store=shared_store)
    agent_b = OracleAgent("agent-b", user_id="shared", store=shared_store)

    mid = len(corpus) // 2
    t0 = time.perf_counter()
    for fact in corpus[:mid]:
        agent_a.remember(fact, visibility="public")
    for fact in corpus[mid:]:
        agent_b.remember(fact, visibility="public")
    ingest_ms = (time.perf_counter() - t0) * 1000

    result.total_ingest_time_ms = ingest_ms
    result.total_queries = len(queries)

    for query, expected in queries:
        t0 = time.perf_counter()
        # Either agent can find all knowledge
        results = agent_a.recall(query)
        recall_ms = (time.perf_counter() - t0) * 1000
        result.total_recall_time_ms += recall_ms

        combined = " ".join(results).lower()
        hit = expected.lower() in combined
        if hit:
            result.correct_recalls += 1
        result.details.append({
            "query": query, "expected": expected,
            "hit": hit, "recall_ms": recall_ms,
        })

    return result


def run_benchmark(
    corpus: list[str] | None = None,
    queries: list[tuple[str, str]] | None = None,
) -> ComparisonResult:
    """
    Run the shared-vs-isolated benchmark.

    Returns a ComparisonResult with side-by-side metrics.
    """
    corpus = corpus or KNOWLEDGE_CORPUS
    queries = queries or QUERIES

    isolated = _bench_isolated(corpus, queries)
    shared = _bench_shared(corpus, queries)

    return ComparisonResult(isolated=isolated, shared=shared)


if __name__ == "__main__":
    result = run_benchmark()
    print(result.summary())
