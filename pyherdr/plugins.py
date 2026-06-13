from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .detect import AgentDetection
from .domain.status import AgentStatus

PluginKind = Literal["detector", "launcher", "theme", "exporter"]
DetectorResult = AgentDetection | AgentStatus | str | dict[str, Any]
DetectorCallable = Callable[[str], DetectorResult]


class PluginManifest(BaseModel):
    """Validated plugin manifest schema for third-party extensions."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: PluginKind
    entrypoint: str = Field(min_length=1)
    description: str = ""
    aliases: list[str] = Field(default_factory=list)


def load_plugin_manifest(path: Path | str) -> PluginManifest:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return PluginManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"invalid plugin manifest {target}: {error}") from error


@dataclass(frozen=True)
class DetectorPlugin:
    """Loaded detector plugin entrypoint."""

    manifest: PluginManifest
    manifest_path: Path
    detect_fn: DetectorCallable

    @property
    def labels(self) -> tuple[str, ...]:
        labels = [self.manifest.name, *self.manifest.aliases]
        return tuple(_normalize_label(label) for label in labels if label.strip())

    def detect(self, content: str) -> AgentDetection:
        return _coerce_detection(self.detect_fn(content), self.manifest.name)


class DetectorPluginRegistry:
    """String-addressable registry for detector plugins."""

    def __init__(self, plugins: Iterable[DetectorPlugin] = ()) -> None:
        self._plugins: dict[str, DetectorPlugin] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: DetectorPlugin) -> None:
        for label in plugin.labels:
            self._plugins[label] = plugin

    def detect(self, label: str, content: str) -> AgentDetection | None:
        plugin = self._plugins.get(_normalize_label(label))
        return plugin.detect(content) if plugin else None

    def table(self) -> list[dict[str, Any]]:
        return [
            {
                "name": plugin.manifest.name,
                "version": plugin.manifest.version,
                "aliases": list(plugin.manifest.aliases),
                "entrypoint": plugin.manifest.entrypoint,
            }
            for plugin in dict.fromkeys(self._plugins.values())
        ]


def load_detector_plugin(path: Path | str) -> DetectorPlugin:
    """Load one detector plugin from a manifest path."""
    manifest_path = Path(path)
    manifest = load_plugin_manifest(manifest_path)
    if manifest.kind != "detector":
        raise ValueError(f"plugin manifest {manifest_path} is {manifest.kind!r}, not 'detector'")
    entrypoint = _resolve_entrypoint(manifest_path, manifest.entrypoint)
    module = _load_module(entrypoint, manifest.name)
    detect_fn = getattr(module, "detect", None)
    if not callable(detect_fn):
        raise ValueError(f"detector plugin {manifest.name!r} must expose a callable detect(content) function")
    return DetectorPlugin(manifest=manifest, manifest_path=manifest_path, detect_fn=detect_fn)


@lru_cache(maxsize=8)
def load_detector_plugin_registry(paths: tuple[str, ...]) -> DetectorPluginRegistry:
    """Load detector plugin manifests into a cached registry."""
    plugins = [load_detector_plugin(Path(path)) for path in paths]
    return DetectorPluginRegistry(plugins)


def detect_plugin_agent(label: str, content: str, manifest_paths: Iterable[str]) -> AgentDetection | None:
    """Detect a non-built-in agent state using configured detector plugins."""
    paths = tuple(str(Path(path).expanduser()) for path in manifest_paths if str(path).strip())
    if not paths:
        return None
    return load_detector_plugin_registry(paths).detect(label, content)


def _resolve_entrypoint(manifest_path: Path, entrypoint: str) -> Path:
    path = Path(entrypoint).expanduser()
    if not path.is_absolute():
        path = manifest_path.parent / path
    if not path.exists():
        raise ValueError(f"plugin entrypoint not found: {path}")
    return path


def _load_module(entrypoint: Path, name: str) -> ModuleType:
    module_name = f"pyherdr_plugin_{_normalize_label(name).replace('-', '_')}_{abs(hash(entrypoint))}"
    spec = importlib.util.spec_from_file_location(module_name, entrypoint)
    if spec is None or spec.loader is None:
        raise ValueError(f"plugin entrypoint is not importable: {entrypoint}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _coerce_detection(result: DetectorResult, plugin_name: str) -> AgentDetection:
    if isinstance(result, AgentDetection):
        return result
    if isinstance(result, AgentStatus):
        return AgentDetection(state=result)
    if isinstance(result, str):
        return AgentDetection(state=AgentStatus(result))
    if isinstance(result, dict):
        state = AgentStatus(str(result.get("state") or AgentStatus.UNKNOWN.value))
        return AgentDetection(
            state=state,
            skip_state_update=bool(result.get("skip_state_update", False)),
            visible_blocker=bool(result.get("visible_blocker", False)),
            visible_idle=bool(result.get("visible_idle", False)),
            visible_working=bool(result.get("visible_working", False)),
        )
    raise ValueError(f"detector plugin {plugin_name!r} returned unsupported result {type(result).__name__}")


def _normalize_label(label: str) -> str:
    return label.strip().lower()
