"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from metarelay.config import MetarelayConfig, RepoConfig, load_config
from metarelay.core.errors import ConfigError


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    """Create a temp config directory."""
    d = tmp_path / ".metarelay"
    d.mkdir()
    return d


@pytest.fixture()
def valid_config_data() -> dict:
    """Minimal valid config data."""
    return {
        "cloud": {
            "supabase_url": "https://test.supabase.co",
            "supabase_key": "test-key",
        },
        "repos": [{"name": "owner/repo", "path": "/tmp/owner/repo"}],
    }


def write_config(path: Path, data: dict) -> Path:
    """Write config data to a YAML file."""
    config_file = path / "config.yaml"
    config_file.write_text(yaml.dump(data))
    return config_file


class TestLoadConfig:
    """Tests for load_config()."""

    def test_loads_valid_config(self, config_dir: Path, valid_config_data: dict) -> None:
        config_file = write_config(config_dir, valid_config_data)
        config = load_config(str(config_file))

        assert config.cloud.supabase_url == "https://test.supabase.co"
        assert config.cloud.supabase_key == "test-key"
        assert config.repo_names == ["owner/repo"]

    def test_missing_file_raises_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Config file not found"):
            load_config(str(tmp_path / "nonexistent.yaml"))

    def test_invalid_yaml_raises_config_error(self, config_dir: Path) -> None:
        config_file = config_dir / "config.yaml"
        config_file.write_text(":\n  bad: [yaml\n")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(str(config_file))

    def test_non_mapping_yaml_raises_config_error(self, config_dir: Path) -> None:
        config_file = config_dir / "config.yaml"
        config_file.write_text("- just a list\n")
        with pytest.raises(ConfigError, match="must contain a YAML mapping"):
            load_config(str(config_file))

    def test_missing_required_fields_raises_config_error(self, config_dir: Path) -> None:
        config_file = write_config(
            config_dir, {"repos": [{"name": "owner/repo", "path": "/tmp/owner/repo"}]}
        )
        with pytest.raises(ConfigError, match="Invalid configuration"):
            load_config(str(config_file))

    def test_env_var_overrides(
        self, config_dir: Path, valid_config_data: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("METARELAY_SUPABASE_URL", "https://env.supabase.co")
        monkeypatch.setenv("METARELAY_SUPABASE_KEY", "env-key")
        config_file = write_config(config_dir, valid_config_data)

        config = load_config(str(config_file))
        assert config.cloud.supabase_url == "https://env.supabase.co"
        assert config.cloud.supabase_key == "env-key"

    def test_env_var_creates_cloud_section(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("METARELAY_SUPABASE_URL", "https://env.supabase.co")
        monkeypatch.setenv("METARELAY_SUPABASE_KEY", "env-key")
        config_file = write_config(
            config_dir, {"repos": [{"name": "owner/repo", "path": "/tmp/owner/repo"}]}
        )

        config = load_config(str(config_file))
        assert config.cloud.supabase_url == "https://env.supabase.co"

    def test_default_db_path(self, config_dir: Path, valid_config_data: dict) -> None:
        config_file = write_config(config_dir, valid_config_data)
        config = load_config(str(config_file))
        assert config.db_path == "~/.metarelay/metarelay.db"

    def test_custom_db_path(self, config_dir: Path, valid_config_data: dict) -> None:
        valid_config_data["db_path"] = "/tmp/custom.db"
        config_file = write_config(config_dir, valid_config_data)
        config = load_config(str(config_file))
        assert config.db_path == "/tmp/custom.db"

    def test_handlers_loaded(self, config_dir: Path, valid_config_data: dict) -> None:
        valid_config_data["handlers"] = [
            {
                "name": "test-handler",
                "event_type": "check_run",
                "action": "completed",
                "command": "echo hello",
            }
        ]
        config_file = write_config(config_dir, valid_config_data)
        config = load_config(str(config_file))
        assert len(config.handlers) == 1
        assert config.handlers[0].name == "test-handler"
        assert config.handlers[0].timeout == 300


class TestRepoValidation:
    """Tests for repo format validation."""

    def test_valid_repo(self) -> None:
        config = MetarelayConfig(
            cloud={"supabase_url": "https://x.supabase.co", "supabase_key": "k"},
            repos=[{"name": "owner/repo", "path": "/tmp/owner/repo"}],
        )
        assert config.repo_names == ["owner/repo"]

    def test_invalid_repo_no_slash(self) -> None:
        with pytest.raises(ValueError, match="Invalid repo format"):
            MetarelayConfig(
                cloud={"supabase_url": "https://x.supabase.co", "supabase_key": "k"},
                repos=[{"name": "justrepo", "path": "/tmp/justrepo"}],
            )

    def test_invalid_repo_too_many_slashes(self) -> None:
        with pytest.raises(ValueError, match="Invalid repo format"):
            MetarelayConfig(
                cloud={"supabase_url": "https://x.supabase.co", "supabase_key": "k"},
                repos=[{"name": "a/b/c", "path": "/tmp/a"}],
            )

    def test_invalid_repo_empty_parts(self) -> None:
        with pytest.raises(ValueError, match="Invalid repo format"):
            MetarelayConfig(
                cloud={"supabase_url": "https://x.supabase.co", "supabase_key": "k"},
                repos=[{"name": "/repo", "path": "/tmp/repo"}],
            )

    def test_multiple_valid_repos(self) -> None:
        config = MetarelayConfig(
            cloud={"supabase_url": "https://x.supabase.co", "supabase_key": "k"},
            repos=[
                {"name": "org/repo1", "path": "/tmp/org/repo1"},
                {"name": "org/repo2", "path": "/tmp/org/repo2"},
            ],
        )
        assert len(config.repos) == 2

    def test_repo_path_lookup(self) -> None:
        config = MetarelayConfig(
            cloud={"supabase_url": "https://x.supabase.co", "supabase_key": "k"},
            repos=[{"name": "owner/repo", "path": "/home/user/repo"}],
        )
        assert config.repo_path("owner/repo") == "/home/user/repo"
        assert config.repo_path("other/repo") is None
