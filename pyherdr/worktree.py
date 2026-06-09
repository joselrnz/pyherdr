"""Git worktree management (ported from herdr's worktree commands).

Worktrees are normal workspaces with Git checkout provenance: `create` adds a
git worktree (default under ``<directory>/<repo>/<branch-slug>``) and opens it
as a workspace; `remove` runs ``git worktree remove`` and never deletes branches.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Worktree:
    """One git worktree entry."""

    path: str
    branch: str
    head: str


def branch_slug(branch: str) -> str:
    """Turn a branch name into a filesystem-safe slug."""
    slug = "".join(ch if (ch.isalnum() or ch in "-_.") else "-" for ch in branch.strip())
    return slug.strip("-") or "worktree"


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd or None, capture_output=True, text=True)


def repo_root(cwd: str) -> str | None:
    """Return the repository top-level directory, or ``None`` outside a repo."""
    result = _git(["rev-parse", "--show-toplevel"], cwd)
    return result.stdout.strip() if result.returncode == 0 else None


def repo_name(cwd: str) -> str:
    """Return the repository directory name (or ``"repo"``)."""
    root = repo_root(cwd)
    return Path(root).name if root else "repo"


def list_worktrees(cwd: str) -> list[Worktree]:
    """List git worktrees via ``git worktree list --porcelain``."""
    result = _git(["worktree", "list", "--porcelain"], cwd)
    if result.returncode != 0:
        return []
    worktrees: list[Worktree] = []
    path = branch = head = ""
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            if path:
                worktrees.append(Worktree(path, branch, head))
            path, branch, head = line[len("worktree ") :], "", ""
        elif line.startswith("HEAD "):
            head = line[len("HEAD ") :]
        elif line.startswith("branch "):
            branch = line[len("branch ") :].replace("refs/heads/", "")
    if path:
        worktrees.append(Worktree(path, branch, head))
    return worktrees


def default_worktree_path(directory: str, cwd: str, branch: str) -> Path:
    """Compute ``<directory>/<repo>/<branch-slug>`` (directory may be empty)."""
    base = Path(directory).expanduser() if directory else Path.home() / ".pyherdr" / "worktrees"
    return base / repo_name(cwd) / branch_slug(branch)


def create_worktree(
    cwd: str,
    branch: str,
    base: str | None = None,
    path: str | None = None,
    directory: str = "",
) -> str:
    """Create a git worktree for ``branch`` and return its absolute path."""
    target = Path(path).expanduser() if path else default_worktree_path(directory, cwd, branch)
    target.parent.mkdir(parents=True, exist_ok=True)

    new_branch = ["worktree", "add", "-b", branch, str(target)]
    if base:
        new_branch.append(base)
    result = _git(new_branch, cwd)
    if result.returncode == 0:
        return str(target)

    # Branch already exists: check it out into a new worktree instead.
    existing = _git(["worktree", "add", str(target), branch], cwd)
    if existing.returncode != 0:
        message = result.stderr.strip() or existing.stderr.strip() or "git worktree add failed"
        raise RuntimeError(message)
    return str(target)


def remove_worktree(cwd: str, path: str, force: bool = False) -> None:
    """Remove a git worktree (never deletes the branch)."""
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(path)
    result = _git(args, cwd)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git worktree remove failed")
