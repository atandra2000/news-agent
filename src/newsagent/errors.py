"""Domain errors. Flat hierarchy — every failure the pipeline can surface."""

from __future__ import annotations


class NewsAgentError(Exception):
    """Base class for all newsagent errors."""


class LLMError(NewsAgentError):
    """All providers in a role's chain failed."""


class PipelineRefusedError(NewsAgentError):
    """Raised by a pre-write gate that refuses to produce a report.

    The brief explicitly required something the assembled text is missing.
    Better to surface the refusal and let the caller re-run with broader
    sources than to write a report that quietly omits a required section."""
