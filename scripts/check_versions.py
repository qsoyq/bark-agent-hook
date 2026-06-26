from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERSION_FILES = {
    "project": ("pyproject.toml", ("project", "version")),
    "codex plugin": ("plugins/bark-agent-hook-codex/.codex-plugin/plugin.json", ("version",)),
    "claude plugin": ("plugins/bark-agent-hook-claude/.claude-plugin/plugin.json", ("version",)),
    "openclaw package": ("plugins/bark-agent-hook-openclaw/package.json", ("version",)),
    "openclaw manifest": ("plugins/bark-agent-hook-openclaw/openclaw.plugin.json", ("version",)),
}


def _read_document(path: Path) -> object:
    if path.suffix == ".toml":
        return tomllib.loads(path.read_text(encoding="utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def _get_nested(document: object, keys: tuple[str, ...]) -> object:
    value = document
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise KeyError(key)
        value = value[key]
    return value


def main() -> int:
    versions: dict[str, str] = {}
    for label, (relative_path, keys) in VERSION_FILES.items():
        path = REPO_ROOT / relative_path
        try:
            value = _get_nested(_read_document(path), keys)
        except (OSError, KeyError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
            print(f"{label}: failed to read version from {relative_path}: {error}", file=sys.stderr)
            return 1
        if not isinstance(value, str) or not value.strip():
            print(f"{label}: version in {relative_path} must be a non-empty string", file=sys.stderr)
            return 1
        versions[label] = value

    unique_versions = set(versions.values())
    if len(unique_versions) != 1:
        print("Package and plugin versions are out of sync:", file=sys.stderr)
        for label, version in versions.items():
            print(f"  {label}: {version}", file=sys.stderr)
        return 1

    version = next(iter(unique_versions))
    print(f"Package and plugin versions are in sync: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
