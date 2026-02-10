# CLAUDE.md

Instructions for Claude Code when working with the metarelay repository.

## Overview

Metarelay is a webhook-based event relay that receives GitHub webhook events via Supabase, stores them in PostgreSQL, and dispatches Claude Code agents locally in response to CI failures, PR reviews, etc.

## Essential Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Format
black .

# Type check
mypy src/

# Quality gate (run before completing any task)
pytest && ruff check . && black --check . && mypy src/
```

## Architecture

Hexagonal architecture with ports and adapters:

```
src/metarelay/
├── core/
│   ├── models.py          # Pydantic domain models (Event, HandlerConfig, etc.)
│   ├── interfaces.py      # Port interfaces (EventStorePort, CloudClientPort, DispatcherPort)
│   └── errors.py          # Error hierarchy with sensitive data redaction
├── adapters/
│   ├── cloud_client.py    # Supabase REST + Realtime adapter
│   ├── local_store.py     # SQLite cursor tracking + event dedup
│   └── agent_dispatcher.py # subprocess-based command execution
├── handlers/
│   ├── registry.py        # Routes (event_type, action) → HandlerConfig
│   └── templates.py       # Built-in handler templates
├── container.py            # DI container with create_default/create_for_testing
├── daemon.py               # Async event loop: catch-up → subscribe → dispatch
├── config.py               # YAML config loading + Pydantic validation
└── cli.py                  # Click CLI: start, status, sync
```

## Key Files

| File | Purpose |
|------|---------|
| `src/metarelay/core/interfaces.py` | Port definitions — start here to understand the architecture |
| `src/metarelay/daemon.py` | Main event loop — catch-up + Realtime subscription |
| `src/metarelay/container.py` | DI container — `create_for_testing()` for tests |
| `src/metarelay/handlers/registry.py` | Event routing with filter evaluation |
| `src/metarelay/adapters/agent_dispatcher.py` | Template resolution + subprocess execution |
| `cloud/supabase/functions/github-webhook/index.ts` | Edge Function (TypeScript/Deno) |

## How To Add a New Handler

1. Add a handler entry in your `config.yaml`:
   ```yaml
   handlers:
     - name: "my-handler"
       event_type: "workflow_run"
       action: "completed"
       command: "claude -p 'Handle {{summary}} in {{repo}}'"
       filters:
         - "payload.conclusion == 'failure'"
   ```

2. Or add a template in `src/metarelay/handlers/templates.py`:
   ```python
   def my_handler() -> HandlerConfig:
       return HandlerConfig(
           name="my-handler",
           event_type="workflow_run",
           action="completed",
           command="claude -p 'Handle {{summary}} in {{repo}}'",
           filters=["payload.conclusion == 'failure'"],
       )
   ```

## How To Add a New Event Type

1. Add the event type to `EventType` enum in `core/models.py`
2. Add extraction logic in `cloud/supabase/functions/github-webhook/index.ts`:
   - `extractRef()` — how to find the git ref
   - `extractSummary()` — human-readable summary
3. Add the event to `github-app/app.yml` under `default_events`
4. Update the GitHub App's webhook subscriptions

## Testing Without Supabase

Use `Container.create_for_testing()` to get a container with stub adapters:

```python
from metarelay.container import Container
from unittest.mock import AsyncMock, MagicMock

container = Container.create_for_testing(
    cloud_client=AsyncMock(),
    dispatcher=MagicMock(),
)
```

The real `SqliteEventStore` can be used in tests with a temp path.

## Testing Patterns

- Unit tests mock external deps (Supabase, subprocess)
- Integration tests use real SQLite + mocked cloud
- `tests/conftest.py` has shared fixtures: `make_event()`, `test_config`, `test_container`
- Use `pytest.mark.asyncio` for async tests

## Critical Guidelines

- **NEVER commit secrets** — config.yaml and .env are in .gitignore
- **Run quality gate before PRs** — `pytest && ruff check . && black --check . && mypy src/`
- **Follow hexagonal architecture** — new adapters implement ports from `core/interfaces.py`
- **Use Container DI** — never instantiate adapters directly in business logic
- **Redact errors** — use `redact_error()` from `core/errors.py` when logging exceptions that might contain tokens
