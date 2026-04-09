"""
Palace adapter — wraps an external palace package as a storage backend.

The palace layer provides:
- MemoryStack (Layer 0-3): identity, essential story, on-demand, deep search
- miner.mine(): file mining into ChromaDB
- searcher.search_memories(): programmatic search

This adapter translates between oracle-memory's MemoryClaim model
and the palace's ChromaDB-based storage.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import MemoryClaim, PalaceCoordinate

# Lazy imports — mempalace is an optional heavy dependency
_mempalace_available: bool | None = None


def _check_palace() -> bool:
    global _mempalace_available
    if _mempalace_available is None:
        try:
            import mempalace.layers  # noqa: F401
            import mempalace.searcher  # noqa: F401
            _mempalace_available = True
        except ImportError:
            _mempalace_available = False
    return _mempalace_available


def _get_chromadb_collection(palace_path: str):
    """Get or create the palace_drawers collection."""
    import chromadb
    os.makedirs(palace_path, exist_ok=True)
    client = chromadb.PersistentClient(path=palace_path)
    try:
        return client.get_collection("palace_drawers")
    except Exception:
        return client.create_collection("palace_drawers")


@dataclass(slots=True)
class PalaceAdapter:
    """
    Wraps an external palace installation as a storage backend
    for oracle-memory claims.

    Usage:
        adapter = PalaceAdapter(palace_path="~/.mempalace/palace")
        adapter.add_claim(claim)
        results = adapter.search("flask oauth", wing="my-project")
    """
    palace_path: str
    wing: str = "oracle"

    def _drawer_id(self, claim: MemoryClaim) -> str:
        raw = f"{claim.user_id}:{claim.claim_id}"
        return f"drawer_oracle_{hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:16]}"

    def add_claim(self, claim: MemoryClaim) -> str:
        """Store a MemoryClaim as a drawer in the MemPalace ChromaDB collection."""
        if not _check_palace():
            raise ImportError("palace backend is not installed")

        collection = _get_chromadb_collection(self.palace_path)
        drawer_id = self._drawer_id(claim)
        room = "general"
        if claim.coordinate:
            room = claim.coordinate.room

        metadata: dict[str, Any] = {
            "wing": claim.coordinate.wing if claim.coordinate else self.wing,
            "room": room,
            "source_file": f"oracle:{claim.source_kind}",
            "chunk_index": 0,
            "added_by": "oracle-memory",
            "filed_at": datetime.utcnow().isoformat(),
            "oracle_claim_id": claim.claim_id,
            "oracle_user_id": claim.user_id,
            "oracle_visibility": claim.visibility,
            "oracle_memory_type": claim.memory_type,
            "oracle_confidence": claim.confidence,
        }
        if claim.title:
            metadata["oracle_title"] = claim.title

        text = claim.content
        if claim.title:
            text = f"{claim.title}: {claim.content}"

        collection.upsert(
            documents=[text],
            ids=[drawer_id],
            metadatas=[metadata],
        )
        return drawer_id

    def search(
        self,
        query: str,
        wing: str | None = None,
        room: str | None = None,
        n_results: int = 5,
        user_id: str | None = None,
        visibility: str | None = None,
    ) -> list[MemoryClaim]:
        """Search the palace and return results as MemoryClaim objects."""
        if not _check_palace():
            raise ImportError("palace backend is not installed")

        from mempalace.searcher import search_memories

        result = search_memories(
            query=query,
            palace_path=self.palace_path,
            wing=wing or self.wing,
            room=room,
            n_results=n_results,
        )

        if "error" in result:
            return []

        claims: list[MemoryClaim] = []
        for hit in result.get("results", []):
            meta = hit.get("metadata", {}) if "metadata" in hit else hit
            claim_user = meta.get("oracle_user_id", "")
            claim_vis = meta.get("oracle_visibility", "public")

            # Filter by user/visibility if requested
            if user_id and claim_user and claim_user != user_id:
                continue
            if visibility and claim_vis != visibility:
                continue

            claims.append(MemoryClaim(
                user_id=claim_user,
                memory_type=meta.get("oracle_memory_type", "general"),
                content=hit.get("text", ""),
                visibility=claim_vis,
                title=meta.get("oracle_title"),
                source_kind="mempalace",
                confidence=float(meta.get("oracle_confidence", 0.6)),
                claim_id=meta.get("oracle_claim_id", ""),
                coordinate=PalaceCoordinate(
                    wing=hit.get("wing", self.wing),
                    hall="hall_facts",
                    room=hit.get("room", "general"),
                ),
            ))
        return claims

    def wake_up(self, wing: str | None = None) -> str:
        """Get L0 + L1 wake-up context from MemPalace."""
        if not _check_palace():
            raise ImportError("palace backend is not installed")

        from mempalace.layers import MemoryStack
        stack = MemoryStack(palace_path=self.palace_path)
        return stack.wake_up(wing=wing or self.wing)

    def recall(self, wing: str | None = None, room: str | None = None,
               n_results: int = 10) -> str:
        """L2 on-demand retrieval from MemPalace."""
        if not _check_palace():
            raise ImportError("palace backend is not installed")

        from mempalace.layers import MemoryStack
        stack = MemoryStack(palace_path=self.palace_path)
        return stack.recall(wing=wing, room=room, n_results=n_results)

    def deep_search(self, query: str, wing: str | None = None,
                    room: str | None = None, n_results: int = 5) -> str:
        """L3 deep semantic search — returns formatted text."""
        if not _check_palace():
            raise ImportError("palace backend is not installed")

        from mempalace.layers import MemoryStack
        stack = MemoryStack(palace_path=self.palace_path)
        return stack.search(query, wing=wing, room=room, n_results=n_results)

    def mine_project(self, project_dir: str, wing: str | None = None,
                     dry_run: bool = False) -> None:
        """Mine a project directory into the palace (delegates to mempalace miner)."""
        if not _check_palace():
            raise ImportError("palace backend is not installed")

        from mempalace.miner import mine
        mine(
            project_dir=project_dir,
            palace_path=self.palace_path,
            wing_override=wing or self.wing,
            agent="oracle-memory",
            dry_run=dry_run,
        )

    def status(self) -> dict[str, Any]:
        """Get palace status via MemoryStack."""
        if not _check_palace():
            return {"error": "mempalace not installed"}

        from mempalace.layers import MemoryStack
        stack = MemoryStack(palace_path=self.palace_path)
        return stack.status()
