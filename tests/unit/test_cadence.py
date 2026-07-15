"""Cadence table + env validation."""

from __future__ import annotations

import pytest

from newsagent.pipeline.cadence import CADENCE, CadenceSpec, resolve_cadence


def test_cadence_table_has_three_entries():
    assert set(CADENCE) == {"daily", "weekly", "monthly"}


def test_cadence_daily_shape():
    d = CADENCE["daily"]
    assert d.days == 1
    assert d.max_tokens >= 1000
    assert d.min_citations >= 0


def test_cadence_max_tokens_scales_with_window():
    """Monthly gets more tokens than daily — long-tail signals need more room."""
    assert CADENCE["monthly"].max_tokens > CADENCE["daily"].max_tokens
    assert CADENCE["weekly"].max_tokens > CADENCE["daily"].max_tokens


def test_cadence_sources_scales_with_window():
    assert CADENCE["monthly"].sources > CADENCE["weekly"].sources > CADENCE["daily"].sources


def test_resolve_cadence_valid():
    assert resolve_cadence("monthly") is CADENCE["monthly"]


@pytest.mark.parametrize("bad", ["", "yearly", "DAILY", None])
def test_resolve_cadence_invalid_falls_back_to_daily(bad):
    assert resolve_cadence(bad) is CADENCE["daily"]


def test_cadence_spec_is_a_dataclass():
    assert CadenceSpec(window="x", days=1, per_section=1, sources=1, max_tokens=100, min_citations=0)
