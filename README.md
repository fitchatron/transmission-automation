# Transmission Automation

Repo has code that allows torrents to be started via a script and move them to a specified path.

## Runtime

This project uses `uv` for environment and dependency management.

## Setup

```bash
uv sync --dev
```

## Run scripts

```bash
uv run init-db
uv run add-media "The Matrix" movie
uv run start-torrent tv-show "magnet:?xt=urn:btih:..."
uv run reconcile
uv run on-done
```

You can also execute script files directly because they use a `uv run` shebang.

## Tests

```bash
uv run pytest
```
