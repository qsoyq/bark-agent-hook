import json

import httpx
from typer.testing import CliRunner

from bark_agent_hook import hook as agent_bark_hook

runner = CliRunner()


def _clear_agent_env(monkeypatch):
    for key in (
        "LODY_SESSION_ID",
        "LODY_WORKSPACE_SESSION_ID",
        "LODY_ELECTRON_BOOTSTRAP",
        "LODY_ELECTRON_SESSION_USER_ID",
        "__CFBundleIdentifier",
        "CLAUDECODE",
        "CLAUDE_CODE",
        "CLAUDE_PROJECT_DIR",
        "CLAUDE_CONFIG_DIR",
        "OPENCLAW_SESSION_ID",
        "OPENCLAW_WORKSPACE_DIR",
        "OPENCLAW_GATEWAY_PORT",
        "CODEX_CI",
        "CODEX_THREAD_ID",
        "BARK_DEVICE_KEY",
        "BARK_GROUP",
        "BARK_SERVER",
        "AGENT_BARK_NOTIFY_HOOK_URL",
        "AGENT_BARK_NOTIFY_TITLE_TEMPLATE",
        "AGENT_BARK_NOTIFY_GROUP_MODE",
        "AGENT_BARK_NOTIFY_PROJECT_NAME",
        "AGENT_BARK_NOTIFY_BRANCH_NAME",
        "AGENT_BARK_NOTIFY_SESSION_NAME",
        "AGENT_BARK_NOTIFY_STATE_DIR",
        "AGENT_BARK_NOTIFY_AUDIT_LOG",
        "AGENT_BARK_NOTIFY_AUDIT_LOG_FILE",
        "OPENCLAW_WORKSPACE_NAME",
        "OPENCLAW_SESSION_NAME",
        "CODEX_WORKSPACE_NAME",
        "CODEX_PROJECT_NAME",
        "CODEX_BRANCH_NAME",
        "CODEX_SESSION_NAME",
        "LODY_WORKSPACE_NAME",
        "LODY_PROJECT_NAME",
        "LODY_SESSION_NAME",
        "GIT_BRANCH",
        "BRANCH_NAME",
    ):
        monkeypatch.delenv(key, raising=False)


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_dry_run_reports_missing_device_key(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(agent_bark_hook.cmd, ["hook", "--event", "completion", "--dry-run"], input="{}")

    assert result.exit_code == 0
    assert "BARK_DEVICE_KEY is missing" in result.output


def test_audit_log_is_disabled_by_default(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(agent_bark_hook.cmd, ["hook", "--event", "completion", "--dry-run"], input="{}")

    assert result.exit_code == 0
    assert not audit_log.exists()


def test_audit_log_uses_default_path_when_enabled(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(agent_bark_hook.cmd, ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"], input=json.dumps({"session_id": "s-audit-default"}))

    assert result.exit_code == 0
    records = _read_jsonl(tmp_path / ".bark-agent-hook" / "bark-agent-hook.log")
    assert len(records) == 1
    assert records[0]["status"] == "skipped_missing_device_key"
    assert records[0]["runtime"] == "codex"
    assert records[0]["event"] == "completion"
    assert records[0]["session_id_hash"]


def test_dry_run_prints_notification(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("BARK_GROUP", "agents")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--message", "done", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s1"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[Codex][Done][demo-project]"
    assert body["body"] == "done"
    assert body["group"] == "agents"
    assert body["url"] == "https://api.day.app/device-key"
    assert "click_url" not in body


def test_default_group_mode_uses_agent_name(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "session_id": "default-group"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "Codex"


def test_group_mode_agent_uses_runtime_identity(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--event", "completion", "--group-mode", "agent", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "session_id": "agent-group"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "OpenClaw"


def test_group_mode_project_uses_project_name(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--group-mode", "project", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "session_id": "project-group"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "Readable Project"


def test_group_mode_project_branch_uses_project_and_branch(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--group-mode", "project-branch", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "branch": "refs/heads/feature/group-mode", "session_id": "project-branch-group"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "Readable Project@feature/group-mode"


def test_group_mode_project_branch_falls_back_to_project_without_branch(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--group-mode", "project-branch", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "cwd": str(tmp_path), "session_id": "project-branch-no-branch"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "Readable Project"


def test_group_mode_environment_value_is_used(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_GROUP_MODE", "project")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"workspace_name": "Env Mode Project", "session_id": "env-group-mode"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "Env Mode Project"


def test_quoted_group_mode_environment_value_is_normalized(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_GROUP_MODE", '"project"')
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"workspace_name": "Quoted Env Project", "session_id": "quoted-env-group-mode"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "Quoted Env Project"


def test_group_mode_cli_overrides_environment_value(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_GROUP_MODE", "project")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--group-mode", "agent", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "session_id": "cli-over-env-group-mode"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "Codex"


def test_bark_group_overrides_group_mode(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("BARK_GROUP", "agents")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_GROUP_MODE", "project")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--group-mode", "project-branch", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "branch_name": "feature/group-mode", "session_id": "bark-group-overrides"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["group"] == "agents"


def test_invalid_group_mode_environment_value_fails(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_GROUP_MODE", "workspace")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "session_id": "invalid-env-group-mode"}),
    )

    assert result.exit_code != 0
    assert "AGENT_BARK_NOTIFY_GROUP_MODE" in result.output
    assert "agent" in result.output
    assert "project" in result.output
    assert "project-branch" in result.output


def test_invalid_group_mode_cli_value_fails(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--group-mode", "workspace", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "session_id": "invalid-cli-group-mode"}),
    )

    assert result.exit_code != 0
    assert "Invalid value for" in result.output
    assert "group" in result.output
    assert "agent" in result.output
    assert "project" in result.output
    assert "project-branch" in result.output


def test_openclaw_completion_dry_run_prints_notification(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--event", "completion", "--dry-run"],
        input=json.dumps({"workspaceDir": "/tmp/demo-project", "sessionId": "openclaw-s1"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[OpenClaw][Done]"
    assert body["body"] == "任务已完成"
    assert body["icon"] == "https://openclaw.ai/apple-touch-icon.png"
    assert body["icon"] == agent_bark_hook.OPENCLAW_ICON_URL


def test_auto_runtime_detects_openclaw_source_icon(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "auto", "--event", "completion", "--dry-run"],
        input=json.dumps({"source": "openclaw", "workspaceDir": "/tmp/demo-project", "sessionId": "openclaw-auto-source"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[OpenClaw][Done]"
    assert body["icon"] == "https://openclaw.ai/apple-touch-icon.png"


def test_openclaw_source_matching_does_not_override_more_specific_env(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("LODY_SESSION_ID", "lody-session")

    lody_result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "auto", "--event", "completion", "--dry-run"],
        input=json.dumps({"source": "openclaw", "cwd": "/tmp/demo-project", "session_id": "lody-priority"}),
    )

    assert lody_result.exit_code == 0
    lody_body = json.loads(lody_result.output)
    assert lody_body["title"] == "[Lody][Done][demo-project]"
    assert lody_body["icon"] == agent_bark_hook.LODY_ICON_URL

    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_CODE", "1")

    claude_result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "auto", "--event", "completion", "--dry-run"],
        input=json.dumps({"source": "openclaw", "cwd": "/tmp/demo-project", "session_id": "claude-priority"}),
    )

    assert claude_result.exit_code == 0
    claude_body = json.loads(claude_result.output)
    assert claude_body["title"] == "[Claude Code][Done][demo-project]"
    assert claude_body["icon"] == agent_bark_hook.CLAUDE_CODE_ICON_URL

    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-thread")

    codex_result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "auto", "--event", "completion", "--dry-run"],
        input=json.dumps({"source": "openclaw", "cwd": "/tmp/demo-project", "session_id": "codex-priority"}),
    )

    assert codex_result.exit_code == 0
    codex_body = json.loads(codex_result.output)
    assert codex_body["title"] == "[Codex][Done][demo-project]"
    assert codex_body["icon"] == agent_bark_hook.CODEX_ICON_URL


def test_openclaw_source_matching_does_not_override_payload_runtime(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "auto", "--event", "completion", "--dry-run"],
        input=json.dumps({"runtime": "codex", "source": "openclaw", "cwd": "/tmp/demo-project", "session_id": "payload-runtime-priority"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[Codex][Done][demo-project]"
    assert body["icon"] == agent_bark_hook.CODEX_ICON_URL


def test_openclaw_auto_event_maps_agent_end(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--dry-run"],
        input=json.dumps({"source": "openclaw", "hook_event_name": "agent_end", "success": True, "workspaceDir": "/tmp/demo-project", "sessionId": "openclaw-agent-end"}),
    )

    assert result.exit_code == 0
    assert "skip: OpenClaw event has no deliverable reply" in result.output


def test_openclaw_agent_end_with_reply_context_sends_completion(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "source": "openclaw",
                "hook_event_name": "agent_end",
                "success": True,
                "last_assistant_message": "Done through agent_end.",
                "workspaceDir": "/tmp/demo-project",
                "sessionId": "openclaw-agent-end-reply",
            }
        ),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[OpenClaw][Done]"
    assert body["body"] == "Done through agent_end."


def test_openclaw_message_sent_no_reply_is_skipped(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "source": "openclaw",
                "hook_event_name": "message_sent",
                "success": True,
                "content": "NO_REPLY",
                "workspaceDir": "/tmp/demo-project",
                "messageId": "no-reply-message",
            }
        ),
    )

    assert result.exit_code == 0
    assert "skip: OpenClaw event has no deliverable reply" in result.output
    records = _read_jsonl(audit_log)
    assert records[-1]["status"] == "skipped_openclaw_no_reply"


def test_openclaw_agent_end_without_reply_context_is_skipped(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "source": "openclaw",
                "hook_event_name": "agent_end",
                "success": True,
                "workspaceDir": "/tmp/demo-project",
                "sessionId": "openclaw-agent-end-empty",
            }
        ),
    )

    assert result.exit_code == 0
    assert "skip: OpenClaw event has no deliverable reply" in result.output
    records = _read_jsonl(audit_log)
    assert records[-1]["status"] == "skipped_openclaw_silent_agent_end"


def test_openclaw_agent_end_failed_without_context_is_skipped(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "source": "openclaw",
                "hook_event_name": "agent_end",
                "success": False,
                "workspaceDir": "/tmp/demo-project",
                "sessionId": "openclaw-agent-end-failed-empty",
            }
        ),
    )

    assert result.exit_code == 0
    assert "skip: OpenClaw event has no deliverable reply" in result.output
    records = _read_jsonl(audit_log)
    assert records[-1]["status"] == "skipped_openclaw_silent_agent_end"


def test_openclaw_failed_title_omits_implicit_project_and_git_branch(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "source": "openclaw",
                "hook_event_name": "agent_end",
                "success": False,
                "error": "gateway error",
                "workspaceDir": ".",
                "agentId": "main",
                "sessionId": "openclaw-agent-end-failed-error",
            }
        ),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[OpenClaw][Failed]"
    assert body["body"] == "本轮因错误停止"


def test_openclaw_message_sent_extracts_delivered_content(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "source": "openclaw",
                "hook_event_name": "message_sent",
                "success": True,
                "content": {"text": "Telegram reply delivered."},
                "workspaceDir": "/tmp/demo-project",
                "sessionKey": "agent:main:telegram:direct:1602727481",
                "conversationId": "1602727481",
                "messageId": "42",
            }
        ),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[OpenClaw][Done]"
    assert body["body"] == "Telegram reply delivered."


def test_audit_log_records_sent_metadata_without_secrets(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "secret-device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--message", "done with token=secret", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s-audit-sent", "raw": "secret-device-key"}),
    )

    assert result.exit_code == 0
    records = _read_jsonl(audit_log)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "sent"
    assert record["project"] == "demo-project"
    assert record["title"] == "[Codex][Done][demo-project]"
    assert record["body_len"] == len("done with token=secret")
    assert record["dedupe_key_hash"]
    raw_record = json.dumps(record)
    assert "secret-device-key" not in raw_record
    assert "done with token=secret" not in raw_record
    assert "lody" not in record


def test_audit_log_records_lody_settings_passthrough(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("LODY_ELECTRON_BOOTSTRAP", " bootstrap ")
    monkeypatch.setenv("LODY_ELECTRON_SESSION_USER_ID", "user-1")
    monkeypatch.setenv("LODY_SESSION_ID", "session-1")
    monkeypatch.setenv("LODY_WORKSPACE_SESSION_ID", "workspace-session-1")
    monkeypatch.setenv("LODY_EXTRA_SECRET", "not-recorded")

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "audit-lody"}),
    )

    assert result.exit_code == 0
    record = _read_jsonl(audit_log)[0]
    assert record["lody"] == {
        "LODY_ELECTRON_BOOTSTRAP": "bootstrap",
        "LODY_ELECTRON_SESSION_USER_ID": "user-1",
        "LODY_SESSION_ID": "session-1",
        "LODY_WORKSPACE_SESSION_ID": "workspace-session-1",
    }
    assert "LODY_EXTRA_SECRET" not in record["lody"]


def test_hook_url_template_renders_lody_settings_encoded(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_BARK_NOTIFY_HOOK_URL", "https://lody.ai/users/{LODY_ELECTRON_SESSION_USER_ID}/sessions/{LODY_SESSION_ID}")
    monkeypatch.setenv("LODY_ELECTRON_SESSION_USER_ID", "user 1")
    monkeypatch.setenv("LODY_SESSION_ID", "s/demo 1")

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "hook-url-lody"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["click_url"] == "https://lody.ai/users/user%201/sessions/s%2Fdemo%201"


def test_title_template_renders_lody_settings_without_url_encoding(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_BARK_NOTIFY_TITLE_TEMPLATE", "Lody   {LODY_SESSION_ID}")
    monkeypatch.setenv("LODY_SESSION_ID", "s/demo 1")

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "title-lody"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "Lody s/demo 1"


def test_lody_electron_session_user_id_detects_lody_runtime(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("LODY_ELECTRON_SESSION_USER_ID", "user-1")

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "auto", "--event", "completion", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "lody-user-id"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[Lody][Done][demo-project]"
    assert body["group"] == "Lody"


def test_send_bark_posts_form_with_group(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("BARK_GROUP", "agents")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    calls: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"code": 200})

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "approval_needed"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s2"}),
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.day.app/device-key"
    form = calls[0].content.decode()
    assert "title=%5BCodex%5D%5BApproval%5D%5Bdemo-project%5D" in form
    assert "body=%E9%9C%80%E8%A6%81%E4%BD%A0%E5%AE%A1%E6%89%B9%E5%BD%93%E5%89%8D%E6%93%8D%E4%BD%9C" in form
    assert "group=agents" in form
    assert "url=" not in form


def test_hook_url_template_renders_encoded_click_url_without_audit_leak(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv(
        "AGENT_BARK_NOTIFY_HOOK_URL",
        "lody://session/{session_id}/{session_key}/{conversation_id}/{message_id}/{run_id}/{agent_id}/{workspace_dir}/{cwd_basename}/{runtime}/{agent}/{event}/{project}/{branch}/{session}",
    )
    monkeypatch.setenv("AGENT_BARK_NOTIFY_SESSION_NAME", "main session")

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--event", "completion", "--dry-run"],
        input=json.dumps(
            {
                "project_name": "Demo Project",
                "branch": "refs/heads/feature/click url",
                "sessionId": "s/demo 1",
                "sessionKey": "agent:main:telegram",
                "conversationId": "conv/1",
                "messageId": "msg 2",
                "runId": "run:3",
                "agentId": "agent/4",
                "workspaceDir": "/tmp/demo project",
            }
        ),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["click_url"] == (
        "lody://session/s%2Fdemo%201/agent%3Amain%3Atelegram/conv%2F1/msg%202/run%3A3/agent%2F4/"
        "%2Ftmp%2Fdemo%20project/demo%20project/openclaw/OpenClaw/completion/Demo%20Project/feature%2Fclick%20url/main%20session"
    )
    audit_text = audit_log.read_text()
    assert "lody://session" not in audit_text
    assert "s%2Fdemo%201" not in audit_text


def test_send_bark_posts_form_with_click_url(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_HOOK_URL", "lody://session/{session_id}")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    calls: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"code": 200})

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s/demo 1"}),
    )

    assert result.exit_code == 0
    assert len(calls) == 1
    form = calls[0].content.decode()
    assert "url=lody%3A%2F%2Fsession%2Fs%252Fdemo%25201" in form


def test_invalid_hook_url_template_is_omitted(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_HOOK_URL", "lody://session/{missing}")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    calls: list[httpx.Request] = []
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"code": 200})

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))

    dry_run = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run", "--no-dedupe"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "invalid-template-dry-run"}),
    )
    sent = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--no-dedupe"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "invalid-template-post"}),
    )

    assert dry_run.exit_code == 0
    assert "click_url" not in json.loads(dry_run.output)
    assert sent.exit_code == 0
    assert len(calls) == 1
    assert "url=" not in calls[0].content.decode()


def test_audit_log_records_http_error_without_url_secret(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("BARK_DEVICE_KEY", "secret-device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    real_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request, text="failed")

    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler)))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s-audit-http-error"}),
    )

    assert result.exit_code == 0
    records = _read_jsonl(audit_log)
    assert len(records) == 1
    record = records[0]
    assert record["status"] == "bark_http_error"
    assert record["error_class"] == "HTTPStatusError"
    assert "secret-device-key" not in record["error_message"]
    assert "https://api.day.app/[REDACTED]" in record["error_message"]


def test_duplicate_event_is_skipped(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    payload = json.dumps({"cwd": "/tmp/demo-project", "session_id": "s3"})

    first = runner.invoke(agent_bark_hook.cmd, ["hook", "--event", "completion", "--dry-run"], input=payload)
    second = runner.invoke(agent_bark_hook.cmd, ["hook", "--event", "completion", "--dry-run"], input=payload)

    assert first.exit_code == 0
    assert second.exit_code == 0
    assert "duplicate notification" in second.output


def test_audit_log_distinguishes_skip_statuses(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(audit_log))
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    unsupported = runner.invoke(agent_bark_hook.cmd, ["hook", "--runtime", "codex", "--dry-run"], input=json.dumps({"hook_event_name": "Notification", "session_id": "s-unsupported"}))
    missing_key = runner.invoke(agent_bark_hook.cmd, ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"], input=json.dumps({"session_id": "s-missing"}))
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    first = runner.invoke(agent_bark_hook.cmd, ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"], input=json.dumps({"session_id": "s-duplicate"}))
    duplicate = runner.invoke(agent_bark_hook.cmd, ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"], input=json.dumps({"session_id": "s-duplicate"}))

    assert unsupported.exit_code == 0
    assert missing_key.exit_code == 0
    assert first.exit_code == 0
    assert duplicate.exit_code == 0
    assert [record["status"] for record in _read_jsonl(audit_log)] == [
        "skipped_unsupported_event",
        "skipped_missing_device_key",
        "sent",
        "skipped_duplicate",
    ]


def test_audit_log_write_failure_does_not_fail_hook(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", "1")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", str(tmp_path))
    monkeypatch.delenv("BARK_DEVICE_KEY", raising=False)
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(agent_bark_hook.cmd, ["hook", "--event", "completion", "--dry-run"], input="{}")

    assert result.exit_code == 0
    assert "BARK_DEVICE_KEY is missing" in result.output


def test_quoted_environment_values_are_normalized(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    audit_log = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG", '"1"')
    monkeypatch.setenv("AGENT_BARK_NOTIFY_AUDIT_LOG_FILE", f'"{audit_log}"')
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("BARK_DEVICE_KEY", '"device-key"')
    monkeypatch.setenv("BARK_GROUP", '"Agent"')
    monkeypatch.setenv("BARK_SERVER", '"https://example.invalid"')

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--event", "completion", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"source": "openclaw", "hook_event_name": "message_sent", "content": "quoted env", "messageId": "quoted-env"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["group"] == "Agent"
    assert body["url"] == "https://example.invalid/device-key"
    records = _read_jsonl(audit_log)
    assert records[-1]["runtime"] == "openclaw"
    assert records[-1]["hook_event_name"] == "message_sent"
    assert records[-1]["status"] == "sent"


def test_auto_event_maps_permission_request(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "claude", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "hook_event_name": "PermissionRequest", "session_id": "s4"}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"] == "[Claude Code][Approval][demo-project]"
    assert body["body"] == "需要你审批当前操作"


def test_titles_include_normalized_event_for_codex_and_claude(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    cases = [
        (
            ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "codex-done"},
            "[Codex][Done][demo-project]",
        ),
        (
            ["hook", "--runtime", "codex", "--event", "approval_needed", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "codex-approval"},
            "[Codex][Approval][demo-project]",
        ),
        (
            ["hook", "--runtime", "claude", "--event", "completion", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "claude-done"},
            "[Claude Code][Done][demo-project]",
        ),
        (
            ["hook", "--runtime", "claude", "--event", "approval_needed", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "claude-approval"},
            "[Claude Code][Approval][demo-project]",
        ),
        (
            ["hook", "--runtime", "codex", "--event", "failed", "--dry-run"],
            {"cwd": "/tmp/demo-project", "session_id": "codex-failed"},
            "[Codex][Failed][demo-project]",
        ),
    ]

    for args, payload, expected_title in cases:
        result = runner.invoke(agent_bark_hook.cmd, args, input=json.dumps(payload))

        assert result.exit_code == 0
        assert json.loads(result.output)["title"] == expected_title


def test_default_title_includes_branch_and_session_when_available(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps(
            {
                "project_name": "Readable Project",
                "branch": "refs/heads/feature/title-context",
                "session_name": "Morning Work",
                "session_id": "title-context",
            }
        ),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "[Codex][Done][Readable Project][feature/title-context][Morning Work]"


def test_default_title_reads_branch_from_git_cwd(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run(args, **kwargs):
        assert args == ["git", "-C", str(repo), "branch", "--show-current"]
        return agent_bark_hook.subprocess.CompletedProcess(args, 0, stdout="feature/git-cwd\n", stderr="")

    monkeypatch.setattr(agent_bark_hook.subprocess, "run", fake_run)

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"cwd": str(repo), "session_id": "git-cwd"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "[Codex][Done][repo][feature/git-cwd]"


def test_title_template_can_be_configured(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_BARK_NOTIFY_TITLE_TEMPLATE", "{event}: {project} via {agent}/{runtime}/{cwd_basename}/{branch}/{session}")

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"project_name": "Readable Project", "cwd": "/tmp/path-basename", "branch_name": "feature/custom", "session_name": "Focus", "session_id": "templated-title"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "Done: Readable Project via Codex/codex/path-basename/feature/custom/Focus"


def test_project_name_prefers_payload_and_env_names_before_paths(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("CODEX_WORKSPACE_NAME", "Env Workspace")

    from_payload = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"workspace_name": "Payload Workspace", "cwd": "/tmp/path-project", "session_id": "project-payload"}),
    )
    from_env = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/path-project", "session_id": "project-env"}),
    )

    assert from_payload.exit_code == 0
    assert json.loads(from_payload.output)["title"] == "[Codex][Done][Payload Workspace]"
    assert from_env.exit_code == 0
    assert json.loads(from_env.output)["title"] == "[Codex][Done][Env Workspace]"


def test_explicit_runtime_controls_title_even_in_lody_env(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("LODY_SESSION_ID", "lody-session")
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "claude", "--event", "completion", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "explicit-claude"}),
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["title"] == "[Claude Code][Done][demo-project]"


def test_extract_completion_uses_last_assistant_message(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "completion", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "cwd": "/tmp/demo-project",
                "session_id": "s5",
                "last_assistant_message": "Implemented safe summaries.\n\n```text\nlarge output\n```",
            }
        ),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Implemented safe summaries."


def test_extract_completion_falls_back_to_transcript(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path / "state"))
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "do the thing"}),
                json.dumps({"type": "assistant_message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Finished transcript work."}]}}),
            ]
        )
    )

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "claude", "--event", "completion", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s6", "transcript_path": str(transcript)}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Finished transcript work."


def test_extract_completion_falls_back_to_fixed_message(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--event", "completion", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"cwd": "/tmp/demo-project", "session_id": "s7", "last_assistant_message": '{"raw": "json", "payload": true}'}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "任务已完成"


def test_extract_approval_uses_tool_description(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "approval_needed", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"session_id": "s8", "tool_input": {"description": "Run pytest for the Bark summary tests"}}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Run pytest for the Bark summary tests"


def test_extract_openclaw_approval_uses_require_approval_description(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "openclaw", "--event", "approval_needed", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps(
            {
                "sessionId": "openclaw-approval",
                "toolName": "exec",
                "params": {"command": "pytest tests/agent_bark_hook_test.py"},
                "requireApproval": {"description": "Allow pytest for the OpenClaw Bark plugin"},
            }
        ),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["title"].startswith("[OpenClaw][Approval]")
    assert body["body"] == "Allow pytest for the OpenClaw Bark plugin"


def test_extract_approval_uses_safe_tool_detail(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "claude", "--event", "approval_needed", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"session_id": "s9", "tool_name": "Edit", "tool_input": {"file_path": "/tmp/demo-project/app.py"}}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Edit 需要审批：/tmp/demo-project/app.py"


def test_extract_approval_uses_tool_name_without_detail(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    result = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--runtime", "codex", "--event", "approval_needed", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"session_id": "s9-tool-only", "tool_name": "Bash", "tool_input": {"command": "curl https://example.test?token=secret " + ("x" * 100)}}),
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["body"] == "Bash 需要审批"


def test_extract_redacts_secrets_url_queries_and_long_commands(monkeypatch, tmp_path):
    _clear_agent_env(monkeypatch)
    monkeypatch.setenv("BARK_DEVICE_KEY", "device-key")
    monkeypatch.setenv("AGENT_BARK_NOTIFY_STATE_DIR", str(tmp_path))

    completion = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--event", "completion", "--summary-mode", "extract", "--summary-max-chars", "80", "--dry-run"],
        input=json.dumps(
            {
                "session_id": "s10",
                "last_assistant_message": "Fetched https://example.test/path?token=secret&x=1 with api_key=abc123 and Authorization: Bearer secret",
            }
        ),
    )
    approval = runner.invoke(
        agent_bark_hook.cmd,
        ["hook", "--event", "approval_needed", "--summary-mode", "extract", "--dry-run"],
        input=json.dumps({"session_id": "s11", "tool_name": "Shell", "tool_input": {"command": "curl https://example.test?token=secret " + ("x" * 100)}}),
    )

    assert completion.exit_code == 0
    completion_body = json.loads(completion.output)["body"]
    assert "secret" not in completion_body.lower()
    assert "?token=" not in completion_body
    assert "[REDACTED]" in completion_body
    assert approval.exit_code == 0
    assert json.loads(approval.output)["body"] == "Shell 需要审批"
