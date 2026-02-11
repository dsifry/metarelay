"""Integration test: full relay flow with mock Supabase."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from metarelay.adapters.local_store import SqliteEventStore
from metarelay.config import CloudConfig, MetarelayConfig, RepoConfig
from metarelay.container import Container
from metarelay.core.models import (
    Event,
    HandlerConfig,
    HandlerResult,
    HandlerResultStatus,
)
from metarelay.daemon import Daemon
from metarelay.handlers.registry import HandlerRegistry


def make_event(id: int, conclusion: str = "failure") -> Event:
    """Create a test event."""
    return Event(
        id=id,
        repo="owner/repo",
        event_type="check_run",
        action="completed",
        ref="feat/test",
        actor="testuser",
        summary="CI Build",
        payload={"conclusion": conclusion},
        delivery_id=f"delivery-{id}",
    )


@pytest.fixture()
def relay_setup(tmp_path: Path) -> tuple[Container, Daemon]:
    """Set up a full relay with real store, mocked cloud/dispatcher."""
    config = MetarelayConfig(
        cloud=CloudConfig(
            supabase_url="https://test.supabase.co",
            supabase_key="test-key",
        ),
        repos=[RepoConfig(name="owner/repo", path=str(tmp_path / "repo"))],
        db_path=str(tmp_path / "relay.db"),
    )

    event_store = SqliteEventStore(str(tmp_path / "relay.db"))

    cloud_client = AsyncMock()

    dispatcher = MagicMock()
    dispatcher.dispatch.return_value = HandlerResult(
        handler_name="pr-shepherd",
        status=HandlerResultStatus.SUCCESS,
        exit_code=0,
        duration_seconds=1.0,
    )

    handler = HandlerConfig(
        name="pr-shepherd",
        event_type="check_run",
        action="completed",
        command="claude -p 'Fix {{repo}}'",
        filters=["payload.conclusion == 'failure'"],
    )
    registry = HandlerRegistry([handler])

    container = Container(
        config=config,
        event_store=event_store,
        cloud_client=cloud_client,
        dispatcher=dispatcher,
        registry=registry,
    )

    return container, Daemon(container)


class TestFullRelayFlow:
    """Integration test: catch-up → realtime → dispatch → cursor."""

    @pytest.mark.asyncio
    async def test_catch_up_processes_events(self, relay_setup: tuple) -> None:
        container, daemon = relay_setup

        # Mock catch-up returns 3 events, then empty
        events = [make_event(1), make_event(2), make_event(3)]
        container.cloud_client.fetch_events_since.side_effect = [events, []]

        await daemon._catch_up()

        # All 3 events dispatched
        assert container.dispatcher.dispatch.call_count == 3

        # Cursor advanced to event 3
        cursor = container.event_store.get_cursor("owner/repo")
        assert cursor is not None
        assert cursor.last_event_id == 3

    @pytest.mark.asyncio
    async def test_catch_up_then_realtime_event(self, relay_setup: tuple) -> None:
        container, daemon = relay_setup

        # Catch-up returns 1 event
        container.cloud_client.fetch_events_since.side_effect = [
            [make_event(1)],
            [],
        ]

        await daemon._catch_up()
        assert container.dispatcher.dispatch.call_count == 1

        # Simulate Realtime event
        daemon._handle_event(make_event(2))

        assert container.dispatcher.dispatch.call_count == 2
        cursor = container.event_store.get_cursor("owner/repo")
        assert cursor is not None
        assert cursor.last_event_id == 2

    @pytest.mark.asyncio
    async def test_dedup_prevents_double_processing(self, relay_setup: tuple) -> None:
        container, daemon = relay_setup

        # Catch-up returns event 1
        container.cloud_client.fetch_events_since.side_effect = [
            [make_event(1)],
            [],
        ]

        await daemon._catch_up()
        assert container.dispatcher.dispatch.call_count == 1

        # Realtime delivers same event 1 again (overlap)
        daemon._handle_event(make_event(1))

        # Should still only be 1 dispatch (dedup kicked in)
        assert container.dispatcher.dispatch.call_count == 1

    @pytest.mark.asyncio
    async def test_filter_skips_non_matching_events(self, relay_setup: tuple) -> None:
        container, daemon = relay_setup

        # Event with conclusion=success should not match the failure filter
        success_event = make_event(10, conclusion="success")
        daemon._handle_event(success_event)

        container.dispatcher.dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_cursor_advances_per_event(self, relay_setup: tuple) -> None:
        container, daemon = relay_setup

        daemon._handle_event(make_event(5))
        cursor = container.event_store.get_cursor("owner/repo")
        assert cursor is not None
        assert cursor.last_event_id == 5

        daemon._handle_event(make_event(10))
        cursor = container.event_store.get_cursor("owner/repo")
        assert cursor is not None
        assert cursor.last_event_id == 10


class TestCLIIntegration:
    """Integration tests for CLI commands with real components."""

    def test_status_shows_cursor_after_processing(self, tmp_path: Path) -> None:
        """Verify status command reflects cursor state."""
        import yaml
        from click.testing import CliRunner

        from metarelay.cli import main

        # Create config
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

        # Pre-populate cursor
        from metarelay.adapters.local_store import SqliteEventStore

        store = SqliteEventStore(str(tmp_path / "test.db"))
        store.set_cursor("owner/repo", 42)
        store.close()

        runner = CliRunner()
        result = runner.invoke(main, ["status", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "last_event_id=42" in result.output
