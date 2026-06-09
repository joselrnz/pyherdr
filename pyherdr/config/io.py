"""Config file location and loading (ported from herdr src/config/io.rs)."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

from .settings import Config

APP_NAME = "PyHerdr"
APP_SLUG = "pyherdr"


def config_path() -> Path:
    """Return the config file path (``PYHERDR_CONFIG_PATH`` overrides)."""
    override = os.environ.get("PYHERDR_CONFIG_PATH")
    if override:
        return Path(override).expanduser()

    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / APP_NAME / "config.toml"

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "config.toml"

    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / APP_SLUG / "config.toml"


def load_config(path: Path | None = None) -> Config:
    """Load config from TOML, returning defaults when the file is absent."""
    target = path or config_path()
    if not target.exists():
        return Config()
    with target.open("rb") as handle:
        data = tomllib.load(handle)
    return Config.model_validate(data)
