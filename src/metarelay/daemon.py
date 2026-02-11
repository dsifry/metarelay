"""Metarelay daemon: async event loop with catch-up and live subscription."""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path

from metarelay.container import Container
from metarelay.core.models import DaemonStatus, Event, HandlerResultStatus

logger = logging.getLogger(__name__)

# Reconnection backoff constants
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 60.0


class Daemon:
    """Async daemon that catches up on missed events then subscribes to live events.

    Features a supervised reconnection loop: if the WebSocket subscription
    drops (CHANNEL_ERROR or TIMED_OUT), the daemon disconnects, waits with
    exponential backoff, reconnects, catches up on missed events, and
    resubscribes.
    """

    def __init__(self, container: Container) -> None:
        self._container = container
        self._status = DaemonStatus.STOPPED
        self._shutdown_event: asyncio.Event | None = None
        self._connection_lost: asyncio.Event | None = None

    @property
    def status(self) -> DaemonStatus:
        """Current daemon status."""
        return self._status

    async def run(self) -> None:
        """Main daemon loop with supervised reconnection.

        Loop: connect → catch-up → subscribe → wait for shutdown or connection loss.
        On connection loss: disconnect, backoff, reconnect, catch-up, resubscribe.
        """
        self._shutdown_event = asyncio.Event()
        self._connection_lost = asyncio.Event()
        self._status = DaemonStatus.STARTING

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._request_shutdown)

        backoff = _INITIAL_BACKOFF

        try:
            while not self._shutdown_event.is_set():
                self._connection_lost.clear()

                logger.info("Connecting to Supabase...")
                await self._container.cloud_client.connect()

                logger.info("Catching up on missed events...")
                self._status = DaemonStatus.CATCHING_UP
                await self._catch_up()

                logger.info("Subscribing to live events...")
                self._status = DaemonStatus.LIVE
                await self._container.cloud_client.subscribe(
                    self._container.config.repo_names,
                    self._handle_event,
                    on_status_change=self._on_subscription_status,
                )

                logger.info("Metarelay daemon is live. Waiting for events...")
                if not self._connection_lost.is_set():
                    backoff = _INITIAL_BACKOFF  # Reset only if still connected

                # Race: shutdown vs connection loss
                shutdown_task = asyncio.create_task(self._shutdown_event.wait())
                lost_task = asyncio.create_task(self._connection_lost.wait())

                done, pending = await asyncio.wait(
                    [shutdown_task, lost_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                if self._shutdown_event.is_set():
                    break

                # Connection lost — disconnect and reconnect with backoff
                self._status = DaemonStatus.RECONNECTING
                await self._container.cloud_client.disconnect()

                logger.warning(
                    "Connection lost. Reconnecting in %.0fs...",
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

        except Exception:
            self._status = DaemonStatus.ERROR
            logger.exception("Daemon error")
            raise
        finally:
            self._status = DaemonStatus.SHUTTING_DOWN
            logger.info("Shutting down...")
            await self._container.cloud_client.disconnect()
            self._status = DaemonStatus.STOPPED

    def _on_subscription_status(self, status: str, error: Exception | None) -> None:
        """Handle subscription status changes from the cloud client."""
        if status == "CHANNEL_ERROR" or status == "TIMED_OUT":
            logger.warning("Subscription %s: %s", status, error)
            if self._connection_lost is not None:
                self._connection_lost.set()

    async def _catch_up(self) -> None:
        """Paginated catch-up: fetch events since last cursor for each repo."""
        for repo in self._container.config.repo_names:
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
        """Process a single event: dedup → write event file → match → dispatch → advance cursor."""
        # Dedup check
        if self._container.event_store.has_event(event.id):
            logger.debug("Skipping duplicate event %d", event.id)
            return

        # Write to per-repo event file (for persistent subagents)
        self._write_event_file(event)

        # Find matching handlers
        handlers = self._container.registry.match(event)
        if not handlers:
            logger.debug(
                "No handlers matched event %d (%s/%s)",
                event.id,
                event.event_type,
                event.action,
            )
        else:
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

        # Always advance cursor
        self._container.event_store.set_cursor(event.repo, event.id)

    def _write_event_file(self, event: Event) -> None:
        """Append event as JSONL to the repo's local .metarelay/events.jsonl."""
        repo_path = self._container.config.repo_path(event.repo)
        if repo_path is None:
            return

        event_dir = Path(repo_path).expanduser() / ".metarelay"
        event_dir.mkdir(parents=True, exist_ok=True)
        event_file = event_dir / "events.jsonl"

        with open(event_file, "a") as f:
            f.write(event.model_dump_json() + "\n")

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
