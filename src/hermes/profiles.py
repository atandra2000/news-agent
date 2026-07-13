"""Report profiles (HERMES_DESIGN §12.10). The pipeline is parameterized by a
profile, never hardcoded; only new profiles are added, no new pipeline code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Canonical section ids in report order.
_ALL_SECTIONS: list[str] = [
    "executive_summary",
    "major_news",
    "paper_analysis",
    "model_releases",
    "open_source",
    "github_highlights",
    "hf_highlights",
    "company_updates",
    "industry_news",
    "community_highlights",
    "benchmark_changes",
    "emerging_trends",
    "technical_deep_dives",
    "engineering_insights",
    "practical_takeaways",
    "evidence_analysis",
    "guidance",
    "references",
]


@dataclass
class ReportProfile:
    name: str
    collectors: list[str] | None = None  # None = use settings.collectors.enabled
    sections: list[str] = field(default_factory=lambda: list(_ALL_SECTIONS))
    top_k_analysis: int = 25
    report_top_k: int = 25
    depth: str = "standard"  # standard | deep | exhaustive
    sinks: list[str] = field(default_factory=lambda: ["markdown"])
    description: str = ""


PROFILES: dict[str, ReportProfile] = {
    "daily": ReportProfile(
        name="daily",
        sections=list(_ALL_SECTIONS),
        top_k_analysis=25,
        report_top_k=25,
        depth="standard",
        sinks=["markdown", "obsidian"],
        description="Default autonomous daily report.",
    ),
    "weekly": ReportProfile(
        name="weekly",
        sections=list(_ALL_SECTIONS),
        top_k_analysis=60,
        report_top_k=60,
        depth="deep",
        sinks=["markdown", "obsidian"],
        description="Weekly deep-dive with higher top-k.",
    ),
    "minimal": ReportProfile(
        name="minimal",
        # No Tavily/Context7 — pure deterministic signal.
        collectors=["arxiv", "rss", "github_trending", "github_releases", "huggingface", "hacker_news"],
        sections=["executive_summary", "technical_deep_dives", "guidance", "references"],
        top_k_analysis=15,
        report_top_k=15,
        depth="standard",
        sinks=["markdown"],
        description="No-API-key minimum: arxiv, rss, github trending/releases, huggingface, hn.",
    ),
    "deep_dive": ReportProfile(
        name="deep_dive",
        sections=["executive_summary", "technical_deep_dives", "evidence_analysis", "engineering_insights", "practical_takeaways", "guidance", "references"],
        top_k_analysis=10,
        report_top_k=10,
        depth="exhaustive",
        sinks=["markdown", "obsidian"],
        description="Focused exhaustive analysis of the top items.",
    ),
    "trend_report": ReportProfile(
        name="trend_report",
        sections=["executive_summary", "emerging_trends", "industry_news", "benchmark_changes", "guidance", "references"],
        top_k_analysis=40,
        report_top_k=40,
        depth="standard",
        sinks=["markdown", "obsidian"],
        description="Trend-focused report.",
    ),
}


def get_profile(name: str) -> ReportProfile:
    if name not in PROFILES:
        raise KeyError(f"Unknown profile: {name}. Available: {list(PROFILES)}")
    return PROFILES[name]


def list_profiles() -> list[str]:
    return list(PROFILES)
