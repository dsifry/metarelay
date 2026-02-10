# Usage Guide

## How Metarelay Works

Metarelay is a local daemon that listens for GitHub webhook events relayed through Supabase. When events arrive (CI failures, PR reviews, etc.), it dispatches Claude Code agents to handle them automatically.

The flow:

```
1. Something happens on GitHub (CI fails, review posted)
2. GitHub sends a webhook to your Supabase Edge Function
3. The Edge Function stores the event in PostgreSQL
4. Your local metarelay daemon receives it via WebSocket
5. The daemon matches the event to a handler
6. The handler runs a command (typically invoking Claude Code)
```

## Running the Daemon

### Foreground (recommended for getting started)

```bash
metarelay start
```

The daemon connects to Supabase, catches up on any missed events since it last ran, then subscribes to live events. It runs until you press `Ctrl+C`.

### With verbose logging

```bash
metarelay start -v
```

Shows detailed debug output including every event received, handler matches, and dispatch results.

### With a custom config path

```bash
metarelay start -c /path/to/config.yaml
```

### Running in the background

Metarelay runs in the foreground by default. For persistent operation, use tmux, screen, or a systemd service:

```bash
# tmux
tmux new-session -d -s metarelay 'metarelay start'

# systemd (create ~/.config/systemd/user/metarelay.service)
# [Service]
# ExecStart=/path/to/.venv/bin/metarelay start
# Restart=on-failure
```

## One-Shot Sync

Process any missed events without subscribing to live updates:

```bash
metarelay sync
```

Useful for catching up after downtime, or for cron-based operation instead of a persistent daemon.

## Checking Status

```bash
metarelay status
```

Shows the cursor position (last processed event ID) for each watched repo. This tells you where in the event stream each repo is caught up to.

## Configuration Reference

Config file location: `~/.metarelay/config.yaml`

```yaml
# Required: Supabase connection
cloud:
  supabase_url: "https://YOUR-PROJECT.supabase.co"
  supabase_key: "YOUR-ANON-KEY"

# Required: repos to watch
repos:
  - "your-org/your-repo"
  - "your-org/another-repo"

# Optional: local database path (default: ~/.metarelay/metarelay.db)
db_path: "~/.metarelay/metarelay.db"

# Optional: logging level (default: INFO)
log_level: "INFO"

# Optional: handler definitions
handlers:
  - name: "handler-name"
    event_type: "check_run"         # GitHub event type
    action: "completed"             # Event action
    command: "echo '{{repo}}'"      # Command to run
    filters:                        # Optional filters (all must match)
      - "payload.conclusion == 'failure'"
    timeout: 300                    # Seconds before timeout (default: 300)
    enabled: true                   # Toggle without removing (default: true)
```

### Environment Variable Overrides

These override values in the config file:

| Variable | Overrides |
|----------|-----------|
| `METARELAY_SUPABASE_URL` | `cloud.supabase_url` |
| `METARELAY_SUPABASE_KEY` | `cloud.supabase_key` |

## Writing Handlers

Handlers define what happens when specific GitHub events arrive. Each handler matches on `event_type` + `action`, optionally filters on payload fields, and runs a command.

### Template Variables

Commands use `{{variable}}` placeholders that are resolved against the event:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `{{repo}}` | Full repo name | `myorg/myrepo` |
| `{{event_type}}` | GitHub event type | `check_run` |
| `{{action}}` | Event action | `completed` |
| `{{ref}}` | Git branch/tag | `feat/my-feature` |
| `{{actor}}` | GitHub username | `octocat` |
| `{{summary}}` | Human-readable summary | `CI Build failure` |
| `{{payload.field}}` | Top-level payload field | `failure` |
| `{{payload.a.b}}` | Nested payload field | _(varies)_ |

Unresolvable placeholders become empty strings (no errors).

### Filter Expressions

Filters narrow which events trigger a handler. All filters must pass (AND logic).

```yaml
filters:
  - "payload.conclusion == 'failure'"     # Equality
  - "actor != 'dependabot[bot]'"          # Inequality
  - "payload.check_run.name == 'build'"   # Nested fields
```

Values must be quoted with single or double quotes.

### Example Handlers

**Invoke PR Shepherd on CI failure:**

```yaml
- name: "pr-shepherd-ci-failure"
  event_type: "check_run"
  action: "completed"
  command: >-
    claude -p 'The CI check "{{summary}}" failed on branch {{ref}}
    in {{repo}}. Investigate the failure and fix it.
    Run /project:pr-shepherd.'
  filters:
    - "payload.conclusion == 'failure'"
```

**Handle new PR review comments:**

```yaml
- name: "handle-review-comment"
  event_type: "pull_request_review_comment"
  action: "created"
  command: >-
    claude -p 'New review comment from {{actor}} on {{repo}}:
    {{summary}}. Run /project:handle-pr-comments.'
```

**Notify on workflow failure (non-Claude):**

```yaml
- name: "slack-notify-workflow-failure"
  event_type: "workflow_run"
  action: "completed"
  command: >-
    curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL
    -d '{"text": "Workflow failed: {{summary}} in {{repo}} on {{ref}}"}'
  filters:
    - "payload.conclusion == 'failure'"
```

### Built-in Templates

Metarelay ships with built-in handler templates in `src/metarelay/handlers/templates.py`:

| Template | Triggers On |
|----------|-------------|
| `pr_shepherd_ci_failure` | `check_run` completed with failure |
| `pr_shepherd_workflow_failure` | `workflow_run` completed with failure |
| `handle_pr_review_comment` | New PR review comment |
| `handle_pr_review_submitted` | PR review submitted |

These are reference implementations. Copy and customize them in your `config.yaml`.

## Supported GitHub Events

| Event Type | Actions | What It Captures |
|------------|---------|------------------|
| `check_run` | `completed`, `created` | CI check results |
| `check_suite` | `completed` | CI suite results |
| `workflow_run` | `completed` | GitHub Actions workflow results |
| `pull_request_review` | `submitted`, `dismissed` | PR review submissions |
| `pull_request_review_comment` | `created`, `edited` | PR inline comments |

To add more event types, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Deduplication

Events are deduplicated at two levels:

1. **Cloud**: The `delivery_id` column has a UNIQUE constraint. GitHub retries are silently ignored.
2. **Local**: The `event_log` table has a UNIQUE constraint on `remote_id`. Catch-up/Realtime overlap is handled gracefully.

You never need to worry about a handler being invoked twice for the same event.

## Cursor Persistence

The daemon tracks progress per-repo using a cursor (the last processed event ID). This is stored in a local SQLite database.

- When the daemon starts, it catches up from the cursor position
- If no cursor exists, it starts from the beginning
- Cursors survive daemon restarts
- Each repo has its own independent cursor

## Troubleshooting

**Daemon can't connect to Supabase**
- Verify `supabase_url` and `supabase_key` in your config
- The anon key is in Supabase Dashboard > Settings > API
- Try `curl https://YOUR-PROJECT.supabase.co/rest/v1/events -H "apikey: YOUR-KEY"` to test connectivity

**Events not appearing in Supabase**
- Check GitHub App > Advanced > Recent Deliveries for webhook delivery status
- Verify the webhook URL matches your Edge Function URL
- Check that the webhook secret matches between GitHub App and Supabase secrets

**Handler not firing**
- Run with `-v` to see which events are received and which handlers match
- Verify `event_type` and `action` match exactly (they're case-sensitive)
- Check filter expressions — a typo means silent non-match

**Handler fires but command fails**
- Check `metarelay status` to verify events are being processed
- The handler result (success/failure/timeout) is logged to the local SQLite database
- Increase `timeout` if commands are being killed prematurely

**Catching up takes too long**
- The daemon fetches events in pages of 100
- If you have thousands of backlogged events, the first sync may take a while
- Consider using `metarelay sync` first, then starting the daemon
