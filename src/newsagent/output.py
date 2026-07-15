"""Output sinks (NEWSAGENT_DESIGN §12.11). Markdown is canonical; a Sink delivers
rendered content. Obsidian = Markdown variant with wikilinks. Notion/Telegram/Discord
are future sinks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Sink(Protocol):
    name: str

    async def deliver(self, content: str, meta: dict) -> None:
        ...


class MarkdownFileSink:
    """Write the canonical Markdown report to storage/reports/ (default)."""

    name = "markdown"

    def __init__(self, reports_dir: Path):
        self.reports_dir = reports_dir

    async def deliver(self, content: str, meta: dict) -> None:
        date = meta.get("date", "report")
        path = self.reports_dir / f"{date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        meta["path"] = str(path)


class ObsidianSink:
    """Mirror the report into an Obsidian vault as a Markdown note (wikilinks optional)."""

    name = "obsidian"

    def __init__(self, vault_dir: Path | None):
        self.vault_dir = vault_dir

    async def deliver(self, content: str, meta: dict) -> None:
        if not self.vault_dir:
            return
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        date = meta.get("date", "report")
        out = _to_obsidian(content)
        path = self.vault_dir / f"newsagent_{date}.md"
        path.write_text(out, encoding="utf-8")
        meta.setdefault("sinks", []).append(f"obsidian:{path}")


def _to_obsidian(md: str) -> str:
    # Keep standard Markdown links (Obsidian supports them); just add tag frontmatter.
    front = "---\ntags: [newsagent, ai-research-intelligence]\n---\n\n"
    return front + md


def build_sinks(settings) -> list[Sink]:
    sinks: list[Sink] = [MarkdownFileSink(settings.reports_dir)]
    vault = settings.storage.obsidian_vault
    if vault:
        sinks.append(ObsidianSink(Path(vault)))
    return sinks
