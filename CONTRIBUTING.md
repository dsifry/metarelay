# Contributing to Metarelay

## Development Setup

```bash
git clone https://github.com/dsifry/metarelay.git
cd metarelay
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Verify your setup:

```bash
pytest && ruff check . && black --check . && mypy src/
```

All 158 tests should pass with 100% coverage.

## Code Quality Standards

Every PR must pass the full quality gate:

```bash
pytest && ruff check . && black --check . && mypy src/
```

- **pytest**: All tests pass, 100% line coverage required
- **ruff**: No lint errors
- **black**: All files formatted (100 char line length)
- **mypy**: No type errors (strict mode)

## Architecture

Metarelay follows **hexagonal architecture** (ports and adapters):

```
core/interfaces.py    ← Abstract ports (EventStorePort, CloudClientPort, DispatcherPort)
     ↑
adapters/             ← Concrete implementations
  local_store.py      ← SQLite (implements EventStorePort)
  cloud_client.py     ← Supabase (implements CloudClientPort)
  agent_dispatcher.py ← subprocess (implements DispatcherPort)
     ↑
container.py          ← DI container wires ports to adapters
     ↑
daemon.py             ← Business logic (uses ports, not adapters)
cli.py                ← User interface
```

**Key principle**: Business logic in `daemon.py` and `handlers/` depends only on port interfaces, never on concrete adapters. This makes testing straightforward — inject mocks via `Container.create_for_testing()`.

## Project Layout

```
src/metarelay/
├── __init__.py              # Version
├── cli.py                   # Click CLI entry point
├── config.py                # YAML config loading + Pydantic validation
├── container.py             # DI container
├── daemon.py                # Async event loop
├── core/
│   ├── models.py            # Domain models (Event, HandlerConfig, etc.)
│   ├── interfaces.py        # Port interfaces (ABCs)
│   └── errors.py            # Error hierarchy + credential redaction
├── adapters/
│   ├── cloud_client.py      # Supabase REST + Realtime
│   ├── local_store.py       # SQLite cursor + event log
│   └── agent_dispatcher.py  # subprocess command execution
└── handlers/
    ├── registry.py          # Event → handler routing
    └── templates.py         # Built-in handler templates

tests/
├── conftest.py              # Shared fixtures
├── unit/                    # Fast, isolated tests (mocked deps)
│   ├── core/
│   ├── adapters/
│   └── handlers/
└── integration/             # Tests with real SQLite + mocked cloud
```

## Testing Patterns

### Writing unit tests

Unit tests mock external dependencies and test one component at a time:

```python
from unittest.mock import MagicMock, AsyncMock
from metarelay.container import Container

# Use create_for_testing() for quick setup
container = Container.create_for_testing(
    event_store=MagicMock(),
    cloud_client=AsyncMock(),
    dispatcher=MagicMock(),
)
```

### Writing integration tests

Integration tests use the real `SqliteEventStore` with a temp database and mock only the cloud:

```python
from metarelay.adapters.local_store import SqliteEventStore

def test_something(tmp_path):
    store = SqliteEventStore(str(tmp_path / "test.db"))
    # ... test with real SQLite
```

### Test fixtures

`tests/conftest.py` provides shared fixtures:

- `test_config` — a valid `MetarelayConfig` pointing to a temp DB
- `tmp_db_path` — a temp database path
- `test_store` — a ready-to-use `SqliteEventStore`
- `test_container` — a `Container` with real store, mocked cloud
- `make_event()` — factory for creating test events

## How to Add a New Event Type

1. Add the type to `EventType` enum in `src/metarelay/core/models.py`
2. Add extraction logic in `cloud/supabase/functions/github-webhook/index.ts`:
   - `extractRef()` — how to find the git ref for this event
   - `extractSummary()` — human-readable summary
3. Add the event name to `github-app/app.yml` under `default_events`
4. Add any necessary permissions to `default_permissions`
5. Write tests
6. Update the GitHub App's webhook subscriptions in the dashboard

## How to Add a New Adapter

1. Implement the appropriate port from `core/interfaces.py`
2. Add a factory path in `container.py` (or use `create_for_testing()`)
3. Write unit tests with the adapter isolated
4. Write integration tests showing the adapter works in the full pipeline

Example — adding a Redis event store:

```python
# src/metarelay/adapters/redis_store.py
from metarelay.core.interfaces import EventStorePort

class RedisEventStore(EventStorePort):
    def get_cursor(self, repo):
        ...
    def set_cursor(self, repo, last_event_id):
        ...
    # etc.
```

## Commit Messages

- Use present tense: "Add feature" not "Added feature"
- Keep the first line under 72 characters
- Reference issues where relevant: "Fix #42"

## Pull Request Process

1. Create a feature branch: `git checkout -b feat/my-feature`
2. Make your changes with tests
3. Run the quality gate: `pytest && ruff check . && black --check . && mypy src/`
4. Push and open a PR
5. Describe what you changed and why

## Security

- Never commit secrets, tokens, or credentials
- Config files with real values are gitignored (`config.yaml`, `.env`)
- The SQLite database uses secure file permissions (0600/0700)
- Error messages are redacted before logging (see `core/errors.py`)
- If you find a security issue, please report it privately
