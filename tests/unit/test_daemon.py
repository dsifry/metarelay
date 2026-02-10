"""Tests for daemon event handling logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from metarelay.config import CloudConfig, MetarelayConfig
from metarelay.container import Container
from metarelay.core.models import (
    CursorPosition,
    Event,
    HandlerConfig,
    HandlerResult,
    HandlerResultStatus,
)
from metarelay.daemon import Daemon
from metarelay.handlers.registry import HandlerRegistry


def make_event(id: int = 1, repo: str = "owner/repo") -> Event:
    """Create a test event."""
    return Event(
        id=id,
        repo=repo,
        event_type="check_run",
        action="completed",
        payload={"conclusion": "failure"},
    )


def make_container(
    tmp_path: Path,
    handlers: list[HandlerConfig] | None = None,
) -> Container:
    """Create a test container with mocked adapters."""
    config = MetarelayConfig(
        cloud=CloudConfig(supabase_url="https://x.supabase.co", supabase_key="k"),
        repos=["owner/repo"],
        db_path=str(tmp_path / "test.db"),
    )

    event_store = MagicMock()
    event_store.has_event.return_value = False
    event_store.get_cursor.return_value = None

    cloud_client = AsyncMock()
    cloud_client.fetch_events_since.return_value = []

    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = HandlerResult(
        handler_name="test",
        status=HandlerResultStatus.SUCCESS,
        exit_code=0,
        duration_seconds=0.5,
    )

    registry = HandlerRegistry(handlers or [])

    return Container(
        config=config,
        event_store=event_store,
        cloud_client=cloud_client,
        dispatcher=dispatcher,
        registry=registry,
    )


class TestDaemonHandleEvent:
    """Tests for Daemon._handle_event()."""

    def test_dispatches_matching_handler(self, tmp_path: Path) -> None:
        handler = HandlerConfig(
            name="test-handler",
            event_type="check_run",
            action="completed",
            command="echo test",
        )
        container = make_container(tmp_path, handlers=[handler])
        daemon = Daemon(container)

        event = make_event()
        daemon._handle_event(event)

        container.dispatcher.dispatch.assert_called_once_with(handler, event)
        container.event_store.log_event.assert_called_once()
        container.event_store.set_cursor.assert_called_once_with("owner/repo", 1)

    def test_skips_duplicate_event(self, tmp_path: Path) -> None:
        handler = HandlerConfig(
            name="test-handler",
            event_type="check_run",
            action="completed",
            command="echo test",
        )
        container = make_container(tmp_path, handlers=[handler])
        container.event_store.has_event.return_value = True
        daemon = Daemon(container)

        daemon._handle_event(make_event())

        container.dispatcher.dispatch.assert_not_called()

    def test_no_matching_handler(self, tmp_path: Path) -> None:
        container = make_container(tmp_path, handlers=[])
        daemon = Daemon(container)

        daemon._handle_event(make_event())

        container.dispatcher.dispatch.assert_not_called()
        container.event_store.set_cursor.assert_not_called()

    def test_advances_cursor_after_dispatch(self, tmp_path: Path) -> None:
        handler = HandlerConfig(
            name="h",
            event_type="check_run",
            action="completed",
            command="echo test",
        )
        container = make_container(tmp_path, handlers=[handler])
        daemon = Daemon(container)

        daemon._handle_event(make_event(id=42))

        container.event_store.set_cursor.assert_called_with("owner/repo", 42)


class TestDaemonCatchUp:
    """Tests for catch-up pagination."""

    @pytest.mark.asyncio
    async def test_catch_up_paginates(self, tmp_path: Path) -> None:
        handler = HandlerConfig(
            name="h",
            event_type="check_run",
            action="completed",
            command="echo test",
        )
        container = make_container(tmp_path, handlers=[handler])

        # First page returns 2 events, second page returns empty
        container.cloud_client.fetch_events_since.side_effect = [
            [make_event(id=1), make_event(id=2)],
            [],
        ]

        daemon = Daemon(container)
        await daemon._catch_up()

        assert container.cloud_client.fetch_events_since.call_count == 2
        assert container.dispatcher.dispatch.call_count == 2

    @pytest.mark.asyncio
    async def test_catch_up_uses_cursor(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        container.event_store.get_cursor.return_value = CursorPosition(
            repo="owner/repo", last_event_id=50
        )

        daemon = Daemon(container)
        await daemon._catch_up()

        container.cloud_client.fetch_events_since.assert_called_with("owner/repo", 50, limit=100)

    @pytest.mark.asyncio
    async def test_catch_up_starts_from_zero_without_cursor(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        container.event_store.get_cursor.return_value = None

        daemon = Daemon(container)
        await daemon._catch_up()

        container.cloud_client.fetch_events_since.assert_called_with("owner/repo", 0, limit=100)
