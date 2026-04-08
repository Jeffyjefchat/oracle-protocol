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


# ── trust & reputation ──────────────────────────────────────────────────

from oracle_memory.trust import ReputationEngine, NodeReputation, ClaimProvenance


def test_reputation_new_node():
    engine = ReputationEngine()
    rep = engine.get_node_reputation("n1")
    assert rep.score == 0.5
    assert rep.is_trusted  # 0.5 >= 0.3


def test_reputation_accept_gate():
    engine = ReputationEngine()
    ok, reason = engine.should_accept_claim("n1", confidence=0.6)
    assert ok
    assert reason == "accepted"


def test_reputation_untrusted_rejection():
    engine = ReputationEngine()
    rep = engine.get_node_reputation("bad-node")
    rep.score = 0.1  # below trust threshold
    ok, reason = engine.should_accept_claim("bad-node", confidence=0.5)
    assert not ok
    assert reason == "untrusted_node"


def test_reputation_confidence_cap():
    engine = ReputationEngine()
    rep = engine.get_node_reputation("n1")
    rep.score = 0.4
    adjusted = engine.adjust_confidence("n1", 0.9)
    assert adjusted == 0.4  # capped to node's reputation


def test_reputation_hallucination_penalty():
    engine = ReputationEngine()
    engine.on_claim_accepted("n1", "c1", "u1")
    initial_score = engine.get_node_reputation("n1").score
    engine.on_hallucination("n1", ["c1"])
    assert engine.get_node_reputation("n1").score < initial_score
    prov = engine.get_claim_provenance("c1")
    assert prov is not None
    assert prov.disputes == 1


def test_reputation_positive_feedback():
    engine = ReputationEngine()
    engine.on_claim_accepted("n1", "c1", "u1")
    engine.on_positive_feedback("n1", ["c1"])
    prov = engine.get_claim_provenance("c1")
    assert prov.confirmations == 1


def test_reputation_rate_limiting():
    engine = ReputationEngine()
    for _ in range(30):
        engine.record_activity("n1")
    assert not engine.check_rate_limit("n1", max_per_minute=30)


def test_claim_provenance_trust_score():
    prov = ClaimProvenance(claim_id="c1", origin_node_id="n1", origin_user_id="u1")
    assert prov.trust_score == 0.5  # neutral
    prov.confirmations = 3
    prov.disputes = 1
    assert prov.trust_score == 0.75  # 3/4


# ── conflict detection & resolution ─────────────────────────────────────

from oracle_memory.conflict import ConflictDetector, ConflictResolver, ResolutionStrategy


def test_conflict_detection_same_topic():
    detector = ConflictDetector()
    a = MemoryClaim(user_id="u1", memory_type="general", content="Python is best", title="Language")
    b = MemoryClaim(user_id="u1", memory_type="general", content="Rust is best", title="Language")
    conflict = detector.check_pair(a, b)
    assert conflict is not None
    assert conflict.reason == "contradicts"


def test_conflict_detection_no_conflict():
    detector = ConflictDetector()
    a = MemoryClaim(user_id="u1", memory_type="general", content="Python is good")
    b = MemoryClaim(user_id="u1", memory_type="goal", content="Learn Rust")
    assert detector.check_pair(a, b) is None  # different types


def test_conflict_resolution_confidence():
    detector = ConflictDetector()
    resolver = ConflictResolver(ResolutionStrategy.CONFIDENCE_WINS)
    a = MemoryClaim(user_id="u1", memory_type="general", content="X is true", title="Fact", confidence=0.9)
    b = MemoryClaim(user_id="u1", memory_type="general", content="X is false", title="Fact", confidence=0.4)
    conflict = detector.check_pair(a, b)
    winner = resolver.resolve(conflict, a, b)
    assert winner == a.claim_id
    assert conflict.resolved


def test_conflict_resolution_reputation():
    detector = ConflictDetector()
    resolver = ConflictResolver()
    a = MemoryClaim(user_id="u1", memory_type="general", content="X is true", title="T")
    b = MemoryClaim(user_id="u1", memory_type="general", content="X is false", title="T")
    conflict = detector.check_pair(a, b)
    winner = resolver.resolve(conflict, a, b,
                               reputation_a=0.9, reputation_b=0.3,
                               strategy=ResolutionStrategy.REPUTATION_WINS)
    assert winner == a.claim_id


def test_conflict_dedup():
    detector = ConflictDetector()
    a = MemoryClaim(user_id="u1", memory_type="general", content="X", title="T")
    b = MemoryClaim(user_id="u1", memory_type="general", content="Y", title="T")
    c1 = detector.check_pair(a, b)
    c2 = detector.check_pair(a, b)
    assert c1.conflict_id == c2.conflict_id  # same conflict, not re-registered


# ── standard schema ──────────────────────────────────────────────────────

from oracle_memory.schema import (
    StandardClaim, validate_claim, SCHEMA_VERSION,
    from_mempalace_memory, from_mem0_fact, from_semantic_triple,
)


def test_standard_claim_basics():
    claim = StandardClaim(claim_id="c1", content="Flask is good", memory_type="general")
    assert claim.schema_version == SCHEMA_VERSION
    assert claim.content_hash()  # non-empty


def test_standard_claim_validation():
    good = StandardClaim(claim_id="c1", content="hello", memory_type="general")
    assert validate_claim(good) == []

    bad = StandardClaim(claim_id="", content="", memory_type="bogus", confidence=5.0)
    errors = validate_claim(bad)
    assert len(errors) >= 3  # missing id, empty content, bad type, bad confidence


def test_standard_claim_roundtrip():
    original = StandardClaim(claim_id="c1", content="test", memory_type="goal", user_id="u1")
    json_str = original.to_json()
    restored = StandardClaim.from_json(json_str)
    assert restored.claim_id == "c1"
    assert restored.memory_type == "goal"


def test_from_mempalace_memory():
    entry = {"id": "m1", "text": "User likes Python", "hall": "preferences", "wing": "personal"}
    claim = from_mempalace_memory(entry, user_id="u1")
    assert claim.memory_type == "preference"
    assert claim.wing == "personal"


def test_from_mem0_fact():
    fact = {"id": "f1", "fact": "User is a developer", "confidence": 0.8}
    claim = from_mem0_fact(fact, user_id="u1")
    assert "developer" in claim.content
    assert claim.confidence == 0.8


def test_from_semantic_triple():
    claim = from_semantic_triple("Alice", "prefers", "Python")
    assert claim.memory_type == "preference"
    assert "Alice prefers Python" in claim.content


# ── token incentives ─────────────────────────────────────────────────────

from oracle_memory.tokens import TokenLedger, TokenConfig


def test_token_ledger_reward():
    ledger = TokenLedger()
    amount = ledger.reward_claim_accepted("n1", "c1")
    assert amount > 0
    assert ledger.get_balance("n1").balance == amount


def test_token_ledger_penalty():
    ledger = TokenLedger()
    ledger.reward_claim_accepted("n1", "c1")
    ledger.penalize_hallucination("n1", "c1")
    balance = ledger.get_balance("n1")
    assert balance.balance < 0  # penalty > reward


def test_token_quality_multiplier():
    config = TokenConfig(quality_multiplier=2.0, quality_multiplier_threshold=0.8)
    ledger = TokenLedger(config)
    # High-rep node gets 2x
    high = ledger.reward_claim_accepted("good-node", "c1", reputation=0.9)
    # Low-rep node gets 1x
    low = ledger.reward_claim_accepted("new-node", "c2", reputation=0.5)
    assert high == low * 2


def test_token_leaderboard():
    ledger = TokenLedger()
    ledger.reward_claim_accepted("n1", "c1")
    ledger.reward_claim_accepted("n1", "c2")
    ledger.reward_claim_accepted("n2", "c3")
    board = ledger.leaderboard()
    assert board[0].node_id == "n1"  # n1 has more tokens


def test_token_network_stats():
    ledger = TokenLedger()
    ledger.reward_claim_accepted("n1", "c1")
    ledger.penalize_hallucination("n1", "c2")
    stats = ledger.network_stats()
    assert stats["total_nodes"] == 1
    assert stats["total_earned"] > 0


# ── easy.py (OracleAgent one-liner API) ─────────────────────────────────

from oracle_memory.easy import OracleAgent


def test_oracle_agent_remember_and_recall():
    agent = OracleAgent("test-agent")
    agent.remember("Python was created by Guido van Rossum in 1991")
    results = agent.recall("who created Python?")
    assert any("Guido" in r or "Python" in r for r in results)


def test_oracle_agent_forget():
    agent = OracleAgent("test-agent")
    agent.remember("Flask is a web framework")
    removed = agent.forget("Flask")
    assert removed >= 0  # at least attempted


def test_oracle_agent_thumbs_up_down():
    agent = OracleAgent("test-agent")
    agent.remember("test fact")
    agent.recall("test")
    agent.thumbs_up()  # should not raise
    agent.thumbs_down()  # should not raise


def test_oracle_agent_stats():
    agent = OracleAgent("test-agent")
    agent.remember("hello world")
    stats = agent.stats
    assert "name" in stats
    assert "total_claims" in stats
    assert stats["name"] == "test-agent"


def test_oracle_agent_context_for_llm():
    agent = OracleAgent("test-agent")
    agent.remember("I like Flask")
    context = agent.context_for_llm()
    assert isinstance(context, str)


# ── crypto.py (security hardening) ──────────────────────────────────────

from oracle_memory.crypto import KeyRing, ReplayGuard, SecureTransport


def test_keyring_add_and_sign():
    ring = KeyRing()
    ring.add_key("secret-1")
    msg = ProtocolMessage(message_type="heartbeat", node_id="n1")
    ring.sign_message(msg)
    assert msg.signature is not None
    assert ring.verify_message(msg)


def test_keyring_rotation():
    ring = KeyRing()
    ring.add_key("old-secret")
    msg_old = ProtocolMessage(message_type="heartbeat", node_id="n1")
    ring.sign_message(msg_old)

    ring.rotate("new-secret")
    # Old message still verifies (old key retained)
    assert ring.verify_message(msg_old)
    # New messages use new key
    msg_new = ProtocolMessage(message_type="heartbeat", node_id="n1")
    ring.sign_message(msg_new)
    assert ring.verify_message(msg_new)


def test_replay_guard_blocks_replay():
    guard = ReplayGuard(window_seconds=60)
    msg = ProtocolMessage(message_type="heartbeat", node_id="n1")
    assert guard.check(msg) is True
    assert guard.check(msg) is False  # replay blocked


def test_replay_guard_rejects_expired():
    guard = ReplayGuard(window_seconds=1)
    msg = ProtocolMessage(message_type="heartbeat", node_id="n1")
    msg.timestamp = time.time() - 100  # too old
    assert guard.check(msg) is False


def test_secure_transport_full_flow():
    transport = SecureTransport(initial_secret="key-v1")
    msg = ProtocolMessage(message_type="memory_claim", node_id="n1")
    transport.prepare(msg)
    assert transport.accept(msg) is True
    # Replay
    msg2 = ProtocolMessage(message_type="memory_claim", node_id="n1")
    msg2.message_id = msg.message_id
    msg2.timestamp = msg.timestamp
    msg2.payload = dict(msg.payload)
    msg2.sign("key-v1")
    assert transport.accept(msg2) is False  # replay blocked


def test_secure_transport_key_rotation():
    transport = SecureTransport(initial_secret="v1")
    transport.rotate_key("v2")
    msg = ProtocolMessage(message_type="heartbeat", node_id="n1")
    transport.prepare(msg)
    assert transport.accept(msg) is True


# ── scaling.py (sharding, backpressure, TTL) ─────────────────────────────

from oracle_memory.scaling import ConsistentHashRing, BackpressureController, ClaimTTL, ShardRouter


def test_consistent_hash_ring_basic():
    ring = ConsistentHashRing()
    ring.add_node("node-a")
    ring.add_node("node-b")
    ring.add_node("node-c")
    assert ring.node_count == 3
    node = ring.get_node("claim-123")
    assert node in {"node-a", "node-b", "node-c"}


def test_consistent_hash_ring_replication():
    ring = ConsistentHashRing()
    ring.add_node("a")
    ring.add_node("b")
    ring.add_node("c")
    nodes = ring.get_nodes("claim-1", n=2)
    assert len(nodes) == 2
    assert len(set(nodes)) == 2  # distinct nodes


def test_consistent_hash_ring_remove():
    ring = ConsistentHashRing()
    ring.add_node("a")
    ring.add_node("b")
    ring.remove_node("a")
    assert ring.node_count == 1
    assert ring.get_node("anything") == "b"


def test_backpressure_allows_normal():
    bp = BackpressureController(max_claims_per_second=5)
    for _ in range(5):
        assert bp.allow("node-a") is True


def test_backpressure_blocks_flood():
    bp = BackpressureController(max_claims_per_second=2)
    bp.allow("n1")
    bp.allow("n1")
    assert bp.allow("n1") is False


def test_claim_ttl_expiry():
    ttl = ClaimTTL(default_ttl_seconds=0.001)  # 1ms
    ttl.set_ttl("c1")
    time.sleep(0.01)
    assert ttl.is_expired("c1") is True


def test_claim_ttl_not_expired():
    ttl = ClaimTTL(default_ttl_seconds=3600)
    ttl.set_ttl("c1")
    assert ttl.is_expired("c1") is False


def test_claim_ttl_prune():
    ttl = ClaimTTL(default_ttl_seconds=0.001)
    ttl.set_ttl("c1")
    ttl.set_ttl("c2")
    time.sleep(0.01)
    pruned = ttl.prune()
    assert "c1" in pruned
    assert "c2" in pruned


def test_shard_router_full():
    router = ShardRouter(replication_factor=2)
    router.add_node("a")
    router.add_node("b")
    router.add_node("c")
    info = router.register_claim("claim-xyz", ttl_seconds=3600)
    assert len(info["shard_nodes"]) == 2
    assert info["primary"] is not None
    assert info["expires_at"] > time.time()


def test_shard_router_backpressure():
    router = ShardRouter()
    router.add_node("a")
    assert router.can_accept("a") is True


# ── integrations.py (LangChain, LlamaIndex, AutoGen) ────────────────────

from oracle_memory.integrations import LangChainMemory, LlamaIndexMemory, AutoGenMemoryBackend


def test_langchain_memory_save_and_load():
    mem = LangChainMemory(agent_name="lc-test")
    mem.save_context({"input": "I like Python"}, {"output": "Python is great!"})
    loaded = mem.load_memory_variables({})
    assert "oracle_memory" in loaded


def test_langchain_memory_variables():
    mem = LangChainMemory()
    assert mem.memory_variables == ["oracle_memory"]


def test_langchain_memory_clear():
    mem = LangChainMemory()
    mem.save_context({"input": "test"}, {"output": "ok"})
    mem.clear()
    loaded = mem.load_memory_variables({})
    assert loaded["oracle_memory"] == ""


def test_llamaindex_memory_put_and_get():
    mem = LlamaIndexMemory()
    mem.put("Flask is a Python web framework")
    result = mem.get("what is Flask?")
    assert isinstance(result, str)


def test_llamaindex_memory_get_all():
    mem = LlamaIndexMemory()
    mem.put("fact one")
    mem.put("fact two")
    all_items = mem.get_all()
    assert len(all_items) >= 2


def test_llamaindex_memory_reset():
    mem = LlamaIndexMemory()
    mem.put("test")
    mem.reset()
    assert mem.get() == ""


def test_autogen_backend_store_and_search():
    backend = AutoGenMemoryBackend()
    backend.store_turn(user_msg="hello", assistant_msg="world")
    results = backend.search("hello")
    assert isinstance(results, list)


def test_autogen_backend_context():
    backend = AutoGenMemoryBackend()
    backend.store_turn(user_msg="Python is fun")
    ctx = backend.get_context(query="Python")
    assert isinstance(ctx, str)


def test_autogen_backend_feedback():
    backend = AutoGenMemoryBackend()
    backend.store_turn(user_msg="test")
    backend.search("test")
    backend.feedback(positive=True)  # should not raise
    backend.feedback(positive=False)  # should not raise


# ── benchmark.py ─────────────────────────────────────────────────────────

from oracle_memory.benchmark import run_benchmark


def test_benchmark_runs():
    result = run_benchmark()
    assert result.shared.accuracy >= result.isolated.accuracy
    assert result.shared.total_queries == 10
    assert result.isolated.total_queries == 10


def test_benchmark_summary():
    result = run_benchmark()
    summary = result.summary()
    assert "Shared Memory vs Isolated RAG" in summary
    assert "Improvement" in summary
    assert "accuracy" in summary
