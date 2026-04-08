from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable

from .models import MemoryClaim


class MemoryStore(ABC):
    @abstractmethod
    def save_claim(self, claim: MemoryClaim) -> MemoryClaim:
        raise NotImplementedError

    @abstractmethod
    def list_claims(self, user_id: str, visibility: str | None = None, limit: int = 20) -> list[MemoryClaim]:
        raise NotImplementedError

    @abstractmethod
    def search_claims(self, user_id: str, query: str, visibility: str | None = None, limit: int = 10) -> list[MemoryClaim]:
        raise NotImplementedError


class InMemoryMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._claims: list[MemoryClaim] = []

    def save_claim(self, claim: MemoryClaim) -> MemoryClaim:
        for existing in self._claims:
            if (
                existing.user_id == claim.user_id
                and existing.memory_type == claim.memory_type
                and existing.visibility == claim.visibility
                and existing.content.lower() == claim.content.lower()
            ):
                existing.updated_at = datetime.utcnow()
                return existing
        self._claims.append(claim)
        return claim

    def list_claims(self, user_id: str, visibility: str | None = None, limit: int = 20) -> list[MemoryClaim]:
        claims = [claim for claim in self._claims if claim.user_id == user_id]
        if visibility:
            claims = [claim for claim in claims if claim.visibility == visibility]
        claims.sort(key=lambda claim: (claim.updated_at, claim.created_at), reverse=True)
        return claims[:limit]

    def search_claims(self, user_id: str, query: str, visibility: str | None = None, limit: int = 10) -> list[MemoryClaim]:
        normalized_terms = [term for term in query.lower().split() if term]
        claims = self.list_claims(user_id=user_id, visibility=visibility, limit=500)
        scored: list[tuple[int, MemoryClaim]] = []
        for claim in claims:
            haystack = f"{claim.title or ''} {claim.content}".lower()
            score = sum(1 for term in normalized_terms if term in haystack)
            if score > 0:
                scored.append((score, claim))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [claim for _, claim in scored[:limit]]


class MemPalaceStore(MemoryStore):
    """
    Store backed by a real MemPalace ChromaDB palace.

    Stores claims as drawers, searches via MemPalace's semantic search.
    Falls back gracefully if mempalace is not installed.
    """

    def __init__(self, palace_path: str, wing: str = "oracle") -> None:
        from .mempalace_adapter import MemPalaceAdapter
        self._adapter = MemPalaceAdapter(palace_path=palace_path, wing=wing)

    def save_claim(self, claim: MemoryClaim) -> MemoryClaim:
        self._adapter.add_claim(claim)
        return claim

    def list_claims(self, user_id: str, visibility: str | None = None, limit: int = 20) -> list[MemoryClaim]:
        # MemPalace doesn't have a list-all API, so search with broad query
        return self._adapter.search(
            query="*",
            user_id=user_id,
            visibility=visibility,
            n_results=limit,
        )

    def search_claims(self, user_id: str, query: str, visibility: str | None = None, limit: int = 10) -> list[MemoryClaim]:
        return self._adapter.search(
            query=query,
            user_id=user_id,
            visibility=visibility,
            n_results=limit,
        )


def bulk_save(store: MemoryStore, claims: Iterable[MemoryClaim]) -> list[MemoryClaim]:
    return [store.save_claim(claim) for claim in claims]
