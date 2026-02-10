"""Tests for core domain models."""

from __future__ import annotations

from metarelay.core.models import (
    CursorPosition,
    DaemonStatus,
    Event,
    EventType,
    HandlerConfig,
    HandlerResult,
    HandlerResultStatus,
)


class TestEvent:
    """Tests for Event model."""

    def test_create_minimal(self) -> None:
        event = Event(id=1, repo="owner/repo", event_type="check_run", action="completed")
        assert event.id == 1
        assert event.repo == "owner/repo"
        assert event.ref is None
        assert event.payload == {}

    def test_create_full(self) -> None:
        event = Event(
            id=1,
            repo="owner/repo",
            event_type="check_run",
            action="completed",
            ref="main",
            actor="user",
            summary="CI passed",
            payload={"conclusion": "success"},
            delivery_id="abc-123",
        )
        assert event.ref == "main"
        assert event.payload["conclusion"] == "success"


class TestHandlerConfig:
    """Tests for HandlerConfig model."""

    def test_defaults(self) -> None:
        hc = HandlerConfig(
            name="test", event_type="check_run", action="completed", command="echo hi"
        )
        assert hc.timeout == 300
        assert hc.enabled is True
        assert hc.filters == []


class TestHandlerResult:
    """Tests for HandlerResult model."""

    def test_success_result(self) -> None:
        result = HandlerResult(
            handler_name="test",
            status=HandlerResultStatus.SUCCESS,
            exit_code=0,
            duration_seconds=1.5,
        )
        assert result.status == HandlerResultStatus.SUCCESS
        assert result.exit_code == 0


class TestEnums:
    """Tests for enum values."""

    def test_event_types(self) -> None:
        assert EventType.CHECK_RUN.value == "check_run"
        assert EventType.PULL_REQUEST_REVIEW.value == "pull_request_review"

    def test_handler_result_statuses(self) -> None:
        assert HandlerResultStatus.SUCCESS.value == "success"
        assert HandlerResultStatus.TIMEOUT.value == "timeout"

    def test_daemon_statuses(self) -> None:
        assert DaemonStatus.STARTING.value == "starting"
        assert DaemonStatus.LIVE.value == "live"


class TestCursorPosition:
    """Tests for CursorPosition model."""

    def test_create(self) -> None:
        cursor = CursorPosition(repo="owner/repo", last_event_id=42)
        assert cursor.repo == "owner/repo"
        assert cursor.last_event_id == 42
