"""Supabase cloud client for event fetching and Realtime subscription."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from metarelay.core.errors import ConnectionError
from metarelay.core.interfaces import CloudClientPort
from metarelay.core.models import Event

logger = logging.getLogger(__name__)


class SupabaseCloudClient(CloudClientPort):
    """Cloud client using Supabase REST for catch-up and Realtime for live events."""

    def __init__(self, supabase_url: str, supabase_key: str) -> None:
        self._url = supabase_url
        self._key = supabase_key
        self._client: Any = None
        self._channel: Any = None

    async def connect(self) -> None:
        """Establish async connection to Supabase."""
        try:
            from supabase import acreate_client

            self._client = await acreate_client(self._url, self._key)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Supabase: {e}") from e

    async def disconnect(self) -> None:
        """Close Supabase connection and unsubscribe from channels."""
        if self._channel is not None:
            try:
                await self._client.realtime.unsubscribe(self._channel)
            except Exception:
                pass
            self._channel = None

    async def fetch_events_since(self, repo: str, after_id: int, limit: int = 100) -> list[Event]:
        """Fetch events from Supabase REST API for catch-up.

        Queries the events table for rows with id > after_id,
        ordered by id ascending, limited to `limit` rows.
        """
        if self._client is None:
            raise ConnectionError("Not connected. Call connect() first.")

        try:
            response = (
                await self._client.table("events")
                .select("*")
                .eq("repo", repo)
                .gt("id", after_id)
                .order("id")
                .limit(limit)
                .execute()
            )
        except Exception as e:
            raise ConnectionError(f"Failed to fetch events: {e}") from e

        events = []
        for row in response.data:
            events.append(_row_to_event(row))
        return events

    async def subscribe(
        self,
        repos: list[str],
        callback: Callable[[Event], None],
        on_status_change: Callable[[str, Exception | None], None] | None = None,
    ) -> None:
        """Subscribe to live events via Supabase Realtime.

        Listens for INSERT events on the events table and calls
        the callback for each new event matching the watched repos.
        """
        if self._client is None:
            raise ConnectionError("Not connected. Call connect() first.")

        repo_set = set(repos)

        def on_event(payload: dict[str, Any]) -> None:
            """Handle a Realtime INSERT event."""
            record = payload.get("record") or payload.get("new", {})
            if not record:
                return
            if record.get("repo") not in repo_set:
                return
            try:
                event = _row_to_event(record)
                callback(event)
            except Exception:
                logger.exception("Failed to process Realtime event")

        def on_subscribe_status(status: Any, error: Exception | None = None) -> None:
            """Forward Supabase subscription status to the daemon."""
            status_str = str(status.value) if hasattr(status, "value") else str(status)
            logger.info("Subscription status: %s", status_str)
            if on_status_change is not None:
                on_status_change(status_str, error)

        try:
            self._channel = self._client.realtime.channel("events")
            self._channel.on_postgres_changes(
                "INSERT",
                schema="public",
                table="events",
                callback=on_event,
            )
            await self._channel.subscribe(callback=on_subscribe_status)
        except Exception as e:
            raise ConnectionError(f"Failed to subscribe to Realtime: {e}") from e


def _row_to_event(row: dict[str, Any]) -> Event:
    """Convert a Supabase row dict to an Event model."""
    return Event(
        id=row["id"],
        repo=row["repo"],
        event_type=row["event_type"],
        action=row.get("action", ""),
        ref=row.get("ref"),
        actor=row.get("actor"),
        summary=row.get("summary"),
        payload=row.get("payload") or {},
        delivery_id=row.get("delivery_id"),
    )
