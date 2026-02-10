"""Tests for daemon full lifecycle (run, shutdown, sync)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metarelay.config import CloudConfig, MetarelayConfig
from metarelay.container import Container
from metarelay.core.models import (
    DaemonStatus,
    Event,
    HandlerConfig,
    HandlerResult,
    HandlerResultStatus,
)
from metarelay.daemon import Daemon, run_sync
from metarelay.handlers.registry import HandlerRegistry


def make_container(tmp_path: Path) -> Container:
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
        handler_name="t", status=HandlerResultStatus.SUCCESS, exit_code=0, duration_seconds=0.1
    )
    return Container(
        config=config,
        event_store=event_store,
        cloud_client=cloud_client,
        dispatcher=dispatcher,
        registry=HandlerRegistry(),
    )


class TestDaemonRun:
    """Tests for Daemon.run() lifecycle."""

    @pytest.mark.asyncio
    async def test_run_connects_catches_up_subscribes_and_shuts_down(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)

        # Make subscribe trigger shutdown
        async def fake_subscribe(repos: list, callback: object) -> None:
            daemon._request_shutdown()

        container.cloud_client.subscribe.side_effect = fake_subscribe

        # Patch add_signal_handler since we're in a test event loop
        loop = asyncio.get_event_loop()
        with patch.object(loop, "add_signal_handler"):
            await daemon.run()

        container.cloud_client.connect.assert_awaited_once()
        container.cloud_client.subscribe.assert_awaited_once()
        container.cloud_client.disconnect.assert_awaited_once()
        assert daemon.status == DaemonStatus.STOPPED

    @pytest.mark.asyncio
    async def test_run_error_sets_error_status(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        container.cloud_client.connect.side_effect = Exception("connection failed")
        daemon = Daemon(container)

        loop = asyncio.get_event_loop()
        with patch.object(loop, "add_signal_handler"):
            with pytest.raises(Exception, match="connection failed"):
                await daemon.run()

        assert daemon.status == DaemonStatus.STOPPED

    def test_status_property(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)
        assert daemon.status == DaemonStatus.STOPPED

    def test_request_shutdown_without_event(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)
        daemon._request_shutdown()

    def test_handle_event_with_failed_handler(self, tmp_path: Path) -> None:
        handler = HandlerConfig(
            name="h", event_type="check_run", action="completed", command="echo"
        )
        container = make_container(tmp_path)
        container.registry = HandlerRegistry([handler])
        container.dispatcher.dispatch.return_value = HandlerResult(
            handler_name="h",
            status=HandlerResultStatus.FAILURE,
            exit_code=1,
            output="error output",
            duration_seconds=0.5,
        )
        daemon = Daemon(container)

        event = Event(id=1, repo="owner/repo", event_type="check_run", action="completed")
        daemon._handle_event(event)

        container.dispatcher.dispatch.assert_called_once()
        container.event_store.log_event.assert_called_once()


class TestRunSync:
    """Tests for one-shot sync."""

    @pytest.mark.asyncio
    async def test_run_sync_connects_catches_up_disconnects(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        await run_sync(container)

        container.cloud_client.connect.assert_awaited_once()
        container.cloud_client.fetch_events_since.assert_awaited()
        container.cloud_client.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_sync_disconnects_on_error(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        container.cloud_client.fetch_events_since.side_effect = Exception("fetch error")

        with pytest.raises(Exception, match="fetch error"):
            await run_sync(container)

        container.cloud_client.disconnect.assert_awaited_once()
