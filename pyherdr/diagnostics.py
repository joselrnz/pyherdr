from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .store import default_state_path
from .workflow import default_workflow_log_path, redact


def create_debug_bundle(
    output: Path | str,
    *,
    state_path: Path | None = None,
    workflow_path: Path | None = None,
    server_info_path: Path | None = None,
) -> Path:
    """Create a small redacted diagnostics zip for support/debugging."""
    target = Path(output).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    state = state_path or default_state_path()
    workflow = workflow_path or default_workflow_log_path()
    server = server_info_path or state.parent / "server.json"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "type": "pyherdr_debug_bundle",
                    "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                    "files": ["state.json", "workflow.jsonl", "server.json"],
                },
                indent=2,
            ),
        )
        archive.writestr("state.json", _redacted_json_file(state))
        archive.writestr("workflow.jsonl", _redacted_jsonl_file(workflow))
        archive.writestr("server.json", _redacted_json_file(server))
    return target


def _redacted_json_file(path: Path) -> str:
    if not path.exists():
        return json.dumps({"missing": str(path)}, indent=2)
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        payload = {"error": str(error)}
    return json.dumps(redact(payload), indent=2)


def _redacted_jsonl_file(path: Path) -> str:
    if not path.exists():
        return ""
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload: Any = json.loads(line)
        except json.JSONDecodeError:
            payload = line
        lines.append(json.dumps(redact(payload), sort_keys=True))
    return "\n".join(lines) + ("\n" if lines else "")
