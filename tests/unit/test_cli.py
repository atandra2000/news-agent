"""Unit tests for the CLI: arg parsing, command dispatch, _parse_date, help."""

from __future__ import annotations

from datetime import timezone

from newsagent.cli import _parse_args, _parse_date, main


class TestParseArgs:
    def test_defaults_command_is_none(self):
        assert _parse_args([])["command"] is None

    def test_all_commands_recognized(self):
        for cmd in ("status", "sources", "profiles", "quality",
                    "news", "eval", "models", "help"):
            assert _parse_args([cmd])["command"] == cmd

    def test_dry_run_flag(self):
        args = _parse_args(["news", "prompt.md", "--dry-run"])
        assert args["flags"]["dry-run"] is True

    def test_daily_cadence(self):
        # The legacy --daily/--weekly/--monthly boolean flags were replaced
        # by a single --cadence opt that news + eval both consume.
        args = _parse_args(["news", "prompt.md", "--cadence", "daily"])
        assert args["opts"]["cadence"] == "daily"

    def test_weekly_cadence(self):
        args = _parse_args(["news", "prompt.md", "--cadence", "weekly"])
        assert args["opts"]["cadence"] == "weekly"

    def test_monthly_cadence(self):
        args = _parse_args(["news", "prompt.md", "--cadence", "monthly"])
        assert args["opts"]["cadence"] == "monthly"

    def test_prompt_opt_takes_value(self):
        args = _parse_args(["eval", "report.md", "--prompt", "my_prompt.md"])
        assert args["opts"]["prompt"] == "my_prompt.md"
        assert args["positionals"] == ["report.md"]

    def test_date_opt_takes_value(self):
        args = _parse_args(["quality", "--date", "2026-07-11"])
        assert args["opts"]["date"] == "2026-07-11"

    def test_cadence_opt_takes_value(self):
        args = _parse_args(["eval", "r.md", "--prompt", "p.md", "--cadence", "weekly"])
        assert args["opts"]["cadence"] == "weekly"

    def test_rate_opt_takes_value(self):
        args = _parse_args(["news", "p.md", "--rate", "5"])
        assert args["opts"]["rate"] == "5"

    def test_positionals_collected(self):
        args = _parse_args(["news", "prompt.md"])
        assert args["positionals"] == ["prompt.md"]

    def test_news_prompt_positional_dispatch(self):
        # `newsagent news <prompt.md>` must be recognized as a single command +
        # positional, ready for the production pipeline dispatch.
        args = _parse_args(["news", "example_prompt.md"])
        assert args["command"] == "news"
        assert args["positionals"] == ["example_prompt.md"]
        assert args["flags"] == {}
        assert args["opts"] == {}

    def test_help_alias_for_minus_h(self):
        assert _parse_args(["-h"])["command"] == "help"

    def test_help_alias_for_double_minus_help(self):
        assert _parse_args(["--help"])["command"] == "help"


class TestParseDate:
    def test_iso_date(self):
        d = _parse_date("2026-07-11")
        assert d is not None
        assert d.year == 2026 and d.month == 7 and d.day == 11
        assert d.tzinfo == timezone.utc

    def test_iso_datetime(self):
        d = _parse_date("2026-07-11T14:30:00")
        assert d is not None
        assert d.hour == 14 and d.minute == 30 and d.second == 0

    def test_invalid_returns_none(self):
        assert _parse_date("not a date") is None
        assert _parse_date("") is None
        assert _parse_date("2026/07/11") is None  # slash format not supported

    def test_none_or_empty(self):
        assert _parse_date("") is None


class TestCLIUsesPipeline:
    def test_cli_dispatches_to_run_news_pipeline(self, tmp_path, monkeypatch):
        # Local import inside _cmd_news reads from newsagent.pipeline.orchestrator,
        # so patch the symbol at its source module.
        from newsagent.pipeline import orchestrator
        from pathlib import Path

        called = {"kwargs": None}

        async def _fake(spec, **kwargs):
            called["kwargs"] = kwargs
            return tmp_path / "fake_report.md"

        monkeypatch.setattr(orchestrator, "run_news_pipeline", _fake)
        from newsagent.cli import main as cli_main
        rc = cli_main(["news", "example_prompt.md"])
        assert rc == 0
        assert Path(called["kwargs"]["brief_path"]).name == "example_prompt.md"
        assert called["kwargs"].get("settings") is not None

    def test_run_news_pipeline_signature(self):
        from newsagent.pipeline.orchestrator import run_news_pipeline
        import inspect
        sig = inspect.signature(run_news_pipeline)
        assert "settings" in sig.parameters
        assert "brief_path" in sig.parameters


class TestCLICommands:
    def test_help_prints_usage(self, capsys):
        rc = main(["help"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "newsagent news" in out
        assert "newsagent models" in out

    def test_no_args_prints_help(self, capsys):
        rc = main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_status_runs_without_crash(self, capsys, tmp_path, monkeypatch):

        monkeypatch.setenv("NEWSAGENT_STORAGE_DIR", str(tmp_path))
        rc = main(["status"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Items:" in out

    def test_models_command_runs(self, capsys, monkeypatch):
        # This hits the live endpoint only if .env is configured; offline it
        # prints the catalog. Either way it should exit 0.
        rc = main(["models"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Go endpoint:" in out or "Ollama endpoint:" in out

    def test_profiles_command_lists_all(self, capsys):
        rc = main(["profiles"])
        assert rc == 0
        out = capsys.readouterr().out
        for name in ("daily", "weekly", "deep_dive", "trend_report"):
            assert name in out

    def test_sources_command(self, capsys):
        rc = main(["sources"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Available collectors:" in out
        assert "Enabled in config:" in out
