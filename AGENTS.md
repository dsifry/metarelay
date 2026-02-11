# Agents Guide

How metarelay works with AI coding agents like Claude Code.

## Overview

Metarelay bridges GitHub events to local AI agents. When a CI check fails or a PR review is posted, metarelay receives the event and makes it available to agents via two dispatch models:

```
GitHub CI fails → webhook → Supabase → metarelay daemon
                                            │
                              ┌──────────────┼──────────────┐
                              ▼                              ▼
                     .metarelay/events.jsonl         subprocess handler
                     (persistent subagents)          (one-shot commands)
```

## Dispatch Models

### File-Based (Recommended for Persistent Subagents)

The daemon writes every event as a JSONL line to `.metarelay/events.jsonl` in the repo's local checkout directory. A persistent subagent watches this file with `tail -f` — zero polling, zero latency, zero process spawns.

```
metarelay daemon ──→ appends to .metarelay/events.jsonl
                                    │
                              tail -f (push)
                                    │
                          subagent wakes up, acts,
                          goes back to waiting
```

This is the recommended approach for AI agents because:

- **Zero startup cost**: The agent is already running, no new process per event
- **Full context**: The agent retains conversation history and codebase knowledge
- **Push-based**: No polling, no wasted API calls — events arrive instantly
- **Natural batching**: Multiple events accumulate if the agent is busy

#### How It Works

When the daemon receives an event for a configured repo, it appends the event as a JSON line to `{repo.path}/.metarelay/events.jsonl`. A persistent subagent watches this file:

```bash
tail -f .metarelay/events.jsonl
```

When a new line appears, the agent reads it, decides how to respond, acts, and then goes back to waiting.

#### Timeout Handling

Claude Code's Bash tool has a maximum timeout (10 minutes). The subagent should loop, restarting `tail -f` if it times out:

```
while true:
    event = tail -f .metarelay/events.jsonl  (blocks up to timeout)
    if event received:
        parse JSON, act on event
    else:
        # timeout — loop and restart tail -f
```

#### Event Format

Each line is a JSON object with these fields:

```json
{
  "id": 42,
  "repo": "myorg/myrepo",
  "event_type": "check_run",
  "action": "completed",
  "ref": "feat/my-feature",
  "actor": "octocat",
  "summary": "CI Build failure",
  "payload": {"conclusion": "failure", ...},
  "delivery_id": "abc-123",
  "created_at": "2026-02-10T12:00:00Z"
}
```

### Subprocess (For One-Shot Commands)

Handlers defined in `config.yaml` run a shell command per event. This is simpler for one-shot tasks like notifications, scripts, or ad-hoc agent invocations.

```yaml
handlers:
  - name: "fix-ci-failure"
    event_type: "check_run"
    action: "completed"
    command: "claude -p 'Fix CI in {{repo}}: {{summary}}'"
    filters:
      - "payload.conclusion == 'failure'"
```

The `claude -p` flag runs Claude Code in non-interactive ("prompt") mode — it receives the instruction, does the work, and exits.

#### Template Variables in Prompts

Metarelay resolves `{{variable}}` placeholders before invoking the command:

| Variable | Description | Example Value |
|----------|-------------|---------------|
| `{{repo}}` | Full repo name | `myorg/myrepo` |
| `{{event_type}}` | GitHub event type | `check_run` |
| `{{action}}` | Event action | `completed` |
| `{{ref}}` | Git branch/tag | `feat/my-feature` |
| `{{actor}}` | GitHub username | `octocat` |
| `{{summary}}` | Human-readable summary | `CI Build failure` |
| `{{payload.field}}` | Payload field | `failure` |

## Recipes

### PR Shepherd with File-Based Dispatch (Recommended)

The PR Shepherd subagent runs persistently, watching for events:

1. Configure the repo in `~/.metarelay/config.yaml`:

```yaml
repos:
  - name: "myorg/myrepo"
    path: "/home/user/projects/myrepo"
```

2. Start metarelay: `metarelay start`

3. In the repo, the subagent watches `.metarelay/events.jsonl` and runs `/project:pr-shepherd` when CI fails or reviews come in.

No handler config needed — the file-based dispatch makes all events available to the subagent.

### PR Shepherd with Subprocess (One-Shot)

```yaml
- name: "pr-shepherd-ci-failure"
  event_type: "check_run"
  action: "completed"
  command: >-
    claude -p 'A CI check failed in {{repo}} on branch {{ref}}.
    Check: {{summary}}. Conclusion: {{payload.conclusion}}.
    Run /project:pr-shepherd to investigate the failure,
    identify the root cause, and push a fix.'
  filters:
    - "payload.conclusion == 'failure'"
  timeout: 600
```

### Handle PR Review Comments (Subprocess)

```yaml
- name: "handle-review"
  event_type: "pull_request_review"
  action: "submitted"
  command: >-
    claude -p 'A PR review was submitted in {{repo}} by {{actor}}.
    Review: {{summary}}.
    Run /project:handle-pr-comments to address the feedback.'
  timeout: 300
```

### Skip Bot-Generated Events

Filter out events from bots to avoid infinite loops:

```yaml
- name: "handle-human-reviews"
  event_type: "pull_request_review"
  action: "submitted"
  command: "claude -p 'Handle review from {{actor}} in {{repo}}: {{summary}}'"
  filters:
    - "actor != 'dependabot[bot]'"
    - "actor != 'github-actions[bot]'"
```

### Non-Agent Commands

You're not limited to Claude Code. Any shell command works:

```yaml
# Slack notification
command: "curl -X POST https://hooks.slack.com/your/webhook -d '{\"text\": \"CI failed in {{repo}}\"}'"

# Custom script
command: "python3 scripts/handle_failure.py --repo {{repo}} --ref {{ref}}"

# macOS notification
command: "osascript -e 'display notification \"CI failed in {{repo}}\"'"
```

## Integration with Good To Go

Metarelay is designed to work with [goodtogo](https://github.com/dsifry/goodtogo) workflows:

- **PR Shepherd** (`/project:pr-shepherd`): Monitors PRs through to merge, handles CI failures, addresses review comments
- **Handle PR Comments** (`/project:handle-pr-comments`): Systematically addresses code review feedback

The handler templates in `src/metarelay/handlers/templates.py` are pre-configured to invoke these workflows.

## Agent Loop Prevention

When an agent pushes a fix, it may trigger new CI events. To prevent infinite loops:

1. **Filter on conclusion**: Only trigger on `failure`, not on `success`
2. **Filter out bot actors**: Exclude `github-actions[bot]` or your app's bot name
3. **Use timeouts**: Set reasonable `timeout` values (default 300s) so runaway agents are killed
4. **Deduplication**: Metarelay's built-in dedup ensures the same event is never processed twice

## Monitoring Agent Activity

Check what handlers have run and their results:

```bash
metarelay status
```

For detailed logs, run the daemon with `-v`:

```bash
metarelay start -v
```

The local SQLite database (`~/.metarelay/metarelay.db`) stores a log of every processed event and handler result. You can query it directly:

```bash
sqlite3 ~/.metarelay/metarelay.db "SELECT * FROM event_log ORDER BY id DESC LIMIT 10"
```

## Gitignore

Add `.metarelay/` to your repo's `.gitignore` to exclude the events file and any local state:

```gitignore
.metarelay/
```
