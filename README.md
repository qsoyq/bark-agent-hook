# bark-agent-hook

Standalone Bark notification hooks for Codex, Claude Code, and OpenClaw.

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
BARK_GROUP=
AGENT_BARK_NOTIFY_GROUP_MODE=agent
AGENT_BARK_NOTIFY_HOOK_URL=
AGENT_BARK_NOTIFY_TITLE_TEMPLATE=
AGENT_BARK_NOTIFY_AUDIT_LOG=1
AGENT_BARK_NOTIFY_AUDIT_LOG_FILE=~/.bark-agent-hook/bark-agent-hook.log
```

The `AGENT_BARK_NOTIFY_*` variable names are intentionally preserved for compatibility with existing hook configuration.

Notifications are sent with Bark's Markdown field by default. The short `body` summary is still produced for dry-run output, duplicate detection, audit metadata, and future compatibility fallbacks, but real Bark requests send `markdown` when available.

The default title is intentionally compact:

```text
{event} - {project}
```

Use `AGENT_BARK_NOTIFY_TITLE_TEMPLATE` to override it. Available title values include `{agent}`, `{event}`, `{project}`, `{runtime}`, `{cwd_basename}`, `{branch}`, and `{session}`.

## Hook Commands

These are the commands installed into the companion plugins:

```shell
bark-agent-hook hook --runtime codex --event approval_needed --summary-mode extract
bark-agent-hook hook --runtime codex --event completion --summary-mode extract
bark-agent-hook hook --runtime claude --event approval_needed --summary-mode extract
bark-agent-hook hook --runtime claude --event completion --summary-mode extract
bark-agent-hook hook --runtime openclaw --event completion --summary-mode extract
```

Local dry-run check:

```shell
printf '%s' '{"session_id":"demo","cwd":"/tmp/demo-project"}' \
  | BARK_DEVICE_KEY=device-key bark-agent-hook hook --runtime codex --event completion --dry-run
```

## Development

```shell
uv sync --group dev
uv run pytest -q
uv run pre-commit run --all-files
uv build
```

This repository does not maintain generated command docs; `bark-agent-hook --help` is the command reference.
