# Installation

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

Edit `~/.metarelay/config.yaml` with your Supabase credentials and repos.
See [USAGE.md](USAGE.md) for full configuration reference.

## Cloud Setup

Metarelay requires a Supabase backend to receive GitHub webhooks.
See [cloud/setup.md](cloud/setup.md) for step-by-step setup instructions covering:

1. Creating a Supabase project
2. Running the database migration
3. Deploying the Edge Function
4. Creating and installing a GitHub App

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
