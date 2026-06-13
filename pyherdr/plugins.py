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
LauncherRecord = dict[str, str]
ThemeRecord = dict[str, Any]
ExporterRecord = dict[str, str]


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


@dataclass(frozen=True)
class LauncherPlugin:
    """Loaded launcher plugin entrypoint."""

    manifest: PluginManifest
    manifest_path: Path
    launchers_fn: Callable[[], Any]

    def launchers(self) -> list[LauncherRecord]:
        items = _coerce_launcher_items(self.launchers_fn())
        return [_coerce_launcher_record(item, self.manifest.name) for item in items]


def load_launcher_plugin(path: Path | str) -> LauncherPlugin:
    """Load one launcher plugin from a manifest path."""
    manifest_path = Path(path)
    manifest = load_plugin_manifest(manifest_path)
    if manifest.kind != "launcher":
        raise ValueError(f"plugin manifest {manifest_path} is {manifest.kind!r}, not 'launcher'")
    entrypoint = _resolve_entrypoint(manifest_path, manifest.entrypoint)
    module = _load_module(entrypoint, manifest.name)
    launchers_fn = getattr(module, "launchers", None)
    if not callable(launchers_fn):
        raise ValueError(f"launcher plugin {manifest.name!r} must expose a callable launchers() function")
    return LauncherPlugin(manifest=manifest, manifest_path=manifest_path, launchers_fn=launchers_fn)


def load_launcher_plugin_records(manifest_paths: Iterable[str]) -> list[LauncherRecord]:
    """Load launcher records from configured launcher plugin manifests."""
    records: list[LauncherRecord] = []
    for raw_path in manifest_paths:
        path = str(raw_path).strip()
        if not path:
            continue
        records.extend(load_launcher_plugin(Path(path).expanduser()).launchers())
    return records


@dataclass(frozen=True)
class ThemePlugin:
    """Loaded theme plugin entrypoint."""

    manifest: PluginManifest
    manifest_path: Path
    themes_fn: Callable[[], Any]

    def themes(self) -> list[ThemeRecord]:
        items = _coerce_theme_items(self.themes_fn())
        return [_coerce_theme_record(item, self.manifest.name) for item in items]


def load_theme_plugin(path: Path | str) -> ThemePlugin:
    """Load one theme plugin from a manifest path."""
    manifest_path = Path(path)
    manifest = load_plugin_manifest(manifest_path)
    if manifest.kind != "theme":
        raise ValueError(f"plugin manifest {manifest_path} is {manifest.kind!r}, not 'theme'")
    entrypoint = _resolve_entrypoint(manifest_path, manifest.entrypoint)
    module = _load_module(entrypoint, manifest.name)
    themes_fn = getattr(module, "themes", None)
    if not callable(themes_fn):
        raise ValueError(f"theme plugin {manifest.name!r} must expose a callable themes() function")
    return ThemePlugin(manifest=manifest, manifest_path=manifest_path, themes_fn=themes_fn)


def load_theme_plugin_records(manifest_paths: Iterable[str]) -> list[ThemeRecord]:
    """Load theme records from configured theme plugin manifests."""
    records: list[ThemeRecord] = []
    for raw_path in manifest_paths:
        path = str(raw_path).strip()
        if not path:
            continue
        records.extend(load_theme_plugin(Path(path).expanduser()).themes())
    return records


@dataclass(frozen=True)
class ExporterPlugin:
    """Loaded recording exporter plugin entrypoint."""

    manifest: PluginManifest
    manifest_path: Path
    export_fn: Callable[..., Any]
    exporters_fn: Callable[[], Any] | None = None

    def exporters(self) -> list[ExporterRecord]:
        if self.exporters_fn is None:
            return [
                {
                    "id": self.manifest.name,
                    "label": self.manifest.name,
                    "description": self.manifest.description,
                    "extension": "",
                }
            ]
        items = _coerce_exporter_items(self.exporters_fn())
        return [_coerce_exporter_record(item, self.manifest.name) for item in items]

    def export(self, recording: dict[str, Any], output: Path | str, *, exporter_id: str = "") -> dict[str, Any]:
        target = Path(output).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = self.export_fn(recording, target, exporter_id=exporter_id)
        except TypeError:
            result = self.export_fn(recording, target)
        return _coerce_export_result(result, target, self.manifest.name)


def load_exporter_plugin(path: Path | str) -> ExporterPlugin:
    """Load one exporter plugin from a manifest path."""
    manifest_path = Path(path)
    manifest = load_plugin_manifest(manifest_path)
    if manifest.kind != "exporter":
        raise ValueError(f"plugin manifest {manifest_path} is {manifest.kind!r}, not 'exporter'")
    entrypoint = _resolve_entrypoint(manifest_path, manifest.entrypoint)
    module = _load_module(entrypoint, manifest.name)
    export_fn = getattr(module, "export", None)
    if not callable(export_fn):
        raise ValueError(f"exporter plugin {manifest.name!r} must expose a callable export(recording, output)")
    exporters_fn = getattr(module, "exporters", None)
    return ExporterPlugin(
        manifest=manifest,
        manifest_path=manifest_path,
        export_fn=export_fn,
        exporters_fn=exporters_fn if callable(exporters_fn) else None,
    )


def load_exporter_plugin_records(manifest_paths: Iterable[str]) -> list[ExporterRecord]:
    """Load exporter records from configured exporter plugin manifests."""
    records: list[ExporterRecord] = []
    for raw_path in manifest_paths:
        path = str(raw_path).strip()
        if not path:
            continue
        records.extend(load_exporter_plugin(Path(path).expanduser()).exporters())
    return records


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


def _coerce_launcher_items(result: Any) -> list[Any]:
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        return result
    if isinstance(result, tuple):
        return list(result)
    raise ValueError(f"launcher plugin returned unsupported result {type(result).__name__}")


def _coerce_launcher_record(item: Any, plugin_name: str) -> LauncherRecord:
    if not isinstance(item, dict):
        raise ValueError(f"launcher plugin {plugin_name!r} returned non-object launcher {type(item).__name__}")
    command = str(item.get("command") or "").strip()
    if not command:
        raise ValueError(f"launcher plugin {plugin_name!r} returned a launcher without command")
    raw_id = str(item.get("id") or item.get("label") or command).strip()
    label = str(item.get("label") or raw_id or command).strip()
    return {
        "id": raw_id,
        "label": label,
        "command": command,
        "description": str(item.get("description") or ""),
        "agent": str(item.get("agent") or ""),
    }


def _coerce_theme_items(result: Any) -> list[Any]:
    if isinstance(result, dict):
        if all(isinstance(value, dict) for value in result.values()):
            return [{"name": name, "palette": palette} for name, palette in result.items()]
        return [result]
    if isinstance(result, list):
        return result
    if isinstance(result, tuple):
        return list(result)
    raise ValueError(f"theme plugin returned unsupported result {type(result).__name__}")


def _coerce_theme_record(item: Any, plugin_name: str) -> ThemeRecord:
    if not isinstance(item, dict):
        raise ValueError(f"theme plugin {plugin_name!r} returned non-object theme {type(item).__name__}")
    name = str(item.get("name") or item.get("id") or "").strip().lower()
    if not name:
        raise ValueError(f"theme plugin {plugin_name!r} returned a theme without name")
    palette = item.get("palette") or item.get("colors")
    if not isinstance(palette, dict):
        palette = {key: value for key, value in item.items() if key not in {"name", "id", "description"}}
    return {
        "name": name,
        "description": str(item.get("description") or ""),
        "palette": {str(key): str(value) for key, value in palette.items()},
    }


def _coerce_exporter_items(result: Any) -> list[Any]:
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        return result
    if isinstance(result, tuple):
        return list(result)
    raise ValueError(f"exporter plugin returned unsupported result {type(result).__name__}")


def _coerce_exporter_record(item: Any, plugin_name: str) -> ExporterRecord:
    if not isinstance(item, dict):
        raise ValueError(f"exporter plugin {plugin_name!r} returned non-object exporter {type(item).__name__}")
    raw_id = str(item.get("id") or item.get("name") or item.get("label") or "").strip()
    if not raw_id:
        raise ValueError(f"exporter plugin {plugin_name!r} returned an exporter without id")
    label = str(item.get("label") or item.get("name") or raw_id).strip()
    return {
        "id": raw_id,
        "label": label,
        "description": str(item.get("description") or ""),
        "extension": str(item.get("extension") or ""),
    }


def _coerce_export_result(result: Any, output: Path, plugin_name: str) -> dict[str, Any]:
    if result is None:
        return {"type": "plugin_export", "plugin": plugin_name, "output": str(output)}
    if isinstance(result, dict):
        payload = dict(result)
        payload.setdefault("type", "plugin_export")
        payload.setdefault("plugin", plugin_name)
        payload.setdefault("output", str(output))
        return payload
    if isinstance(result, (str, Path)):
        return {"type": "plugin_export", "plugin": plugin_name, "output": str(result)}
    raise ValueError(f"exporter plugin {plugin_name!r} returned unsupported result {type(result).__name__}")


def _normalize_label(label: str) -> str:
    return label.strip().lower()
