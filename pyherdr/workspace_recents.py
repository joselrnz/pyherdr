from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .session import session_runtime_dir

MAX_RECENT_WORKSPACES = 12


def default_recents_path() -> Path:
    return session_runtime_dir() / "workspace_recents.json"


def load_workspace_recents(
    path: Path | None = None,
    *,
    limit: int = MAX_RECENT_WORKSPACES,
    include_stale: bool = False,
) -> list[dict[str, Any]]:
    target = path or default_recents_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    roots = payload.get("roots") if isinstance(payload, dict) else None
    if not isinstance(roots, list):
        return []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in roots:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            continue
        workspace_path = Path(raw_path).expanduser().resolve()
        stale = not workspace_path.is_dir()
        if (stale and not include_stale) or str(workspace_path) in seen:
            continue
        seen.add(str(workspace_path))
        records.append(
            {
                "path": str(workspace_path),
                "label": str(item.get("label") or workspace_path.name or "workspace"),
                "last_opened": _float_or_zero(item.get("last_opened")),
                "repo_root": str(item.get("repo_root") or ""),
                "stale": stale,
            }
        )
    records.sort(key=lambda record: float(record["last_opened"]), reverse=True)
    return records[:limit]


def record_workspace_recent(
    workspace_path: str,
    *,
    label: str = "",
    path: Path | None = None,
    limit: int = MAX_RECENT_WORKSPACES,
    now: float | None = None,
) -> Path:
    resolved = Path(workspace_path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"workspace recent path does not exist: {workspace_path}")
    target = path or default_recents_path()
    records = [record for record in load_workspace_recents(target, limit=limit) if record["path"] != str(resolved)]
    record = {
        "path": str(resolved),
        "label": label.strip() or resolved.name or "workspace",
        "last_opened": now if now is not None else time.time(),
        "repo_root": _git_root(resolved),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"version": 1, "roots": [record, *records][:limit]}, indent=2), encoding="utf-8")
    return target


def prune_workspace_recents(path: Path | None = None, *, limit: int = MAX_RECENT_WORKSPACES) -> dict[str, Any]:
    target = path or default_recents_path()
    if not target.exists():
        return {"path": str(target), "kept": 0, "removed": 0}
    records = load_workspace_recents(target, limit=limit, include_stale=True)
    kept = [record for record in records if not record["stale"]]
    target.write_text(
        json.dumps({"version": 1, "roots": [_stored_recent(record) for record in kept]}, indent=2),
        encoding="utf-8",
    )
    return {"path": str(target), "kept": len(kept), "removed": len(records) - len(kept)}


def remove_workspace_recent(
    workspace_path: str | Path,
    path: Path | None = None,
    *,
    limit: int = MAX_RECENT_WORKSPACES,
) -> dict[str, Any]:
    target = path or default_recents_path()
    if not target.exists():
        return {"path": str(target), "kept": 0, "removed": 0}
    resolved = str(Path(workspace_path).expanduser().resolve())
    records = load_workspace_recents(target, limit=limit, include_stale=True)
    kept = [record for record in records if record["path"] != resolved]
    target.write_text(
        json.dumps({"version": 1, "roots": [_stored_recent(record) for record in kept]}, indent=2),
        encoding="utf-8",
    )
    return {"path": str(target), "kept": len(kept), "removed": len(records) - len(kept)}


def _stored_recent(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": record["path"],
        "label": record["label"],
        "last_opened": record["last_opened"],
        "repo_root": record["repo_root"],
    }


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _git_root(path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return str(Path(result.stdout.strip()).resolve()) if result.returncode == 0 and result.stdout.strip() else ""
