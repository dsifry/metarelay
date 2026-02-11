"""Domain models for metarelay."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """GitHub webhook event types that metarelay handles."""

    CHECK_RUN = "check_run"
    CHECK_SUITE = "check_suite"
    WORKFLOW_RUN = "workflow_run"
    PULL_REQUEST_REVIEW = "pull_request_review"
    PULL_REQUEST_REVIEW_COMMENT = "pull_request_review_comment"


class Event(BaseModel):
    """A webhook event received from GitHub via Supabase."""

    id: int = Field(description="Remote event ID from Supabase")
    repo: str = Field(description="Full repo name (owner/repo)")
    event_type: str = Field(description="GitHub event type")
    action: str = Field(description="Event action (e.g. completed, submitted)")
    ref: str | None = Field(default=None, description="Git ref (branch/tag)")
    actor: str | None = Field(default=None, description="GitHub username who triggered")
    summary: str | None = Field(default=None, description="Human-readable summary")
    payload: dict[str, Any] = Field(default_factory=dict, description="Full event payload")
    delivery_id: str | None = Field(default=None, description="GitHub delivery ID for dedup")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When event was created",
    )


class HandlerConfig(BaseModel):
    """Configuration for a handler that responds to events."""

    name: str = Field(description="Handler identifier")
    event_type: str = Field(description="GitHub event type to match")
    action: str = Field(description="Event action to match")
    command: str = Field(description="Command template to execute")
    filters: list[str] = Field(
        default_factory=list,
        description="Filter expressions (field == value)",
    )
    timeout: int = Field(default=300, description="Execution timeout in seconds")
    enabled: bool = Field(default=True, description="Whether handler is active")


class HandlerResultStatus(str, Enum):
    """Outcome of a handler execution."""

    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"
    ERROR = "error"


class HandlerResult(BaseModel):
    """Result of dispatching a handler for an event."""

    handler_name: str = Field(description="Name of the handler that ran")
    status: HandlerResultStatus = Field(description="Execution outcome")
    exit_code: int | None = Field(default=None, description="Process exit code")
    output: str | None = Field(default=None, description="Captured stdout/stderr")
    duration_seconds: float | None = Field(default=None, description="Execution time")


class CursorPosition(BaseModel):
    """Tracks the last processed event ID per repo."""

    repo: str = Field(description="Full repo name (owner/repo)")
    last_event_id: int = Field(description="ID of last processed event")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When cursor was updated",
    )


class DaemonStatus(str, Enum):
    """Current state of the metarelay daemon."""

    STARTING = "starting"
    CATCHING_UP = "catching_up"
    LIVE = "live"
    RECONNECTING = "reconnecting"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"
    ERROR = "error"
