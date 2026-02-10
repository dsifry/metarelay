"""Tests for handler registry and filter evaluation."""

from __future__ import annotations

from metarelay.core.models import Event, HandlerConfig
from metarelay.handlers.registry import HandlerRegistry, _evaluate_filters


def make_event(**kwargs: object) -> Event:
    """Create a test event with defaults."""
    defaults: dict = {
        "id": 1,
        "repo": "owner/repo",
        "event_type": "check_run",
        "action": "completed",
        "actor": "testuser",
        "payload": {"conclusion": "failure"},
    }
    defaults.update(kwargs)
    return Event(**defaults)


def make_handler(**kwargs: object) -> HandlerConfig:
    """Create a test handler config."""
    defaults: dict = {
        "name": "test-handler",
        "event_type": "check_run",
        "action": "completed",
        "command": "echo test",
    }
    defaults.update(kwargs)
    return HandlerConfig(**defaults)


class TestHandlerRegistry:
    """Tests for HandlerRegistry.match()."""

    def test_match_by_event_type_and_action(self) -> None:
        registry = HandlerRegistry()
        handler = make_handler()
        registry.register(handler)

        matches = registry.match(make_event())
        assert len(matches) == 1
        assert matches[0].name == "test-handler"

    def test_no_match_wrong_event_type(self) -> None:
        registry = HandlerRegistry()
        registry.register(make_handler(event_type="workflow_run"))

        matches = registry.match(make_event())
        assert len(matches) == 0

    def test_no_match_wrong_action(self) -> None:
        registry = HandlerRegistry()
        registry.register(make_handler(action="started"))

        matches = registry.match(make_event())
        assert len(matches) == 0

    def test_disabled_handler_not_matched(self) -> None:
        registry = HandlerRegistry()
        registry.register(make_handler(enabled=False))

        matches = registry.match(make_event())
        assert len(matches) == 0

    def test_multiple_handlers_match(self) -> None:
        registry = HandlerRegistry()
        registry.register(make_handler(name="handler-1"))
        registry.register(make_handler(name="handler-2"))

        matches = registry.match(make_event())
        assert len(matches) == 2

    def test_filter_match(self) -> None:
        registry = HandlerRegistry()
        registry.register(make_handler(filters=["payload.conclusion == 'failure'"]))

        matches = registry.match(make_event())
        assert len(matches) == 1

    def test_filter_no_match(self) -> None:
        registry = HandlerRegistry()
        registry.register(make_handler(filters=["payload.conclusion == 'success'"]))

        matches = registry.match(make_event())
        assert len(matches) == 0

    def test_filter_not_equal(self) -> None:
        registry = HandlerRegistry()
        registry.register(make_handler(filters=["actor != 'bot'"]))

        matches = registry.match(make_event(actor="testuser"))
        assert len(matches) == 1

    def test_filter_not_equal_blocks(self) -> None:
        registry = HandlerRegistry()
        registry.register(make_handler(filters=["actor != 'testuser'"]))

        matches = registry.match(make_event(actor="testuser"))
        assert len(matches) == 0

    def test_constructor_with_handlers(self) -> None:
        handlers = [make_handler(name="h1"), make_handler(name="h2")]
        registry = HandlerRegistry(handlers)
        matches = registry.match(make_event())
        assert len(matches) == 2


class TestFilterEvaluation:
    """Tests for filter expression evaluation."""

    def test_payload_equality(self) -> None:
        event = make_event(payload={"conclusion": "failure"})
        assert _evaluate_filters(["payload.conclusion == 'failure'"], event)

    def test_payload_inequality(self) -> None:
        event = make_event(payload={"conclusion": "success"})
        assert not _evaluate_filters(["payload.conclusion == 'failure'"], event)

    def test_top_level_field(self) -> None:
        event = make_event(actor="bot")
        assert _evaluate_filters(["actor == 'bot'"], event)

    def test_double_quotes_in_filter(self) -> None:
        event = make_event(actor="bot")
        assert _evaluate_filters(['actor == "bot"'], event)

    def test_multiple_filters_all_must_pass(self) -> None:
        event = make_event(actor="testuser", payload={"conclusion": "failure"})
        assert _evaluate_filters(
            ["actor == 'testuser'", "payload.conclusion == 'failure'"],
            event,
        )

    def test_multiple_filters_one_fails(self) -> None:
        event = make_event(actor="testuser", payload={"conclusion": "success"})
        assert not _evaluate_filters(
            ["actor == 'testuser'", "payload.conclusion == 'failure'"],
            event,
        )

    def test_empty_filters_passes(self) -> None:
        event = make_event()
        assert _evaluate_filters([], event)

    def test_invalid_filter_expression_fails(self) -> None:
        event = make_event()
        assert not _evaluate_filters(["garbage filter"], event)

    def test_missing_payload_field_returns_none(self) -> None:
        event = make_event(payload={})
        assert not _evaluate_filters(["payload.missing == 'value'"], event)
