# Repository Guidelines

## Project Structure

`bark_agent_hook/` contains the Python package and Typer CLI. The public entry point is `bark-agent-hook`, wired through `bark_agent_hook.cli:cmd`. Runtime plugin assets live under `plugins/`, with separate Codex, Claude Code, and OpenClaw plugin directories. Tests live in `tests/` and mirror CLI behavior and plugin manifests.

## Development Commands

- `uv sync --group dev`: install the local development environment.
- `uv run pytest -q`: run the test suite.
- `uv run tox`: run the configured Python compatibility matrix.
- `uv run pre-commit run --all-files`: run formatting, linting, type, lockfile, and hygiene checks.
- `uv build`: build the wheel and source distribution.

## Conventions

Use Python 3.10+ and keep code typed where practical. Ruff is the formatter and linter with a 200-character line length. Keep this repository focused on Bark agent hooks; do not add unrelated utilities or generated command docs.

## Security

Do not commit real secrets, tokens, certificates, private keys, `.env`, or local service configuration. `bark-agent-hook` audit logging must not record raw hook payloads, Bark device keys/URLs, full notification bodies, or click URLs.
