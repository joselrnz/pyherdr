from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_IGNORE_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "vendor",
    }
)


@dataclass(frozen=True)
class SearchRoot:
    path: str
    label: str = ""
    source: str = "configured"


@dataclass(frozen=True)
class ExplorerRow:
    row_id: str
    kind: str
    label: str
    path: str
    score: int
    source: str
    stale: bool = False
    repo_root: str = ""
    child_count: int = 0
    branch: str = ""
    dirty: bool = False


def search_workspace_rows(
    query: str,
    roots: Iterable[SearchRoot],
    *,
    max_depth: int = 3,
    max_results: int = 80,
    ignore_names: Iterable[str] = DEFAULT_IGNORE_NAMES,
    include_hidden: bool = False,
    cache_path: Path | None = None,
    metadata_ttl_seconds: int = 300,
) -> list[ExplorerRow]:
    """Find likely workspace folders under bounded roots.

    Depth is counted from each root: direct children are depth 1. The scanner
    skips symlinks and ignored directory names so search stays predictable.
    """

    needle = query.strip().lower()
    if not needle:
        return []
    ignored = {name.lower() for name in ignore_names}
    metadata_cache = _load_workspace_cache(cache_path) if cache_path and metadata_ttl_seconds else {}
    now = time.time()
    rows: list[ExplorerRow] = []
    seen: set[str] = set()
    for root in roots:
        root_path = Path(root.path).expanduser().resolve()
        if not root_path.is_dir():
            row = _stale_row(root_path, root, needle)
            if row:
                rows.append(row)
                _update_workspace_cache(metadata_cache, row, root, now, stale=True)
            continue
        rows.extend(
            _scan_root(
                root_path,
                root,
                needle,
                max_depth=max(0, max_depth),
                ignored=ignored,
                include_hidden=include_hidden,
                seen=seen,
                metadata_cache=metadata_cache,
                metadata_ttl_seconds=max(0, metadata_ttl_seconds),
                now=now,
            )
        )
    if cache_path and metadata_ttl_seconds:
        _write_workspace_cache(cache_path, metadata_cache)
    rows.sort(key=lambda row: (-row.score, row.label.lower(), len(row.path), row.path.lower()))
    return rows[:max_results]


def _scan_root(
    root_path: Path,
    root: SearchRoot,
    needle: str,
    *,
    max_depth: int,
    ignored: set[str],
    include_hidden: bool,
    seen: set[str],
    metadata_cache: dict[str, dict[str, Any]],
    metadata_ttl_seconds: int,
    now: float,
) -> list[ExplorerRow]:
    rows: list[ExplorerRow] = []
    stack: list[tuple[Path, int]] = [(root_path, 0)]
    while stack:
        current, depth = stack.pop()
        if _is_ignored(current.name, ignored, include_hidden) and current != root_path:
            continue
        path_key = _path_key(current)
        if path_key in seen:
            continue
        seen.add(path_key)
        row = _candidate_row(
            current,
            root,
            needle,
            metadata_cache=metadata_cache,
            metadata_ttl_seconds=metadata_ttl_seconds,
            now=now,
        )
        if row:
            rows.append(row)
            _update_workspace_cache(metadata_cache, row, root, now, stale=False)
        if depth >= max_depth:
            continue
        children = _child_dirs(current, ignored=ignored, include_hidden=include_hidden)
        stack.extend((child, depth + 1) for child in reversed(children))
    return rows


def _candidate_row(
    path: Path,
    root: SearchRoot,
    needle: str,
    *,
    metadata_cache: dict[str, dict[str, Any]] | None = None,
    metadata_ttl_seconds: int = 300,
    now: float | None = None,
) -> ExplorerRow | None:
    label = path.name or str(path)
    score = _match_score(needle, label, str(path))
    if score is None:
        return None
    repo_root = str(path) if _is_repo_root(path) else ""
    kind = "repo" if repo_root else "folder"
    child_count = _child_count(path)
    branch = ""
    dirty = False
    if repo_root:
        branch, dirty = _repo_metadata(
            path,
            metadata_cache=metadata_cache,
            metadata_ttl_seconds=metadata_ttl_seconds,
            now=time.time() if now is None else now,
        )
    score += _source_boost(root.source) + (80 if kind == "repo" else 0)
    return ExplorerRow(
        row_id=f"{kind}:{path}",
        kind=kind,
        label=label,
        path=str(path),
        score=score,
        source=root.source,
        repo_root=repo_root,
        child_count=child_count,
        branch=branch,
        dirty=dirty,
    )


def _stale_row(path: Path, root: SearchRoot, needle: str) -> ExplorerRow | None:
    label = root.label.strip() or path.name or str(path)
    score = _match_score(needle, label, str(path))
    if score is None:
        return None
    return ExplorerRow(
        row_id=f"stale:{path}",
        kind="stale",
        label=label,
        path=str(path),
        score=score + _source_boost(root.source),
        source=root.source,
        stale=True,
    )


def _child_dirs(path: Path, *, ignored: set[str], include_hidden: bool) -> list[Path]:
    children: list[Path] = []
    try:
        for entry in path.iterdir():
            if _is_ignored(entry.name, ignored, include_hidden) or entry.is_symlink():
                continue
            if entry.is_dir():
                children.append(entry)
    except OSError:
        return []
    return sorted(children, key=lambda child: child.name.lower())


def _child_count(path: Path) -> int:
    try:
        return sum(1 for child in path.iterdir() if child.is_dir() and not child.name.startswith("."))
    except OSError:
        return 0


def _is_repo_root(path: Path) -> bool:
    return (path / ".git").exists()


def default_workspace_search_cache_path() -> Path:
    from .session import session_runtime_dir

    return session_runtime_dir() / "workspace_search_cache.json"


def load_workspace_search_cache(
    cache_path: Path | None = None,
    *,
    include_stale: bool = True,
) -> list[dict[str, Any]]:
    path = cache_path or default_workspace_search_cache_path()
    entries = _load_workspace_cache(path)
    records = [dict(entry) for entry in entries.values() if include_stale or not bool(entry.get("stale"))]
    return sorted(records, key=lambda item: str(item.get("path", "")).lower())


def prune_workspace_search_cache(cache_path: Path | None = None) -> dict[str, Any]:
    path = cache_path or default_workspace_search_cache_path()
    entries = _load_workspace_cache(path)
    kept: dict[str, dict[str, Any]] = {}
    removed_paths: list[str] = []
    for key, entry in entries.items():
        raw_path = str(entry.get("path") or "")
        keep = bool(raw_path) and Path(raw_path).exists() and not bool(entry.get("stale"))
        if keep:
            kept[key] = entry
        else:
            removed_paths.append(raw_path)
    if entries:
        _write_workspace_cache(path, kept)
    return {
        "path": str(path),
        "kept": len(kept),
        "removed": len(removed_paths),
        "removed_paths": removed_paths,
    }


def refresh_workspace_search_cache(
    roots: Iterable[SearchRoot],
    *,
    max_depth: int = 3,
    max_entries: int = 500,
    ignore_names: Iterable[str] = DEFAULT_IGNORE_NAMES,
    include_hidden: bool = False,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    path = cache_path or default_workspace_search_cache_path()
    entries = _load_workspace_cache(path)
    ignored = {name.lower() for name in ignore_names}
    now = time.time()
    indexed = 0
    scanned = 0
    skipped_roots = 0
    seen: set[str] = set()
    entry_limit = max(0, max_entries)
    for root in roots:
        root_path = Path(root.path).expanduser().resolve()
        if not root_path.is_dir():
            skipped_roots += 1
            continue
        stack: list[tuple[Path, int]] = [(root_path, 0)]
        while stack and indexed < entry_limit:
            current, depth = stack.pop()
            if _is_ignored(current.name, ignored, include_hidden) and current != root_path:
                continue
            path_key = _path_key(current)
            if path_key in seen:
                continue
            seen.add(path_key)
            scanned += 1
            if _is_repo_root(current):
                row = _candidate_row(
                    current,
                    root,
                    current.name or str(current),
                    metadata_cache=None,
                    metadata_ttl_seconds=0,
                    now=now,
                )
                if row:
                    _update_workspace_cache(entries, row, root, now, stale=False)
                    indexed += 1
            if depth >= max(0, max_depth):
                continue
            children = _child_dirs(current, ignored=ignored, include_hidden=include_hidden)
            stack.extend((child, depth + 1) for child in reversed(children))
        if indexed >= entry_limit:
            break
    _write_workspace_cache(path, entries)
    return {
        "path": str(path),
        "scanned": scanned,
        "indexed": indexed,
        "cached": len(entries),
        "skipped_roots": skipped_roots,
    }


def _repo_metadata(
    path: Path,
    *,
    metadata_cache: dict[str, dict[str, Any]] | None,
    metadata_ttl_seconds: int,
    now: float,
) -> tuple[str, bool]:
    entry = _cached_workspace_entry(path, metadata_cache, metadata_ttl_seconds=metadata_ttl_seconds, now=now)
    if entry:
        return str(entry.get("branch") or ""), bool(entry.get("dirty"))
    return _git_branch(path), _git_dirty(path)


def _cached_workspace_entry(
    path: Path,
    metadata_cache: dict[str, dict[str, Any]] | None,
    *,
    metadata_ttl_seconds: int,
    now: float,
) -> dict[str, Any] | None:
    if not metadata_cache or metadata_ttl_seconds <= 0:
        return None
    entry = metadata_cache.get(_cache_key(path))
    if not entry:
        return None
    last_seen = _float_or_zero(entry.get("last_seen"))
    if last_seen and now - last_seen <= metadata_ttl_seconds:
        return entry
    return None


def _git_branch(path: Path) -> str:
    result = _run_git(path, "rev-parse", "--abbrev-ref", "HEAD")
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _git_dirty(path: Path) -> bool:
    result = _run_git(path, "status", "--porcelain")
    return result.returncode == 0 and bool(result.stdout.strip())


def _run_git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(["git", *args], returncode=1, stdout="", stderr="")


def _load_workspace_cache(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw_entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(raw_entries, list):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            continue
        resolved = Path(raw_path).expanduser().resolve()
        entries[_cache_key(resolved)] = {
            "path": str(resolved),
            "label": str(item.get("label") or resolved.name or "workspace"),
            "repo_root": str(item.get("repo_root") or ""),
            "branch": str(item.get("branch") or ""),
            "dirty": bool(item.get("dirty")),
            "child_count": _int_or_zero(item.get("child_count")),
            "last_seen": _float_or_zero(item.get("last_seen")),
            "source_root": str(item.get("source_root") or ""),
            "stale": bool(item.get("stale")),
        }
    return entries


def _write_workspace_cache(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    payload = {
        "version": 1,
        "entries": sorted(entries.values(), key=lambda item: str(item.get("path", "")).lower()),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        return


def _update_workspace_cache(
    entries: dict[str, dict[str, Any]],
    row: ExplorerRow,
    root: SearchRoot,
    now: float,
    *,
    stale: bool,
) -> None:
    path = Path(row.path).expanduser().resolve()
    entries[_cache_key(path)] = {
        "path": str(path),
        "label": row.label,
        "repo_root": row.repo_root,
        "branch": row.branch,
        "dirty": row.dirty,
        "child_count": row.child_count,
        "last_seen": now,
        "source_root": str(Path(root.path).expanduser().resolve()),
        "stale": stale,
    }


def _cache_key(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve()))


def _is_ignored(name: str, ignored: set[str], include_hidden: bool) -> bool:
    lowered = name.lower()
    if lowered in ignored:
        return True
    return not include_hidden and name.startswith(".")


def _match_score(needle: str, label: str, path: str) -> int | None:
    label_lower = label.lower()
    path_lower = path.lower()
    if label_lower == needle:
        return 1000
    if label_lower.startswith(needle):
        return 800
    if needle in label_lower:
        return 600
    if _is_subsequence(needle, label_lower):
        return 400
    if needle in path_lower:
        return 300
    return None


def _is_subsequence(needle: str, value: str) -> bool:
    cursor = 0
    for char in value:
        if cursor < len(needle) and char == needle[cursor]:
            cursor += 1
    return cursor == len(needle)


def _source_boost(source: str) -> int:
    boosts: dict[str, int] = {"recent": 50, "current": 40, "workspace": 40, "repo": 30}
    return boosts.get(source, 0)


def _path_key(path: Path) -> str:
    return str(path).casefold()


def _float_or_zero(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def row_to_dict(row: ExplorerRow) -> dict[str, Any]:
    return {
        "id": row.row_id,
        "kind": row.kind,
        "label": row.label,
        "path": row.path,
        "score": row.score,
        "source": row.source,
        "stale": row.stale,
        "repo_root": row.repo_root,
        "child_count": row.child_count,
        "branch": row.branch,
        "dirty": row.dirty,
    }
