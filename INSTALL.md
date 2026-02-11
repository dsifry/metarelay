# Installation

## How Metarelay Is Structured

Metarelay has two parts that live in different places:

1. **This repo (`metarelay/`)** — the infrastructure source code. It contains the Supabase Edge Function, database migration, and the local daemon. You clone it once, deploy the cloud pieces from it, and install the daemon CLI from it. Think of it like installing a tool.

2. **`.metarelay/` in each monitored repo** — a runtime directory created automatically by the daemon. It contains `events.jsonl` (the event stream for that repo). This directory should be added to each repo's `.gitignore`.

```
metarelay/                          ← You clone this once
├── cloud/supabase/                 ← Deploy infrastructure from here
│   ├── migrations/                 ← Database schema
│   └── functions/github-webhook/   ← Edge Function source
├── examples/                       ← Sample skills to copy into your projects
│   └── pr-shepherd/                ← Event-driven PR monitoring skill
└── src/                            ← Daemon source code

your-project/                       ← Each monitored repo
├── .metarelay/                     ← Created at runtime (gitignored)
│   └── events.jsonl                ← Event stream for this repo
└── .claude/commands/               ← Where you'd put the pr-shepherd skill
    └── pr-shepherd.md              ← Copied from examples/
```

## Prerequisites

- **Python 3.11+** (check with `python3 --version`)
- **pip** (usually bundled with Python)
- **git** (to clone the repo)

For cloud features, you'll also need:
- A [Supabase](https://supabase.com) account (free tier is sufficient)
- A GitHub account with admin access to the repos you want to monitor

## Quick Install

```bash
git clone https://github.com/dsifry/metarelay.git
cd metarelay
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify:

```bash
metarelay --version
# metarelay, version 0.1.0
```

## Development Install

If you plan to run tests or contribute:

```bash
git clone https://github.com/dsifry/metarelay.git
cd metarelay
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs additional tools: pytest, black, ruff, mypy.

Verify everything works:

```bash
pytest                    # 158 tests, 100% coverage
ruff check .              # Linting
black --check .           # Formatting
mypy src/                 # Type checking
```

## Configuration

After installing, you need to configure metarelay before running it:

```bash
mkdir -p ~/.metarelay
cp config.example.yaml ~/.metarelay/config.yaml
```

Edit `~/.metarelay/config.yaml` with your Supabase credentials and repo name/path pairs.
See [USAGE.md](USAGE.md) for full configuration reference.

## Cloud Setup

Metarelay requires a Supabase backend to receive GitHub webhooks.
See [cloud/setup.md](cloud/setup.md) for step-by-step setup instructions covering:

1. Creating a Supabase project
2. Running the database migration
3. Deploying the Edge Function
4. Creating and installing a GitHub App

## Setting Up Your Repos

For each repo you want to monitor:

1. **Add `.metarelay/` to `.gitignore`**:

   ```bash
   echo '.metarelay/' >> /path/to/your-repo/.gitignore
   ```

2. **Add the repo to your config** (`~/.metarelay/config.yaml`):

   ```yaml
   repos:
     - name: "your-org/your-repo"
       path: "/path/to/your-repo"
   ```

3. **(Optional) Copy the PR Shepherd sample skill** into your project for event-driven PR monitoring:

   ```bash
   cp /path/to/metarelay/examples/pr-shepherd/pr-shepherd.md /path/to/your-repo/.claude/commands/pr-shepherd.md
   ```

   This gives your Claude Code agents a `/project:pr-shepherd` command that reacts instantly to CI failures and review comments via MetaRelay events. See [AGENTS.md](AGENTS.md) for details and more recipes.

## Updating

```bash
cd metarelay
git pull
source .venv/bin/activate
pip install -e ".[dev]"
```

## Uninstalling

```bash
pip uninstall metarelay
rm -rf ~/.metarelay    # Removes config and local database
```
