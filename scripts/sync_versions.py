from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
VersionFile = tuple[str, tuple[str, ...]]
PROJECT_VERSION_FILE: VersionFile = ("pyproject.toml", ("project", "version"))
PLUGIN_VERSION_FILES: dict[str, VersionFile] = {
    "codex plugin": ("plugins/bark-agent-hook-codex/.codex-plugin/plugin.json", ("version",)),
    "claude plugin": ("plugins/bark-agent-hook-claude/.claude-plugin/plugin.json", ("version",)),
    "openclaw package": ("plugins/bark-agent-hook-openclaw/package.json", ("version",)),
    "openclaw manifest": ("plugins/bark-agent-hook-openclaw/openclaw.plugin.json", ("version",)),
}
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


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


def _read_version(repo_root: Path, label: str, relative_path: str, keys: tuple[str, ...]) -> str:
    path = repo_root / relative_path
    try:
        value = _get_nested(_read_document(path), keys)
    except (OSError, KeyError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"{label}: failed to read version from {relative_path}: {error}") from error
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{label}: version in {relative_path} must be a non-empty string")
    return value


def _version_key(label: str, version: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(version)
    if match is None:
        raise RuntimeError(f"{label}: version {version!r} must use x.y.z semantic version format")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _replace_top_level_json_version(path: Path, old_version: str, new_version: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf'(^\s*"version"\s*:\s*"){re.escape(old_version)}(")', re.MULTILINE)
    updated, count = pattern.subn(rf"\g<1>{new_version}\2", text, count=1)
    if count != 1:
        raise RuntimeError(f"{path}: failed to replace top-level version field")
    path.write_text(updated, encoding="utf-8")


def sync_plugin_versions(repo_root: Path = REPO_ROOT) -> int:
    try:
        project_relative_path, project_keys = PROJECT_VERSION_FILE
        project_version = _read_version(repo_root, "project", project_relative_path, project_keys)
        project_key = _version_key("project", project_version)

        plugin_versions: dict[str, tuple[str, str, tuple[str, ...]]] = {}
        for label, (relative_path, plugin_keys) in PLUGIN_VERSION_FILES.items():
            plugin_version = _read_version(repo_root, label, relative_path, plugin_keys)
            _version_key(label, plugin_version)
            plugin_versions[label] = (plugin_version, relative_path, plugin_keys)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    downgrade_candidates = {
        label: plugin_version
        for label, (plugin_version, _, _) in plugin_versions.items()
        if _version_key(label, plugin_version) > project_key
    }
    if downgrade_candidates:
        print("Refusing to downgrade plugin versions to the package version:", file=sys.stderr)
        print(f"  package: {project_version}", file=sys.stderr)
        for label, plugin_version in downgrade_candidates.items():
            print(f"  {label}: {plugin_version}", file=sys.stderr)
        return 1

    updated_labels: list[str] = []
    for label, (plugin_version, relative_path, keys) in plugin_versions.items():
        if plugin_version == project_version:
            continue
        if keys != ("version",):
            print(f"{label}: only top-level JSON version fields can be synchronized", file=sys.stderr)
            return 1
        try:
            _replace_top_level_json_version(repo_root / relative_path, plugin_version, project_version)
        except RuntimeError as error:
            print(error, file=sys.stderr)
            return 1
        updated_labels.append(label)

    if updated_labels:
        print(f"Updated plugin versions to match package version {project_version}:")
        for label in updated_labels:
            print(f"  {label}")
    else:
        print(f"Plugin versions already match package version: {project_version}")
    return 0


def main() -> int:
    return sync_plugin_versions()


if __name__ == "__main__":
    raise SystemExit(main())
