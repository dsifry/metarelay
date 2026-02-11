"""Tests for daemon full lifecycle (run, shutdown, sync, reconnection)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metarelay.config import CloudConfig, MetarelayConfig, RepoConfig
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
        repos=[RepoConfig(name="owner/repo", path=str(tmp_path / "repo"))],
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
        async def fake_subscribe(
            repos: list, callback: object, on_status_change: object = None
        ) -> None:
            daemon._request_shutdown()

        container.cloud_client.subscribe.side_effect = fake_subscribe

        # Patch add_signal_handler since we're in a test event loop
        loop = asyncio.get_event_loop()
        with patch.object(loop, "add_signal_handler"):
            await daemon.run()

        container.cloud_client.connect.assert_awaited_once()
        container.cloud_client.subscribe.assert_awaited_once()
        container.cloud_client.disconnect.assert_awaited()
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

    @pytest.mark.asyncio
    async def test_run_reconnects_on_connection_lost(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)

        call_count = 0

        async def fake_subscribe(
            repos: list, callback: object, on_status_change: object = None
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First subscribe: simulate connection loss via status callback
                if on_status_change is not None:
                    on_status_change("CHANNEL_ERROR", Exception("ws closed"))
            else:
                # Second subscribe: shut down cleanly
                daemon._request_shutdown()

        container.cloud_client.subscribe.side_effect = fake_subscribe

        loop = asyncio.get_event_loop()
        with patch.object(loop, "add_signal_handler"):
            with patch("metarelay.daemon.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await daemon.run()

        assert call_count == 2
        # Connected twice (initial + reconnect)
        assert container.cloud_client.connect.await_count == 2
        # Disconnect called: once for reconnect cleanup + once in finally
        assert container.cloud_client.disconnect.await_count >= 2
        # Backoff sleep was called
        mock_sleep.assert_awaited_once_with(1.0)
        assert daemon.status == DaemonStatus.STOPPED

    @pytest.mark.asyncio
    async def test_run_reconnect_backoff_increases(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)

        call_count = 0

        async def fake_subscribe(
            repos: list, callback: object, on_status_change: object = None
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                # First 3 subscribes: simulate connection loss
                if on_status_change is not None:
                    on_status_change("TIMED_OUT", None)
            else:
                # 4th subscribe: shut down
                daemon._request_shutdown()

        container.cloud_client.subscribe.side_effect = fake_subscribe

        loop = asyncio.get_event_loop()
        with patch.object(loop, "add_signal_handler"):
            with patch("metarelay.daemon.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await daemon.run()

        assert call_count == 4
        # Backoff: 1.0, 2.0, 4.0
        sleep_args = [call.args[0] for call in mock_sleep.await_args_list]
        assert sleep_args == [1.0, 2.0, 4.0]

    @pytest.mark.asyncio
    async def test_run_resets_backoff_on_successful_subscribe(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)

        call_count = 0

        async def fake_subscribe(
            repos: list, callback: object, on_status_change: object = None
        ) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First: fail immediately (before backoff reset)
                if on_status_change is not None:
                    on_status_change("CHANNEL_ERROR", None)
            elif call_count == 2:
                # Second: succeed (backoff resets), then lose connection
                # Schedule error to fire after subscribe returns (on next event loop tick)
                loop = asyncio.get_event_loop()
                loop.call_soon(on_status_change, "CHANNEL_ERROR", None)
            else:
                # Third: shut down
                daemon._request_shutdown()

        container.cloud_client.subscribe.side_effect = fake_subscribe

        loop = asyncio.get_event_loop()
        with patch.object(loop, "add_signal_handler"):
            with patch("metarelay.daemon.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await daemon.run()

        # First sleep: 1.0 (immediate failure, no reset)
        # Second sleep: 1.0 (backoff was reset because subscribe returned cleanly)
        sleep_args = [call.args[0] for call in mock_sleep.await_args_list]
        assert sleep_args == [1.0, 1.0]

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


class TestSubscriptionStatus:
    """Tests for _on_subscription_status callback."""

    def test_channel_error_sets_connection_lost(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)
        daemon._connection_lost = asyncio.Event()

        daemon._on_subscription_status("CHANNEL_ERROR", Exception("test"))

        assert daemon._connection_lost.is_set()

    def test_timed_out_sets_connection_lost(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)
        daemon._connection_lost = asyncio.Event()

        daemon._on_subscription_status("TIMED_OUT", None)

        assert daemon._connection_lost.is_set()

    def test_subscribed_does_not_set_connection_lost(self, tmp_path: Path) -> None:
        container = make_container(tmp_path)
        daemon = Daemon(container)
        daemon._connection_lost = asyncio.Event()

        daemon._on_subscription_status("SUBSCRIBED", None)

        assert not daemon._connection_lost.is_set()

    def test_status_callback_without_connection_lost_event(self, tmp_path: Path) -> None:
        """Status callback is safe when called before run() initializes _connection_lost."""
        container = make_container(tmp_path)
        daemon = Daemon(container)
        # _connection_lost is None before run()
        daemon._on_subscription_status("CHANNEL_ERROR", Exception("test"))


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
