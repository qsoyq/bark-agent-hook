import json
import sys
from pathlib import Path

from scripts.check_versions import main as check_versions
from scripts.sync_versions import PLUGIN_VERSION_FILES, sync_plugin_versions

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib


def _project_version() -> str:
    doc = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = doc["project"]
    assert isinstance(project, dict)
    version = project["version"]
    assert isinstance(version, str)
    return version


def _write_version_fixture(repo_root: Path, project_version: str, plugin_versions: dict[str, str]) -> None:
    (repo_root / "pyproject.toml").write_text(
        f'[project]\nname = "bark-agent-hook"\nversion = "{project_version}"\n',
        encoding="utf-8",
    )
    for label, (relative_path, _) in PLUGIN_VERSION_FILES.items():
        path = repo_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": plugin_versions[label], "name": label}, indent=2) + "\n",
            encoding="utf-8",
        )


def _read_fixture_plugin_versions(repo_root: Path) -> dict[str, str]:
    versions = {}
    for label, (relative_path, _) in PLUGIN_VERSION_FILES.items():
        document = json.loads((repo_root / relative_path).read_text(encoding="utf-8"))
        version = document["version"]
        assert isinstance(version, str)
        versions[label] = version
    return versions


def test_codex_bark_plugin_uses_default_hook_config_path():
    plugin_root = Path("plugins/bark-agent-hook-codex")
    manifest = json.loads((plugin_root / ".codex-plugin/plugin.json").read_text())

    assert "hooks" not in manifest
    assert (plugin_root / "hooks/hooks.json").is_file()


def test_codex_bark_plugin_hook_config_uses_codex_schema():
    plugin_root = Path("plugins/bark-agent-hook-codex")
    hook_config = json.loads((plugin_root / "hooks/hooks.json").read_text())

    permission_hook = hook_config["hooks"]["PermissionRequest"][0]["hooks"][0]
    stop_hook = hook_config["hooks"]["Stop"][0]["hooks"][0]
    assert permission_hook == {
        "type": "command",
        "command": "bark-agent-hook hook --runtime codex --event approval_needed --summary-mode extract",
    }
    assert stop_hook == {
        "type": "command",
        "command": "bark-agent-hook hook --runtime codex --event completion --summary-mode extract",
    }


def test_bark_plugin_versions_match_project_version():
    project_version = _project_version()
    codex_manifest = json.loads(Path("plugins/bark-agent-hook-codex/.codex-plugin/plugin.json").read_text())
    claude_manifest = json.loads(Path("plugins/bark-agent-hook-claude/.claude-plugin/plugin.json").read_text())
    openclaw_package = json.loads(Path("plugins/bark-agent-hook-openclaw/package.json").read_text())
    openclaw_manifest = json.loads(Path("plugins/bark-agent-hook-openclaw/openclaw.plugin.json").read_text())

    assert codex_manifest["version"] == project_version
    assert claude_manifest["version"] == project_version
    assert openclaw_package["version"] == project_version
    assert openclaw_manifest["version"] == project_version


def test_bark_plugin_versions_stay_in_sync_across_targets():
    versions = {
        "codex": json.loads(Path("plugins/bark-agent-hook-codex/.codex-plugin/plugin.json").read_text())["version"],
        "claude": json.loads(Path("plugins/bark-agent-hook-claude/.claude-plugin/plugin.json").read_text())["version"],
        "openclaw-package": json.loads(Path("plugins/bark-agent-hook-openclaw/package.json").read_text())["version"],
        "openclaw-manifest": json.loads(Path("plugins/bark-agent-hook-openclaw/openclaw.plugin.json").read_text())["version"],
    }

    assert set(versions.values()) == {_project_version()}


def test_version_check_script_accepts_current_versions(capsys):
    assert check_versions() == 0
    assert _project_version() in capsys.readouterr().out


def test_sync_plugin_versions_upgrades_lower_plugin_versions(tmp_path, capsys):
    _write_version_fixture(
        tmp_path,
        "0.2.0",
        {label: "0.1.0" for label in PLUGIN_VERSION_FILES},
    )

    assert sync_plugin_versions(tmp_path) == 0
    assert set(_read_fixture_plugin_versions(tmp_path).values()) == {"0.2.0"}
    assert "Updated plugin versions to match package version 0.2.0" in capsys.readouterr().out


def test_sync_plugin_versions_refuses_to_downgrade_plugins(tmp_path, capsys):
    plugin_versions = {label: "0.1.0" for label in PLUGIN_VERSION_FILES}
    plugin_versions["codex plugin"] = "0.3.0"
    _write_version_fixture(tmp_path, "0.2.0", plugin_versions)

    assert sync_plugin_versions(tmp_path) == 1
    assert _read_fixture_plugin_versions(tmp_path) == plugin_versions
    captured = capsys.readouterr()
    assert "Refusing to downgrade plugin versions to the package version" in captured.err
    assert "codex plugin: 0.3.0" in captured.err


def test_claude_marketplace_exposes_bark_plugin():
    marketplace = json.loads(Path(".claude-plugin/marketplace.json").read_text())
    [plugin] = marketplace["plugins"]

    assert marketplace["name"] == "bark-agent-hook"
    assert plugin["name"] == "bark-agent-hook"
    assert plugin["source"] == "./plugins/bark-agent-hook-claude"
    assert Path("plugins/bark-agent-hook-claude/.claude-plugin/plugin.json").is_file()


def test_openclaw_bark_plugin_has_native_manifest_and_runtime_entry():
    plugin_root = Path("plugins/bark-agent-hook-openclaw")
    package_json = json.loads((plugin_root / "package.json").read_text())
    manifest = json.loads((plugin_root / "openclaw.plugin.json").read_text())
    source_entry = (plugin_root / "index.ts").read_text()
    runtime_entry = (plugin_root / "index.js").read_text()

    assert package_json["openclaw"]["extensions"] == ["./index.ts"]
    assert package_json["openclaw"]["runtimeExtensions"] == ["./index.js"]
    assert manifest["id"] == "bark-agent-hook-openclaw"
    assert manifest["activation"]["onStartup"] is True
    assert manifest["configSchema"] == {"type": "object", "additionalProperties": False}
    assert 'api.on(\n      "agent_end"' in source_entry
    assert "bark-agent-hook" in runtime_entry
    assert "--runtime" in runtime_entry
    assert "openclaw" in runtime_entry
