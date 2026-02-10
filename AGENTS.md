# Agents Guide

How metarelay works with AI coding agents like Claude Code.

## Overview

Metarelay bridges GitHub events to local AI agents. When a CI check fails or a PR review is posted, metarelay invokes a command — typically `claude -p '...'` — that spins up an agent to investigate and fix the issue automatically.

```
GitHub CI fails → webhook → Supabase → metarelay daemon → claude -p 'Fix it'
```

## How Handlers Invoke Agents

Each handler has a `command` field that gets executed as a shell command. For Claude Code, this is usually:

```yaml
command: "claude -p 'Your prompt here with {{template}} variables'"
```

The `claude -p` flag runs Claude Code in non-interactive ("prompt") mode — it receives the instruction, does the work, and exits.

### Template Variables in Prompts

Metarelay resolves `{{variable}}` placeholders before invoking the command, giving the agent full context about what happened:

```yaml
command: >-
  claude -p 'The CI check "{{summary}}" failed on branch {{ref}}
  in repo {{repo}}. The conclusion was {{payload.conclusion}}.
  Actor: {{actor}}. Investigate and fix the issue.'
```

This becomes something like:

```bash
claude -p 'The CI check "build failure" failed on branch feat/login
in repo myorg/myapp. The conclusion was failure.
Actor: octocat. Investigate and fix the issue.'
```

## Recipes: Common Agent Patterns

### PR Shepherd on CI Failure

When CI fails, invoke PR Shepherd to diagnose and fix:

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

### Handle PR Review Comments

When someone posts a review, invoke the comment handler:

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

### Handle Inline Review Comments

```yaml
- name: "handle-inline-comment"
  event_type: "pull_request_review_comment"
  action: "created"
  command: >-
    claude -p 'New inline review comment from {{actor}} in {{repo}}:
    {{summary}}.
    Run /project:handle-pr-comments to address this comment.'
  timeout: 300
```

### Chain Multiple Actions

You can run multiple commands by chaining with `&&`:

```yaml
- name: "fix-and-notify"
  event_type: "workflow_run"
  action: "completed"
  command: >-
    claude -p 'Fix the workflow failure in {{repo}}: {{summary}}'
    && curl -X POST https://hooks.slack.com/your/webhook
    -d '{"text":"Agent fixing {{repo}} workflow failure"}'
  filters:
    - "payload.conclusion == 'failure'"
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

## Writing Custom Agent Commands

You're not limited to Claude Code. Any command that can be run from a shell works:

```yaml
# Run a custom script
command: "python3 scripts/handle_failure.py --repo {{repo}} --ref {{ref}}"

# Use a different AI tool
command: "aider --message 'Fix CI failure in {{repo}}: {{summary}}'"

# Simple notification
command: "osascript -e 'display notification \"CI failed in {{repo}}\"'"
```

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

## Testing Handlers Locally

1. Start the daemon with verbose logging:
   ```bash
   metarelay start -v
   ```

2. Trigger a test webhook from GitHub App > Advanced > Recent Deliveries > Redeliver

3. Watch the daemon output to see:
   - Event received
   - Handler matched (or not)
   - Command executed
   - Result (success/failure/timeout)

For faster iteration, you can test command templates manually:

```bash
# Test what the resolved command looks like
echo "claude -p 'Fix CI in myorg/myrepo on branch feat/test. Build concluded failure.'"
```
