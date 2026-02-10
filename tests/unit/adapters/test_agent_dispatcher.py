"""Tests for agent dispatcher and template resolution."""

from __future__ import annotations

from unittest.mock import patch

from metarelay.adapters.agent_dispatcher import AgentDispatcher, resolve_template
from metarelay.core.models import Event, HandlerConfig, HandlerResultStatus


def make_event(**kwargs: object) -> Event:
    """Create a test event with defaults."""
    defaults: dict = {
        "id": 1,
        "repo": "owner/repo",
        "event_type": "check_run",
        "action": "completed",
        "ref": "feat/my-branch",
        "actor": "testuser",
        "summary": "CI Build",
        "payload": {"conclusion": "failure", "name": "build"},
    }
    defaults.update(kwargs)
    return Event(**defaults)


def make_handler(**kwargs: object) -> HandlerConfig:
    """Create a test handler config with defaults."""
    defaults: dict = {
        "name": "test-handler",
        "event_type": "check_run",
        "action": "completed",
        "command": "echo '{{repo}} {{action}}'",
    }
    defaults.update(kwargs)
    return HandlerConfig(**defaults)


class TestResolveTemplate:
    """Tests for template resolution."""

    def test_resolve_basic_fields(self) -> None:
        event = make_event()
        result = resolve_template("{{repo}} {{action}}", event)
        assert result == "owner/repo completed"

    def test_resolve_ref_and_actor(self) -> None:
        event = make_event()
        result = resolve_template("{{ref}} by {{actor}}", event)
        assert result == "feat/my-branch by testuser"

    def test_resolve_payload_field(self) -> None:
        event = make_event()
        result = resolve_template("conclusion: {{payload.conclusion}}", event)
        assert result == "conclusion: failure"

    def test_resolve_nested_payload(self) -> None:
        event = make_event(payload={"check": {"name": "lint", "status": "done"}})
        result = resolve_template("{{payload.check.name}}", event)
        assert result == "lint"

    def test_unresolvable_placeholder_becomes_empty(self) -> None:
        event = make_event()
        result = resolve_template("{{nonexistent}}", event)
        assert result == ""

    def test_none_field_becomes_empty(self) -> None:
        event = make_event(ref=None)
        result = resolve_template("ref={{ref}}", event)
        assert result == "ref="

    def test_no_placeholders_unchanged(self) -> None:
        event = make_event()
        result = resolve_template("plain text", event)
        assert result == "plain text"

    def test_mixed_text_and_placeholders(self) -> None:
        event = make_event()
        result = resolve_template(
            "Check {{summary}} in {{repo}} concluded {{payload.conclusion}}",
            event,
        )
        assert result == "Check CI Build in owner/repo concluded failure"


class TestAgentDispatcher:
    """Tests for AgentDispatcher.dispatch()."""

    def test_successful_dispatch(self) -> None:
        dispatcher = AgentDispatcher()
        handler = make_handler(command="echo hello")
        event = make_event()

        with patch("metarelay.adapters.agent_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "hello\n"
            mock_run.return_value.stderr = ""
            result = dispatcher.dispatch(handler, event)

        assert result.status == HandlerResultStatus.SUCCESS
        assert result.exit_code == 0
        assert result.handler_name == "test-handler"

    def test_failed_dispatch(self) -> None:
        dispatcher = AgentDispatcher()
        handler = make_handler(command="false")
        event = make_event()

        with patch("metarelay.adapters.agent_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "error\n"
            result = dispatcher.dispatch(handler, event)

        assert result.status == HandlerResultStatus.FAILURE
        assert result.exit_code == 1

    def test_timeout_dispatch(self) -> None:
        dispatcher = AgentDispatcher()
        handler = make_handler(command="sleep 999", timeout=1)
        event = make_event()

        import subprocess

        with patch("metarelay.adapters.agent_dispatcher.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("sleep", 1)
            result = dispatcher.dispatch(handler, event)

        assert result.status == HandlerResultStatus.TIMEOUT

    def test_template_resolution_in_command(self) -> None:
        dispatcher = AgentDispatcher()
        handler = make_handler(command="echo '{{repo}}'")
        event = make_event()

        with patch("metarelay.adapters.agent_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            dispatcher.dispatch(handler, event)

        call_args = mock_run.call_args
        assert "owner/repo" in call_args[0][0]

    def test_template_error_returns_error_result(self) -> None:
        dispatcher = AgentDispatcher()
        handler = make_handler(command="echo {{repo}}")
        event = make_event()

        with patch(
            "metarelay.adapters.agent_dispatcher.resolve_template",
            side_effect=Exception("bad template"),
        ):
            result = dispatcher.dispatch(handler, event)

        assert result.status == HandlerResultStatus.ERROR
        assert "Template resolution failed" in (result.output or "")

    def test_duration_recorded(self) -> None:
        dispatcher = AgentDispatcher()
        handler = make_handler(command="echo hi")
        event = make_event()

        with patch("metarelay.adapters.agent_dispatcher.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""
            result = dispatcher.dispatch(handler, event)

        assert result.duration_seconds is not None
        assert result.duration_seconds >= 0
