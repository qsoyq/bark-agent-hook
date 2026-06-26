# Copilot Instructions

This repository contains the standalone `bark-agent-hook` Python CLI and companion plugin assets for Codex, Claude Code, and OpenClaw.

## Project Boundaries

- Keep the public CLI focused on `hook`, `install`, and `uninstall`.
- Do not add unrelated utilities, broad agent frameworks, or generated command documentation.
- Runtime plugin assets live under `plugins/`; keep their manifest versions synchronized with `pyproject.toml` and the plugin package metadata.

## Development Commands

Use these commands when validating changes:

```shell
uv sync --group dev
uv run pytest -q
uv run tox
uv run pre-commit run --all-files
uv build
```

## Code Style

- Use Python 3.10+ syntax.
- Keep code typed where practical.
- Ruff is the formatter and linter with a 200-character line length.
- Prefer the existing Typer CLI, Pydantic settings, Rich output, and httpx patterns.

## Security Requirements

The hook receives local agent lifecycle payloads and can send Bark requests. Do not log, persist, or expose:

- Raw hook payloads.
- Bark device keys or server URLs.
- Full notification bodies.
- Rendered click URLs.
- Secrets, tokens, certificates, private keys, `.env` files, local service configuration, virtual environments, caches, or build outputs.

Audit logging must remain opt-in and sanitized.
