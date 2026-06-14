"""Run a deterministic PyHerdr plugin extension scenario.

Usage:
    python -m tools.plugin_scenario --json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from pyherdr.api import dispatch
from pyherdr.config import Config, PluginsConfig
from pyherdr.config.theme import theme_registry
from pyherdr.launchers import launcher_presets
from pyherdr.models import AppState
from pyherdr.plugins import (
    load_detector_plugin,
    load_exporter_plugin,
    load_plugin_manifest,
    load_theme_plugin,
    plugin_safety_summary,
)
from pyherdr.recording import build_session_recording
from pyherdr.store import save_state

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "examples" / "plugins" / "agent_workflow"
DETECTOR_MANIFEST = PLUGIN_ROOT / "detector" / "plugin.json"
LAUNCHER_MANIFEST = PLUGIN_ROOT / "launcher" / "plugin.json"
THEME_MANIFEST = PLUGIN_ROOT / "theme" / "plugin.json"
EXPORTER_MANIFEST = PLUGIN_ROOT / "exporter" / "plugin.json"
PLUGIN_MARKER = "PYHERDR_PLUGIN_BLOCKED"


def run_plugin_scenario(work_dir: Path, *, plugin_root: Path = PLUGIN_ROOT) -> dict[str, Any]:
    """Exercise detector, launcher, theme, and exporter plugin paths."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    manifests = _manifests(plugin_root)
    steps: list[str] = []

    manifest_records = []
    for role, manifest_path in manifests.items():
        manifest = load_plugin_manifest(manifest_path)
        manifest_records.append(
            {
                "role": role,
                "name": manifest.name,
                "kind": manifest.kind,
                "version": manifest.version,
                "path": str(manifest_path),
                "safety": plugin_safety_summary(manifest),
            }
        )
    steps.append("manifests_validated")

    config = Config(plugins=PluginsConfig(launchers=[str(manifests["launcher"])]))
    launcher_map = {preset.id: preset for preset in launcher_presets(config, default_shell="pwsh")}
    required_launchers = {"walter-ssh", "ollama-local", "codex-cli", "claude-code"}
    missing = required_launchers - set(launcher_map)
    if missing:
        raise RuntimeError(f"missing launcher plugin records: {sorted(missing)}")
    launchers = {launcher_id: launcher_map[launcher_id].__dict__ for launcher_id in sorted(required_launchers)}
    steps.append("launchers_loaded")

    detector_plugin = load_detector_plugin(manifests["detector"])
    detection = detector_plugin.detect(f"{PLUGIN_MARKER}: user approval required")
    if detection.state.value != "blocked":
        raise RuntimeError(f"detector did not report blocked: {detection.state.value}")
    steps.append("detector_loaded")

    [theme_record] = load_theme_plugin(manifests["theme"]).themes()
    themes = theme_registry([str(manifests["theme"])])
    if theme_record["name"] not in themes:
        raise RuntimeError("plugin theme was not registered")
    steps.append("theme_loaded")

    state = AppState.bootstrap(str(work_dir))
    workspace = state.focused_workspace
    if workspace is None or workspace.focused_tab is None:
        raise RuntimeError("failed to bootstrap plugin workspace")
    workspace.label = "plugin-lab"
    tab = workspace.focused_tab
    tab.label = "extensions"
    pane = tab.focused_pane
    if pane is None:
        raise RuntimeError("failed to bootstrap plugin pane")
    pane.title = "plugin-agent"
    pane.agent = "pyherdr-plugin-agent"
    pane.command = launchers["codex-cli"]["command"]
    pane.append_output("PYHERDR_PLUGIN_WORKING")
    pane.append_output(f"{PLUGIN_MARKER}: waiting on operator")
    steps.append("workspace_created")

    pane.status = detection.state
    pane_record = _pane_record(state, pane.id)
    if pane_record["agent_status"] != "blocked":
        raise RuntimeError("plugin detection was not reflected in pane status")
    steps.append("plugin_status_detected")

    recording = build_session_recording(state, _capture_pane)
    export_output = work_dir / "plugin-scenario.md"
    export_result = load_exporter_plugin(manifests["exporter"]).export(
        recording,
        export_output,
        exporter_id="markdown",
    )
    if not export_output.exists():
        raise RuntimeError("plugin exporter did not create an output file")
    steps.append("recording_exported")

    state_file = save_state(state, work_dir / "plugin-session.json")
    steps.append("state_saved")

    return {
        "result": "ok",
        "steps": steps,
        "manifests": manifest_records,
        "launchers": launchers,
        "detector": {
            "plugin": detector_plugin.manifest.name,
            "labels": list(detector_plugin.labels),
            "state": detection.state.value,
            "visible_blocker": detection.visible_blocker,
        },
        "theme": {
            "name": theme_record["name"],
            "registered": theme_record["name"] in themes,
            "accent": theme_record["palette"]["accent"],
        },
        "pane": pane_record,
        "export": export_result,
        "state_file": str(state_file),
    }


def default_work_dir() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(".artifacts") / "plugin-scenario" / f"{stamp}-{os.getpid()}"


def _manifests(plugin_root: Path) -> dict[str, Path]:
    return {
        "detector": plugin_root / "detector" / "plugin.json",
        "launcher": plugin_root / "launcher" / "plugin.json",
        "theme": plugin_root / "theme" / "plugin.json",
        "exporter": plugin_root / "exporter" / "plugin.json",
    }


def _capture_pane(pane: Any) -> dict[str, Any]:
    lines = list(pane.output)
    return {
        "type": "pane_capture",
        "pane_id": pane.id,
        "styled": False,
        "total_lines": len(lines),
        "line_count": len(lines),
        "truncated": False,
        "lines": lines,
        "output": "\n".join(lines),
    }


def _pane_record(state: AppState, pane_id: str) -> dict[str, Any]:
    response = dispatch(state, {"id": "plugin", "method": "pane.get", "params": {"pane_id": pane_id}})
    error = response.get("error")
    if error:
        raise RuntimeError(str(error.get("message") or error))
    result = response.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("pane"), dict):
        raise RuntimeError(f"unexpected pane response: {response}")
    return result["pane"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PyHerdr plugin extension scenario")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir(), help="directory for scenario artifacts")
    parser.add_argument("--plugin-root", type=Path, default=PLUGIN_ROOT, help="example plugin pack root")
    parser.add_argument("--json", action="store_true", help="print machine-readable scenario report")
    args = parser.parse_args(argv)

    report = run_plugin_scenario(args.work_dir, plugin_root=args.plugin_root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"plugin scenario: {report['result']}")
        print(f"launchers: {', '.join(report['launchers'])}")
        print(f"detector: {report['detector']['plugin']} -> {report['detector']['state']}")
        print(f"export: {report['export']['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
