from __future__ import annotations

import json
import os
from pathlib import Path

from .models import AppState
from .session import session_runtime_dir


def default_state_path() -> Path:
    override = os.environ.get("PYHERDR_STATE_PATH")
    if override:
        return Path(override).expanduser()
    return session_runtime_dir() / "session.json"


def save_state(state: AppState, path: Path | None = None) -> Path:
    target = path or default_state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(to_dict(state), indent=2), encoding="utf-8")
    return target


def load_state(path: Path | None = None) -> AppState:
    target = path or default_state_path()
    if not target.exists():
        return AppState.bootstrap()
    state = from_dict(json.loads(target.read_text(encoding="utf-8")))
    if not state.workspaces:
        # A saved-but-empty session (e.g. last workspace closed) bootstraps a
        # default so the server never serves an unusable empty state.
        return AppState.bootstrap()
    return state


def to_dict(state: AppState) -> dict:
    return state.model_dump(mode="json")


def from_dict(payload: dict) -> AppState:
    return AppState.model_validate(payload)
