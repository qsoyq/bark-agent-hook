from __future__ import annotations

import re
from pathlib import Path

from bark_agent_hook.models import GroupMode

CODEX_ICON_URL = "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/codex-color.png"


CLAUDE_CODE_ICON_URL = "https://raw.githubusercontent.com/lobehub/lobe-icons/refs/heads/master/packages/static-png/light/claudecode-color.png"


OPENCLAW_ICON_URL = "https://openclaw.ai/apple-touch-icon.png"


LODY_ICON_URL = "https://lody.ai/favicon.ico"


DEFAULT_MESSAGES: dict[str, str] = {
    "completion": "任务已完成",
    "approval_needed": "需要你审批当前操作",
    "failed": "本轮因错误停止",
}


EVENT_LABELS: dict[str, str] = {
    "completion": "Done",
    "approval_needed": "Approval",
    "failed": "Failed",
}


MAX_MESSAGE_LENGTH = 80


DEFAULT_SUMMARY_MAX_CHARS = 120


MAX_TRANSCRIPT_BYTES = 1024 * 1024


DEDUP_TTL_SECONDS = 60 * 60


HOOK_URL_TEMPLATE_ENV = "AGENT_BARK_NOTIFY_HOOK_URL"


TITLE_TEMPLATE_ENV = "AGENT_BARK_NOTIFY_TITLE_TEMPLATE"


DEFAULT_TITLE_TEMPLATE = "[{agent}][{event}][{project}][{branch}][{session}]"


GROUP_MODE_ENV = "AGENT_BARK_NOTIFY_GROUP_MODE"


GROUP_MODE_CHOICES: tuple[GroupMode, ...] = ("agent", "project", "project-branch")


AUDIT_LOG_ENV = "AGENT_BARK_NOTIFY_AUDIT_LOG"


AUDIT_LOG_FILE_ENV = "AGENT_BARK_NOTIFY_AUDIT_LOG_FILE"


DEFAULT_AUDIT_LOG_PATH = Path("~/.bark-agent-hook/bark-agent-hook.log")


SENSITIVE_KEY_RE = re.compile(r"(?i)\b(authorization|cookie|set-cookie|x-api-key|api[_-]?key|token|secret|password|passwd|bearer)\b")


SENSITIVE_ASSIGNMENT_RE = re.compile(r"(?i)\b([a-z0-9_.-]*(?:token|secret|password|passwd|cookie|authorization|api[_-]?key)[a-z0-9_.-]*)\s*[:=]\s*('[^']*'|\"[^\"]*\"|[^\s,;]+)")


BEARER_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")


FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)


SHELL_PREFIX_RE = re.compile(r"^\s*(?:bash|zsh|sh|fish|python|python3|node|npm|pnpm|yarn|curl|ssh|scp|rsync)\b", re.IGNORECASE)


OPENCLAW_CONVERSATION_ACCESS_PATCH = '{"plugins":{"entries":{"bark-agent-hook-openclaw":{"hooks":{"allowConversationAccess":true}}}}}'
