"""Handler registry: routes events to matching handler configurations."""

from __future__ import annotations

import logging
import re
from typing import Any

from metarelay.core.models import Event, HandlerConfig

logger = logging.getLogger(__name__)

# Filter expression pattern: field == 'value' or field != 'value'
_FILTER_PATTERN = re.compile(r"^(\w+(?:\.\w+)*)\s*(==|!=)\s*['\"](.+?)['\"]$")


class HandlerRegistry:
    """Routes (event_type, action) pairs to matching HandlerConfigs."""

    def __init__(self, handlers: list[HandlerConfig] | None = None) -> None:
        self._handlers: list[HandlerConfig] = list(handlers) if handlers else []

    def register(self, handler: HandlerConfig) -> None:
        """Register a handler configuration."""
        self._handlers.append(handler)

    def match(self, event: Event) -> list[HandlerConfig]:
        """Find all handlers matching an event.

        Matches on (event_type, action) and then evaluates filters.
        Returns only enabled handlers.
        """
        matches = []
        for handler in self._handlers:
            if not handler.enabled:
                continue
            if handler.event_type != event.event_type:
                continue
            if handler.action != event.action:
                continue
            if not _evaluate_filters(handler.filters, event):
                continue
            matches.append(handler)
        return matches


def _evaluate_filters(filters: list[str], event: Event) -> bool:
    """Evaluate filter expressions against an event.

    Each filter is a string like:
        payload.conclusion == 'failure'
        actor != 'bot'

    All filters must pass (AND logic).
    """
    for filter_expr in filters:
        match = _FILTER_PATTERN.match(filter_expr.strip())
        if match is None:
            logger.warning("Invalid filter expression: %s", filter_expr)
            return False

        field_path, operator, expected = match.groups()
        actual = _resolve_field(field_path, event)

        if operator == "==" and str(actual) != expected:
            return False
        if operator == "!=" and str(actual) == expected:
            return False

    return True


def _resolve_field(field_path: str, event: Event) -> Any:
    """Resolve a dotted field path against an event."""
    parts = field_path.split(".")
    event_dict = event.model_dump()

    if parts[0] == "payload":
        value: Any = event.payload
        for part in parts[1:]:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None
        return value

    return event_dict.get(parts[0])
