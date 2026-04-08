"""
Security hardening — key rotation, replay protection, message expiry.

GPT's VC critique: "HMAC signing is baseline, not sufficient."
This module addresses:
  - Key rotation (versioned secrets)
  - Replay attack protection (nonce registry + timestamp window)
  - Message expiry (TTL enforcement)
  - Constant-time comparison (already in protocol.py via hmac.compare_digest)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any

from .protocol import ProtocolMessage


@dataclass(slots=True)
class KeyVersion:
    """A versioned signing key."""
    version: int
    secret: str
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class KeyRing:
    """
    Manages multiple signing keys with rotation support.

    Usage:
        ring = KeyRing()
        ring.add_key("my-secret-v1")
        ring.rotate("my-secret-v2")  # old key still valid for verification
    """

    def __init__(self, max_old_keys: int = 3) -> None:
        self._keys: list[KeyVersion] = []
        self._max_old_keys = max_old_keys
        self._next_version = 1

    def add_key(self, secret: str, ttl_seconds: float | None = None) -> KeyVersion:
        expires = time.time() + ttl_seconds if ttl_seconds else None
        kv = KeyVersion(
            version=self._next_version,
            secret=secret,
            expires_at=expires,
        )
        self._keys.append(kv)
        self._next_version += 1
        return kv

    def rotate(self, new_secret: str, ttl_seconds: float | None = None) -> KeyVersion:
        """Add a new key and retire old ones beyond max_old_keys."""
        kv = self.add_key(new_secret, ttl_seconds)
        # Prune oldest keys beyond retention limit
        active = [k for k in self._keys if not k.is_expired]
        if len(active) > self._max_old_keys + 1:
            active = active[-(self._max_old_keys + 1):]
            self._keys = active
        return kv

    @property
    def current_key(self) -> KeyVersion | None:
        active = [k for k in self._keys if not k.is_expired]
        return active[-1] if active else None

    def sign_message(self, msg: ProtocolMessage) -> str:
        """Sign with the current key. Stores key version in payload."""
        key = self.current_key
        if key is None:
            raise ValueError("No active signing key")
        msg.payload["_key_version"] = key.version
        return msg.sign(key.secret)

    def verify_message(self, msg: ProtocolMessage) -> bool:
        """Try to verify with any non-expired key."""
        key_ver = msg.payload.get("_key_version")
        if key_ver is not None:
            # Try the specific version first
            for k in self._keys:
                if k.version == key_ver and not k.is_expired:
                    return msg.verify(k.secret)
        # Fallback: try all active keys
        for k in reversed(self._keys):
            if not k.is_expired and msg.verify(k.secret):
                return True
        return False


class ReplayGuard:
    """
    Prevents replay attacks by tracking seen message IDs and
    rejecting messages outside the time window.

    Usage:
        guard = ReplayGuard(window_seconds=300)
        if guard.check(message):
            process(message)
        else:
            reject(message)
    """

    def __init__(self, window_seconds: float = 300, max_nonces: int = 100_000) -> None:
        self._window = window_seconds
        self._max_nonces = max_nonces
        self._seen: dict[str, float] = {}

    def check(self, msg: ProtocolMessage) -> bool:
        """
        Returns True if message is fresh and not replayed.
        Returns False if replayed or expired.
        """
        now = time.time()

        # Reject messages outside time window
        age = abs(now - msg.timestamp)
        if age > self._window:
            return False

        # Reject already-seen message IDs
        if msg.message_id in self._seen:
            return False

        # Record and prune
        self._seen[msg.message_id] = now
        self._prune(now)
        return True

    def _prune(self, now: float) -> None:
        """Remove nonces older than the window."""
        if len(self._seen) > self._max_nonces:
            cutoff = now - self._window
            self._seen = {
                mid: ts for mid, ts in self._seen.items()
                if ts > cutoff
            }


class SecureTransport:
    """
    Combines KeyRing + ReplayGuard into a single security layer.

    Usage:
        transport = SecureTransport(initial_secret="my-key")
        signed_msg = transport.prepare(message)
        is_valid = transport.accept(received_message)
    """

    def __init__(self, initial_secret: str, window_seconds: float = 300) -> None:
        self.keyring = KeyRing()
        self.keyring.add_key(initial_secret)
        self.replay_guard = ReplayGuard(window_seconds=window_seconds)

    def prepare(self, msg: ProtocolMessage) -> ProtocolMessage:
        """Sign a message for sending."""
        self.keyring.sign_message(msg)
        return msg

    def accept(self, msg: ProtocolMessage) -> bool:
        """Validate signature and check for replay. Returns True if safe."""
        if not self.replay_guard.check(msg):
            return False
        if not self.keyring.verify_message(msg):
            return False
        return True

    def rotate_key(self, new_secret: str, ttl_seconds: float | None = None) -> None:
        """Rotate to a new signing key."""
        self.keyring.rotate(new_secret, ttl_seconds)
