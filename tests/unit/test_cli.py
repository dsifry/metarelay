"""Tests for CLI commands."""

from __future__ import annotations

from click.testing import CliRunner

from metarelay.cli import main


class TestCLI:
    """Tests for Click CLI commands."""

    def test_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "metarelay" in result.output
        assert "0.2.0" in result.output

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "webhook-based event relay" in result.output.lower()

    def test_start_missing_config(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["start", "-c", "/nonexistent/config.yaml"])
        assert result.exit_code == 1
        assert "Error loading config" in result.output

    def test_status_missing_config(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["status", "-c", "/nonexistent/config.yaml"])
        assert result.exit_code == 1
        assert "Error loading config" in result.output

    def test_sync_missing_config(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "-c", "/nonexistent/config.yaml"])
        assert result.exit_code == 1
        assert "Error loading config" in result.output

    def test_status_with_valid_config(self, tmp_path: object) -> None:
        from pathlib import Path

        import yaml

        config_dir = Path(str(tmp_path)) / ".metarelay"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "cloud": {
                        "supabase_url": "https://test.supabase.co",
                        "supabase_key": "test-key",
                    },
                    "repos": [{"name": "owner/repo", "path": "/tmp/owner/repo"}],
                    "db_path": str(config_dir / "test.db"),
                }
            )
        )

        runner = CliRunner()
        result = runner.invoke(main, ["status", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "owner/repo" in result.output
        assert "no cursor" in result.output
