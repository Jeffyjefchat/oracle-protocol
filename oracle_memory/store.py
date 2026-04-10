from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from datetime import datetime, timezone
from typing import Iterable

from .models import MemoryClaim

# ── stopwords (common English words that hurt relevance scoring) ────────
_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could of in to for on with "
    "at by from as into about between through during before after above "
    "below it its i me my we our you your he his she her they them their "
    "this that these those what which who whom how when where why all any "
    "each every some no not nor or and but if then else so than too very "
    "just also back only up out off over such now new".split()
)


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase words, stripping punctuation."""
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP_WORDS and len(w) > 1]


def _tf(terms: list[str]) -> dict[str, float]:
    """Term frequency: count / total."""
    counts = Counter(terms)
    total = len(terms) or 1
    return {t: c / total for t, c in counts.items()}


def _idf(term: str, doc_count: int, docs_with_term: int) -> float:
    """Inverse document frequency with smoothing."""
    return math.log((doc_count + 1) / (docs_with_term + 1)) + 1.0


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
                existing.updated_at = datetime.now(timezone.utc)
                return existing
        self._claims.append(claim)
        return claim

    def list_claims(self, user_id: str, visibility: str | None = None, limit: int = 20) -> list[MemoryClaim]:
        claims = [claim for claim in self._claims if claim.user_id == user_id]
        if visibility:
            claims = [claim for claim in claims if claim.visibility == visibility]
        claims.sort(key=lambda claim: (claim.updated_at, claim.created_at), reverse=True)
        return claims[:limit]

    def search_claims(self, user_id: str, query: str, visibility: str | None = None,
                      limit: int = 10, min_relevance: float = 0.1) -> list[MemoryClaim]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []
        claims = self.list_claims(user_id=user_id, visibility=visibility, limit=500)
        if not claims:
            return []

        # Pre-tokenize all claim texts
        claim_tokens = []
        for claim in claims:
            haystack = f"{claim.title or ''} {claim.content}"
            claim_tokens.append(_tokenize(haystack))

        # Build IDF from the claim corpus
        doc_count = len(claims)
        term_doc_counts: Counter = Counter()
        for tokens in claim_tokens:
            term_doc_counts.update(set(tokens))

        query_tf = _tf(query_terms)

        # Score each claim using TF-IDF cosine similarity
        scored: list[tuple[float, MemoryClaim]] = []
        for idx, claim in enumerate(claims):
            doc_tokens = claim_tokens[idx]
            if not doc_tokens:
                continue
            doc_tf = _tf(doc_tokens)

            # Compute dot product of TF-IDF vectors
            dot = 0.0
            query_norm = 0.0
            doc_norm = 0.0
            all_terms = set(query_tf) | set(doc_tf)
            for term in all_terms:
                idf_val = _idf(term, doc_count, term_doc_counts.get(term, 0))
                q_weight = query_tf.get(term, 0.0) * idf_val
                d_weight = doc_tf.get(term, 0.0) * idf_val
                dot += q_weight * d_weight
                query_norm += q_weight * q_weight
                doc_norm += d_weight * d_weight

            if query_norm == 0 or doc_norm == 0:
                continue
            cosine = dot / (math.sqrt(query_norm) * math.sqrt(doc_norm))
            if cosine >= min_relevance:
                scored.append((cosine, claim))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [claim for _, claim in scored[:limit]]


class PalaceStore(MemoryStore):
    """
    Store backed by a palace ChromaDB backend.

    Stores claims as drawers, searches via semantic search.
    Falls back gracefully if the palace backend is not installed.
    """

    def __init__(self, palace_path: str, wing: str = "oracle") -> None:
        from .palace_adapter import PalaceAdapter
        self._adapter = PalaceAdapter(palace_path=palace_path, wing=wing)

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
