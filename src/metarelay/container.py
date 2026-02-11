"""Dependency injection container for metarelay."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from metarelay.config import MetarelayConfig
from metarelay.core.interfaces import CloudClientPort, DispatcherPort, EventStorePort
from metarelay.handlers.registry import HandlerRegistry


@dataclass
class Container:
    """DI container holding all ports and adapters."""

    config: MetarelayConfig
    event_store: EventStorePort
    cloud_client: CloudClientPort
    dispatcher: DispatcherPort
    registry: HandlerRegistry

    @staticmethod
    def create_default(config: MetarelayConfig) -> Container:
        """Create a container with production adapters."""
        from metarelay.adapters.agent_dispatcher import AgentDispatcher
        from metarelay.adapters.cloud_client import SupabaseCloudClient
        from metarelay.adapters.local_store import SqliteEventStore
        from metarelay.core.models import HandlerConfig

        db_path = str(Path(config.db_path).expanduser())
        event_store = SqliteEventStore(db_path)

        cloud_client = SupabaseCloudClient(
            supabase_url=config.cloud.supabase_url,
            supabase_key=config.cloud.supabase_key,
        )

        dispatcher = AgentDispatcher()

        registry = HandlerRegistry()
        for h in config.handlers:
            registry.register(
                HandlerConfig(
                    name=h.name,
                    event_type=h.event_type,
                    action=h.action,
                    command=h.command,
                    filters=h.filters,
                    timeout=h.timeout,
                    enabled=h.enabled,
                )
            )

        return Container(
            config=config,
            event_store=event_store,
            cloud_client=cloud_client,
            dispatcher=dispatcher,
            registry=registry,
        )

    @staticmethod
    def create_for_testing(
        config: MetarelayConfig | None = None,
        event_store: EventStorePort | None = None,
        cloud_client: CloudClientPort | None = None,
        dispatcher: DispatcherPort | None = None,
        registry: HandlerRegistry | None = None,
    ) -> Container:
        """Create a container with test/mock adapters.

        All parameters are optional. Provide mocks for the components
        you want to control in tests.
        """
        from metarelay.config import CloudConfig, RepoConfig

        if config is None:
            config = MetarelayConfig(
                cloud=CloudConfig(
                    supabase_url="https://test.supabase.co",
                    supabase_key="test-key",
                ),
                repos=[RepoConfig(name="test/repo", path="/tmp/test/repo")],
            )

        # Use stubs that raise if accidentally called without being mocked
        class StubEventStore(EventStorePort):
            def get_cursor(self, repo: str) -> None:
                raise NotImplementedError("Provide a mock event_store")

            def set_cursor(self, repo: str, last_event_id: int) -> None:
                raise NotImplementedError("Provide a mock event_store")

            def log_event(self, event: object, result: object) -> None:
                raise NotImplementedError("Provide a mock event_store")

            def has_event(self, remote_id: int) -> bool:
                raise NotImplementedError("Provide a mock event_store")

        class StubCloudClient(CloudClientPort):
            async def connect(self) -> None:
                raise NotImplementedError("Provide a mock cloud_client")

            async def disconnect(self) -> None:
                pass

            async def fetch_events_since(self, repo: str, after_id: int, limit: int = 100) -> list:
                raise NotImplementedError("Provide a mock cloud_client")

            async def subscribe(
                self, repos: list, callback: object, on_status_change: object = None
            ) -> None:
                raise NotImplementedError("Provide a mock cloud_client")

        class StubDispatcher(DispatcherPort):
            def dispatch(self, handler: object, event: object) -> None:  # type: ignore[override]
                raise NotImplementedError("Provide a mock dispatcher")

        return Container(
            config=config,
            event_store=event_store or StubEventStore(),
            cloud_client=cloud_client or StubCloudClient(),
            dispatcher=dispatcher or StubDispatcher(),
            registry=registry or HandlerRegistry(),
        )
