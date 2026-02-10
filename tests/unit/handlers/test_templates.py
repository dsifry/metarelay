"""Tests for built-in handler templates."""

from __future__ import annotations

from metarelay.handlers.templates import (
    ALL_TEMPLATES,
    handle_pr_review_comment,
    handle_pr_review_submitted,
    pr_shepherd_ci_failure,
    pr_shepherd_workflow_failure,
)


class TestTemplates:
    """Tests for handler template factory functions."""

    def test_pr_shepherd_ci_failure(self) -> None:
        handler = pr_shepherd_ci_failure()
        assert handler.name == "pr-shepherd-ci-failure"
        assert handler.event_type == "check_run"
        assert handler.action == "completed"
        assert "{{repo}}" in handler.command
        assert "payload.conclusion == 'failure'" in handler.filters
        assert handler.enabled is True

    def test_pr_shepherd_workflow_failure(self) -> None:
        handler = pr_shepherd_workflow_failure()
        assert handler.name == "pr-shepherd-workflow-failure"
        assert handler.event_type == "workflow_run"
        assert handler.action == "completed"
        assert "{{repo}}" in handler.command

    def test_handle_pr_review_comment(self) -> None:
        handler = handle_pr_review_comment()
        assert handler.name == "handle-review-comment"
        assert handler.event_type == "pull_request_review_comment"
        assert handler.action == "created"
        assert "{{actor}}" in handler.command

    def test_handle_pr_review_submitted(self) -> None:
        handler = handle_pr_review_submitted()
        assert handler.name == "handle-review-submitted"
        assert handler.event_type == "pull_request_review"
        assert handler.action == "submitted"

    def test_all_templates_list(self) -> None:
        assert len(ALL_TEMPLATES) == 4
        for factory in ALL_TEMPLATES:
            handler = factory()
            assert handler.name
            assert handler.event_type
            assert handler.command


class TestCloudClient:
    """Tests for cloud client with mocked Supabase (basic structure validation)."""

    def test_row_to_event(self) -> None:
        from metarelay.adapters.cloud_client import _row_to_event

        row = {
            "id": 42,
            "repo": "owner/repo",
            "event_type": "check_run",
            "action": "completed",
            "ref": "main",
            "actor": "testuser",
            "summary": "CI Build",
            "payload": {"conclusion": "success"},
            "delivery_id": "abc-123",
        }
        event = _row_to_event(row)
        assert event.id == 42
        assert event.repo == "owner/repo"
        assert event.payload["conclusion"] == "success"

    def test_row_to_event_minimal(self) -> None:
        from metarelay.adapters.cloud_client import _row_to_event

        row = {
            "id": 1,
            "repo": "owner/repo",
            "event_type": "workflow_run",
        }
        event = _row_to_event(row)
        assert event.id == 1
        assert event.action == ""
        assert event.payload == {}
