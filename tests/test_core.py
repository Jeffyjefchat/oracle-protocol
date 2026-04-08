"""Tests for oracle_memory core modules (no mempalace/chromadb required)."""
import time

from oracle_memory.models import MemoryClaim, PalaceCoordinate
from oracle_memory.extractor import (
    extract_claims_from_conversation,
    extract_claims_from_document,
    compact_context_lines,
    normalize_text,
    infer_coordinate,
)
from oracle_memory.store import InMemoryMemoryStore, bulk_save
from oracle_memory.service import OracleMemoryService
from oracle_memory.protocol import ProtocolMessage, make_register, make_memory_claim
from oracle_memory.control_plane import Orchestrator, RetrievalPolicy
from oracle_memory.quality import QualityTracker, QualityEvent
from oracle_memory.federation import FederationRegistry, FederationClient


# ── models ──────────────────────────────────────────────────────────────

def test_memory_claim_defaults():
    claim = MemoryClaim(user_id="u1", memory_type="general", content="hello")
    assert claim.visibility == "private"
    assert claim.confidence == 0.6
    assert claim.claim_id  # uuid generated


def test_claim_context_line():
    claim = MemoryClaim(user_id="u1", memory_type="goal", content="build an app", title="Main Goal")
    assert "Goal" in claim.as_context_line()
    assert "Main Goal" in claim.as_context_line()


def test_palace_coordinate():
    coord = PalaceCoordinate(wing="project", hall="facts", room="flask")
    assert coord.wing == "project"


# ── extractor ───────────────────────────────────────────────────────────

def test_normalize_text():
    assert normalize_text("  hello   world  ") == "hello world"
    assert len(normalize_text("x" * 600, limit=500)) == 503  # 500 + "..."


def test_extract_conversation_identity():
    claims = extract_claims_from_conversation("u1", "call me Atlas")
    assert any("Atlas" in c.content for c in claims)
    assert any(c.memory_type == "identity" for c in claims)


def test_extract_conversation_interest():
    claims = extract_claims_from_conversation("u1", "I like machine learning")
    assert any(c.memory_type == "interest" for c in claims)


def test_extract_conversation_goal():
    claims = extract_claims_from_conversation("u1", "My goal is to build a flask app")
    assert any(c.memory_type == "goal" for c in claims)


def test_extract_conversation_general():
    claims = extract_claims_from_conversation("u1", "the project uses Flask and SQLite")
    assert any(c.visibility == "public" for c in claims)


def test_extract_conversation_fallback():
    claims = extract_claims_from_conversation("u1", "random text without patterns")
    assert len(claims) == 1
    assert claims[0].memory_type == "event"


def test_extract_document():
    claims = extract_claims_from_document("u1", "roadmap.txt", "Flask is great. SQLite works. Memory helps.", visibility="public")
    assert len(claims) >= 1
    assert all(c.memory_type == "document" for c in claims)
    assert all(c.visibility == "public" for c in claims)


def test_infer_coordinate():
    coord = infer_coordinate("general", "flask oauth setup")
    # 'oauth' appears first in the string, so it matches before 'flask'
    assert coord.room in ("oauth", "flask-app")


def test_compact_context_lines():
    claims = [
        MemoryClaim(user_id="u1", memory_type="goal", content="build app"),
        MemoryClaim(user_id="u1", memory_type="general", content="uses flask"),
    ]
    lines = compact_context_lines(claims, limit=5)
    assert len(lines) == 2


# ── store ───────────────────────────────────────────────────────────────

def test_in_memory_store_save_and_list():
    store = InMemoryMemoryStore()
    claim = MemoryClaim(user_id="u1", memory_type="general", content="hello")
    store.save_claim(claim)
    results = store.list_claims("u1")
    assert len(results) == 1


def test_in_memory_store_dedup():
    store = InMemoryMemoryStore()
    c1 = MemoryClaim(user_id="u1", memory_type="general", content="hello", visibility="private")
    c2 = MemoryClaim(user_id="u1", memory_type="general", content="hello", visibility="private")
    store.save_claim(c1)
    store.save_claim(c2)
    assert len(store.list_claims("u1")) == 1


def test_in_memory_store_search():
    store = InMemoryMemoryStore()
    store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="flask oauth"))
    store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="redis cache"))
    results = store.search_claims("u1", "flask")
    assert len(results) == 1
    assert "flask" in results[0].content.lower()


def test_in_memory_store_visibility_filter():
    store = InMemoryMemoryStore()
    store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="public fact", visibility="public"))
    store.save_claim(MemoryClaim(user_id="u1", memory_type="identity", content="private pref", visibility="private"))
    assert len(store.list_claims("u1", visibility="public")) == 1
    assert len(store.list_claims("u1", visibility="private")) == 1


def test_bulk_save():
    store = InMemoryMemoryStore()
    claims = [
        MemoryClaim(user_id="u1", memory_type="general", content="a"),
        MemoryClaim(user_id="u1", memory_type="general", content="b"),
    ]
    saved = bulk_save(store, claims)
    assert len(saved) == 2


# ── service ─────────────────────────────────────────────────────────────

def test_service_ingest_conversation():
    store = InMemoryMemoryStore()
    svc = OracleMemoryService(store=store, node_id="test")
    claims = svc.ingest_conversation_text("u1", "I like Python and my goal is to build an API")
    assert len(claims) >= 1


def test_service_ingest_document():
    store = InMemoryMemoryStore()
    svc = OracleMemoryService(store=store)
    claims = svc.ingest_document_text("u1", "readme", "Project uses Flask.", visibility="public")
    assert len(claims) >= 1


def test_service_build_context():
    store = InMemoryMemoryStore()
    svc = OracleMemoryService(store=store)
    svc.ingest_conversation_text("u1", "I like machine learning")
    svc.ingest_document_text("u1", "doc", "Flask and OAuth setup", visibility="public")
    ctx = svc.build_context("u1")
    assert len(ctx) >= 1


def test_service_search():
    store = InMemoryMemoryStore()
    svc = OracleMemoryService(store=store)
    svc.ingest_conversation_text("u1", "the project uses Flask and SQLite")
    results = svc.search("u1", "flask")
    assert len(results) >= 1


def test_service_feedback():
    store = InMemoryMemoryStore()
    svc = OracleMemoryService(store=store, node_id="n1")
    svc.record_feedback("u1", "conv-1", positive=True, claim_ids=["c1"])
    metrics = svc.get_quality_metrics()
    assert metrics["total_events"] >= 1


def test_service_respects_policy():
    store = InMemoryMemoryStore()
    svc = OracleMemoryService(store=store)
    # Save a low-confidence claim
    store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="low conf", visibility="private", confidence=0.1))
    # Set high min_confidence policy
    svc.apply_policy(RetrievalPolicy(min_confidence=0.5))
    ctx = svc.build_context("u1")
    # Low confidence claim should be filtered out
    assert not any("low conf" in line for line in ctx)


# ── protocol ────────────────────────────────────────────────────────────

def test_protocol_sign_verify():
    msg = make_register("node-a", {"supports": ["text"]})
    msg.sign("secret123")
    assert msg.signature != ""
    assert msg.verify("secret123")
    assert not msg.verify("wrong-secret")


def test_protocol_memory_claim():
    msg = make_memory_claim("node-a", "u1", {"claim_id": "c1", "content": "Flask is great", "memory_type": "general", "confidence": 0.8})
    assert msg.message_type == "memory_claim"
    assert msg.payload["claim"]["content"] == "Flask is great"


# ── control_plane ───────────────────────────────────────────────────────

def test_orchestrator_register_and_heartbeat():
    orch = Orchestrator(secret="s")
    record = orch.register_node("n1", {"gpu": True})
    assert record.node_id == "n1"
    assert record.is_alive
    assert orch.node_count == 1

    orch.heartbeat("n1", {"retrieval_hit_rate": 0.9})
    assert record.quality_scores["retrieval_hit_rate"] == 0.9


def test_orchestrator_push_policy():
    orch = Orchestrator(secret="key")
    orch.register_node("n1")
    msg = orch.push_policy_to_node("n1", min_confidence=0.7)
    assert msg is not None
    assert msg.verify("key")
    policy = orch.get_policy_for_node("n1")
    assert policy.min_confidence == 0.7


def test_orchestrator_auto_tune():
    orch = Orchestrator()
    orch.register_node("n1")
    # Report bad quality
    orch.report_quality("n1", "u1", {
        "retrieval_hit_rate": 0.3,
        "hallucination_rate": 0.1,
        "fallback_rate": 0.2,
        "user_satisfaction": 0.5,
    })
    policy = orch.get_policy_for_node("n1")
    # Auto-tune should have widened the window
    assert policy.prefer_recent_hours > 72
    # Auto-tune should have raised min_confidence (hallucination high)
    assert policy.min_confidence > 0.4


def test_orchestrator_global_events():
    orch = Orchestrator()
    orch.add_global_event({"type": "news", "text": "New model released"})
    events = orch.get_recent_global_events()
    assert len(events) == 1
    assert events[0]["text"] == "New model released"


# ── quality ─────────────────────────────────────────────────────────────

def test_quality_tracker_basic():
    qt = QualityTracker(window_seconds=600)
    qt.record_hit("u1", "c1", ["claim1"], node_id="n1")
    qt.record_miss("u1", "c2", node_id="n1")
    metrics = qt.metrics_for_node("n1")
    assert metrics["retrieval_hit_rate"] == 0.5
    assert metrics["total_events"] == 2


def test_quality_tracker_per_user():
    qt = QualityTracker()
    qt.record_positive("u1", "c1")
    qt.record_correction("u2", "c2")
    u1_metrics = qt.metrics_for_user("u1")
    u2_metrics = qt.metrics_for_user("u2")
    assert u1_metrics["user_satisfaction"] == 1.0
    assert u2_metrics["user_satisfaction"] == 0.0


# ── federation ──────────────────────────────────────────────────────────

def test_federation_registry():
    reg = FederationRegistry()
    node = reg.register("n1", endpoint="http://localhost:8000")
    assert node.is_reachable
    assert reg.node_count == 1


def test_federation_accept_public_claim():
    reg = FederationRegistry()
    reg.register("n1")
    public_claim = MemoryClaim(user_id="u1", memory_type="general", content="Flask is good", visibility="public")
    private_claim = MemoryClaim(user_id="u1", memory_type="identity", content="secret", visibility="private")
    assert reg.accept_public_claim(public_claim, "n1") is True
    assert reg.accept_public_claim(private_claim, "n1") is False


def test_federation_query_public_claims():
    reg = FederationRegistry()
    reg.register("n1")
    reg.accept_public_claim(
        MemoryClaim(user_id="u1", memory_type="general", content="Flask is great for APIs", visibility="public"), "n1")
    reg.accept_public_claim(
        MemoryClaim(user_id="u1", memory_type="general", content="Redis is fast", visibility="public"), "n1")
    results = reg.query_public_claims(keywords=["flask"])
    assert len(results) == 1
    assert "Flask" in results[0].content


def test_federation_dedup():
    reg = FederationRegistry()
    reg.register("n1")
    claim = MemoryClaim(user_id="u1", memory_type="general", content="same fact", visibility="public")
    assert reg.accept_public_claim(claim, "n1") is True
    assert reg.accept_public_claim(claim, "n1") is False  # duplicate


def test_federation_client_queue():
    client = FederationClient(node_id="n1", secret="s")
    pub = MemoryClaim(user_id="u1", memory_type="general", content="public", visibility="public")
    priv = MemoryClaim(user_id="u1", memory_type="identity", content="private", visibility="private")
    assert client.queue_claim(pub) is True
    assert client.queue_claim(priv) is False  # private not queued
    pending = client.flush_pending()
    assert len(pending) == 1
    assert pending[0].verify("s")
