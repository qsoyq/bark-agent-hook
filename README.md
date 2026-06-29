# bark-agent-hook

Standalone Bark notification hooks for Codex, Claude Code, and OpenClaw.

## Overview

`bark-agent-hook` is a Python 3.10+ Typer CLI that installs companion hook assets for local coding agents and sends concise Bark notifications when agent lifecycle events need attention or have completed. The package keeps runtime behavior focused on hook execution, plugin installation, and safe notification delivery.

The project includes:

- `bark_agent_hook/`: the typed Python package and CLI entry point.
- `plugins/`: runtime plugin assets for Codex, Claude Code, and OpenClaw.
- `tests/`: CLI and plugin manifest coverage.
- `.github/`: issue templates, PR template, CI, Dependabot, and expected repository governance settings.

## Install

Install the CLI from PyPI:

```shell
pip install bark-agent-hook
bark-agent-hook --help
```

If you prefer `uv`-managed command-line tools:

```shell
uv tool install bark-agent-hook
bark-agent-hook --help
```

You can also run the CLI without installing it first:

```shell
uvx bark-agent-hook --help
uvx bark-agent-hook hook --runtime codex --event completion --dry-run
```

For real agent hooks, keep `bark-agent-hook` installed in `PATH`. The installed Codex, Claude Code, and OpenClaw plugins invoke `bark-agent-hook hook ...` when the agent emits lifecycle events.

## Plugin Setup

Install all locally available agent plugins after installing the CLI:

```shell
bark-agent-hook install
```

Install one or more specific agents:

```shell
bark-agent-hook install --agent codex
bark-agent-hook install --agent claude --agent openclaw
```

`uvx` works for plugin setup too, but the hook runtime still needs an installed `bark-agent-hook` command later:

```shell
uvx bark-agent-hook install --agent codex
```

Uninstall plugin hooks without removing marketplace sources, environment variables, or historical audit logs:

```shell
bark-agent-hook uninstall
bark-agent-hook uninstall --agent codex
```

Upgrade the CLI with your package manager, then run `install` again to refresh companion plugins:

```shell
pip install --upgrade bark-agent-hook
bark-agent-hook install
```

## Runtime Configuration

`BARK_DEVICE_KEY` is required for real delivery. Missing or empty values skip notification delivery and exit successfully.

Common optional settings:

```shell
BARK_SERVER=https://api.day.app
BARK_GROUP={project}
AGENT_BARK_NOTIFY_GROUP_MODE=agent
AGENT_BARK_NOTIFY_HOOK_URL=
AGENT_BARK_NOTIFY_TITLE_TEMPLATE=
AGENT_BARK_NOTIFY_AUDIT_LOG=1
AGENT_BARK_NOTIFY_AUDIT_LOG_FILE=~/.bark-agent-hook/bark-agent-hook.log
```

The `AGENT_BARK_NOTIFY_*` variable names are intentionally preserved for compatibility with existing hook configuration.

Audit JSONL records include best-effort diagnostics for install troubleshooting, including `bark_agent_hook_version` and `command_dir`. Tool lifecycle records also include safe debugging metadata such as `tool_name`, hashed tool call ids, status, exit code, command length, question count, and sanitized summaries where available. These fields are not included in Bark notification text, click URLs, or duplicate detection keys.

Notifications are sent with Bark's Markdown field by default. The short `body` summary is still produced for dry-run output, duplicate detection, audit metadata, and future compatibility fallbacks, but real Bark requests send `markdown` when available.

The default title is intentionally compact:

```text
{event} - {project}
```

Use `AGENT_BARK_NOTIFY_TITLE_TEMPLATE` to override it. Available title values include `{agent}`, `{event}`, `{project}`, `{runtime}`, `{cwd_basename}`, `{branch}`, and `{session}`.

Use `BARK_GROUP` as either a fixed Bark group or a group template. Available group values include `{agent}`, `{event}`, `{project}`, `{runtime}`, `{cwd_basename}`, `{branch}`, and `{session}`. For example, `BARK_GROUP={project}` groups notifications by project, and `BARK_GROUP={project}@{branch}` groups them by project and branch. Group and title variables are not URL-encoded.

## Hook Commands

These are the commands installed into the companion plugins:

```shell
bark-agent-hook hook --runtime codex --event approval_needed --summary-mode extract
bark-agent-hook hook --runtime codex --event attention_needed --summary-mode extract
bark-agent-hook hook --runtime codex --event audit_only --summary-mode extract
bark-agent-hook hook --runtime codex --event completion --summary-mode extract
bark-agent-hook hook --runtime claude --event approval_needed --summary-mode extract
bark-agent-hook hook --runtime claude --event attention_needed --summary-mode extract
bark-agent-hook hook --runtime claude --event audit_only --summary-mode extract
bark-agent-hook hook --runtime claude --event completion --summary-mode extract
bark-agent-hook hook --runtime openclaw --event completion --summary-mode extract
```

Codex and Claude Code hook payloads are grouped into notification events before delivery. Approval and explicit user-input events, including Codex `request_user_input` tool calls, map to `approval_needed`, user-visible attention events such as notifications, elicitations, permission denials, or plan update payloads map to `attention_needed`, successful stop events map to `completion`, failures map to `failed`, and high-volume lifecycle or tool pipeline events map to `audit_only`.

`audit_only` events never call Bark; when audit logging is enabled they are recorded with `logged_audit_only_event`. This keeps prompt submissions, session starts, compact events, and ordinary non-notifying tool use available for diagnostics without creating notification noise.

Codex app builds may expose plan changes internally as `turn/plan/updated`, `plan_update`, or `plan_delta` rather than as a public plugin hook. `bark-agent-hook` recognizes those payload names when it receives them, but direct Plan Mode coverage depends on Codex exposing the corresponding public hook event to installed plugins.

Local dry-run check:

```shell
printf '%s' '{"session_id":"demo","cwd":"/tmp/demo-project"}' \
  | BARK_DEVICE_KEY=device-key bark-agent-hook hook --runtime codex --event completion --dry-run
```

## Development

This project uses `uv`, Ruff, mypy, pytest, tox, and pre-commit.

```shell
uv sync --group dev
uv run pytest -q
uv run pre-commit run --all-files
uv build
```

This repository does not maintain generated command docs; `bark-agent-hook --help` is the command reference.

## Testing And Build

Run the focused test suite during normal development:

```shell
uv run pytest -q
```

Run the compatibility matrix before release-sensitive changes:

```shell
uv run tox
```

Build local distributions with:

```shell
uv build
```

## Release

The `CI` workflow validates pull requests and `main` pushes. Merges to `main` can create a GitHub release for the current `project.version` when one does not already exist. Publishing to PyPI uses trusted publishing through the protected `pypi` GitHub environment.

Manual PyPI publishing is available through the `workflow_dispatch` path by providing an existing stable `x.y.z` release tag. The workflow verifies required CI checks for the release commit before publishing.

## Branch And Review Policy

The repository uses GitHub Flow:

- Open or pick an issue before starting work.
- Branch from `main` using a scoped branch name such as `chore/13-governance-audit-remediation`.
- Keep changes scoped to the issue.
- Open a PR against `main` and fill in the repository PR template.
- Required CI checks and review gates are declared in `.github/settings.yml` and should be verified on GitHub.

## Documentation

Project documentation lives under `docs/`:

- `docs/decisions/`: architecture and governance decisions.
- `docs/design/`: user-facing behavior and design notes.
- `docs/tech/`: implementation notes and technical references.
- `docs/release/`: release and publishing notes.
- `docs/postmortems/`: incident and regression write-ups.

## Ownership

`CODEOWNERS` assigns repository-wide ownership to `@qsoyq`. Security reporting instructions live in `SECURITY.md`, and contribution workflow details live in `CONTRIBUTING.md`.
