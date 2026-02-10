"""Tests for DI container."""

from __future__ import annotations

from pathlib import Path

import pytest

from metarelay.config import CloudConfig, MetarelayConfig
from metarelay.container import Container


class TestContainer:
    """Tests for Container factories."""

    def test_create_for_testing_defaults(self) -> None:
        container = Container.create_for_testing()
        assert container.config is not None
        assert container.config.repos == ["test/repo"]

    def test_create_for_testing_with_custom_config(self) -> None:
        config = MetarelayConfig(
            cloud=CloudConfig(supabase_url="https://x.supabase.co", supabase_key="k"),
            repos=["custom/repo"],
        )
        container = Container.create_for_testing(config=config)
        assert container.config.repos == ["custom/repo"]

    def test_create_for_testing_stubs_raise(self) -> None:
        container = Container.create_for_testing()
        with pytest.raises(NotImplementedError):
            container.event_store.get_cursor("test/repo")
        with pytest.raises(NotImplementedError):
            container.dispatcher.dispatch(None, None)  # type: ignore[arg-type]

    def test_create_default(self, tmp_path: Path) -> None:
        config = MetarelayConfig(
            cloud=CloudConfig(
                supabase_url="https://test.supabase.co",
                supabase_key="test-key",
            ),
            repos=["owner/repo"],
            db_path=str(tmp_path / "test.db"),
            handlers=[],
        )
        container = Container.create_default(config)
        assert container.event_store is not None
        assert container.cloud_client is not None
        assert container.dispatcher is not None

    def test_create_default_registers_handlers(self, tmp_path: Path) -> None:
        config = MetarelayConfig(
            cloud=CloudConfig(
                supabase_url="https://test.supabase.co",
                supabase_key="test-key",
            ),
            repos=["owner/repo"],
            db_path=str(tmp_path / "test.db"),
            handlers=[
                {
                    "name": "h1",
                    "event_type": "check_run",
                    "action": "completed",
                    "command": "echo test",
                }
            ],
        )
        container = Container.create_default(config)
        # Registry should have the registered handler
        from metarelay.core.models import Event

        event = Event(id=1, repo="owner/repo", event_type="check_run", action="completed")
        matches = container.registry.match(event)
        assert len(matches) == 1
        assert matches[0].name == "h1"
