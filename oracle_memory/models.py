from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
import uuid

Visibility = Literal["private", "public"]
MemoryType = Literal["identity", "goal", "interest", "general", "document", "decision", "event"]


@dataclass(slots=True)
class PalaceCoordinate:
    wing: str
    hall: str
    room: str


@dataclass(slots=True)
class MemoryClaim:
    user_id: str
    memory_type: MemoryType
    content: str
    visibility: Visibility = "private"
    title: str | None = None
    source_kind: str = "conversation"
    source_ref: str | None = None
    confidence: float = 0.6
    coordinate: PalaceCoordinate | None = None
    claim_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_context_line(self) -> str:
        label = self.memory_type.replace("_", " ").title()
        if self.title:
            return f"{label}: {self.title} | {self.content}"
        return f"{label}: {self.content}"
