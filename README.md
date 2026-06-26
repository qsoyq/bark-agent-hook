# bark-agent-hook

Standalone Bark notification hooks for Codex, Claude Code, and OpenClaw.

## Install

```shell
uv tool install git+https://github.com/qsoyq/bark-agent-hook.git
bark-agent-hook --help
```

Install all locally available agent plugins:

```shell
bark-agent-hook install
```

Install one or more specific agents:

```shell
bark-agent-hook install --agent codex
bark-agent-hook install --agent claude --agent openclaw
```

Uninstall plugin hooks without removing marketplace sources, environment variables, or historical audit logs:

```shell
bark-agent-hook uninstall
bark-agent-hook uninstall --agent codex
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
