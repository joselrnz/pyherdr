from __future__ import annotations

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


def search_workspace_rows(
    query: str,
    roots: Iterable[SearchRoot],
    *,
    max_depth: int = 3,
    max_results: int = 80,
    ignore_names: Iterable[str] = DEFAULT_IGNORE_NAMES,
    include_hidden: bool = False,
) -> list[ExplorerRow]:
    """Find likely workspace folders under bounded roots.

    Depth is counted from each root: direct children are depth 1. The scanner
    skips symlinks and ignored directory names so search stays predictable.
    """

    needle = query.strip().lower()
    if not needle:
        return []
    ignored = {name.lower() for name in ignore_names}
    rows: list[ExplorerRow] = []
    seen: set[str] = set()
    for root in roots:
        root_path = Path(root.path).expanduser().resolve()
        if not root_path.is_dir():
            row = _stale_row(root_path, root, needle)
            if row:
                rows.append(row)
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
            )
        )
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
        row = _candidate_row(current, root, needle)
        if row:
            rows.append(row)
        if depth >= max_depth:
            continue
        children = _child_dirs(current, ignored=ignored, include_hidden=include_hidden)
        stack.extend((child, depth + 1) for child in reversed(children))
    return rows


def _candidate_row(path: Path, root: SearchRoot, needle: str) -> ExplorerRow | None:
    label = path.name or str(path)
    score = _match_score(needle, label, str(path))
    if score is None:
        return None
    repo_root = str(path) if _is_repo_root(path) else ""
    kind = "repo" if repo_root else "folder"
    score += _source_boost(root.source) + (80 if kind == "repo" else 0)
    return ExplorerRow(
        row_id=f"{kind}:{path}",
        kind=kind,
        label=label,
        path=str(path),
        score=score,
        source=root.source,
        repo_root=repo_root,
        child_count=_child_count(path),
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
    }
