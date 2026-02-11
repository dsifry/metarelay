"""Shared test fixtures for metarelay."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from metarelay.adapters.local_store import SqliteEventStore
from metarelay.config import CloudConfig, MetarelayConfig, RepoConfig
from metarelay.container import Container
from metarelay.core.models import Event, HandlerResult, HandlerResultStatus
from metarelay.handlers.registry import HandlerRegistry


@pytest.fixture()
def test_config(tmp_path: Path) -> MetarelayConfig:
    """Create a test config pointing to a temp database."""
    return MetarelayConfig(
        cloud=CloudConfig(
            supabase_url="https://test.supabase.co",
            supabase_key="test-key",
        ),
        repos=[RepoConfig(name="owner/repo", path=str(tmp_path / "repo"))],
        db_path=str(tmp_path / "test.db"),
    )


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> str:
    """Return a temp database path."""
    return str(tmp_path / "test.db")


@pytest.fixture()
def test_store(tmp_db_path: str) -> SqliteEventStore:
    """Create a test SQLite event store."""
    return SqliteEventStore(tmp_db_path)


@pytest.fixture()
def test_container(test_config: MetarelayConfig, tmp_db_path: str) -> Container:
    """Create a test container with real local store and mocked cloud."""
    event_store = SqliteEventStore(tmp_db_path)
    cloud_client = AsyncMock()
    cloud_client.fetch_events_since.return_value = []
    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = HandlerResult(
        handler_name="test",
        status=HandlerResultStatus.SUCCESS,
        exit_code=0,
        duration_seconds=0.1,
    )
    registry = HandlerRegistry()

    return Container(
        config=test_config,
        event_store=event_store,
        cloud_client=cloud_client,
        dispatcher=dispatcher,
        registry=registry,
    )


def make_event(
    id: int = 1,
    repo: str = "owner/repo",
    event_type: str = "check_run",
    action: str = "completed",
    payload: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Event:
    """Factory for creating test events."""
    return Event(
        id=id,
        repo=repo,
        event_type=event_type,
        action=action,
        payload=payload or {"conclusion": "failure"},
        **kwargs,
    )
