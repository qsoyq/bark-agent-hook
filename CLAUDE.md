# CLAUDE.md

This repository contains the standalone `bark-agent-hook` CLI and companion plugin assets for Codex, Claude Code, and OpenClaw.

## Common Commands

- `uv sync --group dev`
- `uv run pytest -q`
- `uv run pytest -q tests/<file>_test.py`
- `uv run tox`
- `uv run pre-commit run --all-files`
- `uv build`

## Architecture

The Typer CLI is exposed as `bark-agent-hook`. It intentionally has only three subcommands: `hook`, `install`, and `uninstall`. Install guidance belongs in the root help text, not in generated command docs or a separate `plugins` command group.

Plugin manifests are under `plugins/`; marketplace manifests are under `.agents/plugins/` and `.claude-plugin/`. Keep manifest versions synchronized across Codex, Claude Code, OpenClaw package metadata, and OpenClaw native manifest.

## Security-Sensitive Areas

The hook receives agent lifecycle payloads and sends Bark requests. Audit logging must remain opt-in and must not persist raw hook payloads, Bark device keys or URLs, full notification bodies, or rendered click URLs.
