"""Launcher presets for common agent and shell workflows."""

from __future__ import annotations

from dataclasses import dataclass

from .config.settings import Config
from .plugins import load_launcher_plugin_records


@dataclass(frozen=True)
class LauncherPreset:
    """A command that can be launched into a new pane/tab."""

    id: str
    label: str
    command: str
    description: str = ""
    agent: str = ""
    built_in: bool = False


def built_in_launcher_presets(default_shell: str) -> list[LauncherPreset]:
    """Return built-in launchers for common AI agents and a generic shell."""
    return [
        LauncherPreset("claude", "Claude Code", "claude", "Launch Claude Code", "claude", True),
        LauncherPreset("codex", "Codex", "codex", "Launch Codex", "codex", True),
        LauncherPreset("aider", "Aider", "aider", "Launch Aider", "aider", True),
        LauncherPreset("opencode", "OpenCode", "opencode", "Launch OpenCode", "opencode", True),
        LauncherPreset("kimi", "Kimi", "kimi", "Launch Kimi", "kimi", True),
        LauncherPreset("shell", "Generic shell", default_shell, "Launch the configured default shell", "", True),
    ]


def launcher_presets(config: Config, *, default_shell: str) -> list[LauncherPreset]:
    """Merge built-in launcher presets with configured custom launchers."""
    presets = built_in_launcher_presets(default_shell)
    seen = {preset.id for preset in presets}
    for index, item in enumerate(config.launchers.presets, start=1):
        preset_id = (item.id or item.label or f"custom-{index}").strip().lower().replace(" ", "-")
        if not item.command.strip():
            continue
        if preset_id in seen:
            preset_id = f"{preset_id}-{index}"
        seen.add(preset_id)
        presets.append(
            LauncherPreset(
                preset_id,
                item.label or item.command,
                item.command,
                item.description,
                item.agent,
                False,
            )
        )
    for index, record in enumerate(_plugin_launcher_records(config), start=1):
        preset_id = _preset_id(record.get("id") or record.get("label") or f"plugin-{index}")
        if preset_id in seen:
            preset_id = f"{preset_id}-plugin-{index}"
        seen.add(preset_id)
        presets.append(
            LauncherPreset(
                preset_id,
                record.get("label") or record["command"],
                record["command"],
                record.get("description", ""),
                record.get("agent", ""),
                False,
            )
        )
    return presets


def _plugin_launcher_records(config: Config) -> list[dict[str, str]]:
    """Return launcher plugin records, skipping invalid plugins until diagnostics exist."""
    try:
        return load_launcher_plugin_records(config.plugins.launchers)
    except ValueError:
        return []


def _preset_id(value: str) -> str:
    return value.strip().lower().replace(" ", "-")
