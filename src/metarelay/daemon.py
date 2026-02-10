"""Metarelay daemon: async event loop with catch-up and live subscription."""

from __future__ import annotations

import asyncio
import logging
import signal

from metarelay.container import Container
from metarelay.core.models import DaemonStatus, Event, HandlerResultStatus

logger = logging.getLogger(__name__)


class Daemon:
    """Async daemon that catches up on missed events then subscribes to live events."""

    def __init__(self, container: Container) -> None:
        self._container = container
        self._status = DaemonStatus.STOPPED
        self._shutdown_event: asyncio.Event | None = None

    @property
    def status(self) -> DaemonStatus:
        """Current daemon status."""
        return self._status

    async def run(self) -> None:
        """Main daemon loop: catch-up → subscribe → wait for shutdown."""
        self._shutdown_event = asyncio.Event()
        self._status = DaemonStatus.STARTING

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._request_shutdown)

        try:
            logger.info("Connecting to Supabase...")
            await self._container.cloud_client.connect()

            logger.info("Catching up on missed events...")
            self._status = DaemonStatus.CATCHING_UP
            await self._catch_up()

            logger.info("Subscribing to live events...")
            self._status = DaemonStatus.LIVE
            await self._container.cloud_client.subscribe(
                self._container.config.repos, self._handle_event
            )

            logger.info("Metarelay daemon is live. Waiting for events...")
            await self._shutdown_event.wait()

        except Exception:
            self._status = DaemonStatus.ERROR
            logger.exception("Daemon error")
            raise
        finally:
            self._status = DaemonStatus.SHUTTING_DOWN
            logger.info("Shutting down...")
            await self._container.cloud_client.disconnect()
            self._status = DaemonStatus.STOPPED

    async def _catch_up(self) -> None:
        """Paginated catch-up: fetch events since last cursor for each repo."""
        for repo in self._container.config.repos:
            cursor = self._container.event_store.get_cursor(repo)
            after_id = cursor.last_event_id if cursor else 0

            logger.info("Catching up %s from event %d", repo, after_id)

            while True:
                events = await self._container.cloud_client.fetch_events_since(
                    repo, after_id, limit=100
                )
                if not events:
                    break

                for event in events:
                    self._handle_event(event)
                    after_id = event.id

    def _handle_event(self, event: Event) -> None:
        """Process a single event: dedup → match → dispatch → log → advance cursor."""
        # Dedup check
        if self._container.event_store.has_event(event.id):
            logger.debug("Skipping duplicate event %d", event.id)
            return

        # Find matching handlers
        handlers = self._container.registry.match(event)
        if not handlers:
            logger.debug(
                "No handlers matched event %d (%s/%s)",
                event.id,
                event.event_type,
                event.action,
            )
            return

        for handler in handlers:
            logger.info(
                "Dispatching handler %s for event %d (%s/%s)",
                handler.name,
                event.id,
                event.event_type,
                event.action,
            )

            result = self._container.dispatcher.dispatch(handler, event)

            # Log event + result
            self._container.event_store.log_event(event, result)

            if result.status == HandlerResultStatus.SUCCESS:
                logger.info(
                    "Handler %s succeeded (%.1fs)",
                    handler.name,
                    result.duration_seconds or 0,
                )
            else:
                logger.warning(
                    "Handler %s finished with status %s: %s",
                    handler.name,
                    result.status.value,
                    result.output,
                )

        # Advance cursor
        self._container.event_store.set_cursor(event.repo, event.id)

    def _request_shutdown(self) -> None:
        """Signal the daemon to shut down gracefully."""
        logger.info("Shutdown signal received")
        if self._shutdown_event is not None:
            self._shutdown_event.set()


async def run_sync(container: Container) -> None:
    """One-shot catch-up sync without subscribing to live events."""
    daemon = Daemon(container)
    daemon._status = DaemonStatus.CATCHING_UP

    await container.cloud_client.connect()
    try:
        await daemon._catch_up()
    finally:
        await container.cloud_client.disconnect()
        daemon._status = DaemonStatus.STOPPED
