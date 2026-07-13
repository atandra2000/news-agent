"""Shared pytest fixtures: in-memory store + fake router + embedding + logging isolation."""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone

import pytest
import structlog

from hermes.llm.embed import Embedder
from hermes.pipeline.context import RunContext
from hermes.storage.db import Store
from hermes.storage.vectorstore import build_vector_store
from tests.helpers import FakeRouter, _settings


@pytest.fixture(autouse=True)
def _isolated_structlog():
    """Reset structlog config before each test so cached PrintLoggerFactory doesn't
    hold a stale sys.stderr reference (which pytest's capsys may close)."""
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(40),  # CRITICAL only
        logger_factory=structlog.PrintLoggerFactory(file=io.StringIO()),
        cache_logger_on_first_use=False,
    )
    yield
    structlog.reset_defaults()


@pytest.fixture
def fake_ctx(tmp_path):
    settings = _settings(tmp_path)
    store = Store(settings.sqlite_url)
    asyncio.run(store.init())
    router = FakeRouter()
    embedder = Embedder(model=settings.embed.model, dim=settings.embed.dim, normalize=True)
    vectorstore = build_vector_store(
        "numpy", store.session_factory, qdrant_path=str(settings.qdrant_path),
        collection=settings.storage.qdrant_collection, dim=settings.embed.dim,
    )
    ctx = RunContext(settings=settings, store=store, router=router, embedder=embedder, vectorstore=vectorstore)
    ctx.run_date = datetime.now(timezone.utc)
    yield ctx
    asyncio.run(store.close())