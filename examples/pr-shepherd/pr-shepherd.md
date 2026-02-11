# PR Shepherd — Sample Skill for MetaRelay

A sample Claude Code skill that monitors pull requests through to merge using MetaRelay's event-driven architecture. Copy this into your project and customize it.

## Setup

1. Copy this file to your project (e.g., `.claude/commands/pr-shepherd.md`)
2. Add `.metarelay/` to your project's `.gitignore`
3. Ensure MetaRelay is running: `pgrep -f metarelay || metarelay start &`

## Usage

```text
/project:pr-shepherd [pr-number]
```

## How It Works

Instead of polling the GitHub API every 60 seconds, this skill reacts **instantly** to events delivered by MetaRelay. The MetaRelay daemon writes GitHub webhook events to `.metarelay/events.jsonl` in your repo directory. The shepherd watches this file and acts when relevant events arrive.

```text
GitHub webhook → Supabase → MetaRelay daemon → .metarelay/events.jsonl
                                                        ↓
                                                  PR Shepherd reads event
                                                        ↓
                                              Checks CI status, handles reviews,
                                              fixes issues, resolves threads
```

## Skill Definition

### Phase 1: Initialize

```bash
# Get PR info
PR_NUMBER=${1:-$(gh pr view --json number -q .number 2>/dev/null)}
if [ -z "$PR_NUMBER" ]; then
  echo "No PR found. Provide PR number: /project:pr-shepherd 123"
  exit 1
fi

OWNER=$(gh repo view --json owner -q .owner.login)
REPO=$(gh repo view --json name -q .name)
BRANCH=$(gh pr view $PR_NUMBER --json headRefName -q .headRefName)

echo "Shepherding PR #$PR_NUMBER on branch $BRANCH"
```

### Phase 2: Event-Driven Monitoring via MetaRelay

Check if MetaRelay is running. If it is, use event-driven monitoring. If not, fall back to polling.

```bash
# Check MetaRelay status
if pgrep -f metarelay > /dev/null 2>&1; then
  echo "MetaRelay is running — using event-driven monitoring (zero polling)"
  MONITORING_MODE="metarelay"
else
  echo "MetaRelay is not running — falling back to 60s polling"
  echo "Start MetaRelay for instant event delivery: metarelay start &"
  MONITORING_MODE="polling"
fi
```

#### MetaRelay Mode: Watch events.jsonl

```bash
# Watch for events relevant to this PR's branch
tail -f .metarelay/events.jsonl | while IFS= read -r event; do
  EVENT_TYPE=$(echo "$event" | jq -r '.event_type')
  ACTION=$(echo "$event" | jq -r '.action')
  REF=$(echo "$event" | jq -r '.ref')

  # Only act on events for our branch
  if [ "$REF" != "$BRANCH" ] && [ "$REF" != "null" ]; then
    continue
  fi

  case "$EVENT_TYPE" in
    check_run)
      CONCLUSION=$(echo "$event" | jq -r '.payload.conclusion // empty')
      if [ "$CONCLUSION" = "failure" ]; then
        echo "CI failure detected — investigating..."
        # → Transition to FIXING state
      elif [ "$CONCLUSION" = "success" ]; then
        echo "CI check passed — checking overall status..."
        # → Check if all checks are green
      fi
      ;;
    pull_request_review|pull_request_review_comment)
      echo "New review activity — checking for actionable comments..."
      # → Transition to HANDLING_REVIEWS state
      ;;
    pull_request_review_thread)
      echo "Thread status changed — checking resolution..."
      # → Check if all threads resolved
      ;;
  esac
done
```

#### Polling Fallback Mode

```bash
# When MetaRelay is not available, poll every 60 seconds
while true; do
  # Check CI status
  FAILED=$(gh pr checks $PR_NUMBER --json name,conclusion \
    --jq '[.[] | select(.conclusion == "FAILURE")] | length')

  # Check unresolved threads
  UNRESOLVED=$(gh api graphql \
    -f owner="$OWNER" -f repo="$REPO" -F pr="$PR_NUMBER" \
    -f query='query($owner: String!, $repo: String!, $pr: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
          reviewThreads(first: 100) {
            nodes { isResolved }
          }
        }
      }
    }' --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length')

  if [ "$FAILED" = "0" ] && [ "$UNRESOLVED" = "0" ]; then
    echo "All CI green, all threads resolved — PR is ready to merge!"
    break
  fi

  sleep 60
done
```

### Phase 3: Handle Issues

When CI fails or review comments arrive, the shepherd:

1. **Simple CI failures** (lint, type errors, formatting) → auto-fix with TDD
2. **Complex failures** → present options to the user
3. **Review comments** → address feedback, respond to threads
4. **Thread resolution** → resolve threads after reviewer approval

### Phase 4: Done

Exit when ALL of these are true:
- All CI checks pass
- All review threads resolved
- No pending reviewer comments

## Event Types

| Event Type                    | What Triggers It               | Shepherd Action                |
| ----------------------------- | ------------------------------ | ------------------------------ |
| `check_run` (completed)       | CI check finishes              | Check conclusion, fix if fail  |
| `check_suite` (completed)     | CI suite finishes              | Check overall CI status        |
| `workflow_run` (completed)    | GitHub Action finishes         | Check overall CI status        |
| `pull_request_review`         | Review submitted               | Check for actionable feedback  |
| `pull_request_review_comment` | Inline comment posted          | Address comment, respond       |
| `pull_request_review_thread`  | Thread resolved/unresolved     | Update thread tracking         |
| `pull_request` (synchronized) | New push to PR branch          | Wait for new CI results        |

## Customization

This is a starting point. Common customizations:

- **Auto-merge**: Add `gh pr merge --auto --squash` when all checks pass
- **Notification**: Post to Slack when PR is ready
- **Scope filtering**: Only react to specific CI check names
- **Bot filtering**: Ignore events from `dependabot[bot]`, `github-actions[bot]`
