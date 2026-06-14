"""Run a deterministic Zellij/tmux-class multiplexer scenario.

Usage:
    python -m tools.zmux_scenario --json
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from pyherdr.api import dispatch
from pyherdr.layout import NavDirection, Rect, TileLayout
from pyherdr.models import AppState

AREA = Rect(0, 0, 120, 40)
PANE_TITLES = ("main", "logs", "tests", "shell")


def run_zmux_scenario(work_dir: Path) -> dict[str, Any]:
    """Exercise split, resize, swap, zoom-view, and custom layout save/apply."""
    work_dir = work_dir.resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    state = AppState.bootstrap(str(work_dir))
    workspace = state.focused_workspace
    if workspace is None or workspace.focused_tab is None:
        raise RuntimeError("failed to bootstrap workspace")
    workspace.label = "zmux"
    tab = workspace.focused_tab
    steps = ["workspace_created"]

    first = tab.focused_pane
    if first is None:
        raise RuntimeError("failed to bootstrap first pane")
    _result(
        dispatch(
            state,
            {
                "id": "split-right",
                "method": "pane.split",
                "params": {"pane_id": first.id, "direction": "horizontal", "title": "logs"},
            },
        )
    )
    second = tab.focused_pane
    _result(
        dispatch(
            state,
            {
                "id": "split-bottom",
                "method": "pane.split",
                "params": {"pane_id": second.id, "direction": "vertical", "title": "tests"},
            },
        )
    )
    _result(
        dispatch(
            state,
            {
                "id": "split-main-bottom",
                "method": "pane.split",
                "params": {"pane_id": first.id, "direction": "vertical", "title": "shell"},
            },
        )
    )
    for pane, title in zip(tab.panes, PANE_TITLES, strict=True):
        _result(
            dispatch(
                state,
                {"id": f"rename-{title}", "method": "pane.rename", "params": {"pane_id": pane.id, "title": title}},
            )
        )
    steps.append("panes_split")

    layout = TileLayout.from_dict(tab.layout)
    resize_target = tab.panes[0].id
    layout.focus_pane(resize_target)
    before_ratio = _root_ratio(layout)
    if not layout.resize_focused(NavDirection.RIGHT, 0.1, AREA):
        raise RuntimeError("layout resize did not find an adjacent split")
    after_ratio = _root_ratio(layout)
    tab.layout = layout.to_dict()
    tab.focused_pane_id = layout.focus
    _result(dispatch(state, {"id": "persist-resize", "method": "pane.set_layout", "params": {"layout": tab.layout}}))
    steps.append("layout_resized")

    before_swap = _pane_rects(layout)
    first_id = tab.panes[0].id
    last_id = tab.panes[-1].id
    if not layout.swap_panes(first_id, last_id):
        raise RuntimeError("layout swap failed")
    tab.layout = layout.to_dict()
    _result(dispatch(state, {"id": "persist-swap", "method": "pane.set_layout", "params": {"layout": tab.layout}}))
    after_swap = _pane_rects(layout)
    steps.append("panes_swapped")

    zoom = _zoom_view(layout, layout.focus)
    steps.append("pane_zoomed")

    exported = _result(
        dispatch(
            state,
            {
                "id": "export-layout",
                "method": "layout.custom.export",
                "params": {"name": "zmux-grid", "workspace_id": workspace.id, "tab_id": tab.id},
            },
        )
    )["layout"]
    layout_path = work_dir / "zmux-grid.layout.json"
    layout_path.write_text(json.dumps(exported, indent=2, sort_keys=True), encoding="utf-8")
    new_tab = state.create_tab(workspace.id, "restore")
    applied = _result(
        dispatch(
            state,
            {
                "id": "apply-layout",
                "method": "layout.custom.apply",
                "params": {"layout": exported, "workspace_id": workspace.id, "tab_id": new_tab.id},
            },
        )
    )
    steps.append("layout_saved")

    return {
        "result": "ok",
        "steps": steps,
        "workspace": {"id": workspace.id, "label": workspace.label, "cwd": workspace.cwd},
        "tab": {"id": tab.id, "label": tab.label},
        "pane_count": len(tab.panes),
        "panes": [{"id": pane.id, "title": pane.title} for pane in tab.panes],
        "resize": {"pane_id": resize_target, "before_ratio": before_ratio, "after_ratio": after_ratio},
        "swap": {
            "first": first_id,
            "last": last_id,
            "before": {pane_id: _rect_dict(rect) for pane_id, rect in before_swap.items()},
            "after": {pane_id: _rect_dict(rect) for pane_id, rect in after_swap.items()},
        },
        "zoom": zoom,
        "saved_layout": {"id": exported["id"], "path": str(layout_path), "pane_count": exported["pane_count"]},
        "applied_layout": {
            "tab_id": new_tab.id,
            "pane_count": applied["pane_count"],
            "layout_id": applied["layout_id"],
        },
    }


def default_work_dir() -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path(".artifacts") / "zmux-scenario" / f"{stamp}-{os.getpid()}"


def _root_ratio(layout: TileLayout) -> float:
    root = layout.to_dict()["root"]
    if root.get("kind") != "split":
        raise RuntimeError("layout root is not split")
    return float(root["ratio"])


def _pane_rects(layout: TileLayout) -> dict[str, Rect]:
    return {pane.pane_id: pane.rect for pane in layout.panes(AREA)}


def _zoom_view(layout: TileLayout, pane_id: str) -> dict[str, Any]:
    if pane_id not in layout.pane_ids():
        raise RuntimeError(f"cannot zoom missing pane {pane_id}")
    return {"pane_id": pane_id, "visible_panes": 1, "rect": _rect_dict(AREA)}


def _rect_dict(rect: Rect) -> dict[str, int]:
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def _result(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error")
    if error:
        raise RuntimeError(str(error.get("message") or error))
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError(f"unexpected API response: {response}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PyHerdr Zellij/tmux-class multiplexer scenario")
    parser.add_argument("--work-dir", type=Path, default=default_work_dir(), help="directory for scenario artifacts")
    parser.add_argument("--json", action="store_true", help="print machine-readable scenario report")
    args = parser.parse_args(argv)

    report = run_zmux_scenario(args.work_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"zmux scenario: {report['result']}")
        print(f"panes: {report['pane_count']}")
        print(f"layout: {report['saved_layout']['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
