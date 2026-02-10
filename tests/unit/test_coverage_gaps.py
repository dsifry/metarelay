"""Tests to cover remaining coverage gaps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from metarelay.adapters.agent_dispatcher import AgentDispatcher
from metarelay.adapters.local_store import SqliteEventStore
from metarelay.config import load_config
from metarelay.container import Container
from metarelay.core.errors import DispatchError, EventStoreError
from metarelay.core.models import Event, HandlerConfig
from metarelay.handlers.registry import _resolve_field


class TestLocalStoreErrorHandling:
    """Cover local_store error paths."""

    def test_connection_failure_raises_event_store_error(self, tmp_path: Path) -> None:
        bad_path = str(tmp_path / "nonexistent_dir" / "deep" / "nested" / "test.db")
        store = SqliteEventStore(bad_path)
        assert store is not None

    def test_sqlite_connect_error(self, tmp_path: Path) -> None:
        """Force sqlite3.connect to fail."""
        import sqlite3

        store = SqliteEventStore(str(tmp_path / "ok.db"))
        store.close()
        store._connection = None

        with patch(
            "metarelay.adapters.local_store.sqlite3.connect",
            side_effect=sqlite3.Error("disk I/O error"),
        ):
            with pytest.raises(EventStoreError, match="Failed to connect"):
                store.get_cursor("owner/repo")


class TestAgentDispatcherErrors:
    """Cover agent_dispatcher error paths."""

    def test_dispatch_raises_dispatch_error_on_unexpected(self) -> None:
        dispatcher = AgentDispatcher()
        handler = HandlerConfig(
            name="test",
            event_type="check_run",
            action="completed",
            command="echo {{repo}}",
        )
        event = Event(id=1, repo="owner/repo", event_type="check_run", action="completed")

        with patch(
            "metarelay.adapters.agent_dispatcher.subprocess.run",
            side_effect=OSError("exec failed"),
        ):
            with pytest.raises(DispatchError, match="Failed to execute"):
                dispatcher.dispatch(handler, event)

    def test_dispatch_truncates_long_output(self) -> None:
        dispatcher = AgentDispatcher()
        handler = HandlerConfig(
            name="test",
            event_type="check_run",
            action="completed",
            command="echo test",
        )
        event = Event(id=1, repo="owner/repo", event_type="check_run", action="completed")

        with patch("metarelay.adapters.agent_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "x" * 20000
            mock_run.return_value.stderr = ""
            result = dispatcher.dispatch(handler, event)

        assert result.output is not None
        assert len(result.output) <= 10000

    def test_dispatch_combines_stdout_and_stderr(self) -> None:
        dispatcher = AgentDispatcher()
        handler = HandlerConfig(
            name="test",
            event_type="check_run",
            action="completed",
            command="echo test",
        )
        event = Event(id=1, repo="owner/repo", event_type="check_run", action="completed")

        with patch("metarelay.adapters.agent_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "stdout"
            mock_run.return_value.stderr = "stderr"
            result = dispatcher.dispatch(handler, event)

        assert result.output is not None
        assert "stdout" in result.output
        assert "stderr" in result.output

    def test_dispatch_stderr_only(self) -> None:
        dispatcher = AgentDispatcher()
        handler = HandlerConfig(
            name="test",
            event_type="check_run",
            action="completed",
            command="echo test",
        )
        event = Event(id=1, repo="owner/repo", event_type="check_run", action="completed")

        with patch("metarelay.adapters.agent_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "error only"
            result = dispatcher.dispatch(handler, event)

        assert result.output == "error only"


class TestResolveTemplateNonDictPayload:
    """Cover resolve_template payload path hitting non-dict value."""

    def test_nested_payload_non_dict_returns_empty(self) -> None:
        from metarelay.adapters.agent_dispatcher import resolve_template

        event = Event(
            id=1,
            repo="owner/repo",
            event_type="check_run",
            action="completed",
            payload={"check_run": "a_string_not_dict"},
        )
        result = resolve_template("{{payload.check_run.name}}", event)
        assert result == ""


class TestRegistryResolveField:
    """Cover _resolve_field edge cases."""

    def test_resolve_non_dict_payload_nested(self) -> None:
        event = Event(
            id=1,
            repo="owner/repo",
            event_type="check_run",
            action="completed",
            payload={"check_run": "not_a_dict"},
        )
        result = _resolve_field("payload.check_run.name", event)
        assert result is None


class TestContainerStubs:
    """Cover container stub methods."""

    def test_stub_event_store_set_cursor(self) -> None:
        container = Container.create_for_testing()
        with pytest.raises(NotImplementedError):
            container.event_store.set_cursor("repo", 1)

    def test_stub_event_store_log_event(self) -> None:
        container = Container.create_for_testing()
        with pytest.raises(NotImplementedError):
            container.event_store.log_event(None, None)  # type: ignore[arg-type]

    def test_stub_event_store_has_event(self) -> None:
        container = Container.create_for_testing()
        with pytest.raises(NotImplementedError):
            container.event_store.has_event(1)

    @pytest.mark.asyncio
    async def test_stub_cloud_client_connect(self) -> None:
        container = Container.create_for_testing()
        with pytest.raises(NotImplementedError):
            await container.cloud_client.connect()

    @pytest.mark.asyncio
    async def test_stub_cloud_client_disconnect(self) -> None:
        container = Container.create_for_testing()
        # disconnect should not raise
        await container.cloud_client.disconnect()

    @pytest.mark.asyncio
    async def test_stub_cloud_client_fetch(self) -> None:
        container = Container.create_for_testing()
        with pytest.raises(NotImplementedError):
            await container.cloud_client.fetch_events_since("repo", 0)

    @pytest.mark.asyncio
    async def test_stub_cloud_client_subscribe(self) -> None:
        container = Container.create_for_testing()
        with pytest.raises(NotImplementedError):
            await container.cloud_client.subscribe(["repo"], lambda e: None)


class TestConfigReadError:
    """Cover config file read error."""

    def test_unreadable_file_raises_config_error(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("cloud: {}")
        config_file.chmod(0o000)

        from metarelay.core.errors import ConfigError

        try:
            with pytest.raises(ConfigError, match="Cannot read"):
                load_config(str(config_file))
        finally:
            # Restore permissions for cleanup
            config_file.chmod(0o644)
