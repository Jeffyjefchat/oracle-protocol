"""
HTTP transport — send and receive protocol messages over the network.

v2.0.0 feature: federation over HTTP instead of in-process only.
Uses Python's built-in urllib (zero dependencies).

Usage — client side:
    from oracle_memory import HTTPTransport, ProtocolMessage

    transport = HTTPTransport("https://orchestrator.example.com", secret="shared-key")
    msg = ProtocolMessage(message_type="register_node", node_id="my-node")
    response = transport.send(msg)           # POST /protocol/messages
    claims = transport.fetch_claims("flask")  # GET /protocol/claims?q=flask

Usage — server side (Flask example):
    from oracle_memory.http_transport import handle_protocol_request

    @app.post('/protocol/messages')
    def protocol_endpoint():
        result = handle_protocol_request(request.get_json(), secret="shared-key", orchestrator=orch)
        return jsonify(result)
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .protocol import ProtocolMessage


@dataclass
class HTTPTransport:
    """
    Client-side HTTP transport for oracle protocol messages.

    Sends HMAC-signed ProtocolMessages to a remote orchestrator via HTTP POST.
    Retrieves public claims via HTTP GET.
    """

    base_url: str
    secret: str = ""
    timeout: float = 10.0
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def send(self, msg: ProtocolMessage) -> dict[str, Any]:
        """Send a protocol message to the orchestrator.  Returns the JSON response."""
        if self.secret:
            msg.sign(self.secret)
        payload = json.dumps(msg.to_dict(), default=str).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Oracle-Protocol-Version": msg.protocol_version,
            **self.headers,
        }
        req = Request(
            f"{self.base_url}/protocol/messages",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            return {"success": False, "error": f"HTTP {exc.code}", "detail": body}
        except (URLError, OSError) as exc:
            return {"success": False, "error": str(exc)}

    def fetch_claims(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        """Fetch public claims from the orchestrator."""
        from urllib.parse import quote
        url = f"{self.base_url}/protocol/claims?q={quote(query)}&limit={limit}"
        headers = {"Accept": "application/json", **self.headers}
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("claims", [])
        except (HTTPError, URLError, OSError):
            return []

    def register(self, node_id: str, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convenience: register this node with the orchestrator."""
        from .protocol import make_register
        msg = make_register(node_id, capabilities)
        return self.send(msg)

    def heartbeat(self, node_id: str, stats: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convenience: send a heartbeat."""
        from .protocol import make_heartbeat
        msg = make_heartbeat(node_id, stats)
        return self.send(msg)

    def publish_claim(self, node_id: str, user_id: str,
                      claim: dict[str, Any]) -> dict[str, Any]:
        """Convenience: publish a public claim."""
        from .protocol import make_memory_claim
        msg = make_memory_claim(node_id, user_id, claim, scope="public")
        return self.send(msg)


def handle_protocol_request(
    data: dict[str, Any],
    secret: str = "",
    orchestrator: Any = None,
    registry: Any = None,
) -> dict[str, Any]:
    """
    Server-side handler: validate and dispatch an incoming ProtocolMessage.

    Integrate into any web framework:
        result = handle_protocol_request(request.get_json(), secret=SECRET, orchestrator=orch)
        return jsonify(result)
    """
    try:
        msg = ProtocolMessage.from_dict(data)
    except Exception as exc:
        return {"success": False, "error": f"Invalid message: {exc}"}

    # Verify HMAC signature if secret is set
    if secret:
        if not msg.signature:
            return {"success": False, "error": "Missing signature"}
        if not msg.verify(secret):
            return {"success": False, "error": "Invalid signature"}

    # Dispatch by message type
    handlers = {
        "register_node": _handle_register,
        "heartbeat": _handle_heartbeat,
        "memory_claim": _handle_claim,
        "retrieval_request": _handle_retrieval,
        "quality_report": _handle_quality,
        "conversation_feedback": _handle_feedback,
    }
    handler = handlers.get(msg.message_type)
    if not handler:
        return {"success": False, "error": f"Unknown message type: {msg.message_type}"}

    return handler(msg, orchestrator=orchestrator, registry=registry)


def _handle_register(msg: ProtocolMessage, **ctx: Any) -> dict[str, Any]:
    orch = ctx.get("orchestrator")
    if orch and hasattr(orch, "register_node"):
        caps = msg.payload.get("capabilities", {})
        orch.register_node(msg.node_id, caps)
    return {"success": True, "action": "registered", "node_id": msg.node_id}


def _handle_heartbeat(msg: ProtocolMessage, **ctx: Any) -> dict[str, Any]:
    orch = ctx.get("orchestrator")
    if orch and hasattr(orch, "heartbeat"):
        stats = msg.payload.get("stats", {})
        orch.heartbeat(msg.node_id, stats)
    return {"success": True, "action": "heartbeat_ack", "node_id": msg.node_id}


def _handle_claim(msg: ProtocolMessage, **ctx: Any) -> dict[str, Any]:
    registry = ctx.get("registry")
    if registry and hasattr(registry, "receive_claim"):
        registry.receive_claim(msg.node_id, msg.payload.get("claim", {}))
    return {"success": True, "action": "claim_received", "message_id": msg.message_id}


def _handle_retrieval(msg: ProtocolMessage, **ctx: Any) -> dict[str, Any]:
    registry = ctx.get("registry")
    query = msg.payload.get("query", "")
    limit = msg.payload.get("limit", 10)
    claims: list[dict] = []
    if registry and hasattr(registry, "search_public_claims"):
        claims = registry.search_public_claims(query, limit=limit)
    return {"success": True, "claims": claims}


def _handle_quality(msg: ProtocolMessage, **ctx: Any) -> dict[str, Any]:
    orch = ctx.get("orchestrator")
    if orch and hasattr(orch, "report_quality"):
        metrics = msg.payload.get("metrics", {})
        orch.report_quality(msg.node_id, msg.user_id or "", metrics)
    return {"success": True, "action": "quality_ack"}


def _handle_feedback(msg: ProtocolMessage, **ctx: Any) -> dict[str, Any]:
    return {"success": True, "action": "feedback_ack", "message_id": msg.message_id}
