from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

Runtime = Literal["auto", "codex", "claude", "openclaw"]


Event = Literal["auto", "completion", "approval_needed", "attention_needed", "failed", "audit_only"]


SummaryMode = Literal["fixed", "extract"]


GroupMode = Literal["agent", "project", "project-branch"]


InstallStatus = Literal["installed", "updated", "downgraded", "unchanged", "removed", "failed", "skipped"]


class GroupModeOption(str, Enum):
    agent = "agent"
    project = "project"
    project_branch = "project-branch"


class AgentOption(str, Enum):
    codex = "codex"
    claude = "claude"
    openclaw = "openclaw"


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class InstallResult:
    agent: str
    status: InstallStatus
    before_version: str | None
    after_version: str | None
    cli_path: str | None
    note: str
    failed_command: list[str] | None = None


@dataclass(frozen=True)
class AgentIdentity:
    name: str
    icon_url: str


@dataclass(frozen=True)
class Notification:
    title: str
    body: str
    markdown: str | None
    icon_url: str
    group: str | None
    bark_url: str
    click_url: str | None
    dedupe_key: str
