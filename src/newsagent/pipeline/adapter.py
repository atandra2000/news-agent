"""Meta-adapter: tune pipeline knobs from rolling eval scores (raise sources if
citation low, etc.). State persists per-prompt in JSON so changes survive restarts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from newsagent.logging import get_logger

log = get_logger("brief.adapter")


@dataclass
class PromptState:
    """Adaptive state for a prompt — knobs that change based on eval feedback."""

    prompt_path: str
    per_section_sources: int = 12
    days: int | None = None  # None = use default from cadence
    rewrite_threshold: float = 0.7
    extra_queries: int = 2
    history: list[dict] = field(default_factory=list)  # last N eval scores

    def save(self, path: Path) -> None:
        """Save state to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "prompt_path": self.prompt_path,
            "per_section_sources": self.per_section_sources,
            "days": self.days,
            "rewrite_threshold": self.rewrite_threshold,
            "extra_queries": self.extra_queries,
            "history": self.history,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, prompt_path: str) -> "PromptState":
        """Load state from a JSON file, or return defaults if not found."""
        if not path.exists():
            return cls(prompt_path=prompt_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                prompt_path=data.get("prompt_path", prompt_path),
                per_section_sources=data.get("per_section_sources", 12),
                days=data.get("days"),
                rewrite_threshold=data.get("rewrite_threshold", 0.7),
                extra_queries=data.get("extra_queries", 2),
                history=data.get("history", []),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("adapter.load_failed", path=str(path), error=str(exc))
            return cls(prompt_path=prompt_path)


class PromptAdapter:
    """Adapts pipeline knobs based on rolling eval scores."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, prompt_path: str) -> Path:
        """Derive state file path from prompt path."""
        # Hash the prompt path to avoid filesystem issues.
        import hashlib

        h = hashlib.md5(prompt_path.encode()).hexdigest()[:8]
        name = Path(prompt_path).stem
        return self.state_dir / f"{name}_{h}.json"

    def get_state(self, prompt_path: str) -> PromptState:
        """Load adaptive state for a prompt."""
        return PromptState.load(self._state_path(prompt_path), prompt_path)

    def update(self, prompt_path: str, eval_scores: dict[str, float]) -> PromptState:
        """Update state based on eval scores and return adjusted knobs."""
        state = self.get_state(prompt_path)

        state.history.append(eval_scores)
        if len(state.history) > 10:
            state.history = state.history[-10:]

        n = len(state.history)
        if n == 0:
            state.save(self._state_path(prompt_path))
            return state

        avg_coverage = sum(h.get("coverage", 0.5) for h in state.history) / n
        avg_citation = sum(h.get("citation", 0.5) for h in state.history) / n
        avg_quality = sum(h.get("quality", 0.5) for h in state.history) / n
        avg_cadence = sum(h.get("cadence", 0.5) for h in state.history) / n

        # Citation low → raise per_section_sources.
        if avg_citation < 0.6 and state.per_section_sources < 20:
            state.per_section_sources = min(20, state.per_section_sources + 2)
            log.info("adapter.raise_sources", prompt=prompt_path, new=state.per_section_sources)

        # Cadence low → log only; days aren't directly controllable here.
        if avg_cadence < 0.6:
            log.warning("adapter.low_cadence", prompt=prompt_path, avg=avg_cadence)

        # Quality low → lower rewrite_threshold (easier to pass).
        if avg_quality < 0.6 and state.rewrite_threshold > 0.5:
            state.rewrite_threshold = max(0.5, state.rewrite_threshold - 0.05)
            log.info("adapter.lower_threshold", prompt=prompt_path, new=state.rewrite_threshold)

        # Coverage low → raise extra_queries.
        if avg_coverage < 0.6 and state.extra_queries < 5:
            state.extra_queries = min(5, state.extra_queries + 1)
            log.info("adapter.raise_extra_queries", prompt=prompt_path, new=state.extra_queries)

        state.save(self._state_path(prompt_path))
        return state

    def record_feedback(self, prompt_path: str, rating: int, feedback: str = "") -> None:
        """Record user feedback (1-5 rating) for a prompt."""
        state = self.get_state(prompt_path)
        state.history.append({"rating": rating, "feedback": feedback})
        if len(state.history) > 10:
            state.history = state.history[-10:]

        # Low rating → be more aggressive with sources and queries.
        if rating <= 2:
            if state.per_section_sources < 20:
                state.per_section_sources = min(20, state.per_section_sources + 2)
            if state.extra_queries < 5:
                state.extra_queries = min(5, state.extra_queries + 1)
            log.info("adapter.low_rating", prompt=prompt_path, rating=rating)

        state.save(self._state_path(prompt_path))
