from __future__ import annotations

import re
from typing import Iterable

from .models import MemoryClaim, PalaceCoordinate


def normalize_text(value: str, limit: int = 500) -> str:
    normalized = " ".join((value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "..."


def infer_coordinate(memory_type: str, content: str) -> PalaceCoordinate:
    lowered = content.lower()
    wing = "wing_user"
    hall_map = {
        "identity": "hall_preferences",
        "interest": "hall_preferences",
        "goal": "hall_facts",
        "decision": "hall_facts",
        "document": "hall_discoveries",
        "event": "hall_events",
        "general": "hall_facts",
    }
    hall = hall_map.get(memory_type, "hall_facts")
    room = "general"
    if "oauth" in lowered:
        room = "oauth"
    elif "flask" in lowered:
        room = "flask-app"
    elif "memory" in lowered:
        room = "memory-system"
    elif "project" in lowered:
        room = "project"
    return PalaceCoordinate(wing=wing, hall=hall, room=room)


def extract_claims_from_conversation(user_id: str, text: str) -> list[MemoryClaim]:
    normalized = normalize_text(text, 700)
    claims: list[MemoryClaim] = []

    patterns: list[tuple[str, str, str]] = [
        ("identity", r"\bcall me\s+([A-Za-z0-9 _\-]{2,40})", "Preferred nickname: {value}"),
        ("interest", r"\b(?:i like|i love|i am interested in|i'm interested in)\s+(.+)", "Interests: {value}"),
        ("goal", r"\b(?:my goal is to|i want to|i'm trying to|i need to)\s+(.+)", "Goal: {value}"),
        ("general", r"\b(?:i am|i'm|we are|we're) building\s+(.+)", "Building: {value}"),
        ("general", r"\b(?:the|this) project uses\s+(.+)", "Project uses: {value}"),
    ]

    for memory_type, pattern, template in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue
        value = normalize_text(match.group(1).strip(" .,!"), 240)
        if len(value) < 3:
            continue
        visibility = "public" if memory_type == "general" else "private"
        claims.append(
            MemoryClaim(
                user_id=user_id,
                memory_type=memory_type,  # type: ignore[arg-type]
                content=template.format(value=value),
                visibility=visibility,  # type: ignore[arg-type]
                coordinate=infer_coordinate(memory_type, value),
            )
        )

    if not claims and normalized:
        claims.append(
            MemoryClaim(
                user_id=user_id,
                memory_type="event",
                content=normalize_text(normalized, 240),
                visibility="private",
                coordinate=infer_coordinate("event", normalized),
            )
        )
    return claims


def extract_claims_from_document(user_id: str, title: str, text: str, visibility: str = "public") -> list[MemoryClaim]:
    normalized = normalize_text(text, 700)
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    snippets = [normalize_text(sentence, 220) for sentence in sentences if sentence.strip()][:3]
    if not snippets:
        snippets = [normalize_text(normalized, 220)]

    claims: list[MemoryClaim] = []
    for snippet in snippets:
        claims.append(
            MemoryClaim(
                user_id=user_id,
                memory_type="document",
                title=normalize_text(title, 120),
                content=snippet,
                visibility="public" if visibility == "public" else "private",
                source_kind="document",
                coordinate=infer_coordinate("document", snippet),
            )
        )
    return claims


def compact_context_lines(claims: Iterable[MemoryClaim], limit: int = 8) -> list[str]:
    lines: list[str] = []
    for claim in list(claims)[:limit]:
        lines.append(claim.as_context_line())
    return lines
