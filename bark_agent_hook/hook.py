from __future__ import annotations

import shutil
import subprocess

from bark_agent_hook.app import cmd
from bark_agent_hook.commands import hook, install, uninstall
from bark_agent_hook.constants import (
    CLAUDE_CODE_ICON_URL,
    CODEX_ICON_URL,
    LODY_ICON_URL,
    OPENCLAW_ICON_URL,
)
from bark_agent_hook.installer import _openclaw_plugin_dir

__all__ = (
    "CLAUDE_CODE_ICON_URL",
    "CODEX_ICON_URL",
    "LODY_ICON_URL",
    "OPENCLAW_ICON_URL",
    "_openclaw_plugin_dir",
    "cmd",
    "hook",
    "install",
    "shutil",
    "subprocess",
    "uninstall",
)

if __name__ == "__main__":
    cmd()
