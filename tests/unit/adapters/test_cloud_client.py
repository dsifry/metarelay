"""Tests for Supabase cloud client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from metarelay.adapters.cloud_client import SupabaseCloudClient
from metarelay.core.errors import ConnectionError


class TestSupabaseCloudClient:
    """Tests for SupabaseCloudClient."""

    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_supabase = AsyncMock()
        mock_acreate = AsyncMock(return_value=mock_supabase)

        import supabase as supabase_mod

        with patch.object(supabase_mod, "acreate_client", mock_acreate):
            await client.connect()

        assert client._client is mock_supabase

    @pytest.mark.asyncio
    async def test_connect_failure_raises_connection_error(self) -> None:
        client = SupabaseCloudClient("https://bad.supabase.co", "bad-key")
        mock_acreate = AsyncMock(side_effect=Exception("connection failed"))

        import supabase as supabase_mod

        with patch.object(supabase_mod, "acreate_client", mock_acreate):
            with pytest.raises(ConnectionError, match="Failed to connect"):
                await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect_without_channel(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_disconnect_with_channel(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        client._client = AsyncMock()
        client._channel = MagicMock()
        await client.disconnect()
        assert client._channel is None

    @pytest.mark.asyncio
    async def test_disconnect_with_channel_error_suppressed(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        client._client = AsyncMock()
        client._client.realtime.unsubscribe.side_effect = Exception("unsub error")
        client._channel = MagicMock()
        await client.disconnect()
        assert client._channel is None

    @pytest.mark.asyncio
    async def test_fetch_events_not_connected_raises(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        with pytest.raises(ConnectionError, match="Not connected"):
            await client.fetch_events_since("owner/repo", 0)

    @pytest.mark.asyncio
    async def test_fetch_events_success(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")

        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": 1,
                "repo": "owner/repo",
                "event_type": "check_run",
                "action": "completed",
                "ref": "main",
                "actor": "user",
                "summary": "CI Build",
                "payload": {"conclusion": "success"},
                "delivery_id": "d-1",
            }
        ]

        # Build chained async mock — each method returns an object
        # whose next method returns itself, until execute() returns the response
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.gt.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        # execute is the final async call
        chain.execute = AsyncMock(return_value=mock_response)

        mock_client = MagicMock()
        mock_client.table.return_value = chain
        client._client = mock_client

        events = await client.fetch_events_since("owner/repo", 0, limit=50)
        assert len(events) == 1
        assert events[0].id == 1
        assert events[0].repo == "owner/repo"

    @pytest.mark.asyncio
    async def test_fetch_events_error_raises_connection_error(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("query failed")
        client._client = mock_client

        with pytest.raises(ConnectionError, match="Failed to fetch"):
            await client.fetch_events_since("owner/repo", 0)

    @pytest.mark.asyncio
    async def test_subscribe_not_connected_raises(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        with pytest.raises(ConnectionError, match="Not connected"):
            await client.subscribe(["owner/repo"], lambda e: None)

    @pytest.mark.asyncio
    async def test_subscribe_success(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_channel = MagicMock()
        mock_channel.subscribe = AsyncMock()
        mock_client.realtime.channel.return_value = mock_channel
        client._client = mock_client

        callback = MagicMock()
        await client.subscribe(["owner/repo"], callback)

        mock_channel.on_postgres_changes.assert_called_once()
        mock_channel.subscribe.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_subscribe_error_raises(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_client.realtime.channel.side_effect = Exception("subscribe failed")
        client._client = mock_client

        with pytest.raises(ConnectionError, match="Failed to subscribe"):
            await client.subscribe(["owner/repo"], lambda e: None)

    @pytest.mark.asyncio
    async def test_subscribe_callback_filters_by_repo(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_channel = MagicMock()
        mock_channel.subscribe = AsyncMock()
        mock_client.realtime.channel.return_value = mock_channel
        client._client = mock_client

        callback = MagicMock()
        await client.subscribe(["owner/repo"], callback)
        on_event = mock_channel.on_postgres_changes.call_args[1]["callback"]

        # Matching repo
        on_event(
            {
                "record": {
                    "id": 1,
                    "repo": "owner/repo",
                    "event_type": "check_run",
                    "action": "completed",
                }
            }
        )
        assert callback.call_count == 1

        # Non-matching repo
        on_event(
            {
                "record": {
                    "id": 2,
                    "repo": "other/repo",
                    "event_type": "check_run",
                    "action": "completed",
                }
            }
        )
        assert callback.call_count == 1

    @pytest.mark.asyncio
    async def test_subscribe_callback_handles_empty_payload(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_channel = MagicMock()
        mock_channel.subscribe = AsyncMock()
        mock_client.realtime.channel.return_value = mock_channel
        client._client = mock_client

        callback = MagicMock()
        await client.subscribe(["owner/repo"], callback)
        on_event = mock_channel.on_postgres_changes.call_args[1]["callback"]
        on_event({})
        assert callback.call_count == 0

    @pytest.mark.asyncio
    async def test_subscribe_callback_handles_parse_error(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_channel = MagicMock()
        mock_channel.subscribe = AsyncMock()
        mock_client.realtime.channel.return_value = mock_channel
        client._client = mock_client

        callback = MagicMock()
        await client.subscribe(["owner/repo"], callback)
        on_event = mock_channel.on_postgres_changes.call_args[1]["callback"]
        on_event({"record": {"repo": "owner/repo"}})  # Missing required 'id'
        assert callback.call_count == 0

    @pytest.mark.asyncio
    async def test_subscribe_status_callback_with_enum(self) -> None:
        """Status callback extracts .value from enum-like status objects."""
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_channel = MagicMock()
        mock_channel.subscribe = AsyncMock()
        mock_client.realtime.channel.return_value = mock_channel
        client._client = mock_client

        status_callback = MagicMock()
        await client.subscribe(["owner/repo"], MagicMock(), on_status_change=status_callback)

        # Get the callback passed to channel.subscribe()
        on_status = mock_channel.subscribe.call_args[1]["callback"]

        # Simulate enum-like status with .value attribute
        enum_status = MagicMock()
        enum_status.value = "SUBSCRIBED"
        on_status(enum_status)

        status_callback.assert_called_once_with("SUBSCRIBED", None)

    @pytest.mark.asyncio
    async def test_subscribe_status_callback_with_string(self) -> None:
        """Status callback handles plain string status."""
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_channel = MagicMock()
        mock_channel.subscribe = AsyncMock()
        mock_client.realtime.channel.return_value = mock_channel
        client._client = mock_client

        status_callback = MagicMock()
        await client.subscribe(["owner/repo"], MagicMock(), on_status_change=status_callback)

        on_status = mock_channel.subscribe.call_args[1]["callback"]
        err = Exception("test")
        on_status("CHANNEL_ERROR", err)

        status_callback.assert_called_once()
        args = status_callback.call_args[0]
        assert args[0] == "CHANNEL_ERROR"
        assert args[1] is err

    @pytest.mark.asyncio
    async def test_subscribe_status_callback_none(self) -> None:
        """Status callback works when on_status_change is not provided."""
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_channel = MagicMock()
        mock_channel.subscribe = AsyncMock()
        mock_client.realtime.channel.return_value = mock_channel
        client._client = mock_client

        await client.subscribe(["owner/repo"], MagicMock())

        on_status = mock_channel.subscribe.call_args[1]["callback"]
        # Should not raise even without on_status_change
        on_status("SUBSCRIBED")

    @pytest.mark.asyncio
    async def test_subscribe_callback_uses_new_key(self) -> None:
        client = SupabaseCloudClient("https://test.supabase.co", "test-key")
        mock_client = MagicMock()
        mock_channel = MagicMock()
        mock_channel.subscribe = AsyncMock()
        mock_client.realtime.channel.return_value = mock_channel
        client._client = mock_client

        callback = MagicMock()
        await client.subscribe(["owner/repo"], callback)
        on_event = mock_channel.on_postgres_changes.call_args[1]["callback"]
        on_event(
            {
                "new": {
                    "id": 5,
                    "repo": "owner/repo",
                    "event_type": "check_run",
                    "action": "completed",
                }
            }
        )
        assert callback.call_count == 1
