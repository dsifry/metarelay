"""Additional CLI tests for full coverage."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import yaml
from click.testing import CliRunner

from metarelay.cli import _setup_logging, main


def make_config_file(tmp_path: Path) -> Path:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        yaml.dump(
            {
                "cloud": {
                    "supabase_url": "https://test.supabase.co",
                    "supabase_key": "test-key",
                },
                "repos": [{"name": "owner/repo", "path": "/tmp/owner/repo"}],
                "db_path": str(tmp_path / "test.db"),
            }
        )
    )
    return config_file


class TestStartCommand:
    """Tests for the start command."""

    def test_start_with_valid_config(self, tmp_path: Path) -> None:
        config_file = make_config_file(tmp_path)
        runner = CliRunner()

        with patch("metarelay.cli.asyncio.run") as mock_run:
            result = runner.invoke(main, ["start", "-c", str(config_file)])

        assert result.exit_code == 0
        mock_run.assert_called_once()

    def test_start_with_keyboard_interrupt(self, tmp_path: Path) -> None:
        config_file = make_config_file(tmp_path)
        runner = CliRunner()

        with patch("metarelay.cli.asyncio.run", side_effect=KeyboardInterrupt):
            result = runner.invoke(main, ["start", "-c", str(config_file)])

        assert "Shutting down" in result.output

    def test_start_verbose(self, tmp_path: Path) -> None:
        config_file = make_config_file(tmp_path)
        runner = CliRunner()

        with patch("metarelay.cli.asyncio.run"):
            result = runner.invoke(main, ["start", "-c", str(config_file), "-v"])

        assert result.exit_code == 0


class TestSyncCommand:
    """Tests for the sync command."""

    def test_sync_success(self, tmp_path: Path) -> None:
        config_file = make_config_file(tmp_path)
        runner = CliRunner()

        with patch("metarelay.cli.asyncio.run"):
            result = runner.invoke(main, ["sync", "-c", str(config_file)])

        assert result.exit_code == 0
        assert "Sync complete" in result.output

    def test_sync_error(self, tmp_path: Path) -> None:
        config_file = make_config_file(tmp_path)
        runner = CliRunner()

        with patch("metarelay.cli.asyncio.run", side_effect=Exception("sync failed")):
            result = runner.invoke(main, ["sync", "-c", str(config_file)])

        assert result.exit_code == 1
        assert "Sync failed" in result.output

    def test_sync_verbose(self, tmp_path: Path) -> None:
        config_file = make_config_file(tmp_path)
        runner = CliRunner()

        with patch("metarelay.cli.asyncio.run"):
            result = runner.invoke(main, ["sync", "-c", str(config_file), "-v"])

        assert result.exit_code == 0


class TestSetupLogging:
    """Tests for _setup_logging helper."""

    def test_setup_logging_verbose(self) -> None:
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)  # Reset
        _setup_logging(verbose=True)
        assert root.level == logging.DEBUG
        root.handlers.clear()

    def test_setup_logging_normal(self) -> None:
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.WARNING)  # Reset
        _setup_logging(verbose=False)
        assert root.level == logging.INFO
        root.handlers.clear()
