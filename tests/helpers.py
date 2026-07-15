"""Shared test helpers: deterministic FakeRouter + settings factory + fake items.

Imported by conftest.py and every test module that needs an offline pipeline
context. No network, no LLM server — the FakeRouter returns valid structured JSON
for every role the pipeline exercises.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from newsagent.collectors.base import RawItem
from newsagent.config import NewsAgentSettings
from newsagent.llm.router import LLMRouter


class FakeRouter(LLMRouter):
    """Deterministic router: returns valid structured JSON, never heuristic."""

    def __init__(self) -> None:
        self.stats = _StatsShim()
        self.token_budget = 1_000_000
        self.allow_heuristic_fallback = True
        self.timeout = 120.0
        self._available_cache: dict[str, bool] = {}

    async def complete(
        self,
        role: str,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        low = prompt.lower()
        # Chief Analyst prompt — returns a complete report.
        if "chief analyst" in low or "produce the report" in low:
            report = (
                "## **Executive Summary**\n\n"
                "Today's AI ecosystem saw a significant advance in transformer efficiency, "
                "with multiple sources reporting on attention-free architectures that achieve "
                "comparable results with linear complexity. FakeLab's announcement represents "
                "a potential paradigm shift.\n\n"
                "## **The Efficiency Revolution**\n\n"
                "Multiple sources converge on a breakthrough in attention-free transformers. "
                "The proposed architecture achieves 92% on MMLU without attention, matching "
                "transformer SOTA with O(n) complexity. This matters because inference costs "
                "on long sequences could drop by 10x.\n\n"
                "FakeLab leads this effort, but the competitive landscape is shifting rapidly. "
                "GPU vendors may need to rethink attention-optimized silicon.\n\n"
                "## **What to Watch**\n\n"
                "Expect rapid adoption in production inference stacks within weeks. "
                "Training-at-scale results will determine if this replaces transformers entirely.\n\n"
                "## **References**\n\n"
                "1. [primary] https://arxiv.org/abs/0001\n"
                "2. [primary] https://huggingface.co/fake/lab-model\n"
            )
            return _FakeResult(text=report, model="fake", provider="fake")
        return _FakeResult(text="ok", model="fake", provider="fake")

    async def json_complete(self, role: str, prompt: str, *, system: str | None = None, cache: bool | None = None) -> dict:
        low = prompt.lower()
        if "verifier" in low:
            return {"verdicts": []}
        if "critic" in low or "fixes" in low:
            return {"fixes": []}
        if "self-evaluator" in low or "score" in low and "rubric" in low:
            return {
                "scores": {
                    "coverage": 4.0, "accuracy_verification": 3.5, "depth": 4.0,
                    "synthesis": 3.5, "usefulness": 4.0, "trust": 4.0,
                },
                "notes": ["Good coverage but thin verification of key claims."],
            }
        if "label" in low:
            return {"label": "fake-cluster"}
        # Research plan prompt.
        if "research plan" in low or "research strategist" in low:
            return {
                "stories": [
                    {
                        "headline": "Attention-free transformers close the quality gap",
                        "cluster_id": 0,
                        "key_questions": ["Is attention really necessary?", "What are the production implications?"],
                        "priority": 0.85,
                        "evidence_status": "moderate",
                        "missing_evidence": ["Large-scale training results"],
                    },
                ],
                "cross_cutting_themes": ["efficiency", "attention-free"],
                "contradictions_to_resolve": [],
                "noise_to_filter": [],
            }
        # Story synthesis prompt — returns structured story JSON.
        if "narrative" in low and "significance" in low:
            # Batch mode (clusters defined).
            if "clusters" in low or "cluster" in low:
                return {
                    "stories": [{
                        "headline": "Fake breakthrough in AI efficiency",
                        "story_type": "paper",
                        "narrative": "Multiple sources report a significant advance in transformer efficiency. "
                                     "The proposed architecture removes attention entirely, achieving comparable "
                                     "results with linear complexity.",
                        "significance": "Engineers can now explore attention-free architectures for production systems.",
                        "technical_details": "O(n) complexity, 92% on MMLU.",
                        "ecosystem_impact": "FakeLab gains credibility. GPU vendors may rethink silicon.",
                        "historical_context": "Previous attempts (Linear Transformers, Mamba) lagged on quality.",
                        "future_outlook": "Expect rapid adoption in production inference stacks.",
                        "importance": 0.85, "novelty": 0.8, "breadth": 0.6,
                        "entities": [{"name": "FakeLab", "entity_type": "company", "role": "research lab"}],
                        "claims": [{"text": "Achieves 92% on MMLU without attention", "status": "SINGLE_SOURCE", "confidence": 0.6}],
                        "affected_actors": ["FakeLab", "GPU vendors"],
                        "related_topics": ["efficiency"],
                    }],
                }
            # Single mode.
            return {
                "headline": "Fake breakthrough in AI efficiency",
                "story_type": "paper",
                "narrative": "Multiple sources report a significant advance in transformer efficiency.",
                "significance": "Engineers can now explore attention-free architectures.",
                "technical_details": "O(n) complexity, 92% on MMLU.",
                "ecosystem_impact": "FakeLab gains credibility.",
                "historical_context": "Previous attempts lagged on quality.",
                "future_outlook": "Expect rapid adoption.",
                "importance": 0.85, "novelty": 0.8, "breadth": 0.6,
                "entities": [{"name": "FakeLab", "entity_type": "company", "role": "research lab"}],
                "claims": [{"text": "Achieves 92% on MMLU without attention", "status": "SINGLE_SOURCE", "confidence": 0.6}],
                "affected_actors": ["FakeLab"],
                "related_topics": ["efficiency"],
            }
        # Analyzer prompt.
        itype = "paper"
        for t in ("paper", "model_release", "product", "benchmark", "industry_event", "community_signal"):
            if f'item_type"] = "{t}"' in prompt or f'analysis_type": "{t}"' in prompt:
                itype = t
        return {
            "analysis_type": itype,
            "title": "Fake analysis",
            "summary": "A synthetic summary of the item for testing.",
            "beginner_explain": "Think of it like a toaster for ML.",
            "expert_explain": "It uses a synthetic mechanism with gradient-based updates.",
            "entities": [{"name": "FakeLab", "type": "company"}],
            "relations": [{"subject": "FakeModel", "predicate": "released_by", "object": "FakeLab", "confidence": 0.9}],
            "claims": [{"text": "The model improves accuracy.", "status": "SINGLE_SOURCE", "sources": [], "confidence": 0.6}],
            "type_specific": {"note": "synthetic"},
            "importance": 0.8, "novelty": 0.7, "long_term_impact": 0.6,
        }


class _StatsShim:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0
        self.failures = 0
        self.by_provider: dict[str, int] = {}
        self.cost_per_1k_tokens = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def estimated_cost_usd(self) -> float:
        return 0.0


class _FakeResult:
    def __init__(self, text: str, model: str, provider: str) -> None:
        self.text = text
        self.model = model
        self.provider = provider
        self.prompt_tokens = 1
        self.completion_tokens = 1

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def _settings(tmp_path) -> NewsAgentSettings:
    s = NewsAgentSettings()
    s.storage.dir = tmp_path
    s.embed.model = "hashing"
    s.embed.dim = 256
    s.pipeline.top_k_analysis = 8
    s.pipeline.report_top_k = 8
    s.collectors.enabled = []
    return s


def _fake_items() -> list[RawItem]:
    now = datetime.now(timezone.utc)
    return [
        RawItem(
            source_type="arxiv", title="Attention-Free Transformers",
            url="https://arxiv.org/abs/0001",
            content="We propose a new architecture that removes attention entirely.",
            published_at=now,
        ),
        RawItem(
            source_type="huggingface", title="Model: fake/lab-model",
            url="https://huggingface.co/fake/lab-model",
            content="open-weights language model", published_at=now,
            extra={"subtype": "model", "likes": 42},
        ),
        RawItem(
            source_type="github_trending", title="fake/lab-model (trending on GitHub)",
            url="https://github.com/fake/lab-model",
            content="A popular repo", published_at=now,
            extra={"stars_today": 150, "language": "Python"},
        ),
        RawItem(
            source_type="rss", title="FakeLab raises $100M",
            url="https://example.com/news/1",
            content="FakeLab announced a $100M series B.", published_at=now,
        ),
        RawItem(
            source_type="rss", title="A benchmark result on MMLU",
            url="https://example.com/news/2",
            content="New SOTA on MMLU benchmark with 92% accuracy.", published_at=now,
        ),
    ]
