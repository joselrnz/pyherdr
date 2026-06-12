"""Live Textual multiplexer UI, modeled on Herdr.

Two ways to drive it:

* **Mouse** — click a tab to switch, click ``+`` for a new tab, click a pane to
  focus it, and click a shell button in the sidebar (``+ wsl`` / ``+ pwsh`` /
  ``+ bash`` / ``+ cmd``) to open a new terminal running that shell.
* **Keyboard** (like Herdr/tmux) — keys go to the active pane; press the prefix
  ``ctrl+b`` then an action key (``c`` new tab, ``v`` new pane, ``n``/``p``
  next/prev tab, ``1``-``9`` switch tab, ``x`` close pane, ``z`` zoom, ``q``
  quit). ``ctrl+t`` is avoided on purpose — host terminals intercept it.

Layout: a clickable tab bar, a sidebar (workspaces + shell buttons + agents),
the focused tab's panes side-by-side, a hint line, and a status bar. Theme comes
from config (Ocean Blue by default).
"""

from __future__ import annotations

import asyncio
import os
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.containers import Horizontal, HorizontalScroll, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Static

from ..config import AgentPanelScope, load_config
from ..config.theme import BUILTIN_THEMES, DEFAULT_THEME, THEME_NAMES, Palette
from ..layout import Direction, NavDirection, PaneNode, Rect, TileLayout
from ..workflow import WorkflowEvent, build_graph, graph_to_mermaid, read_events
from ..workspace_recents import load_workspace_recents, remove_workspace_recent
from ..workspace_search import (
    DEFAULT_IGNORE_NAMES,
    ExplorerRow,
    SearchRoot,
    default_workspace_search_cache_path,
    search_workspace_rows,
)
from .client import PaneClient, ServerClient

_STATUS_GLYPH = {"blocked": "●", "working": "●", "done": "●", "idle": "○", "unknown": "·"}
_STATUS_PRIORITY = ["blocked", "working", "done", "idle", "unknown"]
# Braille spinner frames for the "working" agent state (herdr src/ui.rs).
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# Quick accent colours offered in the theme picker.
_ACCENT_SWATCHES = ["#89b4fa", "#f5c2e7", "#a6e3a1", "#fab387", "#cba6f7", "#f9e2af", "#94e2d5", "#9399b2"]
_DIR_PICKER_PAGE_STEP = 8
# Prefix action key -> internal action name (defaults; config can remap).
_DEFAULT_PREFIX_ACTIONS = {
    "c": "new_tab",
    "[": "copy_mode",
    "v": "split_sbs",
    "-": "split_stack",
    "n": "next_tab",
    "p": "prev_tab",
    "<": "move_tab_left",
    ">": "move_tab_right",
    "{": "move_workspace_up",
    "}": "move_workspace_down",
    "x": "close_pane",
    "X": "close_tab",
    "T": "rename_tab",
    "P": "rename_pane",
    "N": "new_workspace",
    "W": "worktrees",
    "F": "fanout",
    "b": "toggle_sidebar",
    "w": "next_workspace",
    "g": "goto",
    ":": "palette",
    "m": "pane_menu",
    "s": "settings",
    "z": "zoom",
    "r": "resize",
    "d": "detach",
    "?": "help",
    "q": "quit",
    "tab": "next_pane",
    "h": "focus_left",
    "j": "focus_down",
    "k": "focus_up",
    "l": "focus_right",
    "left": "focus_left",
    "down": "focus_down",
    "up": "focus_up",
    "right": "focus_right",
}
# Clickable buttons shown in the bottom action bar: (label, action). Each posts
# the action through the same dispatch path as the prefix keybinds / menus.
_FOOTER_ACTIONS: tuple[tuple[str, str], ...] = (
    ("? help", "help"),
    ("❯ palette", "palette"),
    ("＋ tab", "new_tab"),
    ("◫ split", "new_pane"),
    ("▾ terminal", "open_shell_picker"),
    ("▤ stats", "resource_monitor"),
    ("◐ theme", "settings"),
    ("↧ detach", "detach"),
    ("✕ quit", "quit"),
)


def _default_shell() -> str:
    """The shell launched in panes. Override with the ``PYHERDR_SHELL`` env var.

    On Windows we prefer WSL (a real Linux shell, so ``ls -ltr`` / ``grep`` work)
    and fall back to ``cmd.exe`` if WSL is not installed.
    """
    override = os.environ.get("PYHERDR_SHELL")
    if override:
        return override
    configured = ""
    mode = "auto"
    try:
        terminal = load_config().terminal
        configured = terminal.default_shell.strip()
        mode = str(terminal.shell_mode)
    except Exception:
        pass
    if configured:
        shell = configured
    elif os.name == "nt":
        shell = shutil.which("wsl.exe") or os.environ.get("COMSPEC", "cmd.exe")
    else:
        shell = os.environ.get("SHELL", "/bin/bash")
    # shell_mode: add a login flag for POSIX login shells (no-op for cmd/pwsh/wsl).
    if mode == "login" and os.path.basename(shell.split()[0] if shell else "").lower() in ("bash", "zsh", "sh", "fish"):
        return f"{shell} -l"
    return shell


def _available_shells() -> list[tuple[str, str]]:
    """``(label, command)`` for the shells installed on this machine."""
    shells: list[tuple[str, str]] = []
    if os.name == "nt":
        # NOTE: Git Bash (MSYS2 bash.exe) is intentionally excluded — it is built
        # for mintty and does not run cleanly under ConPTY (it fails to spawn /
        # produces no output). WSL provides a full bash instead. Override with
        # PYHERDR_SHELL if you really want to point at something else.
        candidates = (
            ("wsl", "wsl.exe"),
            ("pwsh", "pwsh.exe"),
            ("powershell", "powershell.exe"),
        )
        for label, exe in candidates:
            found = shutil.which(exe)
            if found:
                shells.append((label, found))
        shells.append(("cmd", os.environ.get("COMSPEC", "cmd.exe")))
    else:
        shells.append(("bash", os.environ.get("SHELL", "/bin/bash")))
        for label, exe in (("zsh", "zsh"), ("fish", "fish")):
            found = shutil.which(exe)
            if found:
                shells.append((label, found))
    return shells


def _rollup(statuses: list[str]) -> str:
    for status in _STATUS_PRIORITY:
        if status in statuses:
            return status
    return "unknown"


def _git_branch(cwd: str) -> str:
    """Best-effort current git branch for a workspace cwd (empty if none)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_root(cwd: str) -> str:
    """Best-effort git repository root for a cwd (empty if none)."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return os.path.abspath(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else ""


def _git_ahead_behind(cwd: str) -> tuple[int, int]:
    """Return ``(ahead, behind)`` commit counts vs the upstream, or ``(0, 0)``."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "--left-right", "@{u}...HEAD"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return (0, 0)
    if result.returncode != 0:
        return (0, 0)
    parts = result.stdout.split()
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return (int(parts[1]), int(parts[0]))  # right=HEAD (ahead), left=upstream (behind)
    return (0, 0)


def _git_dirty(cwd: str) -> bool:
    """Best-effort dirty worktree marker for picker metadata."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd or None,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


class Activated(Message):
    """Posted when a clickable element (tab, button, pane) is clicked."""

    def __init__(self, action: str, arg: str | None = None) -> None:
        self.action = action
        self.arg = arg
        super().__init__()


class PaneWheel(Message):
    """Posted when a pane receives mouse-wheel input."""

    def __init__(self, pane_id: str, direction: str, x: int, y: int) -> None:
        self.pane_id = pane_id
        self.direction = direction
        self.x = x
        self.y = y
        super().__init__()


class Clickable(Static):
    """A Static that posts an :class:`Activated` message when clicked."""

    def __init__(
        self,
        renderable: Any = "",
        action: str = "",
        arg: str | None = None,
        *,
        dbl_action: str | None = None,
        ctx_action: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(renderable, id=id, classes=classes)
        self._action = action
        self._arg = arg
        self._dbl_action = dbl_action
        self._ctx_action = ctx_action

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if self._ctx_action and getattr(event, "button", 1) == 3:
            self.post_message(Activated(self._ctx_action, self._arg))
        elif self._dbl_action and getattr(event, "chain", 1) >= 2:
            self.post_message(Activated(self._dbl_action, self._arg))
        else:
            self.post_message(Activated(self._action, self._arg))


@dataclass(frozen=True)
class FanoutChoice:
    """One selectable command fan-out target."""

    label: str
    selector: str
    detail: str


@dataclass(frozen=True)
class DirRepoMetadata:
    """Cached repository facts for the workspace picker."""

    repo_root: str
    branch: str
    dirty: bool


@dataclass(frozen=True)
class DirBrowseRow:
    """One keyboard-selectable row in the workspace folder browser."""

    label: str
    action: str
    arg: str | None
    classes: str
    widget_id: str | None = None


SearchCacheKey = tuple[str, tuple[tuple[str, str, str], ...], int, int, bool, tuple[str, ...]]


def _help_text(palette: Palette) -> Text:
    """The grouped keybind cheat-sheet shown in the help overlay."""
    text = Text()
    text.append("press ctrl+b, then a key:\n", style=palette.subtext0)

    def group(title: str) -> None:
        text.append(f"\n{title}\n", style=f"bold {palette.accent}")

    def row(key: str, desc: str) -> None:
        text.append(f"  {key:<12}", style=palette.mauve)
        text.append(f"{desc}\n", style=palette.text)

    group("panes")
    row("v / -", "split right / down")
    row("h/j/k/l", "focus left/down/up/right")
    row("r", "resize mode (then h/l/j/k, esc)")
    row("z", "zoom pane")
    row("m", "pane menu (split/zoom/scroll/close)")
    row("P", "rename pane")
    row("x", "close pane")
    row("[", "copy mode")
    row("pgup/pgdn", "scroll the pane")
    group("tabs")
    row("c", "new tab")
    row("n / p", "next / prev tab")
    row("1-9", "switch to tab N")
    row("< / >", "move tab left / right")
    row("T", "rename tab (or double-click)")
    row("X", "close tab (or click ✕)")
    group("workspaces")
    row("N", "new workspace (folder picker)")
    row("W", "worktrees")
    row("w", "next workspace")
    row("{ / }", "move workspace up / down")
    group("global")
    row(":", "command palette (run anything)")
    row("g", "jump to pane")
    row("s", "theme / settings")
    row("F", "command fan-out")
    row("b", "toggle sidebar")
    row("d", "detach (panes keep running)")
    row("?", "this help")
    row("q", "quit")
    text.append(
        "\nmouse: click tabs/panes · drag to resize · right-click → menus + resource usage\n",
        style=palette.subtext0,
    )
    return text


class HelpScreen(ModalScreen[None]):
    """A dismissable keybind cheat-sheet overlay (ctrl+b ?)."""

    DEFAULT_CSS = """
    HelpScreen { align: center middle; background: $ph-base 70%; }
    #help-box {
        width: 60;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        color: $ph-text;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 2;
    }
    #help-foot { color: $ph-subtext0; padding: 1 2 0 2; }
    """

    def __init__(self, palette: Palette) -> None:
        super().__init__()
        self._palette = palette

    def compose(self) -> ComposeResult:
        box = Static(_help_text(self._palette), id="help-box")
        box.border_title = "keybinds"
        yield box
        yield Static("esc / enter / ? to close", id="help-foot")

    def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "enter", "question_mark", "q"):
            self.dismiss()
        event.stop()

    def on_click(self, event: events.Click) -> None:
        self.dismiss()
        event.stop()


def _dir_picker_help_text() -> Text:
    text = Text()
    text.append("common\n", style="bold")
    text.append("  ↑/↓          move selection\n")
    text.append("  Enter        open highlighted folder\n")
    text.append("  Alt+O        open current folder\n")
    text.append("  Esc          cancel\n")
    text.append("\nshortcuts\n", style="bold")
    text.append("  Backspace    go up one folder\n")
    text.append("  Ctrl+H       jump home\n")
    text.append("  Ctrl+W       jump current workspace\n")
    text.append("  Ctrl+R       jump repo root\n")
    text.append("  Ctrl+F       search mode\n")
    text.append("  Ctrl+L       path mode\n")
    text.append("  y            copy highlighted path\n")
    text.append("  Ctrl+Shift+C copy highlighted path\n")
    text.append("  Ctrl+Shift+V paste into input\n")
    text.append("\ncommands\n", style="bold")
    text.append("  ls           refresh current folder\n")
    text.append("  ls text      filter current folder\n")
    text.append("  cd path      change folder\n")
    text.append("  pwd          show current path\n")
    text.append("  open path    open folder\n")
    text.append("  copy path    copy folder path\n")
    text.append("\nsearch mode\n", style="bold")
    text.append("  PageUp/Down  page results\n")
    text.append("  Space        select result\n")
    text.append("  p            open parent\n")
    text.append("  y            copy path\n")
    text.append("  Delete       hide stale recent\n")
    text.append("  Right-click  result actions\n")
    return text


class DirPickerHelpScreen(ModalScreen[None]):
    """Focused help for the workspace folder picker."""

    DEFAULT_CSS = """
    DirPickerHelpScreen { align: center middle; background: $ph-base 70%; }
    #dir-help-box {
        width: 46;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        color: $ph-text;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 2;
    }
    #dir-help-foot { color: $ph-subtext0; padding: 1 2 0 2; }
    """

    def compose(self) -> ComposeResult:
        box = Static(_dir_picker_help_text(), id="dir-help-box")
        box.border_title = "folder picker help"
        yield box
        yield Static("esc / enter / ? to close", id="dir-help-foot")

    def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "enter", "question_mark", "q"):
            self.dismiss()
        event.stop()

    def on_click(self, event: events.Click) -> None:
        self.dismiss()
        event.stop()


def _fmt_mb(num_bytes: int) -> str:
    """Render a byte count as megabytes (task-manager style)."""
    return f"{num_bytes / 1048576:.1f} MB"


class StatsScreen(ModalScreen[None]):
    """A live CPU/RAM monitor for one pane, a workspace, or every session.

    Refreshes from the server's cached snapshot (~1.5s), so it behaves like a
    small task-manager: per-process CPU% + RSS, biggest first, with a total.
    """

    DEFAULT_CSS = """
    StatsScreen { align: center middle; background: $ph-base 70%; }
    #stats-box {
        width: 92;
        max-width: 96%;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        color: $ph-text;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 2;
    }
    #stats-scroll { height: auto; max-height: 80%; }
    #stats-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(
        self,
        title: str,
        client: PaneClient,
        palette: Palette,
        labels: dict[str, str],
        pane_ids: list[str] | None,
    ) -> None:
        super().__init__()
        self._title = title
        self._client = client
        self._palette = palette
        self._labels = labels
        self._pane_ids = pane_ids  # None = every session

    def compose(self) -> ComposeResult:
        with Vertical(id="stats-box"):
            yield VerticalScroll(Static("", id="stats-body"), id="stats-scroll")
            yield Static("esc to close · sorted by CPU · updates live", id="stats-foot")

    def on_mount(self) -> None:
        self.query_one("#stats-box", Vertical).border_title = self._title
        self._refresh()
        self.set_interval(1.5, self._refresh)

    def _refresh(self) -> None:
        try:
            payload = self._client.stats()
        except Exception:
            payload = {"available": False, "stats": {}}
        self.query_one("#stats-body", Static).update(self._render_stats(payload))

    def _render_stats(self, payload: dict[str, Any]) -> Text:
        palette = self._palette
        text = Text()
        if not payload.get("available", False):
            text.append("psutil is not installed.\n\n", style=f"bold {palette.red}")
            text.append("Install it to see CPU/RAM per session:\n", style=palette.text)
            text.append("    pip install psutil\n", style=palette.subtext0)
            return text
        stats = payload.get("stats", {}) or {}
        ids = self._pane_ids if self._pane_ids is not None else list(stats.keys())
        entries = [(pid, stats[pid]) for pid in ids if pid in stats]
        if not entries:
            text.append("No running processes to report yet.\n", style=palette.subtext0)
            text.append("(panes may still be starting — this refreshes live)\n", style=palette.overlay0)
            return text
        entries.sort(key=lambda kv: kv[1].get("cpu_percent", 0.0), reverse=True)
        total_cpu = sum(s.get("cpu_percent", 0.0) for _, s in entries)
        total_rss = sum(int(s.get("rss_bytes", 0)) for _, s in entries)
        total_procs = sum(int(s.get("num_procs", 0)) for _, s in entries)
        text.append("TOTAL  ", style=f"bold {palette.accent}")
        text.append(f"CPU {total_cpu:.1f}%", style=palette.green)
        text.append(f"   RAM {_fmt_mb(total_rss)}", style=palette.blue)
        text.append(f"   {len(entries)} session(s) · {total_procs} processes\n", style=palette.subtext0)
        for pane_id, stat in entries:
            label = self._labels.get(pane_id, pane_id)
            text.append("\n● ", style=palette.accent)
            text.append(str(label), style=f"bold {palette.text}")
            text.append(f"   CPU {stat.get('cpu_percent', 0.0):.1f}%", style=palette.green)
            text.append(f"   RAM {_fmt_mb(int(stat.get('rss_bytes', 0)))}", style=palette.blue)
            text.append(f"   (pid {stat.get('pid', '?')})\n", style=palette.overlay0)
            procs = stat.get("procs", []) or []
            for proc in procs[:8]:
                text.append(f"    {float(proc.get('cpu_percent', 0.0)):>5.1f}%  ", style=palette.green)
                text.append(f"{_fmt_mb(int(proc.get('rss_bytes', 0))):>10}  ", style=palette.blue)
                text.append(f"{proc.get('cmd') or proc.get('name', '?')}\n", style=palette.subtext0)
            if len(procs) > 8:
                text.append(f"    … {len(procs) - 8} more\n", style=palette.overlay0)
        text.append("\nCPU% can exceed 100% across cores (top-style).", style=palette.overlay0)
        return text

    def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "enter", "q"):
            self.dismiss()
        event.stop()


class WorkflowScreen(ModalScreen[None]):
    """Recent workflow events plus a compact call-flow graph."""

    DEFAULT_CSS = """
    WorkflowScreen { align: center middle; background: $ph-base 70%; }
    #workflow-box {
        width: 104;
        max-width: 96%;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        color: $ph-text;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 2;
    }
    #workflow-scroll { height: auto; max-height: 80%; }
    #workflow-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(self, events: list[WorkflowEvent], palette: Palette) -> None:
        super().__init__()
        self._events = events
        self._palette = palette

    def compose(self) -> ComposeResult:
        with Vertical(id="workflow-box"):
            yield VerticalScroll(
                Static(self._render_body(), id="workflow-body"),
                id="workflow-scroll",
            )
            yield Static("esc to close · terminal call graph + event log + Mermaid source", id="workflow-foot")

    def on_mount(self) -> None:
        self.query_one("#workflow-box", Vertical).border_title = "workflow graph + log"

    def _render_body(self) -> Text:
        palette = self._palette
        text = Text()
        events = self._events[-40:]
        if not events:
            text.append("terminal call graph\n", style=f"bold {palette.accent}")
            text.append("(no events yet)\n", style=palette.subtext0)
            text.append("\nrecent events\n", style=f"bold {palette.accent}")
            text.append("No workflow events recorded yet.\n", style=palette.subtext0)
            text.append(
                "Events appear here as the server, CLI, and agents emit workflow audit entries.\n",
                style=palette.overlay0,
            )
            text.append("\nMermaid source\n", style=f"bold {palette.accent}")
            text.append("flowchart TD\n", style=palette.subtext0)
            return text

        text.append("terminal call graph\n", style=f"bold {palette.accent}")
        self._append_visual_graph(text, events)

        text.append("\nrecent events\n", style=f"bold {palette.accent}")
        for event in reversed(events[-12:]):
            stamp = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
            status = event.status or event.kind
            status_color = self._status_color(status)
            text.append(f"{stamp}  ", style=palette.overlay0)
            text.append(f"{event.kind:<14}", style=palette.blue)
            text.append(f"{status:<10}", style=status_color)
            text.append(event.message or "(no message)", style=palette.text)
            context = self._event_context(event)
            if context:
                text.append(f"\n    {context}", style=palette.overlay0)
            text.append("\n")

        graph = build_graph(events)
        mermaid = graph_to_mermaid(graph)
        graph_lines = mermaid.splitlines()
        text.append("\nMermaid source\n", style=f"bold {palette.accent}")
        for line in graph_lines[:80]:
            text.append(line + "\n", style=palette.subtext0)
        if len(graph_lines) > 80:
            text.append(
                "... graph truncated in view; export full graph with pyherdr workflow graph\n",
                style=palette.overlay0,
            )
        return text

    def _append_visual_graph(self, text: Text, events: list[WorkflowEvent]) -> None:
        recent = events[-12:]
        if len(events) > len(recent):
            text.append(
                f"showing recent {len(recent)} of {len(events)} events; export SVG for the full graph\n",
                style=self._palette.overlay0,
            )
        grouped: dict[str, list[WorkflowEvent]] = {}
        for event in recent:
            grouped.setdefault(event.worksite or "unassigned", []).append(event)

        for worksite, group in grouped.items():
            text.append(f"{worksite}\n", style=f"bold {self._palette.blue}")
            for event in group:
                for line in self._call_graph_event_rows(event):
                    text.append("  " + line + "\n", style=self._palette.subtext0)
                context = self._event_context(event)
                if context:
                    text.append(f"      {context}\n", style=self._palette.overlay0)
                text.append("\n")

    @classmethod
    def _call_graph_event_rows(cls, event: WorkflowEvent) -> list[str]:
        source = event.source or event.agent or event.pane_id or "event"
        target = event.target or "result"
        status = event.status or event.kind
        boxes = [
            cls._node_box("source", source, 16),
            cls._node_box(event.kind, event.message or "event", 24),
            cls._node_box("target", target, 16),
            cls._node_box("status", status, 14),
        ]
        rows: list[str] = []
        connector = "  ──→  "
        spacer = " " * len(connector)
        for index in range(len(boxes[0])):
            joiner = connector if index == 2 else spacer
            rows.append(joiner.join(box[index] for box in boxes))
        if cls._is_response_event(event):
            rows.append(cls._cycle_back_row(boxes, len(connector)))
        return rows

    @classmethod
    def _node_box(cls, title: str, value: str, width: int) -> list[str]:
        content_width = width - 2
        return [
            "┌" + "─" * content_width + "┐",
            "│" + cls._fit_node_text(title, content_width) + "│",
            "│" + cls._fit_node_text(value, content_width) + "│",
            "└" + "─" * content_width + "┘",
        ]

    @staticmethod
    def _fit_node_text(value: str, width: int) -> str:
        normalized = " ".join(str(value).split()) or "(empty)"
        if len(normalized) > width:
            normalized = normalized[: max(0, width - 1)].rstrip() + "…"
        return normalized.ljust(width)

    @classmethod
    def _cycle_back_row(cls, boxes: list[list[str]], connector_width: int) -> str:
        source_mid = len(boxes[0][0]) // 2
        target_mid = (
            len(boxes[0][0])
            + connector_width
            + len(boxes[1][0])
            + connector_width
            + len(boxes[2][0]) // 2
        )
        inner_width = max(0, target_mid - source_mid - 1)
        label = " response/cycle back ← "
        if inner_width <= len(label):
            inner = label
        else:
            left = (inner_width - len(label)) // 2
            right = inner_width - len(label) - left
            inner = "─" * left + label + "─" * right
        return " " * source_mid + "╰" + inner + "╯"

    @staticmethod
    def _is_response_event(event: WorkflowEvent) -> bool:
        detail_keys = " ".join(str(key) for key in event.details)
        marker_text = f"{event.kind} {event.status} {event.message} {detail_keys}".lower()
        return any(
            marker in marker_text
            for marker in ("response", "reply", "return", "result", "ack", "callback")
        )

    def _status_color(self, status: str) -> str:
        lowered = status.lower()
        if lowered in ("blocked", "error", "failed", "unauthorized"):
            return self._palette.red
        if lowered in ("working", "request", "pending"):
            return self._palette.yellow
        if lowered in ("done", "ok", "success", "response"):
            return self._palette.green
        return self._palette.subtext0

    @staticmethod
    def _event_context(event: WorkflowEvent) -> str:
        parts = []
        if event.worksite:
            parts.append(f"worksite={event.worksite}")
        if event.agent:
            parts.append(f"agent={event.agent}")
        if event.pane_id:
            parts.append(f"pane={event.pane_id}")
        if event.source or event.target:
            parts.append(f"{event.source or '?'} -> {event.target or '?'}")
        if event.artifacts:
            parts.append("artifacts=" + ", ".join(event.artifacts[:3]))
        return " · ".join(parts)

    def on_key(self, event: events.Key) -> None:
        if event.key in ("escape", "enter", "q"):
            self.dismiss()
        event.stop()

    def on_click(self, event: events.Click) -> None:
        event.stop()


class ThemeScreen(ModalScreen[None]):
    """A theme picker with swatch previews + accent colours; previews live."""

    DEFAULT_CSS = """
    ThemeScreen { align: center middle; background: $ph-base 70%; }
    #theme-box {
        width: 46;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 1;
    }
    .theme-hdr { width: 1fr; color: $ph-subtext0; padding: 1 0 0 0; }
    #theme-list { height: auto; max-height: 13; }
    .theme-row { width: 1fr; padding: 0 1; }
    .theme-row:hover { background: $ph-surface0; }
    #accent-row { height: 1; }
    .accent-sw { width: auto; padding: 0 1; }
    .accent-sw:hover { background: $ph-surface0; }
    #theme-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(self, names: list[str], current: str) -> None:
        super().__init__()
        self._names = names
        self._current = (current or "").strip().lower()

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-box"):
            yield Static("theme", classes="theme-hdr")
            yield VerticalScroll(id="theme-list")
            yield Static("accent", classes="theme-hdr")
            with Horizontal(id="accent-row"):
                for hex_color in _ACCENT_SWATCHES:
                    swatch = Text("●", style=hex_color)
                    swatch_id = f"accent-{hex_color.lstrip('#')}"
                    yield Clickable(swatch, "pick_accent", hex_color, id=swatch_id, classes="accent-sw")
            yield Static("click to preview · esc to close", id="theme-foot")

    async def on_mount(self) -> None:
        self.query_one("#theme-box", Vertical).border_title = "theme"
        await self._rebuild_rows()

    async def _rebuild_rows(self) -> None:
        listing = self.query_one("#theme-list", VerticalScroll)
        await listing.remove_children()
        rows = [
            Clickable(self._row_text(name), "pick_theme", name, id=f"theme-{name}", classes="theme-row")
            for name in self._names
        ]
        await listing.mount(*rows)

    def _row_text(self, name: str) -> Text:
        text = Text()
        text.append("✓ " if name == self._current else "  ", style="#a6e3a1")
        palette = BUILTIN_THEMES.get(name)
        if palette is not None:
            for token in (palette.accent, palette.green, palette.yellow, palette.red, palette.blue):
                if token.startswith("#"):
                    text.append("●", style=token)
            text.append(" ")
        text.append(name)
        return text

    def on_activated(self, message: Activated) -> None:
        message.stop()
        if message.action == "pick_theme" and message.arg:
            apply = getattr(self.app, "apply_theme", None)
            if callable(apply):
                apply(message.arg)
            self._current = message.arg.strip().lower()
            self.run_worker(self._rebuild_rows())
        elif message.action == "pick_accent" and message.arg:
            apply = getattr(self.app, "apply_accent", None)
            if callable(apply):
                apply(message.arg)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss()
        event.stop()


class RenameScreen(ModalScreen[None]):
    """A modal text-input dialog (rename a tab/pane/workspace)."""

    DEFAULT_CSS = """
    RenameScreen { align: center middle; background: $ph-base 70%; }
    #rename-box {
        width: 56;
        height: auto;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 2;
    }
    #rename-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(self, title: str, current: str, submit: Callable[[str], None]) -> None:
        super().__init__()
        self._title = title
        self._current = current
        self._submit = submit

    def compose(self) -> ComposeResult:
        box = Vertical(
            Input(value=self._current, id="rename-input"),
            Static("enter save · esc cancel", id="rename-foot"),
            id="rename-box",
        )
        box.border_title = self._title
        yield box

    def on_mount(self) -> None:
        self.query_one("#rename-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        value = event.value.strip()
        if value:
            self._submit(value)
        self.dismiss()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()


class NavigatorScreen(ModalScreen[None]):
    """Jump-to-any-pane list (ctrl+b g). Click a row to switch to that pane."""

    DEFAULT_CSS = """
    NavigatorScreen { align: center middle; background: $ph-base 70%; }
    #nav-box {
        width: 60;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 1;
    }
    #nav-list { height: auto; max-height: 18; }
    .nav-row { width: 1fr; color: $ph-text; padding: 0 1; }
    .nav-row:hover { background: $ph-surface0; }
    #nav-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(self, rows: list[tuple[str, Text, str]]) -> None:
        super().__init__()
        self._rows = rows

    def compose(self) -> ComposeResult:
        with Vertical(id="nav-box"):
            yield Input(placeholder="filter panes", id="nav-search")
            yield VerticalScroll(id="nav-list")
            yield Static("type to filter · enter/click jump · esc close", id="nav-foot")

    async def on_mount(self) -> None:
        self.query_one("#nav-box", Vertical).border_title = "navigator"
        self.query_one("#nav-search", Input).focus()
        await self._populate("")

    async def _populate(self, query: str) -> None:
        listing = self.query_one("#nav-list", VerticalScroll)
        await listing.remove_children()
        needle = query.strip().lower()
        items = [
            Clickable(text, "nav_jump", arg, id=f"nav-{index}", classes="nav-row")
            for index, (arg, text, plain) in enumerate(self._rows)
            if needle in plain.lower()
        ]
        if items:
            await listing.mount(*items)

    async def on_input_changed(self, event: Input.Changed) -> None:
        await self._populate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        needle = event.value.strip().lower()
        for arg, _text, plain in self._rows:
            if needle in plain.lower():
                self._jump(arg)
                return

    def on_activated(self, message: Activated) -> None:
        message.stop()
        if message.action == "nav_jump" and message.arg:
            self._jump(message.arg)

    def _jump(self, arg: str) -> None:
        jump = getattr(self.app, "jump_to", None)
        if callable(jump):
            jump(arg)
        self.dismiss()

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()


class CopyModeScreen(ModalScreen[None]):
    """Read-only scrollback view with line selection and clipboard copy."""

    DEFAULT_CSS = """
    CopyModeScreen { align: center middle; background: $ph-base 70%; }
    #copy-box {
        width: 96;
        height: auto;
        max-width: 96%;
        max-height: 90%;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 1;
    }
    #copy-scroll { height: auto; max-height: 22; }
    #copy-body { color: $ph-text; }
    #copy-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(self, pane_label: str, lines: list[str], palette: Palette) -> None:
        super().__init__()
        self._pane_label = pane_label
        self._lines = lines or [""]
        self._palette = palette
        self._cursor = max(0, len(self._lines) - 1)
        self._anchor: int | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="copy-box"):
            with VerticalScroll(id="copy-scroll"):
                yield Static(self._render_body(), id="copy-body")
            yield Static("j/k move · space select · y/enter copy · q/esc close", id="copy-foot")

    def on_mount(self) -> None:
        self.query_one("#copy-box", Vertical).border_title = f"copy mode · {self._pane_label}"
        self.focus()
        self.call_after_refresh(self._scroll_cursor_visible)

    def on_key(self, event: events.Key) -> None:
        event.stop()
        character = getattr(event, "character", None)
        if event.key in ("escape", "q"):
            self.dismiss()
        elif event.key in ("down", "j"):
            self._move(1)
        elif event.key in ("up", "k"):
            self._move(-1)
        elif event.key == "pagedown":
            self._move(10)
        elif event.key == "pageup":
            self._move(-10)
        elif event.key == "g" or character == "g":
            self._jump(0)
        elif event.key in ("G", "upper_g") or character == "G":
            self._jump(len(self._lines) - 1)
        elif event.key in ("space", "v"):
            self._toggle_selection()
        elif event.key in ("enter", "y"):
            self._copy_selection()

    def _move(self, delta: int) -> None:
        self._jump(self._cursor + delta)

    def _jump(self, index: int) -> None:
        self._cursor = max(0, min(len(self._lines) - 1, index))
        self._refresh_body()
        self.call_after_refresh(self._scroll_cursor_visible)

    def _toggle_selection(self) -> None:
        self._anchor = self._cursor if self._anchor is None else None
        self._refresh_body()

    def _selected_range(self) -> tuple[int, int]:
        if self._anchor is None:
            return (self._cursor, self._cursor)
        return (min(self._anchor, self._cursor), max(self._anchor, self._cursor))

    def _selection_text(self) -> str:
        start, end = self._selected_range()
        return "\n".join(self._lines[start : end + 1]).rstrip("\n")

    def _copy_selection(self) -> None:
        text = self._selection_text()
        if text:
            self.app.copy_to_clipboard(text)
            self.app.notify("copied selection to clipboard", timeout=3)
        self.dismiss()

    def _refresh_body(self) -> None:
        self.query_one("#copy-body", Static).update(self._render_body())

    def _scroll_cursor_visible(self) -> None:
        try:
            self.query_one("#copy-scroll", VerticalScroll).scroll_to(y=self._cursor, animate=False)
        except Exception:
            pass

    def _render_body(self) -> Text:
        selected_start, selected_end = self._selected_range()
        body = Text()
        for index, line in enumerate(self._lines):
            selected = selected_start <= index <= selected_end and self._anchor is not None
            cursor = index == self._cursor
            if cursor:
                prefix = "> "
                style = f"bold {self._palette.text}"
            else:
                prefix = "  "
                style = self._palette.text
            if selected:
                style = f"bold {self._palette.panel_bg} on {self._palette.accent}"
            body.append(prefix, style=self._palette.accent if cursor else self._palette.overlay0)
            body.append(line or " ", style=style)
            if index < len(self._lines) - 1:
                body.append("\n")
        return body


class WorktreeScreen(ModalScreen[None]):
    """Manage git worktrees without leaving the TUI."""

    DEFAULT_CSS = """
    WorktreeScreen { align: center middle; background: $ph-base 70%; }
    #wt-box {
        width: 82;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 1;
    }
    #wt-create-row { height: 3; }
    #wt-branch { width: 1fr; }
    #wt-create {
        width: 16;
        height: 3;
        background: $ph-surface0;
        color: $ph-green;
        content-align: center middle;
        text-style: bold;
        margin: 0 0 0 1;
    }
    #wt-create:hover { background: $ph-green; color: $ph-base; }
    #wt-list { height: auto; max-height: 15; border: round $ph-surface0; background: $ph-base; }
    .wt-row { width: 1fr; color: $ph-text; padding: 0 1; }
    .wt-row:hover { background: $ph-surface0; }
    .wt-remove { width: 1fr; color: $ph-red; padding: 0 1; }
    .wt-remove:hover { background: $ph-red; color: $ph-base; }
    #wt-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(self, client: PaneClient, on_changed: Callable[[bool], None] | None = None) -> None:
        super().__init__()
        self._client = client
        self._on_changed = on_changed
        self._worktrees: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="wt-box"):
            with Horizontal(id="wt-create-row"):
                yield Input(placeholder="new worktree branch, e.g. feature/sidebar", id="wt-branch")
                yield Clickable("+ worktree", "wt_create", id="wt-create")
            yield VerticalScroll(id="wt-list")
            yield Static("click a row to open · remove only removes the worktree checkout · esc close", id="wt-foot")

    async def on_mount(self) -> None:
        self.query_one("#wt-box", Vertical).border_title = "worktrees"
        self.query_one("#wt-branch", Input).focus()
        await self._refresh()

    async def _refresh(self) -> None:
        listing = self.query_one("#wt-list", VerticalScroll)
        await listing.remove_children()
        try:
            self._worktrees = self._client.worktree_list()
        except Exception as exc:
            self._worktrees = []
            await listing.mount(Static(f"could not list worktrees: {exc}", classes="wt-row"))
            return
        if not self._worktrees:
            await listing.mount(Static("no git worktrees found for the current workspace", classes="wt-row"))
            return
        rows: list[Widget] = []
        for index, item in enumerate(self._worktrees):
            rows.append(
                Clickable(
                    self._worktree_text(item),
                    "wt_open",
                    str(index),
                    id=f"wt-open-{index}",
                    classes="wt-row",
                )
            )
            rows.append(
                Clickable(
                    f"  remove checkout  {item.get('path', '')}",
                    "wt_remove",
                    str(index),
                    id=f"wt-remove-{index}",
                    classes="wt-remove",
                )
            )
        await listing.mount(*rows)

    @staticmethod
    def _worktree_text(item: dict[str, Any]) -> Text:
        text = Text()
        branch = str(item.get("branch") or "detached")
        path = str(item.get("path") or "")
        head = str(item.get("head") or "")[:8]
        text.append("open  ", style="#89b4fa")
        text.append(branch, style="bold")
        if head:
            text.append(f"  {head}", style="#6c7086")
        text.append(f"\n      {path}", style="#a6adc8")
        return text

    def on_activated(self, message: Activated) -> None:
        message.stop()
        if message.action == "wt_create":
            self._create()
        elif message.action in ("wt_open", "wt_remove") and message.arg is not None:
            index = int(message.arg)
            if 0 <= index < len(self._worktrees):
                if message.action == "wt_open":
                    self._open(self._worktrees[index])
                else:
                    self._remove(self._worktrees[index])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._create()

    def _create(self) -> None:
        branch = self.query_one("#wt-branch", Input).value.strip()
        if not branch:
            self.query_one("#wt-foot", Static).update("enter a branch name first")
            return
        try:
            self._client.worktree_create(branch, label=branch)
        except Exception as exc:
            self.query_one("#wt-foot", Static).update(f"create failed: {exc}")
            return
        self._changed_and_close()

    def _open(self, item: dict[str, Any]) -> None:
        path = str(item.get("path") or "")
        if not path:
            return
        branch = str(item.get("branch") or Path(path).name)
        try:
            self._client.worktree_open(path, label=branch)
        except Exception as exc:
            self.query_one("#wt-foot", Static).update(f"open failed: {exc}")
            return
        self._changed_and_close()

    def _remove(self, item: dict[str, Any]) -> None:
        path = str(item.get("path") or "")
        if not path:
            return
        try:
            self._client.worktree_remove(path, force=False)
        except Exception as exc:
            self.query_one("#wt-foot", Static).update(f"remove failed: {exc}")
            return
        self._changed_and_close()

    def _changed_and_close(self) -> None:
        self.dismiss()
        if self._on_changed is not None:
            self.app.call_after_refresh(self._on_changed, True)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()


class CommandPaletteScreen(ModalScreen[None]):
    """Fuzzy launcher for every action + custom command (ctrl+b p)."""

    DEFAULT_CSS = """
    CommandPaletteScreen { align: center middle; background: $ph-base 70%; }
    #cmd-box {
        width: 58;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 1;
    }
    #cmd-list { height: auto; max-height: 16; }
    .cmd-row { width: 1fr; color: $ph-text; padding: 0 1; }
    .cmd-row:hover { background: $ph-accent; color: $ph-base; text-style: bold; }
    #cmd-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(self, entries: list[tuple[str, str, bool]]) -> None:
        super().__init__()
        self._entries = entries

    def compose(self) -> ComposeResult:
        with Vertical(id="cmd-box"):
            yield Input(placeholder="type a command…", id="cmd-search")
            yield VerticalScroll(id="cmd-list")
            yield Static("type to filter · enter/click run · esc close", id="cmd-foot")

    async def on_mount(self) -> None:
        self.query_one("#cmd-box", Vertical).border_title = "command palette"
        self.query_one("#cmd-search", Input).focus()
        await self._populate("")

    async def _populate(self, query: str) -> None:
        listing = self.query_one("#cmd-list", VerticalScroll)
        await listing.remove_children()
        needle = query.strip().lower()
        rows = [
            Clickable(label, "palette_pick", str(index), id=f"cmd-{index}", classes="cmd-row")
            for index, (label, _value, _is_command) in enumerate(self._entries)
            if needle in label.lower()
        ]
        if rows:
            await listing.mount(*rows)

    async def on_input_changed(self, event: Input.Changed) -> None:
        await self._populate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        needle = event.value.strip().lower()
        for index, (label, _value, _is_command) in enumerate(self._entries):
            if needle in label.lower():
                self._run(index)
                return

    def on_activated(self, message: Activated) -> None:
        message.stop()
        if message.action == "palette_pick" and message.arg is not None:
            self._run(int(message.arg))

    def _run(self, index: int) -> None:
        if not 0 <= index < len(self._entries):
            self.dismiss()
            return
        _label, value, is_command = self._entries[index]
        runner = getattr(self.app, "run_palette_entry", None)
        self.dismiss()
        if callable(runner):
            self.app.call_after_refresh(runner, value, is_command)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()


class FanoutScreen(ModalScreen[None]):
    """Preview and execute command fan-out to a selected pane group."""

    DEFAULT_CSS = """
    FanoutScreen { align: center middle; background: $ph-base 70%; }
    #fanout-box {
        width: 76;
        height: auto;
        max-height: 90%;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 1;
    }
    #fanout-targets { height: auto; max-height: 9; }
    .fanout-row { width: 1fr; color: $ph-text; padding: 0 1; }
    .fanout-row:hover { background: $ph-surface0; }
    #fanout-preview {
        width: 1fr;
        min-height: 5;
        max-height: 9;
        color: $ph-subtext0;
        border: round $ph-overlay0;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    #fanout-send { width: 1fr; color: $ph-green; text-style: bold; padding: 0 1; margin: 1 0 0 0; }
    #fanout-send:hover { background: $ph-accent; color: $ph-base; }
    #fanout-foot { color: $ph-subtext0; padding: 1 0 0 0; }
    """

    def __init__(
        self,
        choices: list[FanoutChoice],
        submit: Callable[[str, str, bool], dict[str, Any]],
    ) -> None:
        super().__init__()
        self._choices = choices
        self._submit = submit
        self._selected = 0
        self._last_preview_key: tuple[str, str] | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="fanout-box"):
            yield Input(placeholder="command to preview, then send", id="fanout-command")
            yield VerticalScroll(id="fanout-targets")
            yield Static(self._empty_preview(), id="fanout-preview")
            yield Clickable("send after preview", "fanout_execute", id="fanout-send")
            yield Static("select target · enter preview · send executes · esc cancel", id="fanout-foot")

    async def on_mount(self) -> None:
        self.query_one("#fanout-box", Vertical).border_title = "command fan-out"
        self.query_one("#fanout-command", Input).focus()
        await self._rebuild_targets()

    async def _rebuild_targets(self) -> None:
        listing = self.query_one("#fanout-targets", VerticalScroll)
        await listing.remove_children()
        rows = [
            Clickable(
                self._target_text(index, choice),
                "fanout_target",
                str(index),
                id=f"fanout-target-{index}",
                classes="fanout-row",
            )
            for index, choice in enumerate(self._choices)
        ]
        if rows:
            await listing.mount(*rows)

    def _target_text(self, index: int, choice: FanoutChoice) -> Text:
        text = Text()
        text.append("✓ " if index == self._selected else "  ", style="#a6e3a1")
        text.append(choice.label, style="bold" if index == self._selected else "")
        text.append(f"  {choice.detail}", style="#6c7086")
        return text

    @staticmethod
    def _empty_preview() -> Text:
        text = Text()
        text.append("type a command and press enter to preview targets")
        return text

    def on_activated(self, message: Activated) -> None:
        message.stop()
        if message.action == "fanout_target" and message.arg is not None:
            index = int(message.arg)
            if 0 <= index < len(self._choices):
                self._selected = index
                self._last_preview_key = None
                self.run_worker(self._rebuild_targets())
                self._preview_if_ready()
        elif message.action == "fanout_execute":
            self._execute_or_preview()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._preview(event.value.strip())

    def _command_text(self) -> str:
        return self.query_one("#fanout-command", Input).value.strip()

    def _preview_if_ready(self) -> None:
        command = self._command_text()
        if command:
            self._preview(command)

    def _preview(self, command: str) -> None:
        if not self._choices:
            self.query_one("#fanout-preview", Static).update("no panes available")
            return
        if not command:
            self.query_one("#fanout-preview", Static).update(self._empty_preview())
            return
        choice = self._choices[self._selected]
        try:
            result = self._submit(choice.selector, command, True)
        except Exception as exc:
            self._last_preview_key = None
            self.query_one("#fanout-preview", Static).update(f"preview failed: {exc}")
            return
        self._last_preview_key = (choice.selector, command)
        self.query_one("#fanout-preview", Static).update(self._preview_text(result))

    def _execute_or_preview(self) -> None:
        command = self._command_text()
        if not command:
            self._preview("")
            return
        choice = self._choices[self._selected]
        if self._last_preview_key != (choice.selector, command):
            self._preview(command)
            return
        try:
            result = self._submit(choice.selector, command, False)
        except Exception as exc:
            self.query_one("#fanout-preview", Static).update(f"send failed: {exc}")
            return
        sent = result.get("sent", 0) if isinstance(result, dict) else 0
        notify = getattr(self.app, "notify", None)
        if callable(notify):
            notify(f"sent command to {sent} panes", timeout=3)
        self.dismiss()

    @staticmethod
    def _preview_text(result: dict[str, Any]) -> Text:
        count = int(result.get("target_count", 0))
        text = Text()
        text.append(f"preview: {count} {'pane' if count == 1 else 'panes'}\n", style="bold")
        if result.get("requires_confirmation") and result.get("risk"):
            text.append(f"risk: {result['risk']} · send confirms\n", style="#f38ba8")
        for record in result.get("targets", [])[:6]:
            workspace = str(record.get("workspace_label", "ws"))
            tab = str(record.get("tab_label", "tab"))
            title = str(record.get("title", record.get("pane_id", "pane")))
            status = str(record.get("status", "unknown"))
            text.append(f"  {workspace} / {tab} / {title}  {status}\n")
        extra = count - 6
        if extra > 0:
            text.append(f"  +{extra} more\n")
        text.append("click send to execute", style="#a6e3a1")
        return text

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()


class ContextMenuScreen(ModalScreen[None]):
    """A small right-click action menu; clicking an item runs that action."""

    DEFAULT_CSS = """
    ContextMenuScreen { align: center middle; background: $ph-base 50%; }
    #ctx-box {
        width: 32;
        height: auto;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 0 1;
    }
    .ctx-row { width: 1fr; color: $ph-text; padding: 0 1; }
    .ctx-row:hover { background: $ph-accent; color: $ph-base; text-style: bold; }
    """

    def __init__(self, title: str, items: list[tuple[str, str, str | None]]) -> None:
        super().__init__()
        self._title = title
        self._items = items

    def compose(self) -> ComposeResult:
        rows = [
            Clickable(label, action, arg, id=f"ctx-{index}", classes="ctx-row")
            for index, (label, action, arg) in enumerate(self._items)
        ]
        box = Vertical(*rows, id="ctx-box")
        box.border_title = self._title
        yield box

    def on_activated(self, message: Activated) -> None:
        message.stop()
        action, arg = message.action, message.arg
        handler = getattr(self.app, "run_menu_action", None)
        self.dismiss()
        if callable(handler):
            self.app.call_after_refresh(handler, action, arg)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()


class ShellPickerScreen(ModalScreen[None]):
    """A dropdown to pick which shell a new terminal/tab runs (ctrl+b n-area)."""

    DEFAULT_CSS = """
    ShellPickerScreen { align: center middle; background: $ph-base 60%; }
    #shell-box {
        width: 32;
        height: auto;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 0 1;
    }
    .shell-row { width: 1fr; color: $ph-text; padding: 0 1; }
    .shell-row:hover { background: $ph-accent; color: $ph-base; text-style: bold; }
    #shell-foot { color: $ph-subtext0; padding: 1 1 0 1; }
    """

    def __init__(self, shells: list[tuple[str, str]]) -> None:
        super().__init__()
        self._shells = shells

    def compose(self) -> ComposeResult:
        rows = [
            Clickable(f"  {label}", "new_shell", command, id=f"shellpick-{index}", classes="shell-row")
            for index, (label, command) in enumerate(self._shells)
        ]
        box = Vertical(*rows, Static("click a shell · esc close", id="shell-foot"), id="shell-box")
        box.border_title = "new terminal"
        yield box

    def on_activated(self, message: Activated) -> None:
        message.stop()
        if message.action == "new_shell" and message.arg:
            handler = getattr(self.app, "run_menu_action", None)
            self.dismiss()
            if callable(handler):
                self.app.call_after_refresh(handler, "new_shell", message.arg)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()


class DirSearchMenuScreen(ModalScreen[None]):
    """Context menu for a workspace search result row."""

    DEFAULT_CSS = """
    DirSearchMenuScreen { align: center middle; background: $ph-base 50%; }
    #dir-search-menu-box {
        width: 30;
        height: auto;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 0 1;
    }
    .dir-search-menu-row { width: 1fr; color: $ph-text; padding: 0 1; }
    .dir-search-menu-row:hover { background: $ph-accent; color: $ph-base; text-style: bold; }
    """

    def __init__(self, row: ExplorerRow, on_action: Callable[[str, str | None], None]) -> None:
        super().__init__()
        self._row = row
        self._on_action = on_action

    def compose(self) -> ComposeResult:
        rows = [
            Clickable(label, action, arg, id=f"dir-search-menu-{index}", classes="dir-search-menu-row")
            for index, (label, action, arg) in enumerate(self._items())
        ]
        box = Vertical(*rows, id="dir-search-menu-box")
        box.border_title = self._row.label
        yield box

    def _items(self) -> list[tuple[str, str, str | None]]:
        items: list[tuple[str, str, str | None]] = []
        if not self._row.stale:
            items.append(("open result", "dir_search_open", self._row.path))
        items.append(("open parent", "dir_search_parent", self._row.path))
        items.append(("copy path", "dir_search_copy_path", self._row.path))
        if self._row.stale:
            items.append(("remove stale", "dir_search_hide_stale", self._row.path))
        return items

    def on_activated(self, message: Activated) -> None:
        message.stop()
        action, arg = message.action, message.arg
        self.dismiss()
        self.app.call_after_refresh(self._on_action, action, arg)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()


class DirPickerScreen(ModalScreen[None]):
    """A folder browser: click into directories, then 'open this folder'."""

    DEFAULT_CSS = """
    DirPickerScreen { align: center middle; background: $ph-base 70%; }
    #dir-box {
        width: 72;
        height: 30;
        max-height: 90%;
        background: $ph-mantle;
        border: round $ph-accent;
        border-title-color: $ph-accent;
        padding: 1 1;
    }
    #dir-current {
        height: 5;
        padding: 0;
        margin: 1 0 1 0;
    }
    #dir-current-card {
        width: 1fr;
        height: 5;
        background: $ph-mantle;
        border: round $ph-surface0;
        padding: 0 1;
    }
    #dir-path {
        width: 1fr;
        height: 3;
        color: $ph-text;
        padding: 0 1;
    }
    .dir-current-open {
        width: 13;
        height: 1;
        background: $ph-surface0;
        color: $ph-green;
        content-align: center middle;
        text-style: bold;
        padding: 0 0;
        margin: 1 1 0 1;
    }
    .dir-current-open:hover { background: $ph-green; color: $ph-base; }
    #dir-list-panel {
        height: 1fr;
        min-height: 7;
        border: round $ph-surface0;
        background: $ph-base;
        padding: 0 0;
    }
    #dir-list { height: 1fr; }
    .dir-row { width: 1fr; color: $ph-text; padding: 0 1; }
    .dir-row:hover { background: $ph-surface0; }
    .dir-quick { width: 1fr; color: $ph-subtext0; padding: 0 1; }
    .dir-quick:hover { background: $ph-surface0; }
    .dir-search { width: 1fr; color: $ph-text; padding: 0 1; }
    .dir-search:hover { background: $ph-surface0; }
    .dir-active { background: $ph-surface0; }
    .dir-selected { color: $ph-green; }
    .dir-stale { color: $ph-subtext0; }
    .dir-open { width: 1fr; color: $ph-green; text-style: bold; padding: 0 1; }
    .dir-open:hover { background: $ph-accent; color: $ph-base; }
    #dir-input-hint { color: $ph-overlay0; height: 1; padding: 0 1 0 1; }
    #dir-separator { height: 1; color: $ph-surface0; }
    #dir-footer { height: 1; padding: 0 0 0 0; }
    #dir-foot { width: 1fr; color: $ph-subtext0; height: auto; min-height: 1; }
    .dir-help-button {
        width: 8;
        height: 1;
        background: $ph-mantle;
        color: $ph-accent;
        content-align: center middle;
        text-style: bold;
        padding: 0 0;
    }
    .dir-help-button:hover { background: $ph-accent; color: $ph-base; }
    """

    def __init__(
        self,
        start: str,
        on_select: Callable[[str], None],
        *,
        quick_paths: list[tuple[str, str]] | None = None,
        search_roots: list[SearchRoot] | None = None,
        search_debounce: float = 0.08,
        search_max_depth: int = 3,
        search_max_results: int = 80,
        search_ignore_names: list[str] | tuple[str, ...] | None = None,
        search_include_hidden: bool = False,
        search_cache_ttl_seconds: int = 300,
        search_metadata_cache_path: str | os.PathLike[str] | None = None,
    ) -> None:
        super().__init__()
        self._cwd = os.path.abspath(start or os.getcwd())
        self._on_select = on_select
        self._quick_paths = self._normalize_quick_paths(quick_paths or [])
        self._search_roots = self._normalize_search_roots(search_roots or [])
        if not self._search_roots:
            self._search_roots = [SearchRoot(self._cwd, label="current folder", source="current")]
        self._repo_metadata_cache: dict[str, DirRepoMetadata] = {}
        self._search_mode = False
        self._browse_rows: list[DirBrowseRow] = []
        self._active_browse_row = 0
        self._search_rows: list[ExplorerRow] = []
        self._search_max_depth = max(0, search_max_depth)
        self._search_max_results = max(1, search_max_results)
        self._search_ignore_names = tuple(DEFAULT_IGNORE_NAMES if search_ignore_names is None else search_ignore_names)
        self._search_include_hidden = search_include_hidden
        self._search_cache_ttl_seconds = max(0, search_cache_ttl_seconds)
        self._search_cache: dict[SearchCacheKey, tuple[float, list[ExplorerRow]]] = {}
        self._search_metadata_cache_path = search_metadata_cache_path
        self._pending_search_key: SearchCacheKey | None = None
        self._search_revision = 0
        self._search_debounce = max(0.0, search_debounce)
        self._active_row = 0
        self._selected_paths: set[str] = set()
        self._query = ""
        self._command_status = ""
        self._populate_lock = asyncio.Lock()

    def compose(self) -> ComposeResult:
        with Vertical(id="dir-box"):
            yield Input(placeholder=" search folders, cd, ls, open, or paste a path", id="dir-jump")
            yield Static("filter here, or use ls text / cd path / open path", id="dir-input-hint")
            with Horizontal(id="dir-current"):
                with Horizontal(id="dir-current-card"):
                    yield Static("", id="dir-path")
                    yield Clickable("Open Folder", "dir_open", classes="dir-current-open", id="dir-open-current")
            with Vertical(id="dir-list-panel"):
                yield VerticalScroll(id="dir-list")
                yield Static("─" * 66, id="dir-separator")
            with Horizontal(id="dir-footer"):
                yield Static("↑/↓ move · Enter open · Esc cancel", id="dir-foot")
                yield Clickable("? Help", "dir_help", classes="dir-help-button", id="dir-help")

    async def on_mount(self) -> None:
        self.query_one("#dir-box", Vertical).border_title = "choose workspace folder"
        self._update_browse_footer()
        await self._populate("")

    async def _populate(self, query: str | None = None) -> None:
        async with self._populate_lock:
            await self._populate_locked(query)

    async def _populate_locked(self, query: str | None = None) -> None:
        subdirs = self._subdirs()
        self.query_one("#dir-path", Static).update(self._path_summary(subdirs))
        listing = self.query_one("#dir-list", VerticalScroll)
        await listing.remove_children()
        if query is not None:
            if query != self._query:
                self._active_browse_row = 0
            self._query = query
        needle = self._query.strip().lower()
        if self._search_mode:
            await self._populate_search(listing, needle)
            return
        browse_rows: list[DirBrowseRow] = []
        parent = os.path.dirname(self._cwd)
        if parent and parent != self._cwd:
            browse_rows.append(DirBrowseRow("..", "dir_up", None, "dir-row", "dir-up"))
        for index, (label, path) in enumerate(self._quick_paths):
            if needle and needle not in label.lower() and needle not in path.lower():
                continue
            browse_rows.append(
                DirBrowseRow(
                    label,
                    "dir_quick",
                    path,
                    "dir-quick",
                    f"dir-quick-{index}",
                )
            )
        for index, name in enumerate(subdirs):
            full = os.path.join(self._cwd, name)
            if needle and needle not in name.lower() and needle not in full.lower():
                continue
            browse_rows.append(DirBrowseRow(f"{name}/", "dir_enter", full, "dir-row", f"dir-{index}"))
        self._browse_rows = browse_rows
        if self._active_browse_row >= len(self._browse_rows):
            self._active_browse_row = max(0, len(self._browse_rows) - 1)
        rows: list[Static] = []
        for index, row in enumerate(self._browse_rows):
            classes = row.classes
            if index == self._active_browse_row:
                classes += " dir-active"
            rows.append(
                Clickable(
                    self._browse_row_text(row, index),
                    row.action,
                    row.arg,
                    classes=classes,
                    id=row.widget_id,
                )
            )
        await listing.mount(*rows)
        self._update_browse_footer()
        self._scroll_active_dir_row_visible(self._active_browse_row)

    def _browse_row_text(self, row: DirBrowseRow, index: int) -> Text:
        cursor = ">" if index == self._active_browse_row else " "
        text = Text(f"{cursor} ")
        if row.action == "dir_up":
            text.append("..", style="bold")
            text.append(" parent folder", style="dim")
            return text
        if row.action == "dir_quick" and row.arg:
            text.append(row.label, style="bold")
            detail = self._quick_path_detail(row.label, row.arg)
            if detail:
                text.append(" · ", style="dim")
                text.append(detail, style="dim")
            return text
        text.append(row.label)
        return text

    @staticmethod
    def _quick_path_detail(label: str, path: str) -> str:
        normalized = os.path.abspath(path).rstrip("\\/")
        leaf = os.path.basename(normalized) or normalized
        if leaf and leaf.lower() in label.lower():
            return ""
        return leaf

    async def _populate_search(self, listing: VerticalScroll, needle: str) -> None:
        if not needle:
            self._search_rows = []
            self._pending_search_key = None
            await listing.mount(Static("  type to search configured roots", classes="dir-row"))
            self._update_search_footer()
            return
        cache_key = self._search_cache_key(needle)
        cached = self._cached_search_rows(cache_key)
        if cached is None:
            self._search_rows = []
            await listing.mount(Static(f"  searching roots for {needle}", classes="dir-row"))
            self._start_search_worker(needle, cache_key)
            self._update_search_footer()
            return
        await self._mount_search_rows(listing, cached)

    async def _mount_search_rows(self, listing: VerticalScroll, rows: list[ExplorerRow]) -> None:
        self._search_rows = rows
        if self._active_row >= len(self._search_rows):
            self._active_row = max(0, len(self._search_rows) - 1)
        if not self._search_rows:
            await listing.mount(Static("  no matching folders or repos", classes="dir-row"))
            self._update_search_footer()
            return
        row_widgets: list[Static] = []
        for index, row in enumerate(self._search_rows):
            classes = "dir-search"
            if index == self._active_row:
                classes += " dir-active"
            if row.path in self._selected_paths:
                classes += " dir-selected"
            if row.stale:
                classes += " dir-stale"
            row_widgets.append(
                Clickable(
                    self._search_row_text(row, index),
                    "dir_search_focus",
                    row.path,
                    classes=classes,
                    dbl_action="dir_search_open",
                    ctx_action="dir_search_menu",
                )
            )
        await listing.mount(*row_widgets)
        self._update_search_footer()
        self._scroll_active_dir_row_visible(self._active_row)

    def _start_search_worker(self, needle: str, cache_key: SearchCacheKey) -> None:
        if self._pending_search_key == cache_key:
            return
        self._search_revision += 1
        revision = self._search_revision
        self._pending_search_key = cache_key
        self.run_worker(
            self._run_search_worker(needle, cache_key, revision),
            group="dir-search",
            exclusive=True,
        )

    async def _run_search_worker(self, needle: str, cache_key: SearchCacheKey, revision: int) -> None:
        try:
            if self._search_debounce:
                await asyncio.sleep(self._search_debounce)
            rows = await asyncio.to_thread(
                search_workspace_rows,
                needle,
                list(self._search_roots),
                max_depth=self._search_max_depth,
                max_results=self._search_max_results,
                ignore_names=self._search_ignore_names,
                include_hidden=self._search_include_hidden,
                cache_path=None if self._search_metadata_cache_path is None else Path(self._search_metadata_cache_path),
                metadata_ttl_seconds=self._search_cache_ttl_seconds,
            )
        except asyncio.CancelledError:
            if self._pending_search_key == cache_key:
                self._pending_search_key = None
            raise
        if self._search_cache_ttl_seconds:
            self._search_cache[cache_key] = (time.monotonic(), rows)
        if self._pending_search_key == cache_key:
            self._pending_search_key = None
        if revision != self._search_revision or not self._search_mode or self._query.strip().lower() != needle:
            return
        await self._populate()

    def _cached_search_rows(self, cache_key: SearchCacheKey) -> list[ExplorerRow] | None:
        if not self._search_cache_ttl_seconds:
            return None
        cached = self._search_cache.get(cache_key)
        if cached is None:
            return None
        cached_at, rows = cached
        if time.monotonic() - cached_at > self._search_cache_ttl_seconds:
            del self._search_cache[cache_key]
            return None
        return rows

    def _search_cache_key(self, needle: str) -> SearchCacheKey:
        return (
            needle,
            tuple((root.path, root.label, root.source) for root in self._search_roots),
            self._search_max_depth,
            self._search_max_results,
            self._search_include_hidden,
            self._search_ignore_names,
        )

    def _search_row_text(self, row: ExplorerRow, index: int) -> Text:
        cursor = ">" if index == self._active_row else " "
        selected = "[x]" if row.path in self._selected_paths else "[ ]"
        kind = "repo" if row.kind == "repo" else ("stale" if row.stale else "dir")
        facts = self._search_row_facts(row)
        detail = self._display_path(row.path)
        text = Text(f"{cursor} {selected} {kind:<5} {row.label}")
        if facts:
            text.append(f"  {' · '.join(facts)}", style="dim")
        text.append(f"\n    {detail}", style="dim")
        return text

    def _search_row_facts(self, row: ExplorerRow) -> list[str]:
        facts: list[str] = []
        if row.source:
            facts.append(row.source)
        if row.repo_root:
            if os.path.normcase(os.path.abspath(row.repo_root)) == os.path.normcase(os.path.abspath(row.path)):
                facts.append("repo root")
            else:
                facts.append(f"repo {os.path.basename(row.repo_root) or row.repo_root}")
        if row.child_count:
            facts.append(self._folder_count_text(row.child_count))
        if row.branch:
            facts.append(f"branch {row.branch}")
            facts.append("dirty" if row.dirty else "clean")
        if row.stale:
            facts.append("stale")
        return facts

    def _update_search_footer(self) -> None:
        self._update_footer(
            "search mode · ↑/↓ move · Enter open · Space select · Esc cancel"
        )

    def _update_browse_footer(self) -> None:
        self._update_footer(
            "↑/↓ move · Enter open · Esc cancel"
        )

    def _update_footer(self, help_text: str) -> None:
        text = help_text
        if self._command_status:
            text = f"{self._command_status}\n{help_text}"
        self.query_one("#dir-foot", Static).update(text)

    def _path_summary(self, subdirs: list[str]) -> Text:
        text = Text("CURRENT FOLDER:\n", style="dim")
        text.append(self._cwd.replace("\\", "/"), style="bold")
        facts = [self._folder_count_text(len(subdirs))]
        metadata = self._repo_metadata()
        if metadata.repo_root:
            if os.path.normcase(os.path.abspath(self._cwd)) == os.path.normcase(os.path.abspath(metadata.repo_root)):
                facts.append("repo root")
            else:
                facts.append(f"repo {os.path.basename(metadata.repo_root) or metadata.repo_root}")
            if metadata.branch and metadata.branch != "HEAD":
                facts.append(f"branch {metadata.branch}")
            elif metadata.branch == "HEAD":
                facts.append("detached HEAD")
            facts.append("dirty" if metadata.dirty else "clean")
        text.append("\n" + " · ".join(facts), style="dim")
        return text

    def _repo_metadata(self) -> DirRepoMetadata:
        key = os.path.abspath(self._cwd)
        cached = self._repo_metadata_cache.get(key)
        if cached is not None:
            return cached
        repo_root = _git_root(key)
        metadata = DirRepoMetadata(
            repo_root=repo_root,
            branch=_git_branch(key) if repo_root else "",
            dirty=_git_dirty(key) if repo_root else False,
        )
        self._repo_metadata_cache[key] = metadata
        return metadata

    @staticmethod
    def _folder_count_text(count: int) -> str:
        return f"{count} folder" if count == 1 else f"{count} folders"

    @staticmethod
    def _display_path(path: str) -> str:
        return path.replace("\\", "/")

    @staticmethod
    def _normalize_quick_paths(paths: list[tuple[str, str]]) -> list[tuple[str, str]]:
        normalized: list[tuple[str, str]] = []
        seen: set[str] = set()
        for label, raw_path in paths:
            path = os.path.abspath(os.path.expanduser(raw_path.strip()))
            if not label.strip() or not os.path.isdir(path) or path in seen:
                continue
            seen.add(path)
            normalized.append((label.strip(), path))
        return normalized

    @staticmethod
    def _normalize_search_roots(roots: list[SearchRoot]) -> list[SearchRoot]:
        normalized: list[SearchRoot] = []
        seen: set[str] = set()
        for root in roots:
            path = os.path.abspath(os.path.expanduser(root.path.strip()))
            key = os.path.normcase(path)
            if not path or key in seen:
                continue
            seen.add(key)
            normalized.append(SearchRoot(path, label=root.label, source=root.source))
        return normalized

    def _subdirs(self) -> list[str]:
        try:
            names = [entry.name for entry in os.scandir(self._cwd) if entry.is_dir() and not entry.name.startswith(".")]
        except OSError:
            names = []
        return sorted(names, key=str.lower)

    def _set_cwd(self, path: str, *, status: str = "") -> None:
        self._cwd = os.path.abspath(path)
        self._query = ""
        self._search_mode = False
        self._active_browse_row = 0
        self._command_status = status
        self.query_one("#dir-jump", Input).value = ""
        self.run_worker(self._populate(), exclusive=True)

    def _clear_input_filter(self, *, status: str = "") -> None:
        self._query = ""
        self._active_browse_row = 0
        self._command_status = status
        self.query_one("#dir-jump", Input).value = ""
        self.run_worker(self._populate(), exclusive=True)

    def _resolve_input_path(self, raw_path: str) -> str:
        path = raw_path.strip().strip("\"'")
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.isabs(path):
            path = os.path.join(self._cwd, path)
        return os.path.abspath(path)

    def _folder_for_input_path(self, raw_path: str) -> tuple[str, bool] | None:
        path = self._resolve_input_path(raw_path)
        if os.path.isdir(path):
            return path, False
        if os.path.isfile(path):
            return os.path.dirname(path), True
        return None

    def _handle_input_command(self, raw: str) -> bool:
        command, separator, rest = raw.partition(" ")
        verb = command.lower()
        arg = rest.strip() if separator else ""
        if verb not in {"cd", "ls", "dir", "pwd", "open", "copy"}:
            return False
        if verb == "pwd":
            self._clear_input_filter(status=f"pwd: {self._display_path(self._cwd)}")
            return True
        if verb in {"ls", "dir"}:
            self._handle_ls_command(arg)
            return True
        if verb == "cd":
            self._handle_cd_command(arg)
            return True
        if verb == "open":
            self._handle_open_command(arg)
            return True
        self._handle_copy_command(arg)
        return True

    def _handle_ls_command(self, arg: str) -> None:
        if not arg:
            self._clear_input_filter(status=f"ls: {self._display_path(self._cwd)}")
            return
        folder = self._folder_for_input_path(arg)
        if folder:
            target, from_file = folder
            status = "ls: showing containing folder" if from_file else f"ls: {self._display_path(target)}"
            self._set_cwd(target, status=status)
            return
        self._query = arg
        self._command_status = f"ls: filtering for {arg}"
        self.query_one("#dir-jump", Input).value = ""
        self.run_worker(self._populate(arg), exclusive=True)

    def _handle_cd_command(self, arg: str) -> None:
        target_arg = arg or "~"
        folder = self._folder_for_input_path(target_arg)
        if not folder:
            self._clear_input_filter(status=f"cd: not found: {target_arg}")
            return
        target, from_file = folder
        status = "cd: showing containing folder" if from_file else f"cd: {self._display_path(target)}"
        self._set_cwd(target, status=status)

    def _handle_open_command(self, arg: str) -> None:
        if not arg or arg == ".":
            self._on_select(os.path.abspath(self._cwd))
            self.dismiss()
            return
        folder = self._folder_for_input_path(arg)
        if not folder:
            self._clear_input_filter(status=f"open: not found: {arg}")
            return
        target, _from_file = folder
        self._on_select(os.path.abspath(target))
        self.dismiss()

    def _handle_copy_command(self, arg: str) -> None:
        if not arg or arg == ".":
            target = os.path.abspath(self._cwd)
        else:
            folder = self._folder_for_input_path(arg)
            if not folder:
                self._clear_input_filter(status=f"copy: not found: {arg}")
                return
            target, _from_file = folder
            target = os.path.abspath(target)
        self.app.copy_to_clipboard(target)
        self._clear_input_filter(status=f"copied: {self._display_path(target)}")

    def on_activated(self, message: Activated) -> None:
        message.stop()
        if message.action == "dir_open":
            self._on_select(self._cwd)
            self.dismiss()
        elif message.action == "dir_help":
            self.app.push_screen(DirPickerHelpScreen())
        elif message.action == "dir_up":
            self._enter_browse_path(os.path.dirname(self._cwd))
        elif message.action == "dir_quick" and message.arg and os.path.isdir(message.arg):
            self._enter_browse_path(message.arg)
        elif message.action == "dir_enter" and message.arg:
            self._enter_browse_path(message.arg)
        elif message.action == "dir_search_focus" and message.arg:
            self._focus_search_path(message.arg)
            self.run_worker(self._populate(), exclusive=True)
        elif message.action == "dir_search_open" and message.arg:
            self._open_search_path(message.arg)
        elif message.action == "dir_search_menu" and message.arg:
            self._open_search_menu(message.arg)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        if self._search_mode:
            self._open_active_search_row()
            return
        raw = event.value.strip()
        if not raw:
            self._open_active_browse_row()
            return
        if self._handle_input_command(raw):
            return
        folder = self._folder_for_input_path(raw)
        if folder:
            target, from_file = folder
            status = "path: showing containing folder" if from_file else ""
            self._set_cwd(target, status=status)
        else:
            self._clear_input_filter(status=f"not a folder or command: {raw}")

    async def on_input_changed(self, event: Input.Changed) -> None:
        if not self._search_mode and self._is_command_draft(event.value):
            self._query = ""
            await self._populate("")
            return
        await self._populate(event.value)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            event.stop()
            self.dismiss()
        elif event.key in ("question_mark", "f1"):
            event.stop()
            event.prevent_default()
            self.app.push_screen(DirPickerHelpScreen())
        elif event.key == "ctrl+f":
            event.stop()
            event.prevent_default()
            self._search_mode = True
            self._active_row = 0
            self.run_worker(self._populate(), exclusive=True)
        elif event.key == "ctrl+l":
            event.stop()
            event.prevent_default()
            self._search_mode = False
            self._search_revision += 1
            self._pending_search_key = None
            self._update_browse_footer()
            self.run_worker(self._populate(), exclusive=True)
        elif event.key in ("alt+o", "ctrl+enter"):
            event.stop()
            event.prevent_default()
            self._on_select(os.path.abspath(self._cwd))
            self.dismiss()
        elif not self._search_mode and event.key == "backspace" and not self.query_one("#dir-jump", Input).value:
            event.stop()
            event.prevent_default()
            self._jump_to_parent_folder()
        elif event.key == "ctrl+h":
            event.stop()
            event.prevent_default()
            self._jump_to_home_folder()
        elif event.key == "ctrl+w":
            event.stop()
            event.prevent_default()
            self._jump_to_current_workspace()
        elif event.key == "ctrl+r":
            event.stop()
            event.prevent_default()
            self._jump_to_repo_root()
        elif event.key == "ctrl+shift+c":
            event.stop()
            event.prevent_default()
            if self._search_mode:
                self._copy_active_search_path()
            else:
                self._copy_active_browse_path()
        elif event.key == "ctrl+shift+v":
            event.stop()
            event.prevent_default()
            self._paste_clipboard_into_input()
        elif not self._search_mode and event.key in {"y", "ctrl+y"}:
            event.stop()
            event.prevent_default()
            self._copy_active_browse_path()
        elif not self._search_mode and event.key in ("up", "down"):
            event.stop()
            event.prevent_default()
            delta = -1 if event.key == "up" else 1
            self._move_active_browse_row(delta)
            self.run_worker(self._populate(), exclusive=True)
        elif not self._search_mode and event.key in ("pageup", "pagedown"):
            event.stop()
            event.prevent_default()
            delta = -_DIR_PICKER_PAGE_STEP if event.key == "pageup" else _DIR_PICKER_PAGE_STEP
            self._move_active_browse_row(delta)
            self.run_worker(self._populate(), exclusive=True)
        elif self._search_mode and event.key in ("up", "down"):
            event.stop()
            event.prevent_default()
            delta = -1 if event.key == "up" else 1
            self._move_active_search_row(delta)
            self.run_worker(self._populate(), exclusive=True)
        elif self._search_mode and event.key in ("pageup", "pagedown"):
            event.stop()
            event.prevent_default()
            delta = -_DIR_PICKER_PAGE_STEP if event.key == "pageup" else _DIR_PICKER_PAGE_STEP
            self._move_active_search_row(delta)
            self.run_worker(self._populate(), exclusive=True)
        elif self._search_mode and event.key == "space":
            event.stop()
            event.prevent_default()
            self._toggle_active_search_row()
            self.run_worker(self._populate(), exclusive=True)
        elif self._search_mode and event.key in {"p", "ctrl+p"}:
            event.stop()
            event.prevent_default()
            self._open_active_search_parent()
        elif self._search_mode and event.key == "delete":
            event.stop()
            event.prevent_default()
            self._hide_active_stale_search_row()
        elif self._search_mode and event.key in {"y", "ctrl+y"}:
            event.stop()
            event.prevent_default()
            self._copy_active_search_path()

    @staticmethod
    def _is_command_draft(value: str) -> bool:
        command = value.strip().split(" ", 1)[0].lower()
        return command in {"cd", "ls", "dir", "pwd", "open", "copy"}

    def _enter_browse_path(self, path: str) -> None:
        self._cwd = os.path.abspath(path)
        self._query = ""
        self._command_status = ""
        self._active_browse_row = 0
        self.query_one("#dir-jump", Input).value = ""
        self.run_worker(self._populate(), exclusive=True)

    def _jump_to_parent_folder(self) -> None:
        parent = os.path.dirname(self._cwd)
        if parent and parent != self._cwd and os.path.isdir(parent):
            self._set_cwd(parent, status=f"up: {self._display_path(parent)}")

    def _jump_to_home_folder(self) -> None:
        home = os.path.abspath(os.path.expanduser("~"))
        if os.path.isdir(home):
            self._set_cwd(home, status=f"home: {self._display_path(home)}")
        else:
            self._clear_input_filter(status="home: not available")

    def _jump_to_current_workspace(self) -> None:
        workspace = self._quick_path_named("current workspace")
        if workspace and os.path.isdir(workspace):
            self._set_cwd(workspace, status=f"workspace: {self._display_path(workspace)}")
        else:
            self._clear_input_filter(status="workspace: not available")

    def _jump_to_repo_root(self) -> None:
        repo_root = _git_root(self._cwd)
        if repo_root and os.path.isdir(repo_root):
            self._set_cwd(repo_root, status=f"repo: {self._display_path(repo_root)}")
        else:
            self._clear_input_filter(status="repo: not available")

    def _quick_path_named(self, label: str) -> str:
        target_label = label.strip().lower()
        for candidate_label, path in self._quick_paths:
            if candidate_label.strip().lower() == target_label:
                return path
        return ""

    def _move_active_browse_row(self, delta: int) -> None:
        if not self._browse_rows:
            self._active_browse_row = 0
            return
        self._active_browse_row = max(0, min(len(self._browse_rows) - 1, self._active_browse_row + delta))

    def _scroll_active_dir_row_visible(self, row_index: int) -> None:
        listing = self.query_one("#dir-list", VerticalScroll)
        if row_index < 0 or row_index >= len(listing.children):
            return
        active_row = listing.children[row_index]

        def scroll_after_layout() -> None:
            if active_row not in listing.children:
                return
            region = active_row.virtual_region
            if not region:
                return
            viewport_height = max(1, listing.size.height)
            viewport_top = int(listing.scroll_y)
            viewport_bottom = viewport_top + viewport_height
            row_top = region.y
            row_bottom = row_top + max(1, region.height)
            if row_top < viewport_top:
                target_y = row_top
            elif row_bottom > viewport_bottom:
                target_y = row_bottom - viewport_height
            else:
                return
            listing.scroll_to(
                y=max(0, min(target_y, int(listing.max_scroll_y))),
                animate=False,
                immediate=True,
            )

        self.call_after_refresh(scroll_after_layout)

    def _open_active_browse_row(self) -> None:
        row = self._active_browse_row_record()
        if row is None:
            return
        if row.action == "dir_up":
            self._enter_browse_path(os.path.dirname(self._cwd))
        elif row.action in {"dir_quick", "dir_enter"} and row.arg and os.path.isdir(row.arg):
            self._enter_browse_path(row.arg)

    def _active_browse_row_record(self) -> DirBrowseRow | None:
        if not self._browse_rows:
            return None
        return self._browse_rows[max(0, min(len(self._browse_rows) - 1, self._active_browse_row))]

    def _copy_active_browse_path(self) -> None:
        row = self._active_browse_row_record()
        if row is None:
            self._copy_search_path(self._cwd)
            return
        if row.action == "dir_up":
            target = os.path.dirname(os.path.abspath(self._cwd))
        else:
            target = row.arg or self._cwd
        self._copy_search_path(target)

    def _paste_clipboard_into_input(self) -> None:
        jump = self.query_one("#dir-jump", Input)
        jump.action_paste()
        if not self._search_mode and self._is_command_draft(jump.value):
            self._query = ""
            self.run_worker(self._populate(""), exclusive=True)
            return
        self.run_worker(self._populate(jump.value), exclusive=True)

    def _move_active_search_row(self, delta: int) -> None:
        if not self._search_rows:
            self._active_row = 0
            return
        self._active_row = max(0, min(len(self._search_rows) - 1, self._active_row + delta))

    def _toggle_active_search_row(self) -> None:
        row = self._active_search_row()
        if row is None or row.stale:
            return
        if row.path in self._selected_paths:
            self._selected_paths.remove(row.path)
        else:
            self._selected_paths.add(row.path)

    def _open_active_search_row(self) -> None:
        row = self._active_search_row()
        if row is not None:
            self._open_search_path(row.path)

    def _open_search_menu(self, path: str) -> None:
        self._focus_search_path(path)
        row = self._active_search_row()
        if row is not None:
            self.app.push_screen(DirSearchMenuScreen(row, self._handle_search_menu_action))

    def _handle_search_menu_action(self, action: str, path: str | None) -> None:
        if path:
            self._focus_search_path(path)
        if action == "dir_search_open" and path:
            self._open_search_path(path)
        elif action == "dir_search_parent":
            self._open_active_search_parent()
        elif action == "dir_search_copy_path" and path:
            self._copy_search_path(path)
        elif action == "dir_search_hide_stale":
            self._hide_active_stale_search_row()

    def _open_active_search_parent(self) -> None:
        row = self._active_search_row()
        if row is None:
            return
        parent = os.path.dirname(os.path.abspath(row.path))
        if not parent or parent == os.path.abspath(row.path) or not os.path.isdir(parent):
            self._command_status = f"parent: not available for {self._display_path(row.path)}"
            self.run_worker(self._populate(), exclusive=True)
            return
        self._set_cwd(parent, status=f"parent: {self._display_path(parent)}")

    def _copy_active_search_path(self) -> None:
        row = self._active_search_row()
        if row is not None:
            self._copy_search_path(row.path)

    def _copy_search_path(self, path: str) -> None:
        resolved = os.path.abspath(path)
        display = self._display_path(resolved)
        try:
            self.app.copy_to_clipboard(resolved)
        except Exception:
            self._command_status = f"path: {display}"
        else:
            self._command_status = f"copied path: {display}"
        if self._search_mode:
            self._update_search_footer()
        else:
            self._update_browse_footer()
        self.run_worker(self._populate(), exclusive=True)

    def _hide_active_stale_search_row(self) -> None:
        row = self._active_search_row()
        if row is None:
            return
        if not row.stale:
            self._command_status = "delete: only stale search rows can be hidden"
            self.run_worker(self._populate(), exclusive=True)
            return
        row_id = row.row_id
        self._selected_paths.discard(row.path)
        self._search_rows = [candidate for candidate in self._search_rows if candidate.row_id != row_id]
        for cache_key, (cached_at, rows) in list(self._search_cache.items()):
            filtered = [candidate for candidate in rows if candidate.row_id != row_id]
            if len(filtered) != len(rows):
                self._search_cache[cache_key] = (cached_at, filtered)
        if self._active_row >= len(self._search_rows):
            self._active_row = max(0, len(self._search_rows) - 1)
        removed_recent = False
        if row.source == "recent":
            summary = remove_workspace_recent(row.path)
            removed_recent = int(summary["removed"]) > 0
        action = "removed stale recent root" if removed_recent else "hidden stale root"
        self._command_status = f"{action}: {self._display_path(row.path)}"
        self.run_worker(self._populate(), exclusive=True)

    def _active_search_row(self) -> ExplorerRow | None:
        if not self._search_rows:
            return None
        return self._search_rows[max(0, min(len(self._search_rows) - 1, self._active_row))]

    def _focus_search_path(self, path: str) -> None:
        for index, row in enumerate(self._search_rows):
            if os.path.normcase(row.path) == os.path.normcase(path):
                self._active_row = index
                return

    def _open_search_path(self, path: str) -> None:
        if not os.path.isdir(path):
            return
        self._on_select(os.path.abspath(path))
        self.dismiss()


class PaneView(Static):
    """A bordered, titled view of one pane's screen. Click it to focus."""

    can_focus = False

    def __init__(self, pane_id: str, title: str) -> None:
        super().__init__("", id=f"pane-{pane_id}")
        self.pane_id = pane_id
        self.border_title = title

    def on_click(self, event: events.Click) -> None:
        event.stop()
        if getattr(event, "button", 1) == 3:
            self.post_message(Activated("ctx_pane", self.pane_id))
        else:
            self.post_message(Activated("focus_pane", self.pane_id))

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.post_message(PaneWheel(self.pane_id, "up", int(event.x) + 1, int(event.y) + 1))
        event.stop()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.post_message(PaneWheel(self.pane_id, "down", int(event.x) + 1, int(event.y) + 1))
        event.stop()


class SplitDivider(Static):
    """A draggable divider between two split panes (drag to resize)."""

    DEFAULT_CSS = """
    SplitDivider { background: $ph-base; }
    SplitDivider.divider-h { width: 1; height: 1fr; }
    SplitDivider.divider-v { width: 1fr; height: 1; }
    SplitDivider:hover { background: $ph-surface0; }
    """

    def __init__(self, direction: Direction, path: tuple[bool, ...]) -> None:
        cls = "divider-h" if direction == Direction.HORIZONTAL else "divider-v"
        super().__init__("", classes=cls)
        self._direction = direction
        self._path = path
        self._dragging = False

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self._dragging = True
        self.capture_mouse()
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self.release_mouse()
            persist = getattr(self.app, "persist_layout", None)
            if callable(persist):
                persist()
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._dragging or self.parent is None:
            return
        region = getattr(self.parent, "region", None)
        if region is None:
            return
        if self._direction == Direction.HORIZONTAL:
            ratio = (event.screen_x - region.x) / max(1, region.width)
        else:
            ratio = (event.screen_y - region.y) / max(1, region.height)
        ratio = max(0.1, min(0.9, ratio))
        siblings = list(self.parent.children)
        index = siblings.index(self) if self in siblings else -1
        if index <= 0 or index + 1 >= len(siblings):
            return
        first, second = siblings[index - 1], siblings[index + 1]
        pct = max(1, min(99, round(ratio * 100)))
        if self._direction == Direction.HORIZONTAL:
            first.styles.width = f"{pct}fr"
            second.styles.width = f"{100 - pct}fr"
        else:
            first.styles.height = f"{pct}fr"
            second.styles.height = f"{100 - pct}fr"
        remember = getattr(self.app, "_remember_ratio", None)
        if callable(remember):
            remember(self._path, ratio)
        event.stop()


class PyHerdrTui(App):
    """A Herdr-style terminal multiplexer over the PyHerdr server."""

    def __init__(self, client: PaneClient | None = None, *, poll_interval: float = 0.1) -> None:
        # Set the palette before super().__init__(): App.__init__ parses CSS and
        # calls get_css_variables(), which reads self._palette.
        config = load_config()
        self._config = config
        self._palette: Palette = config.theme.resolve()
        self._theme_name = (config.theme.name or DEFAULT_THEME).strip()
        # Keybindings: custom prefix, action→key overrides, and user commands.
        self._prefix_key = (config.keys.prefix or "ctrl+b").strip()
        self._prefix_actions = dict(_DEFAULT_PREFIX_ACTIONS)
        for action, key in config.keys.bindings.items():
            key = key.removeprefix("prefix+").strip()
            if not key:
                continue
            for existing in [k for k, a in self._prefix_actions.items() if a == action]:
                del self._prefix_actions[existing]
            self._prefix_actions[key] = action
        self._commands = {
            binding.key.removeprefix("prefix+").strip(): binding.command
            for binding in config.keys.commands
            if binding.key and binding.command
        }
        super().__init__()
        self._client: PaneClient = client or ServerClient()
        self._poll_interval = poll_interval
        self._shells = _available_shells()
        self._state: dict = {"workspaces": []}
        self._branches: dict[str, str] = {}
        self._ahead_behind: dict[str, tuple[int, int]] = {}
        self._pending_layout: dict | None = None
        self._agent_status: dict[str, str] = {}
        self._workspace_id: str | None = None
        self._tab_id: str | None = None
        self._pane_id: str | None = None
        self._terminal_versions: dict[str, int] = {}
        self._terminal_sizes: dict[str, tuple[int, int]] = {}
        self._terminal_metadata: dict[str, dict[str, bool]] = {}
        self._terminal_input: queue.Queue[tuple[str, str, str]] = queue.Queue()
        self._terminal_input_lock = threading.Lock()
        self._terminal_input_started = False
        self._sidebar_compact = False
        self._agent_panel_scope = config.ui.agent_panel_scope
        self._prefix = False
        self._zoom = False
        self._resize = False
        self._spin = 0
        self._seeding = False

    CSS = """
    Screen { background: $ph-base; color: $ph-text; }
    #tabbar {
        dock: top;
        height: 1;
        background: $ph-mantle;
        color: $ph-subtext0;
    }
    #tabstrip {
        width: 1fr;
        height: 1;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }
    .tabscroll { width: 3; content-align: center middle; color: $ph-overlay0; }
    .tabscroll:hover { background: $ph-surface0; color: $ph-accent; text-style: bold; }
    .wsname { width: auto; padding: 0 1; color: $ph-accent; text-style: bold; }
    .tabcell { width: auto; padding: 0 1; color: $ph-subtext0; }
    .tabcell:hover { background: $ph-surface0; color: $ph-text; }
    .tabcell.active { background: $ph-accent; color: $ph-base; text-style: bold; }
    .tabclose { width: auto; color: $ph-overlay0; }
    .tabclose:hover { background: $ph-surface0; color: $ph-red; text-style: bold; }
    .tabplus { width: auto; padding: 0 1; color: $ph-overlay0; text-style: bold; }
    .tabplus:hover { background: $ph-surface0; color: $ph-text; }
    #body { height: 1fr; }
    #nav {
        width: 40;
        height: 1fr;
        background: $ph-mantle;
        border: round $ph-overlay0;
        border-title-color: $ph-accent;
        padding: 0 1;
    }
    #nav.compact {
        width: 6;
        padding: 0 0;
    }
    .attention { width: 1fr; padding: 1 0 1 0; }
    .wsrow { width: 1fr; height: auto; padding: 0 0 1 0; }
    .wsrow:hover { background: $ph-surface0; }
    .wsrow.active { background: $ph-surface0; }
    .wscompact { width: 1fr; height: 1; content-align: center middle; }
    .wscompact:hover { background: $ph-surface0; }
    .wscompact.active { background: $ph-surface0; }
    .navhead { width: 1fr; height: 1; }
    .navtitle { width: 1fr; height: 1; color: $ph-subtext0; }
    .navtoggle { width: 3; height: 1; content-align: center middle; color: $ph-accent; }
    .navtoggle:hover { background: $ph-surface0; }
    .compact-attention { width: 1fr; padding: 1 0; content-align: center middle; }
    .compact-agents { width: 1fr; padding: 1 0 0 0; content-align: center middle; }
    .navhdr { width: 1fr; color: $ph-subtext0; padding: 1 0 0 0; }
    .navtop { width: 1fr; color: $ph-subtext0; }
    .navsectionhead { width: 1fr; color: $ph-subtext0; padding: 0 0 1 0; }
    .navgap { width: 1fr; height: 1; }
    .sidebar-divider { width: 1fr; height: 1; color: $ph-overlay0; }
    .newterm { width: 1fr; color: $ph-blue; }
    .newterm:hover { background: $ph-surface0; text-style: bold; }
    .workflow { width: 1fr; padding: 1 0 0 0; }
    .agents { width: 1fr; height: 1fr; padding: 1 0 0 0; }
    .agents:hover { background: $ph-surface0; }
    .sidebar-footer { width: 1fr; height: 1; dock: bottom; }
    .sidebar-action { width: auto; padding: 0 1 0 0; color: $ph-blue; }
    .sidebar-action:hover { background: $ph-surface0; color: $ph-text; text-style: bold; }
    #panes { height: 1fr; width: 1fr; }
    PaneView {
        width: 1fr;
        height: 1fr;
        border: round $ph-overlay0;
        border-title-color: $ph-blue;
        padding: 0 1;
        background: $ph-base;
    }
    PaneView.active { border: round $ph-accent; border-title-color: $ph-accent; }
    #footer { dock: bottom; height: 2; }
    #actionbar {
        height: 1;
        background: $ph-surface0;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-size: 0 0;
    }
    .abtn { width: auto; padding: 0 1; color: $ph-subtext0; }
    .abtn:hover { background: $ph-accent; color: $ph-base; text-style: bold; }
    #statusbar { height: 1; background: $ph-mantle; color: $ph-subtext0; padding: 0 1; }
    """

    def get_css_variables(self) -> dict[str, str]:
        variables = super().get_css_variables()
        palette = self._palette
        variables.update(
            {
                "ph-base": palette.panel_bg,
                "ph-mantle": palette.surface_dim,
                "ph-surface0": palette.surface0,
                "ph-overlay0": palette.overlay0,
                "ph-text": palette.text,
                "ph-subtext0": palette.subtext0,
                "ph-accent": palette.accent,
                "ph-blue": palette.blue,
                "ph-red": palette.red,
                "ph-green": palette.green,
            }
        )
        return variables

    def compose(self) -> ComposeResult:
        yield Horizontal(id="tabbar")
        with Horizontal(id="body"):
            yield Vertical(id="nav")
            yield Horizontal(id="panes")
        with Vertical(id="footer"):
            with HorizontalScroll(id="actionbar"):
                for label, action in _FOOTER_ACTIONS:
                    yield Clickable(label, action, classes="abtn")
            yield Static("", id="statusbar")

    async def on_mount(self) -> None:
        self.title = "PyHerdr"
        await self.reload()
        self.run_worker(self._terminal_refresh_loop(), group="terminal-refresh", exclusive=True)
        self.set_interval(max(1.0, self._poll_interval), self._tick)

    # ----- input: prefix model -----
    def on_key(self, event: events.Key) -> None:
        # When a modal screen (help/theme/rename/navigator/menu) is open it owns
        # the keyboard — don't let the main pane key handler intercept its keys.
        if len(self.screen_stack) > 1:
            return
        # All server I/O is wrapped so a dropped connection or server hiccup can
        # never crash the UI (e.g. forwarding ctrl+c to a pane).
        try:
            if self._resize:
                self._handle_resize_key(event.key)
            elif self._prefix:
                self._prefix = False
                self._run_prefix_action(event.key, event.character)
                self._refresh_hint()
            elif event.key == self._prefix_key:
                self._prefix = True
                self._refresh_hint()
            elif self._pane_id and event.key in ("pageup", "pagedown"):
                self._scroll_pane(self._pane_id, "up" if event.key == "pageup" else "down")
            elif self._pane_id:
                char = event.character
                if char is not None and char.isprintable():
                    self._queue_terminal_input("text", self._pane_id, char)
                else:
                    self._queue_terminal_input("key", self._pane_id, event.key)
        except Exception:
            self._prefix = False
        event.stop()
        event.prevent_default()

    def _queue_terminal_input(self, kind: str, pane_id: str, payload: str) -> None:
        self._ensure_terminal_input_worker()
        self._terminal_input.put((kind, pane_id, payload))

    def _ensure_terminal_input_worker(self) -> None:
        with self._terminal_input_lock:
            if self._terminal_input_started:
                return
            self._terminal_input_started = True
            threading.Thread(target=self._terminal_input_worker, name="pyherdr-terminal-input", daemon=True).start()

    def _terminal_input_worker(self) -> None:
        pending: tuple[str, str, str] | None = None
        while True:
            if pending is None:
                item = self._terminal_input.get()
            else:
                item = pending
                pending = None
            kind, pane_id, payload = item
            try:
                self._pin_pane_to_bottom(pane_id)
                if kind == "text":
                    payload, pending = self._coalesced_terminal_text(pane_id, payload)
                    self._client.send_text(pane_id, payload)
                else:
                    self._client.send_key(pane_id, payload)
            except Exception:
                pass
            finally:
                self._terminal_input.task_done()

    def _pin_pane_to_bottom(self, pane_id: str) -> None:
        try:
            self._client.pane_scroll(pane_id, "bottom")
        except Exception:
            pass

    def _coalesced_terminal_text(
        self, pane_id: str, text: str
    ) -> tuple[str, tuple[str, str, str] | None]:
        # Give a burst of typed/pasted printable characters a tiny window to
        # batch into one socket request, while staying below human-visible lag.
        time.sleep(0.005)
        while True:
            try:
                kind, next_pane_id, payload = self._terminal_input.get_nowait()
            except queue.Empty:
                return text, None
            if kind == "text" and next_pane_id == pane_id:
                text += payload
                self._terminal_input.task_done()
                continue
            return text, (kind, next_pane_id, payload)

    def _run_prefix_action(self, key: str, character: str | None) -> None:
        command = self._commands.get(character or "") or self._commands.get(key)
        if command:
            self.run_worker(self._new_tab_with_shell(command), exclusive=True)
            return
        if character and character.isdigit() and character != "0":
            self._switch_tab(int(character) - 1)
            return
        action = self._prefix_actions.get(character or "") or self._prefix_actions.get(key)
        if action:
            self._run_named_action(action)

    def _run_named_action(self, action: str) -> None:
        if action == "new_tab":
            self._client.create_tab()
            self.run_worker(self._reload_focus_last_tab(), exclusive=True)
        elif action == "split_sbs":
            self.run_worker(self._split("horizontal"), exclusive=True)
        elif action == "split_stack":
            self.run_worker(self._split("vertical"), exclusive=True)
        elif action == "new_workspace":
            self._open_new_workspace()
        elif action == "worktrees":
            self._open_worktrees()
        elif action == "close_pane" and self._pane_id:
            self._client.close_pane(self._pane_id)
            self._pane_id = None
            self.run_worker(self.reload(), exclusive=True)
        elif action == "close_tab" and self._tab_id:
            self._client.close_tab(self._tab_id)
            self._tab_id = None
            self.run_worker(self.reload(), exclusive=True)
        elif action == "rename_tab":
            self._open_rename_tab(self._tab_id)
        elif action == "rename_pane":
            self._open_rename_pane(self._pane_id)
        elif action in ("move_tab_left", "move_tab_right") and self._tab_id:
            self._client.move_tab(self._tab_id, "left" if action == "move_tab_left" else "right")
            self.run_worker(self.reload(), exclusive=True)
        elif action in ("move_workspace_up", "move_workspace_down") and self._workspace_id:
            self._client.move_workspace(self._workspace_id, "up" if action == "move_workspace_up" else "down")
            self.run_worker(self.reload(), exclusive=True)
        elif action == "settings":
            self.push_screen(ThemeScreen(THEME_NAMES, self._theme_name))
        elif action == "toggle_sidebar":
            self._sidebar_compact = not self._sidebar_compact
            self.run_worker(self._refresh_sidebar(), exclusive=True)
            self._refresh_statusbar()
        elif action == "toggle_agent_scope":
            self._toggle_agent_scope()
        elif action == "goto":
            rows = self._navigator_rows()
            if rows:
                self.push_screen(NavigatorScreen(rows))
        elif action == "next_tab":
            self._cycle_tab(1)
        elif action == "prev_tab":
            self._cycle_tab(-1)
        elif action == "next_pane":
            self._cycle_pane(1)
        elif action == "prev_pane":
            self._cycle_pane(-1)
        elif action in ("focus_left", "focus_down", "focus_up", "focus_right"):
            self._focus_direction(action)
        elif action == "next_workspace":
            self._cycle_workspace(1)
        elif action == "zoom":
            self._zoom = not self._zoom
            self.run_worker(self.reload(), exclusive=True)
        elif action == "resize":
            self._resize = True
            self._refresh_hint()
        elif action == "help":
            self.push_screen(HelpScreen(self._palette))
        elif action == "palette":
            self._open_command_palette()
        elif action == "pane_menu":
            self._open_pane_menu()
        elif action == "copy_mode":
            self._open_copy_mode(self._pane_id)
        elif action == "copy_output":
            self._copy_pane_output(self._pane_id)
        elif action == "resource_monitor":
            self._open_stats("resource monitor · all sessions", None)
        elif action == "workflow_view":
            self._open_workflow_view()
        elif action == "fanout":
            self._open_fanout_picker()
        elif action in ("quit", "detach"):
            # Detach == leave the TUI; the background server keeps every pane
            # running, so reopening `pyherdr tui` re-attaches to them.
            self.exit()

    # ----- input: mouse -----
    def on_activated(self, message: Activated) -> None:
        message.stop()
        try:
            self._dispatch_activated(message.action, message.arg)
        except Exception:
            pass

    def on_pane_wheel(self, message: PaneWheel) -> None:
        message.stop()
        self._handle_pane_wheel(message.pane_id, message.direction, message.x, message.y)

    def _dispatch_activated(self, action: str, arg: str | None) -> None:
        if action == "focus_pane" and arg:
            self._pane_id = arg
            self._mark_active_pane()
            self._pin_pane_to_bottom(arg)
            self._update_pane_contents({arg})
            self._refresh_statusbar()
        elif action == "switch_tab" and arg:
            self._focus_tab_on_server(arg)
            self._tab_id = arg
            self._pane_id = None
            self.run_worker(self.reload(), exclusive=True)
        elif action == "tab_scroll_left":
            self._scroll_tabbar(-1)
        elif action == "tab_scroll_right":
            self._scroll_tabbar(1)
        elif action == "switch_workspace" and arg:
            self._focus_workspace_on_server(arg)
            self._workspace_id = arg
            self._tab_id = None
            self._pane_id = None
            self.run_worker(self.reload(), exclusive=True)
        elif action == "new_tab":
            self._client.create_tab()
            self.run_worker(self._reload_focus_last_tab(), exclusive=True)
        elif action == "new_pane":
            self.run_worker(self._split("horizontal", arg), exclusive=True)
        elif action == "split_down":
            self.run_worker(self._split("vertical", arg), exclusive=True)
        elif action == "zoom":
            self._zoom = not self._zoom
            self.run_worker(self.reload(), exclusive=True)
        elif action == "close_pane" and arg:
            self._client.close_pane(arg)
            self._pane_id = None
            self.run_worker(self.reload(), exclusive=True)
        elif action == "ctx_tab" and arg:
            self.push_screen(
                ContextMenuScreen(
                    "tab",
                    [("rename", "rename_tab", arg), ("close", "close_tab", arg), ("new tab", "new_tab", None)],
                )
            )
        elif action == "ctx_pane" and arg:
            self._pane_id = arg
            self._mark_active_pane()
            self._pin_pane_to_bottom(arg)
            self._update_pane_contents({arg})
            self.push_screen(
                ContextMenuScreen(
                    "pane",
                    [
                        ("split right", "new_pane", arg),
                        ("split down", "split_down", arg),
                        ("zoom", "zoom", None),
                        ("copy mode", "copy_mode", arg),
                        ("copy output", "copy_output", arg),
                        ("resource usage", "pane_stats", arg),
                        ("close", "close_pane", arg),
                        ("rename", "rename_pane", arg),
                    ],
                )
            )
        elif action == "close_tab" and arg:
            self._client.close_tab(arg)
            self._tab_id = None
            self.run_worker(self.reload(), exclusive=True)
        elif action == "rename_tab" and arg:
            self._open_rename_tab(arg)
        elif action == "rename_pane" and arg:
            self.call_after_refresh(self._open_rename_pane, arg)
        elif action == "ctx_workspace" and arg:
            self.push_screen(
                ContextMenuScreen(
                    "workspace",
                    [
                        ("switch to", "switch_workspace", arg),
                        ("rename", "rename_workspace", arg),
                        ("move up", "move_workspace_up", arg),
                        ("move down", "move_workspace_down", arg),
                        ("resource usage", "workspace_stats", arg),
                        ("close", "close_workspace", arg),
                    ],
                )
            )
        elif action == "rename_workspace" and arg:
            self._open_rename_workspace(arg)
        elif action == "close_workspace" and arg:
            self._client.close_workspace(arg)
            self._workspace_id = None
            self.run_worker(self.reload(), exclusive=True)
        elif action in ("move_workspace_up", "move_workspace_down") and arg:
            self._client.move_workspace(arg, "up" if action == "move_workspace_up" else "down")
            self.run_worker(self.reload(), exclusive=True)
        elif action == "open_shell_picker":
            self.push_screen(ShellPickerScreen(self._shells))
        elif action == "new_workspace":
            self._open_new_workspace()
        elif action == "new_shell" and arg:
            self.run_worker(self._new_tab_with_shell(arg), exclusive=True)
        elif action in ("pane_scroll_up", "pane_scroll_down") and arg:
            self._scroll_pane(arg, "up" if action == "pane_scroll_up" else "down")
        elif action == "copy_output" and arg:
            self._copy_pane_output(arg)
        elif action == "copy_mode" and arg:
            self._open_copy_mode(arg)
        elif action == "pane_stats" and arg:
            self._open_stats(f"resource usage · {self._pane_label_map().get(arg, arg)}", [arg])
        elif action == "workspace_stats" and arg:
            self._open_stats("resource usage · workspace", self._workspace_pane_ids(arg))
        elif action == "resource_monitor":
            self._open_stats("resource monitor · all sessions", None)
        elif action == "workflow_view":
            self._open_workflow_view()
        elif action in (
            "help", "palette", "settings", "detach", "quit",
            "pane_menu", "resize", "goto", "next_tab", "prev_tab", "next_workspace", "fanout", "worktrees",
            "copy_mode",
            "rename_pane", "toggle_sidebar", "toggle_agent_scope",
        ):
            # Global actions (footer buttons / palette) share the keybind handler.
            self._run_named_action(action)

    def _scroll_tabbar(self, direction: int) -> None:
        try:
            strip = self.query_one("#tabstrip", HorizontalScroll)
        except Exception:
            return
        step = max(8, int(strip.size.width * 0.75) if strip.size.width else 12)
        strip.scroll_relative(x=direction * step, animate=False, force=True, immediate=True)

    def _navigator_rows(self) -> list[tuple[str, Text, str]]:
        rows: list[tuple[str, Text, str]] = []
        for workspace in self._workspaces():
            for tab in workspace.get("tabs", []):
                for pane in tab.get("panes", []):
                    glyph, color = self._dot(str(pane.get("status", "unknown")))
                    ws_label = str(workspace.get("label", "ws"))
                    tab_label = str(tab.get("label", "tab"))
                    pane_label = str(pane.get("title", "pane"))
                    plain = f"{ws_label} {tab_label} {pane_label}"
                    label = Text()
                    label.append(f"{glyph} ", style=color)
                    label.append(f"{ws_label} · {tab_label} · {pane_label}", style=self._palette.text)
                    arg = f"{workspace.get('id')}|{tab.get('id')}|{pane.get('id')}"
                    rows.append((arg, label, plain))
        return rows

    def run_menu_action(self, action: str, arg: str | None) -> None:
        """Run a context-menu item's action (after the menu has closed)."""
        self._dispatch_activated(action, arg)

    def _pane_label_map(self) -> dict[str, str]:
        """Map pane id -> 'workspace · tab · pane' for the resource monitor."""
        labels: dict[str, str] = {}
        for workspace in self._workspaces():
            ws = str(workspace.get("label", "ws"))
            for tab in workspace.get("tabs", []):
                tb = str(tab.get("label", "tab"))
                for pane in tab.get("panes", []):
                    labels[str(pane.get("id"))] = f"{ws} · {tb} · {pane.get('title', 'pane')}"
        return labels

    def _workspace_pane_ids(self, ws_id: str) -> list[str]:
        """Every pane id that belongs to one workspace."""
        for workspace in self._workspaces():
            if str(workspace.get("id")) == ws_id:
                return [str(p.get("id")) for t in workspace.get("tabs", []) for p in t.get("panes", [])]
        return []

    def _open_stats(self, title: str, pane_ids: list[str] | None) -> None:
        self.push_screen(StatsScreen(title, self._client, self._palette, self._pane_label_map(), pane_ids))

    def _workflow_events(self) -> list[WorkflowEvent]:
        try:
            return read_events(limit=80)
        except Exception:
            return []

    def _open_workflow_view(self) -> None:
        self.push_screen(WorkflowScreen(self._workflow_events(), self._palette))

    def _open_fanout_picker(self) -> None:
        choices = self._fanout_choices()
        if not choices:
            self.notify("no panes available for fan-out", timeout=3)
            return
        self.push_screen(FanoutScreen(choices, self._fanout_submit))

    def _fanout_submit(self, selector: str, command: str, dry_run: bool) -> dict[str, Any]:
        return self._client.pane_fanout([selector], command, enter=True, dry_run=dry_run, confirm_risky=not dry_run)

    def _fanout_choices(self) -> list[FanoutChoice]:
        choices: list[FanoutChoice] = []
        pane = self._pane_by_id(self._pane_id)
        if pane is not None and self._pane_id:
            choices.append(FanoutChoice("focused pane", f"pane:{self._pane_id}", self._pane_detail(pane)))
        tab = self._focused_tab()
        if tab is not None:
            tab_id = str(tab.get("id"))
            panes = [pane for pane in tab.get("panes", []) if isinstance(pane, dict)]
            choices.append(
                FanoutChoice("current tab", f"tab:{tab_id}", f"{tab.get('label', 'tab')} · {len(panes)} panes")
            )
        workspace = self._focused_workspace()
        if workspace is not None:
            ws_id = str(workspace.get("id"))
            choices.append(
                FanoutChoice(
                    "current workspace",
                    f"workspace:{ws_id}",
                    f"{workspace.get('label', 'ws')} · {len(self._workspace_panes(workspace))} panes",
                )
            )
        all_panes = self._all_panes()
        choices.append(FanoutChoice("all panes", "all", f"{len(all_panes)} panes"))
        for agent in self._agent_names():
            choices.append(FanoutChoice(f"agent:{agent}", f"agent:{agent}", "matching agent panes"))
        deduped: list[FanoutChoice] = []
        seen: set[str] = set()
        for choice in choices:
            if choice.selector in seen:
                continue
            seen.add(choice.selector)
            deduped.append(choice)
        return deduped

    _PALETTE_ACTIONS = [
        ("New tab", "new_tab"),
        ("Split pane right", "split_sbs"),
        ("Split pane down", "split_stack"),
        ("Zoom pane", "zoom"),
        ("Resize mode", "resize"),
        ("Copy mode", "copy_mode"),
        ("Copy pane output", "copy_output"),
        ("Close pane", "close_pane"),
        ("Rename pane", "rename_pane"),
        ("Close tab", "close_tab"),
        ("Rename tab", "rename_tab"),
        ("Move tab left", "move_tab_left"),
        ("Move tab right", "move_tab_right"),
        ("Next tab", "next_tab"),
        ("Previous tab", "prev_tab"),
        ("New workspace…", "new_workspace"),
        ("Worktrees…", "worktrees"),
        ("Move workspace up", "move_workspace_up"),
        ("Move workspace down", "move_workspace_down"),
        ("New terminal (pick shell)…", "open_shell_picker"),
        ("Change theme…", "settings"),
        ("Jump to pane…", "goto"),
        ("Pane menu…", "pane_menu"),
        ("Resource monitor (CPU/RAM)…", "resource_monitor"),
        ("Workflow graph + log…", "workflow_view"),
        ("Command fan-out…", "fanout"),
        ("Toggle sidebar", "toggle_sidebar"),
        ("Keybindings help", "help"),
        ("Detach (keep panes running)", "detach"),
        ("Quit", "quit"),
    ]

    def _palette_entries(self) -> list[tuple[str, str, bool]]:
        entries: list[tuple[str, str, bool]] = [(label, action, False) for label, action in self._PALETTE_ACTIONS]
        for command in self._commands.values():
            entries.append((f"Run: {command}", command, True))
        return entries

    def _open_command_palette(self) -> None:
        self.push_screen(CommandPaletteScreen(self._palette_entries()))

    def run_palette_entry(self, value: str, is_command: bool) -> None:
        if is_command:
            self.run_worker(self._new_tab_with_shell(value), exclusive=True)
        else:
            self._run_named_action(value)

    def _open_copy_mode(self, pane_id: str | None) -> None:
        """Open a modal scrollback selector for a pane."""
        if not pane_id:
            return
        try:
            text = self._client.pane_read(pane_id, lines=2000)
        except Exception:
            return
        lines = text.splitlines() or [""]
        self.push_screen(CopyModeScreen(self._pane_label_map().get(pane_id, pane_id), lines, self._palette))

    def _open_pane_menu(self) -> None:
        """A selectable pop-up of actions for the focused pane (ctrl+b m)."""
        if not self._pane_id:
            return
        pane_id = self._pane_id
        self.push_screen(
            ContextMenuScreen(
                "pane",
                [
                    ("split right", "new_pane", pane_id),
                    ("split down", "split_down", pane_id),
                    ("zoom", "zoom", None),
                    ("scroll up", "pane_scroll_up", pane_id),
                    ("scroll down", "pane_scroll_down", pane_id),
                    ("copy mode", "copy_mode", pane_id),
                    ("copy output", "copy_output", pane_id),
                    ("resource usage", "pane_stats", pane_id),
                    ("close pane", "close_pane", pane_id),
                    ("rename", "rename_pane", pane_id),
                ],
            )
        )

    def _remember_ratio(self, path: tuple[bool, ...], ratio: float) -> None:
        """Record a split-ratio change during a divider drag (persisted on release)."""
        base = self._pending_layout or (self._focused_tab() or {}).get("layout") or {}
        if not base:
            return
        try:
            layout = TileLayout.from_dict(base)
        except (KeyError, ValueError, TypeError):
            return
        layout.set_ratio_at(path, ratio)
        self._pending_layout = layout.to_dict()

    def persist_layout(self) -> None:
        """Persist a drag-resized layout to the server, then re-render."""
        if not self._pending_layout:
            return
        try:
            self._client.set_layout(self._pending_layout)
        except Exception:
            pass
        self._pending_layout = None
        self.run_worker(self.reload(), exclusive=True)

    def jump_to(self, target: str) -> None:
        """Switch focus to ``ws_id|tab_id|pane_id`` (from the navigator)."""
        parts = target.split("|")
        if len(parts) != 3:
            return
        self._workspace_id, self._tab_id, self._pane_id = parts
        self.run_worker(self.reload(), exclusive=True)

    def _open_new_workspace(self) -> None:
        """Browse for a directory, then open a new workspace rooted there."""
        self.push_screen(
            DirPickerScreen(
                self._workspace_picker_start(),
                self._create_workspace_at,
                quick_paths=self._workspace_picker_quick_paths(),
                search_roots=self._workspace_picker_search_roots(),
                search_max_depth=self._config.workspace.search_max_depth,
                search_max_results=self._config.workspace.search_max_results,
                search_ignore_names=self._config.workspace.search_ignore,
                search_include_hidden=self._config.workspace.search_include_hidden,
                search_cache_ttl_seconds=self._config.workspace.search_cache_ttl_seconds,
                search_metadata_cache_path=default_workspace_search_cache_path(),
            )
        )

    def _open_worktrees(self) -> None:
        """Open the worktree manager modal."""
        self.push_screen(WorktreeScreen(self._client, self._worktree_changed))

    def _worktree_changed(self, _changed: bool = True) -> None:
        self._workspace_id = None
        self._tab_id = None
        self._pane_id = None
        self.run_worker(self.reload(), exclusive=True)

    def _workspace_picker_start(self) -> str:
        workspace = self._focused_workspace()
        cwd = str(workspace.get("cwd") or "") if workspace else ""
        if cwd and os.path.isdir(os.path.expanduser(cwd)):
            return os.path.abspath(os.path.expanduser(cwd))
        return os.getcwd()

    def _workspace_picker_quick_paths(self) -> list[tuple[str, str]]:
        start = self._workspace_picker_start()
        paths = [("current workspace", start)]
        repo_root = _git_root(start)
        if repo_root:
            paths.append(("repo root", repo_root))
        for recent in load_workspace_recents():
            paths.append((f"recent: {recent['label']}", str(recent["path"])))
        paths.append(("process cwd", os.getcwd()))
        paths.append(("home", os.path.expanduser("~")))
        return paths

    def _workspace_picker_search_roots(self) -> list[SearchRoot]:
        roots: list[SearchRoot] = []
        start = self._workspace_picker_start()
        roots.append(SearchRoot(start, label="current workspace", source="current"))
        configured = self._config.workspace.search_roots
        if configured:
            for raw_path in configured:
                path = self._expand_config_path(raw_path)
                if path:
                    roots.append(SearchRoot(path, label=self._search_root_label(path), source="configured"))
        else:
            home = os.path.expanduser("~")
            for name in ("github", "code", "src", "work"):
                candidate = os.path.join(home, name)
                if os.path.isdir(candidate):
                    roots.append(SearchRoot(candidate, label=name, source="configured"))
        repo_root = _git_root(start)
        if repo_root:
            roots.append(SearchRoot(repo_root, label="repo root", source="repo"))
        for recent in load_workspace_recents(include_stale=True):
            roots.append(SearchRoot(str(recent["path"]), label=str(recent["label"]), source="recent"))
        return self._dedupe_search_roots(roots)

    @staticmethod
    def _expand_config_path(path: str) -> str:
        expanded = os.path.expandvars(os.path.expanduser(path.strip()))
        return os.path.abspath(expanded) if expanded else ""

    @staticmethod
    def _search_root_label(path: str) -> str:
        return os.path.basename(os.path.normpath(path)) or path

    @staticmethod
    def _dedupe_search_roots(roots: list[SearchRoot]) -> list[SearchRoot]:
        deduped: list[SearchRoot] = []
        seen: set[str] = set()
        for root in roots:
            path = os.path.abspath(os.path.expanduser(root.path))
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(SearchRoot(path, label=root.label, source=root.source))
        return deduped

    def _create_workspace_at(self, path: str) -> None:
        target = os.path.expanduser(path.strip())
        if not target:
            return
        label = os.path.basename(os.path.normpath(target)) or "workspace"
        try:
            self._client.create_workspace(label, target)
        except Exception:
            return
        self._workspace_id = None
        self.run_worker(self.reload(), exclusive=True)

    def _open_rename_workspace(self, workspace_id: str) -> None:
        workspace = next((w for w in self._workspaces() if w.get("id") == workspace_id), None)
        current = str(workspace.get("label", "")) if workspace else ""
        self.push_screen(
            RenameScreen("rename workspace", current, lambda value: self._rename_workspace(workspace_id, value))
        )

    def _rename_workspace(self, workspace_id: str, value: str) -> None:
        if not value.strip():
            return
        try:
            self._client.rename_workspace(workspace_id, value.strip())
        except Exception:
            return
        self.run_worker(self.reload(), exclusive=True)

    def _open_rename_tab(self, tab_id: str | None) -> None:
        if not tab_id:
            return
        tab = next((item for item in self._focused_tabs() if item.get("id") == tab_id), None)
        current = str(tab.get("label", "")) if tab else ""
        self.push_screen(RenameScreen("rename tab", current, lambda value: self._rename_tab(str(tab_id), value)))

    def _rename_tab(self, tab_id: str, value: str) -> None:
        try:
            self._client.rename_tab(tab_id, value)
        except Exception:
            return
        self.run_worker(self.reload(), exclusive=True)

    def _open_rename_pane(self, pane_id: str | None) -> None:
        if not pane_id:
            return
        pane = self._pane_by_id(pane_id)
        current = str(pane.get("title", "")) if pane else ""
        self.push_screen(RenameScreen("rename pane", current, lambda value: self._rename_pane(str(pane_id), value)))

    def _rename_pane(self, pane_id: str, value: str) -> None:
        rename = getattr(self._client, "rename_pane", None)
        if not callable(rename):
            return
        try:
            rename(pane_id, value)
        except Exception:
            return
        self.run_worker(self.reload(), exclusive=True)

    def apply_theme(self, name: str) -> None:
        """Switch the live theme (re-resolves the $ph-* CSS variables)."""
        palette = BUILTIN_THEMES.get(name.strip().lower())
        if palette is None:
            return
        self._palette = palette
        self._theme_name = name.strip().lower()
        try:
            self.refresh_css()
        except Exception:
            pass
        self.run_worker(self.reload(), exclusive=True)

    def apply_accent(self, hex_color: str) -> None:
        """Override the accent colour of the current palette, live."""
        try:
            self._palette = self._palette.model_copy(update={"accent": hex_color})
        except Exception:
            return
        try:
            self.refresh_css()
        except Exception:
            pass
        self.run_worker(self.reload(), exclusive=True)

    # ----- state helpers -----
    def _workspaces(self) -> list[dict]:
        return self._state.get("workspaces", [])

    def _focused_workspace(self) -> dict | None:
        workspaces = self._workspaces()
        for workspace in workspaces:
            if workspace.get("id") == self._workspace_id:
                return workspace
        return workspaces[0] if workspaces else None

    def _focused_tabs(self) -> list[dict]:
        workspace = self._focused_workspace()
        return workspace.get("tabs", []) if workspace else []

    def _focused_tab(self) -> dict | None:
        tabs = self._focused_tabs()
        for tab in tabs:
            if tab.get("id") == self._tab_id:
                return tab
        return tabs[0] if tabs else None

    def _focused_panes(self) -> list[dict]:
        tab = self._focused_tab()
        return tab.get("panes", []) if tab else []

    def _visible_pane_ids(self) -> list[str]:
        return [view.pane_id for view in self.query(PaneView)]

    def _pane_by_id(self, pane_id: str | None) -> dict[str, Any] | None:
        if not pane_id:
            return None
        for workspace in self._workspaces():
            for tab in workspace.get("tabs", []):
                for pane in tab.get("panes", []):
                    if isinstance(pane, dict) and str(pane.get("id")) == pane_id:
                        return pane
        return None

    def _pane_detail(self, pane: dict[str, Any]) -> str:
        pane_id = str(pane.get("id", ""))
        for workspace in self._workspaces():
            for tab in workspace.get("tabs", []):
                for candidate in tab.get("panes", []):
                    if isinstance(candidate, dict) and str(candidate.get("id", "")) == pane_id:
                        return (
                            f"{workspace.get('label', 'ws')} · {tab.get('label', 'tab')} · "
                            f"{pane.get('title', pane.get('id', 'pane'))}"
                        )
        return str(pane.get("title", pane.get("id", "pane")))

    def _agent_names(self) -> list[str]:
        names = {
            str(pane.get("agent")).strip()
            for pane in self._all_panes()
            if str(pane.get("agent", "")).strip()
        }
        return sorted(names, key=str.lower)

    def _cycle_tab(self, delta: int) -> None:
        tabs = self._focused_tabs()
        if not tabs:
            return
        ids = [tab["id"] for tab in tabs]
        index = ids.index(self._tab_id) if self._tab_id in ids else 0
        self._switch_tab((index + delta) % len(ids))

    def _switch_tab(self, index: int) -> None:
        tabs = self._focused_tabs()
        if 0 <= index < len(tabs):
            self._tab_id = tabs[index]["id"]
            self._focus_tab_on_server(self._tab_id)
            self._pane_id = None
            self.run_worker(self.reload(), exclusive=True)

    def _focus_tab_on_server(self, tab_id: str) -> None:
        """Keep the server's focused tab in sync so split/close target it."""
        try:
            self._client.focus_tab(tab_id)
        except Exception:
            pass

    def _cycle_pane(self, delta: int) -> None:
        panes = self._focused_panes()
        if not panes:
            return
        ids = [pane["id"] for pane in panes]
        index = ids.index(self._pane_id) if self._pane_id in ids else 0
        self._pane_id = ids[(index + delta) % len(ids)]
        self._mark_active_pane()

    _NAV = {
        "focus_left": NavDirection.LEFT,
        "focus_down": NavDirection.DOWN,
        "focus_up": NavDirection.UP,
        "focus_right": NavDirection.RIGHT,
    }

    def _focus_direction(self, action: str) -> None:
        """Move focus to the geometric neighbour pane in the split tree."""
        if not self._pane_id:
            return
        layout_data = (self._focused_tab() or {}).get("layout") or {}
        if not layout_data:
            return
        try:
            layout = TileLayout.from_dict(layout_data)
        except (KeyError, ValueError, TypeError):
            return
        if not layout.contains(self._pane_id):
            return
        layout.focus = self._pane_id
        region = self.query_one("#panes", Horizontal).size
        neighbour = layout.find_in_direction(self._NAV[action], Rect(0, 0, region.width, region.height))
        if neighbour:
            self._pane_id = neighbour
            self._mark_active_pane()
            self._refresh_statusbar()

    _RESIZE_NAV = {
        "h": NavDirection.LEFT,
        "l": NavDirection.RIGHT,
        "j": NavDirection.DOWN,
        "k": NavDirection.UP,
        "left": NavDirection.LEFT,
        "right": NavDirection.RIGHT,
        "down": NavDirection.DOWN,
        "up": NavDirection.UP,
    }

    def _handle_resize_key(self, key: str) -> None:
        if key in ("escape", "enter", "q", "ctrl+b"):
            self._resize = False
            self._refresh_hint()
            return
        nav = self._RESIZE_NAV.get(key)
        if nav is not None:
            self._resize_focused(nav)

    def _resize_focused(self, nav: NavDirection) -> None:
        """Adjust the focused pane's adjacent split ratio and persist it."""
        if not self._pane_id:
            return
        layout_data = (self._focused_tab() or {}).get("layout") or {}
        if not layout_data:
            return
        try:
            layout = TileLayout.from_dict(layout_data)
        except (KeyError, ValueError, TypeError):
            return
        if not layout.contains(self._pane_id):
            return
        layout.focus = self._pane_id
        region = self.query_one("#panes", Horizontal).size
        if not layout.resize_focused(nav, 0.05, Rect(0, 0, region.width, region.height)):
            return
        try:
            self._client.set_layout(layout.to_dict())
        except Exception:
            return
        self.run_worker(self.reload(), exclusive=True)

    def _cycle_workspace(self, delta: int) -> None:
        workspaces = self._workspaces()
        if not workspaces:
            return
        ids = [workspace["id"] for workspace in workspaces]
        current = self._workspace_id if self._workspace_id in ids else ids[0]
        self._workspace_id = ids[(ids.index(current) + delta) % len(ids)]
        self._focus_workspace_on_server(self._workspace_id)
        self._tab_id = None
        self._pane_id = None
        self.run_worker(self.reload(), exclusive=True)

    def _focus_workspace_on_server(self, workspace_id: str) -> None:
        """Keep the server's focused workspace in sync so scoped ops are correct."""
        try:
            self._client.focus_workspace(workspace_id)
        except Exception:
            pass

    # ----- rendering -----
    async def reload(self) -> None:
        """Fetch state and rebuild the tab bar, sidebar, and pane views."""
        try:
            self._state = self._client.state()
        except Exception:
            return
        if not self._workspaces():
            # Self-heal: never strand the user on an empty session (e.g. after
            # closing the last workspace). Seed one default workspace + tab.
            if not self._seeding:
                self._seeding = True
                try:
                    self._client.create_workspace("main", os.getcwd())
                    self._client.create_tab()
                    self._state = self._client.state()
                except Exception:
                    pass
        else:
            self._seeding = False
        workspace = self._focused_workspace()
        self._workspace_id = workspace.get("id") if workspace else None
        tab = self._focused_tab()
        self._tab_id = tab.get("id") if tab else None
        panes = self._focused_panes()
        if self._pane_id not in {pane["id"] for pane in panes}:
            self._pane_id = panes[0]["id"] if panes else None

        self._ensure_shells()
        self._branches = {str(ws.get("id")): _git_branch(str(ws.get("cwd", ""))) for ws in self._workspaces()}
        self._ahead_behind = {
            ws_id: _git_ahead_behind(str(ws.get("cwd", "")))
            for ws in self._workspaces()
            if (ws_id := str(ws.get("id"))) and self._branches.get(ws_id)
        }
        try:
            await self._refresh_tabbar()
            await self._refresh_sidebar()
            await self._rebuild_panes()
            self._refresh_statusbar()
        except Exception:
            return  # the screen may be tearing down (a reload worker can outlive the DOM)

    async def _reload_focus_last_tab(self) -> None:
        """Reload, then switch focus to the newly created (last) tab."""
        await self.reload()
        tabs = self._focused_tabs()
        if tabs:
            self._tab_id = tabs[-1]["id"]
            self._pane_id = None
            await self.reload()

    async def _reload_focus_last_pane(self) -> None:
        """Reload, then focus the newly created (last) pane in the tab."""
        await self.reload()
        panes = self._focused_panes()
        if panes:
            self._pane_id = panes[-1]["id"]
            self._mark_active_pane()
            self._refresh_statusbar()

    async def _new_tab_with_shell(self, shell: str) -> None:
        """Create a tab and run the chosen shell in its pane, then focus it."""
        response = self._client.create_tab()
        pane_id = None
        if isinstance(response, dict):
            pane_id = response.get("result", {}).get("tab", {}).get("focused_pane_id")
        # Start the chosen shell *before* reload, so _ensure_shells sees it
        # running and does not override it with the default shell.
        if pane_id:
            try:
                self._client.start_pane(str(pane_id), shell)
            except Exception:
                pane_id = None
        await self.reload()
        tabs = self._focused_tabs()
        if tabs:
            self._tab_id = tabs[-1]["id"]
            self._pane_id = None
            await self.reload()

    async def _rebuild_panes(self) -> None:
        container = self.query_one("#panes", Horizontal)
        await container.remove_children()
        panes = {str(pane["id"]): pane for pane in self._focused_panes()}
        self._terminal_sizes = {pane_id: size for pane_id, size in self._terminal_sizes.items() if pane_id in panes}
        if not panes:
            return
        if self._zoom and self._pane_id and self._pane_id in panes:
            await container.mount(self._pane_view(self._pane_id, panes))
            self._mark_active_pane()
            self._update_pane_contents()
            self.call_after_refresh(self._update_pane_contents)
            return
        tab = self._focused_tab() or {}
        widget = self._layout_widget(tab.get("layout") or {}, panes)
        if widget is not None:
            await container.mount(widget)
        else:  # fallback: flat side-by-side row if the layout is missing/out-of-sync
            await container.mount(*[self._pane_view(pid, panes) for pid in panes])
        self._mark_active_pane()
        self._update_pane_contents()
        self.call_after_refresh(self._update_pane_contents)

    def _pane_view(self, pane_id: str, panes: dict[str, dict]) -> PaneView:
        pane = panes.get(pane_id, {})
        host = str(pane.get("remote_host") or "")
        title = f"{host}:{pane.get('title', 'pane')}" if host else str(pane.get("title", "pane"))
        return PaneView(pane_id, f"{title} · {pane.get('status', '?')}")

    def _layout_widget(self, layout_data: dict, panes: dict[str, dict]) -> Widget | None:
        if not layout_data:
            return None
        try:
            layout = TileLayout.from_dict(layout_data)
        except (KeyError, ValueError, TypeError):
            return None
        if set(layout.pane_ids()) != set(panes):
            return None
        return self._build_node_widget(layout.root, panes)

    def _build_node_widget(self, node: object, panes: dict[str, dict], path: tuple[bool, ...] = ()) -> Widget:
        if isinstance(node, PaneNode):
            return self._pane_view(node.pane_id, panes)
        first = self._build_node_widget(node.first, panes, path + (False,))  # type: ignore[attr-defined]
        second = self._build_node_widget(node.second, panes, path + (True,))  # type: ignore[attr-defined]
        ratio = max(1, min(99, round(node.ratio * 100)))  # type: ignore[attr-defined]
        direction = node.direction  # type: ignore[attr-defined]
        divider = SplitDivider(direction, path)
        if direction == Direction.HORIZONTAL:
            first.styles.width = f"{ratio}fr"
            first.styles.height = "1fr"
            second.styles.width = f"{100 - ratio}fr"
            second.styles.height = "1fr"
            box: Widget = Horizontal(first, divider, second)
        else:
            first.styles.height = f"{ratio}fr"
            first.styles.width = "1fr"
            second.styles.height = f"{100 - ratio}fr"
            second.styles.width = "1fr"
            box = Vertical(first, divider, second)
        box.styles.width = "1fr"
        box.styles.height = "1fr"
        return box

    async def _split(self, direction: str, pane_id: str | None = None) -> None:
        try:
            response = self._client.split_pane(direction, pane_id)
        except Exception:
            return
        new_id = None
        if isinstance(response, dict):
            pane = response.get("result", {}).get("pane", {})
            new_id = pane.get("pane_id") or pane.get("id")
        await self.reload()
        if new_id and new_id in {str(pane["id"]) for pane in self._focused_panes()}:
            self._pane_id = new_id
            self._mark_active_pane()
            self._refresh_statusbar()

    def _mark_active_pane(self) -> None:
        for view in self.query(PaneView):
            view.set_class(view.pane_id == self._pane_id, "active")

    async def _refresh_tabbar(self) -> None:
        bar = self.query_one("#tabbar", Horizontal)
        await bar.remove_children()
        strip = HorizontalScroll(id="tabstrip")
        widgets: list[Static] = []
        workspace = self._focused_workspace()
        if workspace:
            widgets.append(Static(Text(f" {workspace.get('label', 'ws')} │"), classes="wsname"))
        tabs = self._focused_tabs()
        for index, tab in enumerate(tabs, start=1):
            tab_id = str(tab.get("id"))
            active = tab_id == self._tab_id
            rollup = _rollup([str(pane.get("status", "unknown")) for pane in tab.get("panes", [])])
            glyph, color = self._dot(rollup)
            label = Text()
            label.append(f" {glyph} ", style=color)
            label.append(f"{index}:{tab.get('label', 'tab')} ")
            classes = "tabcell active" if active else "tabcell"
            widgets.append(
                Clickable(
                    label,
                    "switch_tab",
                    tab_id,
                    dbl_action="rename_tab",
                    ctx_action="ctx_tab",
                    id=f"tabcell-{tab_id}",
                    classes=classes,
                )
            )
            if len(tabs) > 1:  # never offer to close the last tab
                widgets.append(Clickable("✕ ", "close_tab", tab_id, id=f"tabclose-{tab_id}", classes="tabclose"))
        await bar.mount(
            Clickable("‹", "tab_scroll_left", id="tabscroll-left", classes="tabscroll"),
            strip,
            Clickable("›", "tab_scroll_right", id="tabscroll-right", classes="tabscroll"),
            Clickable(" + ", "new_tab", id="tabplus", classes="tabplus"),
        )
        await strip.mount(*widgets)
        # When tabs overflow the width, keep the active one (and the +) in view.
        active_cell = next((w for w in widgets if getattr(w, "id", "") == f"tabcell-{self._tab_id}"), None)
        if active_cell is not None:
            self.call_after_refresh(active_cell.scroll_visible, animate=False)

    async def _refresh_sidebar(self) -> None:
        nav = self.query_one("#nav", Vertical)
        await nav.remove_children()
        nav.set_class(self._sidebar_compact, "compact")
        if self._sidebar_compact:
            await nav.mount(*self._compact_sidebar_widgets())
            return
        workspaces = self._workspaces()
        widgets: list[Widget] = [
            Horizontal(
                Static("pyherdr", classes="navtitle"),
                Clickable("◄", "toggle_sidebar", id="sidebar-toggle", classes="navtoggle"),
                classes="navhead",
            ),
            Static(self._attention_text(), id="attention", classes="attention"),
            Static(self._spaces_header_text(workspaces), classes="navsectionhead"),
        ]
        for index, workspace in enumerate(workspaces, start=1):
            ws_id = str(workspace.get("id"))
            active = ws_id == self._workspace_id
            widgets.append(
                Clickable(
                    self._workspace_row_text(index, workspace, active),
                    "switch_workspace",
                    ws_id,
                    ctx_action="ctx_workspace",
                    id=f"wsrow-{ws_id}",
                    classes="wsrow active" if active else "wsrow",
                )
            )
        widgets.append(Static(self._sidebar_divider_text(), classes="sidebar-divider"))
        widgets.append(Clickable(self._agents_text(), "toggle_agent_scope", id="agents", classes="agents"))
        widgets.append(
            Horizontal(
                Clickable("+ workspace", "new_workspace", id="newws", classes="sidebar-action"),
                Clickable("+ terminal ▾", "open_shell_picker", id="newterm", classes="sidebar-action"),
                Clickable("menu ⋯", "palette", id="sidebarmenu", classes="sidebar-action"),
                classes="sidebar-footer",
            )
        )
        await nav.mount(*widgets)

    def _compact_sidebar_widgets(self) -> list[Widget]:
        widgets: list[Widget] = [
            Clickable("►", "toggle_sidebar", id="sidebar-toggle", classes="navtoggle"),
            Static(self._compact_attention_text(), id="attention", classes="compact-attention"),
        ]
        for index, workspace in enumerate(self._workspaces(), start=1):
            ws_id = str(workspace.get("id"))
            active = ws_id == self._workspace_id
            widgets.append(
                Clickable(
                    self._compact_workspace_row_text(index, workspace, active),
                    "switch_workspace",
                    ws_id,
                    ctx_action="ctx_workspace",
                    id=f"wsrow-{ws_id}",
                    classes="wscompact active" if active else "wscompact",
                )
            )
        widgets.append(Static(self._compact_agents_text(), id="compact-agents", classes="compact-agents"))
        return widgets

    @staticmethod
    def _workspace_panes(workspace: dict[str, Any]) -> list[dict[str, Any]]:
        panes: list[dict[str, Any]] = []
        for tab in workspace.get("tabs", []):
            if not isinstance(tab, dict):
                continue
            for pane in tab.get("panes", []):
                if isinstance(pane, dict):
                    panes.append(pane)
        return panes

    def _all_panes(self) -> list[dict[str, Any]]:
        panes: list[dict[str, Any]] = []
        for workspace in self._workspaces():
            panes.extend(self._workspace_panes(workspace))
        return panes

    @staticmethod
    def _status_counts(panes: list[dict[str, Any]]) -> dict[str, int]:
        counts = {status: 0 for status in _STATUS_PRIORITY}
        for pane in panes:
            status = str(pane.get("status", "unknown"))
            if status not in counts:
                status = "unknown"
            counts[status] += 1
        return counts

    def _spaces_header_text(self, workspaces: list[dict[str, Any]]) -> Text:
        text = Text("spaces", style=self._palette.subtext0)
        text.append(f" {len(workspaces)}", style=self._palette.overlay0)
        return text

    def _sidebar_divider_text(self) -> Text:
        text = Text("──────────────", style=self._palette.overlay0)
        text.append(" drag", style=self._palette.overlay0)
        return text

    def _sidebar_footer_text(self) -> Text:
        text = Text("+ workspace", style=self._palette.blue)
        text.append("  + terminal ▾", style=self._palette.blue)
        text.append("  menu ⋯", style=self._palette.accent)
        return text

    def _append_status_count(self, text: Text, label: str, count: int, color: str) -> None:
        if count:
            text.append(f"{label} {count}", style=color)
            text.append("  ", style=self._palette.overlay0)

    def _attention_text(self) -> Text:
        panes = self._all_panes()
        counts = self._status_counts(panes)
        text = Text()
        if any(counts[status] for status in ("blocked", "working", "done")):
            if counts["blocked"]:
                text.append("● ", style=self._palette.red)
                self._append_status_count(text, "blocked", counts["blocked"], self._palette.red)
            if counts["working"]:
                text.append("● ", style=self._palette.yellow)
                self._append_status_count(text, "working", counts["working"], self._palette.yellow)
            if counts["done"]:
                text.append("✓ ", style=self._palette.green)
                self._append_status_count(text, "done", counts["done"], self._palette.green)
        else:
            text.append("· ", style=self._palette.overlay0)
            text.append("all quiet", style=self._palette.green)
        return text

    def _compact_attention_text(self) -> Text:
        counts = self._status_counts(self._all_panes())
        active_count = counts["blocked"] or counts["working"] or counts["done"]
        if counts["blocked"]:
            status = "blocked"
        elif counts["working"]:
            status = "working"
        elif counts["done"]:
            status = "done"
        else:
            status = "idle"
        glyph, color = self._dot(status)
        text = Text()
        text.append(glyph, style=color)
        text.append("\n")
        text.append(str(active_count), style=color if active_count else self._palette.overlay0)
        return text

    def _workspace_row_text(self, index: int, workspace: dict[str, Any], active: bool) -> Text:
        ws_id = str(workspace.get("id"))
        panes = self._workspace_panes(workspace)
        counts = self._status_counts(panes)
        glyph, color = self._dot(_rollup([str(pane.get("status", "unknown")) for pane in panes]))
        branch = self._branches.get(ws_id, "")
        tabs = workspace.get("tabs", [])
        tab_count = len(tabs) if isinstance(tabs, list) else 0
        row = Text()
        row.append("▌" if active else " ", style=self._palette.accent if active else self._palette.overlay0)
        row.append(f" {index}  ", style=self._palette.overlay0)
        row.append(f"{glyph} ", style=color)
        label_style = f"bold {self._palette.accent}" if active else self._palette.text
        row.append(str(workspace.get("label", "ws")), style=label_style)
        row.append("\n   ", style=self._palette.overlay0)
        if branch:
            row.append(branch, style=self._palette.overlay0)
        else:
            cwd = str(workspace.get("cwd", ".")).replace("\\", "/")
            row.append(cwd[-14:], style=self._palette.overlay0)
        ahead, behind = self._ahead_behind.get(ws_id, (0, 0))
        if ahead:
            row.append(f" ↑{ahead}", style=self._palette.green)
        if behind:
            row.append(f" ↓{behind}", style=self._palette.red)
        row.append(f"   {tab_count} {'tab' if tab_count == 1 else 'tabs'}", style=self._palette.overlay0)
        row.append("   ", style=self._palette.overlay0)
        if counts["blocked"]:
            row.append(f"blocked {counts['blocked']}", style=self._palette.red)
        elif counts["working"]:
            row.append(f"working {counts['working']}", style=self._palette.yellow)
        elif counts["done"]:
            row.append(f"done {counts['done']}", style=self._palette.green)
        elif counts["idle"]:
            row.append(f"idle {counts['idle']}", style=self._palette.overlay0)
        else:
            row.append("empty", style=self._palette.overlay0)
        return row

    def _compact_workspace_row_text(self, index: int, workspace: dict[str, Any], active: bool) -> Text:
        panes = self._workspace_panes(workspace)
        glyph, color = self._dot(_rollup([str(pane.get("status", "unknown")) for pane in panes]))
        text = Text()
        text.append("▌" if active else " ", style=self._palette.accent if active else self._palette.overlay0)
        text.append(str(index), style=f"bold {self._palette.accent}" if active else self._palette.subtext0)
        text.append(glyph, style=color)
        return text

    def _workflow_text(self) -> Text:
        text = Text("workflow", style=self._palette.subtext0)
        text.append("\n◎ calls", style=self._palette.blue)
        text.append("  logs", style=self._palette.teal)
        text.append("  graph", style=self._palette.accent)
        text.append("\n✓ validate every run", style=self._palette.green)
        return text

    def _agent_entries(self) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
        entries: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for workspace in self._workspaces():
            if self._agent_panel_scope == AgentPanelScope.CURRENT and workspace.get("id") != self._workspace_id:
                continue
            for tab in workspace.get("tabs", []):
                if not isinstance(tab, dict):
                    continue
                for pane in tab.get("panes", []):
                    if isinstance(pane, dict) and pane.get("agent"):
                        entries.append((workspace, tab, pane))
        return entries

    def _toggle_agent_scope(self) -> None:
        self._agent_panel_scope = (
            AgentPanelScope.ALL if self._agent_panel_scope == AgentPanelScope.CURRENT else AgentPanelScope.CURRENT
        )
        self.run_worker(self._refresh_sidebar(), exclusive=True)

    def _agents_text(self) -> Text:
        """The 'agents' sidebar section; working agents show an animated spinner."""
        entries = self._agent_entries()
        text = Text("agents", style=self._palette.subtext0)
        text.append(f" {self._agent_panel_scope.value}", style=self._palette.accent)
        frame = _SPINNER[self._spin % len(_SPINNER)]
        if not entries:
            text.append("\n· none", style=self._palette.overlay0)
            return text
        for workspace, _tab, pane in entries:
            status = str(pane.get("status", "unknown"))
            if status == "working":
                glyph, color = frame, self._palette.yellow
            else:
                glyph, color = self._dot(status)
            workspace_label = str(workspace.get("label", "ws"))
            pane_label = str(pane.get("title", "pane"))
            agent_label = str(pane.get("agent", "agent"))
            text.append("\n")
            text.append(f"{glyph} ", style=color)
            text.append(f"{workspace_label} · {pane_label}", style=self._palette.text)
            text.append("\n  ")
            text.append(status, style=color)
            text.append(f" · {agent_label}", style=self._palette.overlay0)
        return text

    def _compact_agents_text(self) -> Text:
        panes = [pane for pane in self._all_panes() if pane.get("agent")]
        working = sum(1 for pane in panes if str(pane.get("status", "unknown")) == "working")
        blocked = sum(1 for pane in panes if str(pane.get("status", "unknown")) == "blocked")
        status = "blocked" if blocked else ("working" if working else ("idle" if panes else "unknown"))
        if status == "working":
            glyph, color = _SPINNER[self._spin % len(_SPINNER)], self._palette.yellow
        else:
            glyph, color = self._dot(status)
        text = Text()
        text.append(glyph, style=color)
        text.append("\n")
        text.append(str(len(panes)), style=self._palette.subtext0)
        return text

    def _has_working_agent(self) -> bool:
        return any(
            pane.get("agent") and str(pane.get("status")) == "working"
            for workspace in self._workspaces()
            for tab in workspace.get("tabs", [])
            for pane in tab.get("panes", [])
        )

    def _refresh_statusbar(self) -> None:
        workspace = self._focused_workspace()
        bar = Text()
        if workspace:
            bar.append(str(workspace.get("cwd", "")).replace("\\", "/"), style=self._palette.accent)
            branch = self._branches.get(str(workspace.get("id", "")), "")
            if branch:
                bar.append(f"  ⎇ {branch}", style=self._palette.green)
            bar.append("  ")
        mode = "RESIZE" if self._resize else ("PREFIX" if self._prefix else "TERMINAL")
        bar.append(mode, style=f"bold {self._palette.overlay0}")
        if self._resize:
            bar.append("  h/l width · j/k height · esc done", style=self._palette.subtext0)
        elif self._prefix:
            bar.append("  next key = action · ? = help", style=self._palette.subtext0)
        if self._pane_id:
            bar.append("  ")
            bar.append(str(self._pane_id), style=self._palette.blue)
        bar.append("   ● ", style=self._palette.accent)
        bar.append(self._theme_name, style=self._palette.subtext0)
        self.query_one("#statusbar", Static).update(bar)

    def _refresh_hint(self) -> None:
        # The bottom action bar is clickable buttons now; transient prefix/resize
        # guidance lives in the status bar's mode indicator.
        self._refresh_statusbar()

    def _ensure_shells(self) -> None:
        """Revive any pane without a live session, like herdr.

        After a server restart, panes persist in state but their PTY sessions do
        not. A non-running pane that hosts an agent is **resumed** by re-running
        its command (honouring ``session.resume_agents_on_restore``); any other
        non-running pane is (re)started as a shell so it is always typeable.
        Live panes are left untouched.
        """
        shell = _default_shell()
        resume_agents = True
        try:
            resume_agents = load_config().session.resume_agents_on_restore
        except Exception:
            pass
        for pane in self._focused_panes():
            if pane.get("running"):
                continue
            command = str(pane.get("command") or "")
            if resume_agents and pane.get("agent") and command:
                target = command  # resume the agent in its pane
            else:
                target = shell
            try:
                self._client.start_pane(str(pane["id"]), target)
            except Exception:
                continue

    def _scroll_pane(self, pane_id: str, direction: str) -> None:
        try:
            self._client.pane_scroll(pane_id, direction)
        except Exception:
            return
        self._update_pane_contents({pane_id})

    def _handle_pane_wheel(self, pane_id: str, direction: str, x: int = 1, y: int = 1) -> None:
        if self._pane_owns_wheel(pane_id):
            try:
                self._client.send_text(pane_id, self._xterm_wheel_sequence(direction, x, y))
            except Exception:
                return
            return
        self._scroll_pane(pane_id, direction)

    def _pane_owns_wheel(self, pane_id: str) -> bool:
        metadata = self._terminal_metadata.get(pane_id, {})
        return bool(metadata.get("alt_screen") or metadata.get("mouse_reporting"))

    def _read_terminal_metadata(self, pane_id: str) -> dict[str, bool]:
        try:
            return self._client.pane_terminal_metadata(pane_id)
        except Exception:
            return {"alt_screen": False, "mouse_reporting": False}

    @staticmethod
    def _xterm_wheel_sequence(direction: str, x: int, y: int) -> str:
        button = 64 if direction == "up" else 65
        col = max(1, int(x))
        row = max(1, int(y))
        return f"\x1b[<{button};{col};{row}M"

    def _copy_pane_output(self, pane_id: str | None) -> None:
        """Copy a pane's text (visible + scrollback) to the system clipboard."""
        if not pane_id:
            return
        try:
            text = self._client.pane_read(pane_id, lines=2000)
        except Exception:
            return
        self.copy_to_clipboard(text)
        self.notify("copied pane output to clipboard", timeout=3)

    def _tick(self) -> None:
        self._spin += 1
        # Animate the working spinner without a full sidebar rebuild.
        if self._has_working_agent():
            self._refresh_agent_panel()
        self.run_worker(self._poll_state(), group="poll", exclusive=True)

    async def _terminal_refresh_loop(self) -> None:
        while True:
            try:
                await self._terminal_refresh_loop_step()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(1.0)

    async def _terminal_refresh_loop_step(self) -> None:
        pane_ids = self._visible_pane_ids()
        if not pane_ids:
            await asyncio.sleep(0.25)
            return
        versions = {pane_id: self._terminal_versions.get(pane_id, -1) for pane_id in pane_ids}
        try:
            result = await asyncio.to_thread(self._client.pane_wait_output, versions, 1.0)
        except AttributeError:
            await asyncio.sleep(max(0.05, self._poll_interval))
            self._update_pane_contents()
            return
        latest = result.get("versions", {})
        if isinstance(latest, dict):
            self._terminal_versions.update({str(pane_id): int(version) for pane_id, version in latest.items()})
        changed = result.get("changed", {})
        if isinstance(changed, dict) and changed:
            changed_ids = {str(pane_id) for pane_id in changed}
            self._terminal_versions.update({str(pane_id): int(version) for pane_id, version in changed.items()})
            self._update_pane_contents(changed_ids)
        elif result.get("timed_out"):
            await asyncio.sleep(max(0.25, min(self._poll_interval, 1.0)))

    async def _poll_state(self) -> None:
        try:
            self._state = self._client.state()
        except Exception:
            return
        self._emit_agent_toasts()
        self._refresh_agent_panel()

    def _refresh_agent_panel(self) -> None:
        try:
            if self._sidebar_compact:
                self.query_one("#compact-agents", Static).update(self._compact_agents_text())
            else:
                self.query_one("#agents", Static).update(self._agents_text())
        except Exception:
            pass

    def _emit_agent_toasts(self) -> None:
        """Pop a toast when a background agent becomes blocked or finishes."""
        for workspace in self._workspaces():
            for tab in workspace.get("tabs", []):
                for pane in tab.get("panes", []):
                    if not pane.get("agent"):
                        continue
                    pane_id = str(pane.get("id"))
                    status = str(pane.get("status", ""))
                    previous = self._agent_status.get(pane_id)
                    self._agent_status[pane_id] = status
                    if previous is None or previous == status or pane_id == self._pane_id:
                        continue
                    name = f"{pane.get('agent')}·{pane.get('title', 'pane')}"
                    if status == "blocked":
                        self.notify(f"{name} needs attention", severity="warning", timeout=6)
                    elif status in ("idle", "done") and previous == "working":
                        self.notify(f"{name} finished", severity="information", timeout=5)

    def _update_pane_contents(self, pane_ids: set[str] | None = None) -> None:
        for view in self.query(PaneView):
            if pane_ids is not None and view.pane_id not in pane_ids:
                continue
            try:
                self._sync_pane_terminal_size(view)
                output = self._client.pane_read(
                    view.pane_id, lines=400, styled=True, cursor=view.pane_id == self._pane_id
                )
                self._terminal_metadata[view.pane_id] = self._read_terminal_metadata(view.pane_id)
            except Exception:
                continue
            if output and output.strip():
                view.update(Text.from_ansi(output))
            else:
                view.update(Text("starting shell…", style=self._palette.overlay0))

    @staticmethod
    def _pane_terminal_size(view: PaneView) -> tuple[int, int] | None:
        width = int(view.size.width)
        height = int(view.size.height)
        if width <= 0 or height <= 0:
            return None
        # PaneView has a one-cell border and horizontal padding. The PTY should
        # match the cells available for terminal text, not the outer widget box.
        rows = max(1, height - 2)
        cols = max(1, width - 4)
        return rows, cols

    def _sync_pane_terminal_size(self, view: PaneView) -> None:
        size = self._pane_terminal_size(view)
        if size is None or self._terminal_sizes.get(view.pane_id) == size:
            return
        rows, cols = size
        self._client.pane_resize(view.pane_id, rows, cols)
        self._terminal_sizes[view.pane_id] = size

    # ----- styling helpers -----
    def _dot(self, status: str) -> tuple[str, str]:
        glyph = _STATUS_GLYPH.get(status, "·")
        color = {
            "blocked": self._palette.red,
            "working": self._palette.yellow,
            "done": self._palette.teal,
            "idle": self._palette.green,
        }.get(status, self._palette.overlay0)
        return glyph, color


def main() -> None:
    """Launch the Textual UI."""
    PyHerdrTui().run()
