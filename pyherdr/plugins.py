from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PluginKind = Literal["detector", "launcher", "theme", "exporter"]


class PluginManifest(BaseModel):
    """Validated plugin manifest schema for third-party extensions."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: PluginKind
    entrypoint: str = Field(min_length=1)
    description: str = ""


def load_plugin_manifest(path: Path | str) -> PluginManifest:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return PluginManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"invalid plugin manifest {target}: {error}") from error
