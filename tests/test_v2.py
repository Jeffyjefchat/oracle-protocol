"""Tests for oracle_memory v2 features: SQLiteStore, HTTP transport, GDPR compliance."""
import json
import os
import tempfile
import time

import pytest

from oracle_memory.models import MemoryClaim
from oracle_memory.sqlite_store import SQLiteStore
from oracle_memory.http_transport import HTTPTransport, handle_protocol_request
from oracle_memory.protocol import ProtocolMessage, make_register, make_heartbeat, make_memory_claim
from oracle_memory.gdpr import GDPRController, ConsentRecord, ErasureResult
from oracle_memory.easy import OracleAgent
from oracle_memory.store import InMemoryMemoryStore


# ══════════════════════════════════════════════════════════════════════════
# SQLiteStore
# ══════════════════════════════════════════════════════════════════════════

class TestSQLiteStore:
    """SQLiteStore — persistent storage via sqlite3."""

    def setup_method(self):
        self.store = SQLiteStore(":memory:")

    def test_save_and_list(self):
        claim = MemoryClaim(user_id="u1", memory_type="general", content="Python is great")
        saved = self.store.save_claim(claim)
        assert saved.claim_id == claim.claim_id
        claims = self.store.list_claims("u1")
        assert len(claims) == 1
        assert claims[0].content == "Python is great"

    def test_dedup_same_content(self):
        c1 = MemoryClaim(user_id="u1", memory_type="general", content="Flask is a web framework")
        c2 = MemoryClaim(user_id="u1", memory_type="general", content="flask is a web framework")
        self.store.save_claim(c1)
        self.store.save_claim(c2)
        claims = self.store.list_claims("u1")
        assert len(claims) == 1

    def test_different_users_isolated(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="A"))
        self.store.save_claim(MemoryClaim(user_id="u2", memory_type="general", content="B"))
        assert len(self.store.list_claims("u1")) == 1
        assert len(self.store.list_claims("u2")) == 1

    def test_visibility_filter(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="pub", visibility="public"))
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="priv", visibility="private"))
        pub = self.store.list_claims("u1", visibility="public")
        priv = self.store.list_claims("u1", visibility="private")
        assert len(pub) == 1 and pub[0].content == "pub"
        assert len(priv) == 1 and priv[0].content == "priv"

    def test_search_tfidf(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="Python was created by Guido van Rossum"))
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="Flask is a lightweight web framework"))
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="JavaScript runs in the browser"))
        results = self.store.search_claims("u1", "who created Python?")
        assert len(results) >= 1
        assert "Python" in results[0].content

    def test_search_empty_query(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="test"))
        results = self.store.search_claims("u1", "")
        assert results == []

    def test_delete_claim(self):
        c = MemoryClaim(user_id="u1", memory_type="general", content="delete me")
        self.store.save_claim(c)
        assert self.store.delete_claim(c.claim_id)
        assert len(self.store.list_claims("u1")) == 0

    def test_delete_claim_nonexistent(self):
        assert not self.store.delete_claim("nonexistent-id")

    def test_delete_user_data(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="A"))
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="B"))
        self.store.save_claim(MemoryClaim(user_id="u2", memory_type="general", content="C"))
        deleted = self.store.delete_user_data("u1")
        assert deleted == 2
        assert len(self.store.list_claims("u1")) == 0
        assert len(self.store.list_claims("u2")) == 1

    def test_export_user_data(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="fact 1"))
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="event", content="fact 2"))
        export = self.store.export_user_data("u1")
        assert len(export) == 2
        assert all("claim_id" in d for d in export)

    def test_count_claims(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="A"))
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="B"))
        self.store.save_claim(MemoryClaim(user_id="u2", memory_type="general", content="C"))
        assert self.store.count_claims("u1") == 2
        assert self.store.count_claims() == 3

    def test_persistence_across_connections(self):
        """Data survives when using a file-based DB."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            store1 = SQLiteStore(db_path)
            store1.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="persisted"))
            store1.close()

            store2 = SQLiteStore(db_path)
            claims = store2.list_claims("u1")
            assert len(claims) == 1
            assert claims[0].content == "persisted"
            store2.close()
        finally:
            os.unlink(db_path)

    def test_limit_respected(self):
        for i in range(10):
            self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content=f"fact {i}"))
        assert len(self.store.list_claims("u1", limit=3)) == 3

    def test_update_timestamp_on_dedup(self):
        c = MemoryClaim(user_id="u1", memory_type="general", content="Same content")
        self.store.save_claim(c)
        time.sleep(0.01)
        c2 = MemoryClaim(user_id="u1", memory_type="general", content="Same content")
        self.store.save_claim(c2)
        claims = self.store.list_claims("u1")
        assert len(claims) == 1

    def test_oracle_agent_with_sqlite_store(self):
        """OracleAgent works with SQLiteStore as drop-in replacement."""
        agent = OracleAgent("test-agent", store=self.store)
        agent.remember("Flask is a Python web framework")
        results = agent.recall("what is Flask?")
        assert len(results) >= 1
        assert "Flask" in results[0]


# ══════════════════════════════════════════════════════════════════════════
# HTTP Transport
# ══════════════════════════════════════════════════════════════════════════

class TestHTTPTransport:
    """HTTPTransport — network-ready federation."""

    def test_transport_init(self):
        t = HTTPTransport("http://localhost:8000", secret="my-secret")
        assert t.base_url == "http://localhost:8000"
        assert t.secret == "my-secret"

    def test_transport_strips_trailing_slash(self):
        t = HTTPTransport("http://localhost:8000/")
        assert t.base_url == "http://localhost:8000"

    def test_send_unreachable(self):
        """Sending to unreachable host returns error dict, never raises."""
        t = HTTPTransport("http://127.0.0.1:59999")
        result = t.send(ProtocolMessage(message_type="register_node", node_id="n1"))
        assert result.get("success") is False
        assert "error" in result

    def test_fetch_claims_unreachable(self):
        t = HTTPTransport("http://127.0.0.1:59999")
        claims = t.fetch_claims("test")
        assert claims == []


class TestHandleProtocolRequest:
    """Server-side protocol message handler."""

    def test_register_node(self):
        msg = make_register("node-a", {"supports": ["text"]})
        result = handle_protocol_request(msg.to_dict())
        assert result["success"] is True
        assert result["action"] == "registered"

    def test_heartbeat(self):
        msg = make_heartbeat("node-a", {"active_users": 5})
        result = handle_protocol_request(msg.to_dict())
        assert result["success"] is True
        assert result["action"] == "heartbeat_ack"

    def test_claim_received(self):
        msg = make_memory_claim("node-a", "user-1", {"content": "test fact"}, scope="public")
        result = handle_protocol_request(msg.to_dict())
        assert result["success"] is True
        assert result["action"] == "claim_received"

    def test_invalid_message(self):
        result = handle_protocol_request({"bad": "data"})
        assert result["success"] is False

    def test_signature_verification(self):
        msg = make_register("node-a")
        msg.sign("shared-secret")
        result = handle_protocol_request(msg.to_dict(), secret="shared-secret")
        assert result["success"] is True

    def test_signature_rejection(self):
        msg = make_register("node-a")
        msg.sign("correct-secret")
        result = handle_protocol_request(msg.to_dict(), secret="wrong-secret")
        assert result["success"] is False
        assert "signature" in result.get("error", "").lower() or "invalid" in result.get("error", "").lower()

    def test_missing_signature_rejected(self):
        msg = make_register("node-a")
        # Don't sign it
        result = handle_protocol_request(msg.to_dict(), secret="some-secret")
        assert result["success"] is False

    def test_unknown_message_type(self):
        msg = ProtocolMessage(message_type="conflict_notice", node_id="node-a")
        result = handle_protocol_request(msg.to_dict())
        assert result["success"] is False


# ══════════════════════════════════════════════════════════════════════════
# GDPR Controller
# ══════════════════════════════════════════════════════════════════════════

class TestGDPRController:
    """GDPRController — privacy compliance hooks."""

    def setup_method(self):
        self.store = InMemoryMemoryStore()
        self.gdpr = GDPRController(self.store)

    def test_record_consent(self):
        record = self.gdpr.record_consent("u1", purpose="memory_storage")
        assert record.granted is True
        assert record.purpose == "memory_storage"

    def test_has_consent(self):
        assert not self.gdpr.has_consent("u1", "memory_storage")
        self.gdpr.record_consent("u1", "memory_storage")
        assert self.gdpr.has_consent("u1", "memory_storage")

    def test_revoke_consent(self):
        self.gdpr.record_consent("u1", "memory_storage")
        assert self.gdpr.revoke_consent("u1", "memory_storage")
        assert not self.gdpr.has_consent("u1", "memory_storage")

    def test_revoke_nonexistent(self):
        assert not self.gdpr.revoke_consent("u1", "nonexistent")

    def test_list_consents(self):
        self.gdpr.record_consent("u1", "memory_storage")
        self.gdpr.record_consent("u1", "analytics")
        consents = self.gdpr.list_consents("u1")
        assert len(consents) == 2
        purposes = {c["purpose"] for c in consents}
        assert "memory_storage" in purposes
        assert "analytics" in purposes

    def test_export_user_data(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="fact A"))
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="fact B"))
        self.gdpr.record_consent("u1", "memory_storage")
        export = self.gdpr.export_user_data("u1")
        assert export["user_id"] == "u1"
        assert export["total_claims"] == 2
        assert len(export["consents"]) == 1

    def test_erase_user_data_in_memory(self):
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="A"))
        self.store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="B"))
        self.store.save_claim(MemoryClaim(user_id="u2", memory_type="general", content="C"))
        self.gdpr.record_consent("u1", "test")
        result = self.gdpr.erase_user_data("u1")
        assert result.claims_deleted == 2
        assert result.consent_records_cleared == 1
        assert result.success
        assert len(self.store.list_claims("u1", limit=100)) == 0
        assert len(self.store.list_claims("u2", limit=100)) == 1

    def test_erase_user_data_sqlite(self):
        store = SQLiteStore(":memory:")
        gdpr = GDPRController(store)
        store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="A"))
        store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="B"))
        result = gdpr.erase_user_data("u1")
        assert result.claims_deleted == 2
        assert store.count_claims("u1") == 0

    def test_audit_log(self):
        self.gdpr.record_consent("u1", "storage")
        self.gdpr.export_user_data("u1")
        self.gdpr.erase_user_data("u1")
        log = self.gdpr.get_audit_log("u1")
        assert len(log) == 3
        actions = [e["action"] for e in log]
        assert "consent_recorded" in actions
        assert "data_exported" in actions
        assert "data_erased" in actions

    def test_audit_log_filtered(self):
        self.gdpr.record_consent("u1", "storage")
        self.gdpr.record_consent("u2", "storage")
        assert len(self.gdpr.get_audit_log("u1")) == 1
        assert len(self.gdpr.get_audit_log()) == 2

    def test_export_with_sqlite_store(self):
        store = SQLiteStore(":memory:")
        gdpr = GDPRController(store)
        store.save_claim(MemoryClaim(user_id="u1", memory_type="general", content="fact"))
        export = gdpr.export_user_data("u1")
        assert export["total_claims"] == 1
        assert export["claims"][0]["content"] == "fact"

    def test_erasure_result_to_dict(self):
        result = ErasureResult(user_id="u1", claims_deleted=5, consent_records_cleared=2)
        d = result.to_dict()
        assert d["user_id"] == "u1"
        assert d["claims_deleted"] == 5
        assert d["success"] is True
