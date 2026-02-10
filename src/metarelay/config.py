"""Configuration loading and validation for metarelay."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from metarelay.core.errors import ConfigError

DEFAULT_CONFIG_PATH = "~/.metarelay/config.yaml"


class CloudConfig(BaseModel):
    """Supabase cloud backend configuration."""

    supabase_url: str = Field(description="Supabase project URL")
    supabase_key: str = Field(description="Supabase anon/service key")
    webhook_secret: str | None = Field(default=None, description="GitHub webhook secret")


class HandlerConfigYAML(BaseModel):
    """Handler definition from config file."""

    name: str
    event_type: str
    action: str
    command: str
    filters: list[str] = Field(default_factory=list)
    timeout: int = Field(default=300)
    enabled: bool = Field(default=True)


class MetarelayConfig(BaseModel):
    """Top-level metarelay configuration."""

    cloud: CloudConfig
    repos: list[str] = Field(description="Repos to watch (owner/repo format)")
    handlers: list[HandlerConfigYAML] = Field(default_factory=list)
    db_path: str = Field(default="~/.metarelay/metarelay.db", description="SQLite database path")
    log_level: str = Field(default="INFO", description="Logging level")

    @field_validator("repos")
    @classmethod
    def validate_repos(cls, v: list[str]) -> list[str]:
        """Validate repo names are in owner/repo format."""
        for repo in v:
            parts = repo.split("/")
            if len(parts) != 2 or not parts[0] or not parts[1]:
                raise ValueError(f"Invalid repo format: {repo!r}. Expected 'owner/repo'.")
        return v


def load_config(path: str | None = None) -> MetarelayConfig:
    """Load and validate configuration from a YAML file.

    Environment variable overrides:
        METARELAY_SUPABASE_URL: overrides cloud.supabase_url
        METARELAY_SUPABASE_KEY: overrides cloud.supabase_key

    Args:
        path: Path to config file. Defaults to ~/.metarelay/config.yaml.

    Returns:
        Validated MetarelayConfig.

    Raises:
        ConfigError: If config file is missing, unreadable, or invalid.
    """
    config_path = Path(path or DEFAULT_CONFIG_PATH).expanduser()

    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        raw = config_path.read_text()
    except OSError as e:
        raise ConfigError(f"Cannot read config file: {e}") from e

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError("Config file must contain a YAML mapping")

    # Apply environment variable overrides
    if "cloud" not in data:
        data["cloud"] = {}

    env_url = os.environ.get("METARELAY_SUPABASE_URL")
    if env_url:
        data["cloud"]["supabase_url"] = env_url

    env_key = os.environ.get("METARELAY_SUPABASE_KEY")
    if env_key:
        data["cloud"]["supabase_key"] = env_key

    try:
        return MetarelayConfig(**data)
    except Exception as e:
        raise ConfigError(f"Invalid configuration: {e}") from e
