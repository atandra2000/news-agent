"""Normalized collector contract. Add a source by dropping a file in collectors/ and listing it in config.collectors.enabled."""

from __future__ import annotations

import abc
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import ClassVar


@dataclass
class RawItem:
    source_type: str
    title: str
    url: str
    content: str = ""
    summary: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.published_at is not None and self.published_at.tzinfo is None:
            self.published_at = self.published_at.replace(tzinfo=timezone.utc)
        if not self.summary:
            self.summary = (self.content or self.title)[:400]

    @property
    def uid(self) -> str:
        """Stable id from canonical url, else content hash."""
        if self.url:
            return hashlib.sha256(self.url.strip().lower().encode("utf-8")).hexdigest()
        return hashlib.sha256(
            f"{self.source_type}|{self.title}|{self.content[:512]}".encode("utf-8")
        ).hexdigest()


class CollectorAdapter(abc.ABC):
    source_type: ClassVar[str]

    @abc.abstractmethod
    async def collect(self, *, since: datetime, limit: int = 50) -> list[RawItem]:
        ...

    @property
    def name(self) -> str:
        return self.source_type
