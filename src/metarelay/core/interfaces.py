"""Port interfaces for metarelay (hexagonal architecture)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from metarelay.core.models import CursorPosition, Event, HandlerConfig, HandlerResult


class EventStorePort(ABC):
    """Port for local event persistence and cursor management."""

    @abstractmethod
    def get_cursor(self, repo: str) -> CursorPosition | None:
        """Get the current cursor position for a repo.

        Args:
            repo: Full repo name (owner/repo).

        Returns:
            CursorPosition if one exists, None otherwise.
        """

    @abstractmethod
    def set_cursor(self, repo: str, last_event_id: int) -> None:
        """Update the cursor position for a repo.

        Args:
            repo: Full repo name (owner/repo).
            last_event_id: ID of the last processed event.
        """

    @abstractmethod
    def log_event(self, event: Event, result: HandlerResult) -> None:
        """Log a processed event and its handler result.

        Args:
            event: The event that was processed.
            result: The handler execution result.
        """

    @abstractmethod
    def has_event(self, remote_id: int) -> bool:
        """Check if an event has already been processed (dedup).

        Args:
            remote_id: The remote event ID from Supabase.

        Returns:
            True if the event has already been logged.
        """


class CloudClientPort(ABC):
    """Port for communication with the Supabase cloud backend."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the cloud backend."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the cloud backend."""

    @abstractmethod
    async def fetch_events_since(self, repo: str, after_id: int, limit: int = 100) -> list[Event]:
        """Fetch events from cloud after the given ID (for catch-up).

        Args:
            repo: Full repo name (owner/repo).
            after_id: Fetch events with ID greater than this.
            limit: Maximum events to fetch per call.

        Returns:
            List of events ordered by ID ascending.
        """

    @abstractmethod
    async def subscribe(
        self,
        repos: list[str],
        callback: Callable[[Event], None],
        on_status_change: Callable[[str, Exception | None], None] | None = None,
    ) -> None:
        """Subscribe to live events via Realtime WebSocket.

        Args:
            repos: List of repo names to subscribe to.
            callback: Function called for each new event.
            on_status_change: Optional callback for subscription status changes.
                Called with (status, error) where status is one of:
                "SUBSCRIBED", "CHANNEL_ERROR", "TIMED_OUT".
        """


class DispatcherPort(ABC):
    """Port for dispatching handlers in response to events."""

    @abstractmethod
    def dispatch(self, handler: HandlerConfig, event: Event) -> HandlerResult:
        """Execute a handler for the given event.

        Args:
            handler: Handler configuration with command template.
            event: The event to handle.

        Returns:
            HandlerResult with execution outcome.
        """
