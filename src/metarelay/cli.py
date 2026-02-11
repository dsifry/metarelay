"""CLI entry point for metarelay."""

from __future__ import annotations

import asyncio
import logging
import sys

import click

from metarelay import __version__


@click.group()
@click.version_option(version=__version__, prog_name="metarelay")
def main() -> None:
    """Metarelay: webhook-based event relay for Claude Code orchestration."""
    pass


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default=None,
    help="Path to config file (default: ~/.metarelay/config.yaml)",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose (DEBUG) logging",
)
def start(config_path: str | None, verbose: bool) -> None:
    """Start the metarelay daemon (foreground)."""
    _setup_logging(verbose)

    from metarelay.config import load_config
    from metarelay.container import Container
    from metarelay.daemon import Daemon

    try:
        config = load_config(config_path)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

    container = Container.create_default(config)
    daemon = Daemon(container)

    try:
        asyncio.run(daemon.run())
    except KeyboardInterrupt:
        click.echo("Shutting down...")


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default=None,
    help="Path to config file",
)
def status(config_path: str | None) -> None:
    """Show cursor positions and event counts."""
    from metarelay.config import load_config
    from metarelay.container import Container

    try:
        config = load_config(config_path)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

    container = Container.create_default(config)

    click.echo("Metarelay Status")
    click.echo("=" * 40)

    for repo in config.repos:
        cursor = container.event_store.get_cursor(repo.name)
        if cursor:
            click.echo(f"  {repo.name}: last_event_id={cursor.last_event_id}")
        else:
            click.echo(f"  {repo.name}: no cursor (not yet synced)")


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default=None,
    help="Path to config file",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose (DEBUG) logging",
)
def sync(config_path: str | None, verbose: bool) -> None:
    """One-shot catch-up sync (no live subscription)."""
    _setup_logging(verbose)

    from metarelay.config import load_config
    from metarelay.container import Container
    from metarelay.daemon import run_sync

    try:
        config = load_config(config_path)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

    container = Container.create_default(config)

    try:
        asyncio.run(run_sync(container))
        click.echo("Sync complete.")
    except Exception as e:
        click.echo(f"Sync failed: {e}", err=True)
        sys.exit(1)


def _setup_logging(verbose: bool) -> None:
    """Configure logging for the daemon."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
