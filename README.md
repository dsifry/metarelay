# Metarelay

**Event-driven orchestration for Claude Code.** Metarelay replaces GitHub API polling with a lightweight webhook relay — GitHub pushes events to Supabase, and your local daemon dispatches AI agents in response.

CI fails? An agent investigates and pushes a fix. PR review posted? An agent addresses the feedback. No polling, no manual intervention.

## How It Works

```
GitHub webhooks ──→ Supabase Edge Function ──→ PostgreSQL
                                                   │
                                          Realtime WebSocket
                                                   │
                                            Local daemon
                                                   │
                                    ┌──────────────┼──────────────┐
                                    ▼              ▼              ▼
                             PR Shepherd    Handle Reviews    Custom handlers
                            (claude -p)     (claude -p)      (any command)
```

**On startup**, the daemon catches up on any events it missed (cursor-based pagination). Then it subscribes to live events via WebSocket. Events are deduplicated at both cloud and local levels — handlers never fire twice for the same event.

## Quick Start

```bash
# Install
git clone https://github.com/dsifry/metarelay.git
cd metarelay
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Configure (after setting up Supabase — see cloud/setup.md)
mkdir -p ~/.metarelay
cp config.example.yaml ~/.metarelay/config.yaml
# Edit with your Supabase URL, key, and repos

# Run
metarelay start
```

See [INSTALL.md](INSTALL.md) for detailed installation instructions.

## Example: Auto-Fix CI Failures

Add this handler to your `~/.metarelay/config.yaml`:

```yaml
handlers:
  - name: "fix-ci-failure"
    event_type: "check_run"
    action: "completed"
    command: >-
      claude -p 'CI check "{{summary}}" failed on branch {{ref}}
      in {{repo}}. Conclusion: {{payload.conclusion}}.
      Investigate the failure and push a fix.'
    filters:
      - "payload.conclusion == 'failure'"
```

When CI fails, metarelay resolves the `{{variables}}` against the event and runs the command. Claude Code investigates, identifies the issue, and pushes a fix — all automatically.

## Documentation

| Document | Description |
|----------|-------------|
| **[INSTALL.md](INSTALL.md)** | Prerequisites, installation, and setup |
| **[USAGE.md](USAGE.md)** | Configuration, CLI reference, writing handlers, troubleshooting |
| **[AGENTS.md](AGENTS.md)** | How metarelay integrates with Claude Code and other AI agents |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | Development setup, architecture, testing, PR process |
| **[cloud/setup.md](cloud/setup.md)** | Supabase and GitHub App setup (step-by-step) |
| **[CLAUDE.md](CLAUDE.md)** | Instructions for AI agents working on this codebase |

## CLI

```
metarelay start [-c CONFIG] [-v]    Start the daemon (foreground)
metarelay sync [-c CONFIG] [-v]     One-shot catch-up (no live subscription)
metarelay status [-c CONFIG]        Show cursor positions per repo
metarelay --version                 Print version
```

## Supported Events

| Event | Use Case |
|-------|----------|
| `check_run` | CI check pass/fail |
| `check_suite` | CI suite results |
| `workflow_run` | GitHub Actions workflow results |
| `pull_request_review` | PR review submissions |
| `pull_request_review_comment` | PR inline comments |

## Architecture

Hexagonal architecture with dependency injection. Business logic depends on abstract ports, not concrete implementations — making it straightforward to test (158 tests, 100% coverage) and extend.

```
core/interfaces.py     ← Ports (abstract)
adapters/              ← Implementations (Supabase, SQLite, subprocess)
container.py           ← Wires ports to adapters
daemon.py              ← Event loop (catch-up → subscribe → dispatch)
handlers/registry.py   ← Routes events to handlers
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full architecture guide.

## Related Projects

- **[goodtogo](https://github.com/dsifry/goodtogo)** — Claude Code workflow system (PR Shepherd, session management, task tracking)
- **[warmstart-tng](https://github.com/dsifry/warmstart-tng)** — CI/CD actions for Claude Code

## License

[MIT](LICENSE)
