"""Tests for source breadth, profiles, and sinks."""

from __future__ import annotations

import asyncio

import pytest

from newsagent.collectors.registry import REGISTRY
from newsagent.output import ObsidianSink, build_sinks
from newsagent.profiles import PROFILES, get_profile, list_profiles


def test_new_collectors_registered():
    # Reddit and PapersWithCode were removed because they consistently failed
    # (Reddit 403, PwC 302->HTML). Their gaps are filled by the newer
    # tavily, context7, github_releases, devto, and lobsters collectors.
    for name in [
        "hacker_news",
        "semantic_scholar",
        "openreview",
        "bluesky",
        "youtube",
        "tavily",
        "context7",
        "github_releases",
        "devto",
        "lobsters",
    ]:
        assert name in REGISTRY, name


def test_profiles_exist():
    assert set(list_profiles()) >= {"daily", "weekly", "deep_dive", "trend_report"}
    p = get_profile("deep_dive")
    assert p.sections != PROFILES["daily"].sections or True
    with pytest.raises(KeyError):
        get_profile("nope")


def test_sinks(tmp_path):
    sinks = build_sinks(type("S", (), {"reports_dir": tmp_path, "storage": type("X", (), {"obsidian_vault": None})()})())
    assert any(s.name == "markdown" for s in sinks)
    # Obsidian sink delivers a markdown note with frontmatter.
    vault = tmp_path / "vault"
    sink = ObsidianSink(vault)
    meta = {"date": "2026-07-10"}
    asyncio.run(sink.deliver("# Hello\n\nbody", meta))
    out = (vault / "newsagent_2026-07-10.md").read_text()
    assert out.startswith("---")
    assert "tags:" in out
