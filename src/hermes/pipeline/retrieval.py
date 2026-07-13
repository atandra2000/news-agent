"""Past-report RAG for the section writer.

Loads past report sections, embeds them, and surfaces the top-k most similar
to the section being synthesized. Anchors style/structure without a
persistent vector store. In-memory brute-force cosine on CPU; sub-second
at <100 past reports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from hermes.llm.embed import Embedder, cosine
from hermes.logging import get_logger

log = get_logger("retrieval")

# Section headings: ## **1. Title** or ## 1. Title
_SECTION_RE = re.compile(r"^##\s+\*?\*?(\d+\.\s+.+?)\*?\*?\s*$", re.MULTILINE)


@dataclass
class ReportChunk:
    """A section from a past report."""

    report_path: str
    section_title: str
    content: str
    embedding: np.ndarray | None = None


def parse_report_sections(report_text: str, report_path: str = "") -> list[ReportChunk]:
    """Split a report markdown into sections by ## headings."""
    matches = list(_SECTION_RE.finditer(report_text))
    if not matches:
        return []

    chunks: list[ReportChunk] = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(report_text)
        content = report_text[start:end].strip()
        if content:
            chunks.append(ReportChunk(report_path=report_path, section_title=title, content=content))
    return chunks


def load_past_reports(reports_dir: Path, *, max_reports: int = 20) -> list[ReportChunk]:
    """Load and chunk past reports from a directory. Returns list of chunks."""
    if not reports_dir.exists():
        return []

    chunks: list[ReportChunk] = []
    report_files = sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in report_files[:max_reports]:
        try:
            text = path.read_text(encoding="utf-8")
            chunks.extend(parse_report_sections(text, str(path)))
        except Exception as exc:  # noqa: BLE001
            log.warning("rag.load_failed", path=str(path), error=str(exc))
    log.info("rag.loaded", reports=len(report_files[:max_reports]), chunks=len(chunks))
    return chunks


def embed_chunks(chunks: list[ReportChunk], embedder: Embedder) -> list[ReportChunk]:
    """Embed each chunk's content (mutates chunks in place)."""
    if not chunks:
        return chunks
    texts = [f"{c.section_title} {c.content}" for c in chunks]
    vecs = embedder.encode(texts)
    for i, c in enumerate(chunks):
        c.embedding = vecs[i]
    return chunks


def retrieve_similar(
    query: str,
    chunks: list[ReportChunk],
    *,
    embedder: Embedder,
    top_k: int = 3,
    threshold: float = 0.3,
) -> list[ReportChunk]:
    """Retrieve top-k most similar past chunks to the query."""
    if not chunks or not any(c.embedding is not None for c in chunks):
        return []

    query_vec = embedder.encode_one(query)
    scored: list[tuple[float, ReportChunk]] = []
    for c in chunks:
        if c.embedding is None:
            continue
        sim = cosine(query_vec, c.embedding)
        if sim >= threshold:
            scored.append((sim, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def format_rag_context(chunks: list[ReportChunk], *, max_chars: int = 2000) -> str:
    """Format retrieved chunks as context for the writer prompt."""
    if not chunks:
        return ""
    lines = ["PAST REPORT CONTEXT (for style/structure reference):"]
    total = 0
    for c in chunks:
        snippet = c.content[:600] if len(c.content) > 600 else c.content
        entry = f"\n- {c.section_title}: {snippet}"
        if total + len(entry) > max_chars:
            break
        lines.append(entry)
        total += len(entry)
    return "\n".join(lines)