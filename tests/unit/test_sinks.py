"""Unit tests for output sinks: MarkdownFileSink + ObsidianSink + build_sinks."""

from __future__ import annotations


import pytest

from hermes.output import MarkdownFileSink, ObsidianSink, build_sinks


class TestMarkdownFileSink:
    @pytest.mark.asyncio
    async def test_deliver_writes_file(self, tmp_path):
        reports_dir = tmp_path / "reports"
        sink = MarkdownFileSink(reports_dir)
        meta = {"date": "2026-07-11"}
        await sink.deliver("# Title\n\nbody", meta)
        out = reports_dir / "2026-07-11.md"
        assert out.exists()
        assert out.read_text() == "# Title\n\nbody"
        assert meta["path"] == str(out)

    @pytest.mark.asyncio
    async def test_deliver_creates_parent_dirs(self, tmp_path):
        sink = MarkdownFileSink(tmp_path / "nested" / "deep")
        await sink.deliver("content", {"date": "test"})
        assert (tmp_path / "nested" / "deep" / "test.md").exists()

    @pytest.mark.asyncio
    async def test_deliver_uses_default_name_when_no_date(self, tmp_path):
        sink = MarkdownFileSink(tmp_path)
        await sink.deliver("text", {})
        assert (tmp_path / "report.md").exists()

    def test_name_is_markdown(self, tmp_path):
        assert MarkdownFileSink(tmp_path).name == "markdown"


class TestObsidianSink:
    @pytest.mark.asyncio
    async def test_deliver_writes_with_frontmatter(self, tmp_path):
        vault = tmp_path / "vault"
        sink = ObsidianSink(vault)
        await sink.deliver("# Report\n\nbody text", {"date": "2026-07-11"})
        out = vault / "Hermes_2026-07-11.md"
        assert out.exists()
        text = out.read_text()
        assert text.startswith("---")
        assert "tags:" in text
        assert "hermes" in text
        assert "# Report" in text

    @pytest.mark.asyncio
    async def test_deliver_appends_to_sinks_meta(self, tmp_path):
        sink = ObsidianSink(tmp_path / "vault")
        meta: dict = {"date": "2026-07-11"}
        await sink.deliver("content", meta)
        assert "sinks" in meta
        assert any("obsidian" in s for s in meta["sinks"])

    @pytest.mark.asyncio
    async def test_deliver_noops_when_vault_is_none(self, tmp_path):
        sink = ObsidianSink(None)
        # Should not raise.
        await sink.deliver("content", {"date": "test"})
        # No file written.
        assert not (tmp_path / "Hermes_test.md").exists()

    def test_name_is_obsidian(self):
        assert ObsidianSink(None).name == "obsidian"


class TestBuildSinks:
    def test_always_includes_markdown(self, tmp_path):
        settings = type("S", (), {
            "reports_dir": tmp_path,
            "storage": type("X", (), {"obsidian_vault": None})(),
        })()
        sinks = build_sinks(settings)
        assert any(s.name == "markdown" for s in sinks)

    def test_includes_obsidian_when_vault_set(self, tmp_path):
        settings = type("S", (), {
            "reports_dir": tmp_path,
            "storage": type("X", (), {"obsidian_vault": str(tmp_path / "vault")})(),
        })()
        sinks = build_sinks(settings)
        names = [s.name for s in sinks]
        assert "markdown" in names
        assert "obsidian" in names

    def test_excludes_obsidian_when_vault_none(self, tmp_path):
        settings = type("S", (), {
            "reports_dir": tmp_path,
            "storage": type("X", (), {"obsidian_vault": None})(),
        })()
        sinks = build_sinks(settings)
        names = [s.name for s in sinks]
        assert "obsidian" not in names