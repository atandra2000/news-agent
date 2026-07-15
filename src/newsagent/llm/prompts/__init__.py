"""Versioned Jinja2 prompt templates for the analysis engine."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROMPT_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(str(_PROMPT_DIR)),
    autoescape=select_autoescape(enabled_extensions=()),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(name: str, **ctx) -> str:
    return _env.get_template(name).render(**ctx)
