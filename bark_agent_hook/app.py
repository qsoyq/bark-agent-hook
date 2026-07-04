from __future__ import annotations

import importlib.metadata
from typing import Any

import typer

helptext = """
从 agent 生命周期 hook 和直接 CLI 请求发送 Bark 通知。

安装插件:
  bark-agent-hook install
  bark-agent-hook install --agent codex
  bark-agent-hook install --agent claude --agent openclaw
  bark-agent-hook install --agent zed-claude-code-acp

卸载插件:
  bark-agent-hook uninstall
  bark-agent-hook uninstall --agent codex

直接发送 Bark 通知:
  bark-agent-hook send --title "Test" --body "Hello"
  bark-agent-hook send --device-key key1 --device-key key2 --body "Batch"

插件使用的 hook 命令:
  bark-agent-hook hook --runtime codex --event completion
  bark-agent-hook hook --runtime claude --event approval_needed --summary-mode extract
  bark-agent-hook hook --runtime claude --event attention_needed --summary-mode extract
  bark-agent-hook hook --runtime codex --event audit_only --summary-mode extract
  bark-agent-hook hook --runtime openclaw --event completion --summary-mode extract

直接安装插件命令:
  codex plugin marketplace add qsoyq/bark-agent-hook
  codex plugin add bark-agent-hook-codex@bark-agent-hook
  claude plugin marketplace add qsoyq/bark-agent-hook
  claude plugin install bark-agent-hook@bark-agent-hook --scope user
  openclaw plugins install --link ./plugins/bark-agent-hook-openclaw
  openclaw plugins enable bark-agent-hook-openclaw

配置:
  hook: BARK_DEVICE_KEY 必填。缺失或为空时跳过通知并以 0 退出。
  send: 必须提供 BARK_DEVICE_KEY、BARK_DEVICE_KEYS 或 --device-key；缺失会使命令失败。
  BARK_DEVICE_KEYS 是逗号分隔列表，仅 send 使用。
  BARK_SERVER 默认 https://api.day.app。
  BARK_GROUP 可选。hook 中会覆盖自动计算的 Bark 分组，可为固定值或模板；send 中按字面使用。
  AGENT_BARK_NOTIFY_GROUP_MODE=agent|project|project-branch，在 BARK_GROUP 未设置时选择 hook 的自动分组。
  AGENT_BARK_NOTIFY_HOOK_URL 默认为空，可设置 Bark 点击 URL 模板。
  示例: AGENT_BARK_NOTIFY_HOOK_URL=https://lody.ai/users/{LODY_ELECTRON_SESSION_USER_ID}/sessions/{LODY_SESSION_ID}
  AGENT_BARK_NOTIFY_TITLE_TEMPLATE 可设置通知标题模板。
  AGENT_BARK_NOTIFY_AUDIT_LOG=1 启用本地 JSONL 审计日志。
  AGENT_BARK_NOTIFY_AUDIT_LOG_FILE 在启用审计日志时默认 ~/.bark-agent-hook/bark-agent-hook.log。
  BARK_LEVEL、BARK_URL、BARK_EXTRA_PARAMS、BARK_DRY_RUN 和 BARK_TIMEOUT 由 send 使用。

模板变量:
  AGENT_BARK_NOTIFY_TITLE_TEMPLATE 支持:
    {agent}, {event}, {project}, {branch}, {session}, {runtime}, {cwd_basename},
    {LODY_ELECTRON_BOOTSTRAP}, {LODY_ELECTRON_SESSION_USER_ID}, {LODY_SESSION_ID},
    {LODY_WORKSPACE_SESSION_ID}.
    示例: AGENT_BARK_NOTIFY_TITLE_TEMPLATE='[{agent}][{event}][{LODY_SESSION_ID}]'
  BARK_GROUP 支持:
    {repo_or_project}, {workdir}, {branch}, {workspace}, {runtime}.
    {repo_or_project}: 按 payload 工作目录解析；在 git 仓库内为仓库顶层目录名，否则回退到 project 名。
    project 名依次来自 payload 项目字段、项目环境变量、payload 路径 basename、当前 cwd basename。
    {workdir}: payload 工作目录 basename；payload 无路径时为当前 cwd basename。
    {branch}: 依次来自 payload 分支字段、分支环境变量、git 当前分支。
    {workspace}: Lody workspace 会话，来自 LODY_WORKSPACE_SESSION_ID；缺失时为空。
    模板使用 Python format 语法；{{repo_or_project}} 会作为字面量 {repo_or_project} 输出。
    示例: BARK_GROUP='{repo_or_project}@{branch}'
  AGENT_BARK_NOTIFY_HOOK_URL 支持:
    {runtime}, {agent}, {event}, {project}, {branch}, {session}, {session_id},
    {session_key}, {conversation_id}, {message_id}, {run_id}, {agent_id},
    {workspace_dir}, {cwd_basename}, {LODY_ELECTRON_BOOTSTRAP},
    {LODY_ELECTRON_SESSION_USER_ID}, {LODY_SESSION_ID}, {LODY_WORKSPACE_SESSION_ID}.
    示例: AGENT_BARK_NOTIFY_HOOK_URL='https://lody.ai/users/{LODY_ELECTRON_SESSION_USER_ID}/sessions/{LODY_SESSION_ID}'
  Hook URL 变量值会做 percent-encode；标题和分组变量不会 URL 编码。
  Lody 透传变量由 LodySettings 读取，并限制为上述四个 LODY_* key。

审计日志字段来源:
  hook 命令生成:
    1. time: 创建审计记录时的 UTC 时间戳。
    2. status: 最终 hook 处理结果，例如 sent、logged_audit_only_event、skipped_duplicate 或 skipped_missing_device_key。
    3. bark_agent_hook_version: 已安装 bark-agent-hook 包版本；无法读取包元数据时为 null。
    4. command_dir: 从 sys.argv[0] 或 PATH 解析出的命令所在目录；无法解析时为 null。
  CLI 选项:
    1. runtime: --runtime 选择或自动检测出的 agent runtime。
    2. event: --event 选择或从 payload 推断出的通知事件。
    3. summary_mode: --summary-mode 选择的通知正文模式。
  Hook payload 派生值:
    1. hook_event_name: 从 hook_event_name、event、event_name 或 type 读取的 hook 事件名。
    2. project: 从 payload 元数据或当前工作目录派生出的 project 名。
    3. session_id_hash: session 标识的哈希值；不会记录原始 session ID。
  构建通知派生值:
    1. dedupe_key_hash: 通知去重 key 的哈希值。
    2. title: 最终通知标题。
    3. body_len: 最终通知正文长度；不会记录通知正文。
  Lody 环境透传:
    1. lody: LodySettings 管理的非空白名单环境值。
       Keys: LODY_ELECTRON_BOOTSTRAP, LODY_ELECTRON_SESSION_USER_ID,
       LODY_SESSION_ID, and LODY_WORKSPACE_SESSION_ID.
"""


def version_callback(ctx: typer.Context, value: bool) -> None:
    if not value:
        return
    name = ctx.find_root().info_name or "bark-agent-hook"
    version = importlib.metadata.version("bark-agent-hook")
    typer.echo(f"{name} cli version: {version}")
    raise typer.Exit(0)


def default_invoke_without_command(
    _: bool = typer.Option(False, "--version", "-v", "-V", callback=version_callback),
) -> None:
    return None


def make_typer(help: str, **kwargs: Any) -> typer.Typer:
    app = typer.Typer(help=help, **kwargs)
    app.callback(invoke_without_command=True)(default_invoke_without_command)
    return app


cmd = make_typer(helptext)
