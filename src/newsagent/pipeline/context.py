"""Shared run context injected into every pipeline stage (NEWSAGENT_DESIGN §6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from newsagent.config import NewsAgentSettings
from newsagent.llm.embed import Embedder
from newsagent.llm.router import LLMRouter
from newsagent.storage.db import Store
from newsagent.storage.vectorstore import VectorStore


@dataclass
class RunContext:
    settings: NewsAgentSettings
    store: Store
    router: LLMRouter
    embedder: Embedder
    vectorstore: VectorStore
    run_date: datetime = field(default_factory=lambda: datetime.now())
    # Per-run accumulation across stages.
    sources_checked: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    notes: dict = field(default_factory=dict)
    # Self-improving memory: past critique/quality lessons fed into writer/critic.
    memory_lessons: list[str] = field(default_factory=list)
