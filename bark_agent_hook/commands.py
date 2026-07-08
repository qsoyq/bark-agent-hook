import json
import os
from typing import Any

import httpx
import typer
from rich.console import Console

from bark_agent_hook.app import cmd
from bark_agent_hook.audit import _finish_audit_record, _new_audit_record
from bark_agent_hook.constants import DEFAULT_SUMMARY_MAX_CHARS
from bark_agent_hook.installer import _install_for_available_agents, _uninstall_for_available_agents
from bark_agent_hook.model_context import payload_with_model_context, remember_model_context
from bark_agent_hook.models import (
    AgentOption,
    BarkLevelOption,
    Event,
    GroupModeOption,
    Runtime,
    SummaryMode,
)
from bark_agent_hook.notification import (
    already_sent,
    build_notification,
    resolve_group_mode,
    send_bark,
    send_bark_json,
    should_dedupe_notification,
    skip_notification_reason,
)
from bark_agent_hook.output import (
    _found_cli_count,
    _print_install_results,
    _print_uninstall_results,
    _succeeded,
)
from bark_agent_hook.runtime import _read_stdin, detect_event, detect_runtime, parse_hook_payload
from bark_agent_hook.settings import LodySettings
from bark_agent_hook.summary import extract_summary
from bark_agent_hook.utils import _env_value

TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


def _optional_env(env: dict[str, str], key: str) -> str | None:
    value = _env_value(env, key)
    return value or None


def _resolve_option(value: str | None, env: dict[str, str], key: str, default: str | None = None) -> str | None:
    if value is not None:
        return value
    return _optional_env(env, key) or default


def _resolve_bool_option(value: bool | None, env: dict[str, str], key: str, default: bool | None = None) -> bool | None:
    if value is not None:
        return value
    env_text = _optional_env(env, key)
    if env_text is None:
        return default
    normalized = env_text.casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    choices = ", ".join(sorted(TRUE_VALUES | FALSE_VALUES))
    raise typer.BadParameter(f"{key} must be one of: {choices}; got {env_text!r}")


def _resolve_float_option(value: float | None, env: dict[str, str], key: str, default: float) -> float:
    if value is not None:
        return value
    env_text = _optional_env(env, key)
    if env_text is None:
        return default
    try:
        resolved = float(env_text)
    except ValueError as e:
        raise typer.BadParameter(f"{key} must be a number; got {env_text!r}") from e
    if resolved < 0.1:
        raise typer.BadParameter(f"{key} must be at least 0.1; got {env_text!r}")
    return resolved


def _split_device_keys(value: str | None) -> list[str]:
    if not value:
        return []
    return [key for item in value.split(",") if (key := item.strip())]


def _resolve_device_keys(cli_device_keys: list[str] | None, env: dict[str, str]) -> list[str]:
    keys = [key.strip() for key in (cli_device_keys or []) if key.strip()]
    if keys:
        return keys
    env_keys = _split_device_keys(_optional_env(env, "BARK_DEVICE_KEYS"))
    if env_keys:
        return env_keys
    env_key = _optional_env(env, "BARK_DEVICE_KEY")
    return [env_key] if env_key else []


def _parse_extra_param(value: str) -> tuple[str, str]:
    key, separator, param_value = value.partition("=")
    key = key.strip()
    if separator != "=" or not key:
        raise typer.BadParameter(f"--param must use KEY=VALUE format; got {value!r}")
    return key, param_value


def _parse_extra_params(params: list[str] | None, env: dict[str, str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    env_params = _optional_env(env, "BARK_EXTRA_PARAMS")
    if env_params:
        try:
            loaded = json.loads(env_params)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"BARK_EXTRA_PARAMS must be a JSON object: {e}") from e
        if not isinstance(loaded, dict):
            raise typer.BadParameter("BARK_EXTRA_PARAMS must be a JSON object")
        parsed.update(loaded)
    for param in params or []:
        key, value = _parse_extra_param(param)
        parsed[key] = value
    return parsed


def _add_text(payload: dict[str, Any], key: str, value: str | None) -> None:
    if value is not None:
        payload[key] = value


def _add_number(payload: dict[str, Any], key: str, value: int | float | None) -> None:
    if value is not None:
        payload[key] = value


def _add_flag(payload: dict[str, Any], key: str, value: bool | None) -> None:
    if value is not None:
        payload[key] = "1" if value else "0"


def _validate_send_payload(payload: dict[str, Any]) -> None:
    if payload.get("delete") == "1" and not payload.get("id"):
        raise typer.BadParameter("--delete requires --id")
    if payload.get("delete") == "1":
        return
    if payload.get("ciphertext"):
        return
    if not any(payload.get(key) for key in ("title", "subtitle", "body", "markdown")):
        raise typer.BadParameter("send requires at least one of --title, --subtitle, --body, --markdown, --ciphertext, or --delete with --id")


@cmd.command()
def install(
    agents: list[AgentOption] | None = typer.Option(None, "--agent", help="要安装插件的 agent。可重复指定多个；默认安装所有支持且本地可用的 agent。"),
) -> None:
    """为本地可用的 agent 安装 bark-agent-hook 插件或适配器。

    未传 --agent 时会检查 PATH 中的 codex、claude、openclaw 和 node CLI；缺失的 CLI 会跳过。

    安装的插件:
      Codex:        bark-agent-hook-codex@bark-agent-hook
      Claude Code:  bark-agent-hook@bark-agent-hook --scope user
      OpenClaw:     plugins/bark-agent-hook-openclaw 中的本地链接插件
      Zed Claude Code ACP: ~/.bark-agent-hook/bin/claude-code-acp-bark 本地 ACP 适配器（Windows 为 .cmd 后缀）
    """
    results = _install_for_available_agents(agents)
    _print_install_results(results, Console(highlight=False, width=120))
    if _found_cli_count(results) > 0 and _succeeded(results) == 0:
        raise typer.Exit(1)


@cmd.command()
def uninstall(
    agents: list[AgentOption] | None = typer.Option(None, "--agent", help="要卸载插件的 agent。可重复指定多个；默认卸载所有支持且本地可用的 agent。"),
) -> None:
    """为本地可用的 agent 卸载 bark-agent-hook 插件。"""
    results = _uninstall_for_available_agents(agents)
    _print_uninstall_results(results, Console(highlight=False, width=120))
    if _found_cli_count(results) > 0 and _succeeded(results) == 0:
        raise typer.Exit(1)


def _resolve_level(level: BarkLevelOption | None, env: dict[str, str]) -> str | None:
    if level is not None:
        return level.value
    env_level = _optional_env(env, "BARK_LEVEL")
    if env_level is None:
        return None
    try:
        return BarkLevelOption(env_level).value
    except ValueError as e:
        choices = ", ".join(option.value for option in BarkLevelOption)
        raise typer.BadParameter(f"BARK_LEVEL must be one of: {choices}; got {env_level!r}") from e


@cmd.command()
def send(
    server: str | None = typer.Option(None, "--server", help="Bark 服务端基础 URL，不包含 device key。环境变量: BARK_SERVER。默认: https://api.day.app。"),
    device_keys: list[str] | None = typer.Option(None, "--device-key", help="Bark device key。可重复指定多个。环境变量: BARK_DEVICE_KEYS 或 BARK_DEVICE_KEY。"),
    title: str | None = typer.Option(None, "--title", help="推送标题。"),
    subtitle: str | None = typer.Option(None, "--subtitle", help="推送副标题。"),
    body: str | None = typer.Option(None, "--body", help="推送正文。如果同时提供 --markdown，Bark 会忽略 body。"),
    markdown: str | None = typer.Option(None, "--markdown", help="Markdown 推送正文，适合多行或富文本内容。"),
    level: BarkLevelOption | None = typer.Option(None, "--level", help="中断级别: critical、active、timeSensitive 或 passive。环境变量: BARK_LEVEL。"),
    volume: int | None = typer.Option(None, "--volume", min=0, max=10, help="Critical alert 音量，范围 0..10。"),
    badge: int | None = typer.Option(None, "--badge", help="Bark app badge 数字。"),
    call: bool | None = typer.Option(None, "--call/--no-call", help="是否重复通知铃声。启用时发送 call=1。"),
    auto_copy: bool | None = typer.Option(None, "--auto-copy/--no-auto-copy", help="是否自动复制推送内容。启用时发送 autoCopy=1。"),
    copy: str | None = typer.Option(None, "--copy", help="复制文本覆盖值。省略时 Bark 复制完整推送内容。"),
    sound: str | None = typer.Option(None, "--sound", help="Bark 通知声音名称。"),
    icon: str | None = typer.Option(None, "--icon", help="自定义通知图标 URL。"),
    image: str | None = typer.Option(None, "--image", help="推送图片 URL。"),
    group: str | None = typer.Option(None, "--group", help="Bark 通知分组。环境变量: BARK_GROUP。send 按字面使用；hook 模板不会在这里渲染。"),
    ciphertext: str | None = typer.Option(None, "--ciphertext", help="加密推送 ciphertext。CLI 仅透传，不负责加密。"),
    archive: bool | None = typer.Option(None, "--archive/--no-archive", help="是否保存到 Bark 历史。true 发送 isArchive=1；false 发送 isArchive=0。"),
    ttl: int | None = typer.Option(None, "--ttl", min=0, help="历史保留时间，单位秒。"),
    url: str | None = typer.Option(None, "--url", help="点击通知时打开的 URL。环境变量: BARK_URL。"),
    action: str | None = typer.Option(None, "--action", help="通知 action 类型；上游当前文档为 alert。"),
    id: str | None = typer.Option(None, "--id", help="折叠/更新通知 ID。复用 ID 会更新匹配通知。"),
    delete: bool | None = typer.Option(None, "--delete/--no-delete", help="删除指定 id 的通知。需要 --id。"),
    params: list[str] | None = typer.Option(None, "--param", help="额外 Bark 参数，格式 KEY=VALUE。可重复指定。环境变量: BARK_EXTRA_PARAMS JSON object。"),
    dry_run: bool | None = typer.Option(None, "--dry-run/--no-dry-run", help="打印最终 JSON payload，不发送 HTTP 请求。环境变量: BARK_DRY_RUN。"),
    timeout: float | None = typer.Option(None, "--timeout", min=0.1, help="HTTP 请求超时时间，单位秒。环境变量: BARK_TIMEOUT。默认: 10。"),
) -> None:
    """直接发送一条 Bark 通知。"""
    env = dict(os.environ)
    resolved_server = _resolve_option(server, env, "BARK_SERVER", "https://api.day.app")
    if resolved_server is None:
        resolved_server = "https://api.day.app"
    resolved_device_keys = _resolve_device_keys(device_keys, env)
    if not resolved_device_keys:
        raise typer.BadParameter("send requires --device-key, BARK_DEVICE_KEYS, or BARK_DEVICE_KEY")

    payload = _parse_extra_params(params, env)
    if len(resolved_device_keys) == 1:
        payload["device_key"] = resolved_device_keys[0]
        payload.pop("device_keys", None)
    else:
        payload["device_keys"] = resolved_device_keys
        payload.pop("device_key", None)

    _add_text(payload, "title", title)
    _add_text(payload, "subtitle", subtitle)
    _add_text(payload, "body", body)
    _add_text(payload, "markdown", markdown)
    _add_text(payload, "level", _resolve_level(level, env))
    _add_number(payload, "volume", volume)
    _add_number(payload, "badge", badge)
    _add_flag(payload, "call", call)
    _add_flag(payload, "autoCopy", auto_copy)
    _add_text(payload, "copy", copy)
    _add_text(payload, "sound", sound)
    _add_text(payload, "icon", icon)
    _add_text(payload, "image", image)
    _add_text(payload, "group", _resolve_option(group, env, "BARK_GROUP"))
    _add_text(payload, "ciphertext", ciphertext)
    _add_flag(payload, "isArchive", archive)
    _add_number(payload, "ttl", ttl)
    _add_text(payload, "url", _resolve_option(url, env, "BARK_URL"))
    _add_text(payload, "action", action)
    _add_text(payload, "id", id)
    _add_flag(payload, "delete", delete)
    _validate_send_payload(payload)

    if _resolve_bool_option(dry_run, env, "BARK_DRY_RUN", False):
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    resolved_timeout = _resolve_float_option(timeout, env, "BARK_TIMEOUT", 10)
    try:
        send_bark_json(resolved_server, payload, timeout=resolved_timeout)
    except httpx.HTTPError as e:
        typer.echo(f"Bark notification failed: {e}", err=True)
        raise typer.Exit(1) from e


@cmd.command()
def hook(
    runtime: Runtime = typer.Option("auto", "--runtime", help="Hook runtime: codex、claude、openclaw 或 auto。"),
    event: Event = typer.Option("auto", "--event", help="通知事件覆盖值。"),
    message: str | None = typer.Option(None, "--message", help="覆盖短通知正文。"),
    group_mode: GroupModeOption | None = typer.Option(None, "--group-mode", help="Bark 分组模式: agent、project 或 project-branch。"),
    summary_mode: SummaryMode = typer.Option("fixed", "--summary-mode", help="通知摘要模式: fixed 或 extract。"),
    summary_max_chars: int = typer.Option(DEFAULT_SUMMARY_MAX_CHARS, "--summary-max-chars", min=1, help="extract 摘要最大长度。"),
    dry_run: bool = typer.Option(False, "--dry-run", help="打印通知摘要，不发送 Bark 请求。"),
    no_dedupe: bool = typer.Option(False, "--no-dedupe", help="禁用重复通知抑制。"),
) -> None:
    """从 stdin 读取 hook JSON，并尽力发送 Bark 通知。

    配置:
      BARK_DEVICE_KEY 必填；缺失或为空时跳过通知并以 0 退出。
      BARK_SERVER 默认 https://api.day.app。
      BARK_GROUP 可为固定值或模板，会覆盖 --group-mode / AGENT_BARK_NOTIFY_GROUP_MODE。
      AGENT_BARK_NOTIFY_GROUP_MODE=agent|project|project-branch，在 BARK_GROUP 未设置时选择自动分组。
      AGENT_BARK_NOTIFY_HOOK_URL 默认为空，可设置 Bark 点击 URL 模板。
      AGENT_BARK_NOTIFY_TITLE_TEMPLATE 可设置通知标题模板。
      AGENT_BARK_NOTIFY_AUDIT_LOG=1 启用本地 JSONL 审计日志。
      AGENT_BARK_NOTIFY_AUDIT_LOG_FILE 在启用审计日志时默认 ~/.bark-agent-hook/bark-agent-hook.log。

    模板变量:
      AGENT_BARK_NOTIFY_TITLE_TEMPLATE 支持:
        {agent}, {event}, {project}, {branch}, {session}, {runtime}, {cwd_basename},
        {model}, {provider},
        {LODY_ELECTRON_BOOTSTRAP}, {LODY_ELECTRON_SESSION_USER_ID}, {LODY_SESSION_ID},
        {LODY_WORKSPACE_SESSION_ID}.
      BARK_GROUP 支持:
        {repo_or_project}, {workdir}, {branch}, {workspace}, {runtime}, {model}, {provider}.
        {repo_or_project}: 按 payload 工作目录解析；在 git 仓库内为仓库顶层目录名，否则回退到 project 名。
        project 名依次来自 payload 项目字段、项目环境变量、payload 路径 basename、当前 cwd basename。
        {workdir}: payload 工作目录 basename；payload 无路径时为当前 cwd basename。
        {branch}: 依次来自 payload 分支字段、分支环境变量、git 当前分支。
        {workspace}: Lody workspace 会话，来自 LODY_WORKSPACE_SESSION_ID；缺失时为空。
        模板使用 Python format 语法；{{repo_or_project}} 会作为字面量 {repo_or_project} 输出。
      AGENT_BARK_NOTIFY_HOOK_URL 支持:
        {runtime}, {agent}, {event}, {project}, {branch}, {session}, {session_id},
        {session_key}, {conversation_id}, {message_id}, {run_id}, {agent_id},
        {workspace_dir}, {cwd_basename}, {model}, {provider}, {LODY_ELECTRON_BOOTSTRAP},
        {LODY_ELECTRON_SESSION_USER_ID}, {LODY_SESSION_ID}, {LODY_WORKSPACE_SESSION_ID}.
      Hook URL 变量值会做 percent-encode；标题和分组变量不会 URL 编码。
    """
    env = dict(os.environ)
    payload = parse_hook_payload(_read_stdin())
    lody_settings = LodySettings()
    resolved_runtime = detect_runtime(runtime, env, payload, lody_settings)
    remember_model_context(resolved_runtime, payload, env)
    payload = payload_with_model_context(resolved_runtime, payload, env)
    resolved_event = detect_event(event, payload)
    resolved_group_mode = resolve_group_mode(group_mode, env)
    audit_record = _new_audit_record(runtime=resolved_runtime, event=resolved_event, payload=payload, summary_mode=summary_mode, lody_settings=lody_settings)
    try:
        if resolved_event is None:
            _finish_audit_record(env, audit_record, status="skipped_unsupported_event")
            if dry_run:
                typer.echo("skip: unsupported hook event")
            return

        if resolved_event == "audit_only":
            _finish_audit_record(env, audit_record, status="logged_audit_only_event")
            if dry_run:
                typer.echo("logged: audit-only event")
            return

        resolved_message = message
        if resolved_message is None and summary_mode == "extract":
            resolved_message = extract_summary(resolved_runtime, resolved_event, payload, summary_max_chars)

        skip_reason = skip_notification_reason(resolved_runtime, resolved_event, payload, resolved_message)
        if skip_reason is not None:
            _finish_audit_record(env, audit_record, status=skip_reason)
            if dry_run:
                typer.echo("skip: OpenClaw event has no deliverable reply")
            return

        notification = build_notification(
            runtime=resolved_runtime,
            event=resolved_event,
            message=resolved_message,
            env=env,
            payload=payload,
            lody_settings=lody_settings,
            group_mode=resolved_group_mode,
        )
        if notification is None:
            _finish_audit_record(env, audit_record, status="skipped_missing_device_key")
            if dry_run:
                typer.echo("skip: BARK_DEVICE_KEY is missing")
            return

        if not no_dedupe and should_dedupe_notification(resolved_runtime, resolved_event, payload) and already_sent(notification.dedupe_key, env):
            _finish_audit_record(env, audit_record, status="skipped_duplicate", notification=notification)
            if dry_run:
                typer.echo("skip: duplicate notification")
            return

        if dry_run:
            _finish_audit_record(env, audit_record, status="sent", notification=notification)
            output = {
                "title": notification.title,
                "body": notification.body,
                "markdown": notification.markdown,
                "icon": notification.icon_url,
                "group": notification.group,
                "url": notification.bark_url,
            }
            if notification.click_url:
                output["click_url"] = notification.click_url
            typer.echo(json.dumps(output, ensure_ascii=False))
            return

        try:
            send_bark(notification)
        except httpx.HTTPError as e:
            _finish_audit_record(env, audit_record, status="bark_http_error", notification=notification, error=e)
            typer.echo(f"Bark notification failed: {e}", err=True)
            return
        _finish_audit_record(env, audit_record, status="sent", notification=notification)
    except Exception as e:
        _finish_audit_record(env, audit_record, status="hook_exception", error=e)
        typer.echo(f"Bark hook failed: {e}", err=True)
        return
