"""Per-pane process resource sampling (CPU% + RAM) via ``psutil``.

Each pane owns a PTY whose child-process *tree* (the shell plus whatever it
spawns — an agent CLI, ``node``, ``python``, …) is attributed to that pane.
:class:`ProcSampler` keeps persistent ``psutil.Process`` handles so each
``cpu_percent()`` reading reflects usage since the previous sample, and produces
a task-manager-style snapshot keyed by pane id.

``psutil`` is an optional dependency. When it is missing, :data:`AVAILABLE` is
``False`` and sampling is a no-op, so the UI can explain how to enable it instead
of crashing.
"""

from __future__ import annotations

from typing import Any

# psutil is optional. Bind it to a plain ``Any`` handle (not the import name) so
# the fallback assignment never trips "cannot assign to a module" and no
# per-line ignore is needed regardless of whether psutil ships type stubs.
try:
    import psutil as _psutil

    _PS: Any = _psutil
    AVAILABLE = True
except ImportError:  # pragma: no cover - only hit when psutil is absent
    _PS = None
    AVAILABLE = False


def _short_cmd(proc: Any, limit: int = 60) -> str:
    """A compact command label for one process (cmdline, else name)."""
    text = ""
    try:
        parts = proc.cmdline()
        text = " ".join(part for part in parts if part)
    except Exception:
        text = ""
    if not text:
        try:
            text = proc.name()
        except Exception:
            text = f"pid {getattr(proc, 'pid', '?')}"
    return text if len(text) <= limit else text[: limit - 1] + "…"


class ProcSampler:
    """Samples CPU%/RSS for each pane's process tree, keyed by pane id."""

    def __init__(self) -> None:
        # Persistent handles so cpu_percent() measures the inter-sample delta.
        self._procs: dict[int, Any] = {}
        self._snapshot: dict[str, dict[str, Any]] = {}

    def _handle(self, pid: int) -> Any | None:
        proc = self._procs.get(pid)
        if proc is None:
            try:
                proc = _PS.Process(pid)
                proc.cpu_percent(None)  # prime; the first reading is meaningless
            except Exception:
                return None
            self._procs[pid] = proc
        return proc

    def _empty_stat(self, root_pid: int, message: str, warnings: list[str] | None = None) -> dict[str, Any]:
        return {
            "pid": root_pid,
            "cpu_percent": 0.0,
            "rss_bytes": 0,
            "num_procs": 0,
            "procs": [],
            "error": message,
            "warnings": warnings or [],
        }

    def sample(self, pane_pids: dict[str, int]) -> None:
        """Refresh the cached snapshot for the given ``pane id -> root pid`` map."""
        if not AVAILABLE:
            self._snapshot = {}
            return
        snapshot: dict[str, dict[str, Any]] = {}
        seen: set[int] = set()
        for pane_id, root_pid in pane_pids.items():
            warnings: list[str] = []
            failures = 0
            root = self._handle(root_pid)
            if root is None:
                snapshot[pane_id] = self._empty_stat(root_pid, "process unavailable or permission denied")
                continue
            try:
                tree = [root, *root.children(recursive=True)]
            except Exception as exc:
                tree = [root]
                warnings.append(f"could not inspect child processes: {type(exc).__name__}")
            procs: list[dict[str, Any]] = []
            cpu_total = 0.0
            rss_total = 0
            for member in tree:
                handle = self._handle(member.pid)
                if handle is None:
                    failures += 1
                    continue
                try:
                    cpu = handle.cpu_percent(None)
                    rss = int(handle.memory_info().rss)
                    name = handle.name()
                except Exception:
                    failures += 1
                    continue
                seen.add(member.pid)
                cpu_total += cpu
                rss_total += rss
                procs.append(
                    {
                        "pid": member.pid,
                        "name": name,
                        "cmd": _short_cmd(handle),
                        "cpu_percent": round(cpu, 1),
                        "rss_bytes": rss,
                    }
                )
            procs.sort(key=lambda row: (row["cpu_percent"], row["rss_bytes"]), reverse=True)
            snapshot[pane_id] = {
                "pid": root_pid,
                "cpu_percent": round(cpu_total, 1),
                "rss_bytes": rss_total,
                "num_procs": len(procs),
                "procs": procs,
                "warnings": warnings,
            }
            if failures and not procs:
                snapshot[pane_id]["error"] = "process inspection failed or permission denied"
            elif failures:
                snapshot[pane_id]["warnings"].append(f"{failures} process(es) could not be inspected")
        # Drop handles for processes that have gone away, to bound memory.
        self._procs = {pid: proc for pid, proc in self._procs.items() if pid in seen}
        self._snapshot = snapshot

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return the most recent per-pane resource snapshot."""
        return self._snapshot
