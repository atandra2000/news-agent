"""Domain errors. Flat hierarchy — every failure the pipeline can surface."""

from __future__ import annotations


class HermesError(Exception):
    """Base class for all Hermes errors."""


class LLMError(HermesError):
    """All providers in a role's chain failed."""
