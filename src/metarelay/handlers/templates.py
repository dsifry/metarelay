"""Built-in handler templates for common CI/CD orchestration patterns."""

from __future__ import annotations

from metarelay.core.models import HandlerConfig


def pr_shepherd_ci_failure() -> HandlerConfig:
    """Handler template: invoke PR Shepherd on CI failure."""
    return HandlerConfig(
        name="pr-shepherd-ci-failure",
        event_type="check_run",
        action="completed",
        command=(
            "claude -p 'Run /project:pr-shepherd for the PR on branch {{ref}} "
            "in {{repo}}. The check run {{summary}} concluded with {{payload.conclusion}}. "
            "Investigate the failure and fix it.'"
        ),
        filters=["payload.conclusion == 'failure'"],
        timeout=300,
    )


def pr_shepherd_workflow_failure() -> HandlerConfig:
    """Handler template: invoke PR Shepherd on workflow run failure."""
    return HandlerConfig(
        name="pr-shepherd-workflow-failure",
        event_type="workflow_run",
        action="completed",
        command=(
            "claude -p 'Run /project:pr-shepherd for {{repo}}. "
            "Workflow {{summary}} on {{ref}} has failed with conclusion {{payload.conclusion}}. "
            "Investigate and fix.'"
        ),
        filters=["payload.conclusion == 'failure'"],
        timeout=300,
    )


def handle_pr_review_comment() -> HandlerConfig:
    """Handler template: handle new PR review comments."""
    return HandlerConfig(
        name="handle-review-comment",
        event_type="pull_request_review_comment",
        action="created",
        command=(
            "claude -p 'Run /project:handle-pr-comments for {{repo}}. "
            "New review comment from {{actor}}: {{summary}}'"
        ),
        timeout=300,
    )


def handle_pr_review_submitted() -> HandlerConfig:
    """Handler template: handle PR review submissions."""
    return HandlerConfig(
        name="handle-review-submitted",
        event_type="pull_request_review",
        action="submitted",
        command=(
            "claude -p 'Run /project:handle-pr-comments for {{repo}}. "
            "{{actor}} submitted a review: {{summary}}'"
        ),
        timeout=300,
    )


ALL_TEMPLATES = [
    pr_shepherd_ci_failure,
    pr_shepherd_workflow_failure,
    handle_pr_review_comment,
    handle_pr_review_submitted,
]
"""All built-in handler template factory functions."""
