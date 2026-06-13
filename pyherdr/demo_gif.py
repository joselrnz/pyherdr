from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .demo_screenshot import DEMO_OUTPUTS, DEMO_PICKER_ROOT, DEMO_SCREENSHOT_VIEWS, DEMO_STATE, DEMO_WORKFLOW_EVENTS

DEMO_GIF_DEFAULT_STORYBOARD = ("main", "workflow", "fanout", "workspace-search")

_BG = "#061923"
_PANEL = "#082433"
_PANEL_ALT = "#10364a"
_BORDER = "#34c9ff"
_MUTED = "#7fa7b9"
_TEXT = "#c2e8f5"
_GREEN = "#76f0a0"
_YELLOW = "#ffd65a"
_PURPLE = "#a773ff"
_RED = "#ff7f7f"


def render_demo_gif(
    path: Path,
    *,
    width: int = 960,
    height: int = 540,
    duration_ms: int = 900,
    views: Sequence[str] | None = None,
) -> Path:
    """Render a deterministic animated GIF from PyHerdr demo state."""

    if width < 420 or height < 260:
        raise ValueError("demo GIF requires at least 420x260 pixels")
    if duration_ms < 50:
        raise ValueError("demo GIF duration must be at least 50ms per frame")

    storyboard = tuple(views or DEMO_GIF_DEFAULT_STORYBOARD)
    invalid = sorted(set(storyboard) - set(DEMO_SCREENSHOT_VIEWS))
    if invalid:
        raise ValueError(f"unknown demo GIF view: {', '.join(invalid)}")

    font = ImageFont.load_default()
    frames = [_render_frame(view, width, height, font) for view in storyboard]

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        target,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
    )
    return target


def _render_frame(view: str, width: int, height: int, font: Any) -> Image.Image:
    image = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(image)
    margin = 18
    header_h = 34
    footer_h = 28
    sidebar_w = max(190, min(270, width // 4))

    _fill_rect(draw, (margin, margin, width - margin, height - margin), _BG, _BORDER)
    _text(draw, (margin + 16, margin + 10), "pyherdr demo", _BORDER, font)
    _text(draw, (width - margin - 170, margin + 10), f"view: {view}", _MUTED, font)

    content_top = margin + header_h
    content_bottom = height - margin - footer_h
    sidebar = (margin + 12, content_top, margin + sidebar_w, content_bottom)
    body = (sidebar[2] + 12, content_top, width - margin - 12, content_bottom)

    _draw_sidebar(draw, sidebar, font)
    if view == "workflow":
        _draw_workflow(draw, body, font)
    elif view == "fanout":
        _draw_fanout(draw, body, font)
    elif view.startswith("workspace"):
        _draw_workspace_search(draw, body, font, view=view)
    else:
        _draw_terminal_layout(draw, body, font)

    footer = (margin + 12, content_bottom + 8, width - margin - 12, height - margin - 8)
    _fill_rect(draw, footer, "#082c3c")
    _text(
        draw,
        (footer[0] + 10, footer[1] + 7),
        "? help   : palette   + tab   split   terminal   stats   theme",
        _MUTED,
        font,
    )
    _text(draw, (footer[2] - 230, footer[1] + 7), "scripted product state", _BORDER, font)
    return image


def _draw_sidebar(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    font: Any,
) -> None:
    _fill_rect(draw, rect, "#051721", "#4e86a0")
    x, y, x2, _ = rect
    cursor = y + 14
    _text(draw, (x + 12, cursor), "spaces 2", _MUTED, font)
    cursor += 26
    for index, workspace in enumerate(DEMO_STATE["workspaces"], start=1):
        selected = workspace["id"] == DEMO_STATE["focused_workspace_id"]
        row = (x + 10, cursor - 8, x2 - 10, cursor + 36)
        if selected:
            _fill_rect(draw, row, _PANEL_ALT)
        marker = "*" if selected else "."
        status = _workspace_status(workspace)
        _text(draw, (x + 20, cursor), f"{index} {marker} {workspace['label']}", _YELLOW if selected else _TEXT, font)
        _text(
            draw,
            (x + 36, cursor + 18),
            f"{len(workspace['tabs'])} tabs   {status}",
            _GREEN if status == "working" else _MUTED,
            font,
        )
        cursor += 54

    cursor += 8
    _text(draw, (x + 12, cursor), "agents current", _TEXT, font)
    cursor += 22
    _text(draw, (x + 20, cursor), "codex  working", _GREEN, font)
    cursor += 18
    _text(draw, (x + 20, cursor), "claude blocked", _RED, font)
    _text(draw, (x + 12, rect[3] - 28), "+ workspace  + terminal  menu ...", _BORDER, font)


def _draw_terminal_layout(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    font: Any,
) -> None:
    x, y, x2, y2 = rect
    left_w = int((x2 - x) * 0.58)
    gap = 10
    left = (x, y, x + left_w - gap, y2)
    right_top = (left[2] + gap, y, x2, y + (y2 - y) // 2 - gap // 2)
    right_bottom = (left[2] + gap, right_top[3] + gap, x2, y2)

    _draw_pane(draw, left, "pane . working", DEMO_OUTPUTS["pane-loop"], font, focused=True)
    _draw_pane(draw, right_top, "pane . done", DEMO_OUTPUTS["pane-ci"], font)
    _draw_pane(draw, right_bottom, "pane . done", DEMO_OUTPUTS["pane-tests"], font)


def _draw_workflow(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    font: Any,
) -> None:
    _fill_rect(draw, rect, _PANEL, _BORDER)
    x, y, _, _ = rect
    _text(draw, (x + 16, y + 14), "workflow audit log", _BORDER, font)
    cursor = y + 48
    for event in DEMO_WORKFLOW_EVENTS:
        status = event.status
        color = _GREEN if status == "done" else _YELLOW if status == "blocked" else _TEXT
        line = f"{event.kind}  {event.source} -> {event.target}  {event.message}"
        _text(draw, (x + 24, cursor), line, color, font)
        _text(
            draw,
            (x + 44, cursor + 18),
            f"{event.worksite}  pane={event.pane_id}  agent={event.agent}",
            _MUTED,
            font,
        )
        cursor += 50


def _draw_fanout(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    font: Any,
) -> None:
    _fill_rect(draw, rect, _PANEL, _BORDER)
    x, y, x2, _ = rect
    _text(draw, (x + 16, y + 14), "command fan-out preview", _BORDER, font)
    _text(draw, (x + 16, y + 46), "target: current workspace", _TEXT, font)
    _text(draw, (x + 16, y + 70), "command: python -m unittest discover -s tests", _YELLOW, font)
    cursor = y + 110
    for title, status in (("Codex loop", "working"), ("CI scope", "done"), ("validation", "done")):
        _fill_rect(draw, (x + 22, cursor - 8, x2 - 22, cursor + 28), "#0b3042")
        _text(draw, (x + 38, cursor), f"* {title}", _TEXT, font)
        _text(draw, (x2 - 150, cursor), status, _GREEN if status == "done" else _YELLOW, font)
        cursor += 44
    _text(
        draw,
        (x + 16, cursor + 12),
        "dry run first; send requires confirmation for risky multi-pane commands",
        _MUTED,
        font,
    )


def _draw_workspace_search(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    font: Any,
    *,
    view: str,
) -> None:
    _fill_rect(draw, rect, _PANEL, _BORDER)
    x, y, x2, _ = rect
    selected = view == "workspace-search-selected"
    stale = view == "workspace-search-stale"
    long_path = view == "workspace-search-long-path"
    _text(draw, (x + 16, y + 14), "workspace search mode", _BORDER, font)
    _text(draw, (x + 16, y + 46), f"root: {DEMO_PICKER_ROOT}", _MUTED, font)
    rows = [
        ("[x] repo" if selected else "[ ] repo", "pyherdr-demo", DEMO_PICKER_ROOT),
        (
            ("[ ] stale", "pyherdr-missing", "C:/old/pyherdr-missing")
            if stale
            else ("[ ] dir", "ghostc-plugin", "C:/work/ghostc-plugin")
        ),
    ]
    if long_path:
        rows[0] = (
            "[ ] repo",
            "pyherdr-operations-console",
            "C:/Users/josel/github/regional-command-center/operations/pyherdr-operations-console",
        )
    cursor = y + 88
    for kind, label, path in rows:
        _fill_rect(
            draw,
            (x + 22, cursor - 8, x2 - 22, cursor + 42),
            "#0b3042" if label.startswith("pyherdr") else _PANEL,
        )
        _text(draw, (x + 36, cursor), f"{kind}  {label}", _YELLOW if label.startswith("pyherdr") else _TEXT, font)
        _text(draw, (x + 36, cursor + 20), _shorten(path, 88), _MUTED, font)
        cursor += 58
    _text(draw, (x + 16, cursor + 16), "enter opens workspace; tab filters results; esc returns to panes", _MUTED, font)


def _draw_pane(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    title: str,
    body: str,
    font: Any,
    *,
    focused: bool = False,
) -> None:
    _fill_rect(draw, rect, "#061d28", _BORDER if focused else "#5d8799")
    x, y, _, y2 = rect
    _text(draw, (x + 12, y + 10), title, _BORDER, font)
    cursor = y + 34
    for line in body.splitlines():
        if cursor > y2 - 18:
            break
        color = _line_color(line)
        _text(draw, (x + 12, cursor), _shorten(line, max(24, (rect[2] - rect[0] - 24) // 7)), color, font)
        cursor += 16


def _workspace_status(workspace: dict[str, Any]) -> str:
    for tab in workspace["tabs"]:
        for pane in tab["panes"]:
            if pane.get("status") == "working":
                return "working"
    return "idle"


def _line_color(line: str) -> str:
    if line.startswith("$") or line.startswith("python") or "pyherdr" in line:
        return _YELLOW
    if "All checks passed" in line or "Success" in line or line == "OK":
        return _GREEN
    if line.startswith("- "):
        return _RED
    if line.startswith("+ "):
        return _GREEN
    if line.startswith("WS-"):
        return _PURPLE
    return _TEXT


def _fill_rect(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    fill: str,
    outline: str | None = None,
) -> None:
    draw.rectangle(rect, fill=fill, outline=outline)


def _text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fill: str,
    font: Any,
) -> None:
    draw.text(xy, text, fill=fill, font=font)


def _shorten(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return f"{text[: max(1, width - 1)]}..."
