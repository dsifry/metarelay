"""Agent dispatcher: executes handler commands via subprocess."""

from __future__ import annotations

import logging
import re
import subprocess
import time
from typing import Any

from metarelay.core.errors import DispatchError
from metarelay.core.interfaces import DispatcherPort
from metarelay.core.models import Event, HandlerConfig, HandlerResult, HandlerResultStatus

logger = logging.getLogger(__name__)

# Pattern for {{variable}} template placeholders
_TEMPLATE_PATTERN = re.compile(r"\{\{(\w+(?:\.\w+)*)\}\}")


class AgentDispatcher(DispatcherPort):
    """Dispatches handler commands by resolving templates and running subprocess."""

    def dispatch(self, handler: HandlerConfig, event: Event) -> HandlerResult:
        """Execute a handler command for the given event.

        Resolves {{variable}} placeholders in the command template
        against event fields and payload, then runs via subprocess.
        """
        try:
            command = resolve_template(handler.command, event)
        except Exception as e:
            return HandlerResult(
                handler_name=handler.name,
                status=HandlerResultStatus.ERROR,
                output=f"Template resolution failed: {e}",
            )

        logger.info("Dispatching handler %s: %s", handler.name, command)

        start = time.monotonic()
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=handler.timeout,
            )
            duration = time.monotonic() - start

            status = (
                HandlerResultStatus.SUCCESS
                if result.returncode == 0
                else HandlerResultStatus.FAILURE
            )

            output = result.stdout
            if result.stderr:
                output = f"{output}\n--- stderr ---\n{result.stderr}" if output else result.stderr

            return HandlerResult(
                handler_name=handler.name,
                status=status,
                exit_code=result.returncode,
                output=output[:10000] if output else None,
                duration_seconds=round(duration, 2),
            )

        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return HandlerResult(
                handler_name=handler.name,
                status=HandlerResultStatus.TIMEOUT,
                duration_seconds=round(duration, 2),
                output=f"Command timed out after {handler.timeout}s",
            )

        except Exception as e:
            raise DispatchError(f"Failed to execute handler {handler.name}: {e}") from e


def resolve_template(template: str, event: Event) -> str:
    """Resolve {{variable}} placeholders in a command template.

    Supports:
        {{repo}} — event.repo
        {{event_type}} — event.event_type
        {{action}} — event.action
        {{ref}} — event.ref
        {{actor}} — event.actor
        {{summary}} — event.summary
        {{payload.field}} — event.payload["field"]
        {{payload.nested.field}} — event.payload["nested"]["field"]

    Unresolvable placeholders are replaced with empty string.
    """
    event_dict = event.model_dump()

    def replacer(match: re.Match[str]) -> str:
        path = match.group(1)
        parts = path.split(".")

        if parts[0] == "payload":
            value: Any = event.payload
            for part in parts[1:]:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return ""
            return str(value) if value is not None else ""

        value = event_dict.get(parts[0])
        return str(value) if value is not None else ""

    return _TEMPLATE_PATTERN.sub(replacer, template)
