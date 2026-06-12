"""Pure-Python BSP split-tree layout engine — port of herdr's ``src/layout.rs``.

A tab's panes are arranged as a **binary space-partition (BSP) tree**: every node
is either a single ``PaneNode`` (leaf) or a ``SplitNode`` of two children at a
``ratio`` in ``[0.1, 0.9]``.

* ``Direction.HORIZONTAL`` splits the **width** → children sit side-by-side
  (a vertical divider; this is herdr's "split vertical" / ``split│``).
* ``Direction.VERTICAL`` splits the **height** → children are stacked
  (a horizontal divider; herdr's "split horizontal" / ``split─``).

This module owns the geometry (which pane gets which rectangle), neighbour
navigation, keyboard resize, swapping, and (de)serialization. It is deliberately
free of any UI framework so it can be unit-tested in isolation, exactly like the
Rust original.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

MIN_RATIO = 0.1
MAX_RATIO = 0.9


def clamp_ratio(ratio: float) -> float:
    """Clamp a split ratio to herdr's ``[0.1, 0.9]`` range."""
    return max(MIN_RATIO, min(MAX_RATIO, ratio))


class Direction(Enum):
    """Split orientation (matches herdr's ``layout::Direction``)."""

    HORIZONTAL = "horizontal"  # split the width → side-by-side children
    VERTICAL = "vertical"  # split the height → stacked children


class NavDirection(Enum):
    """A directional movement/resize request."""

    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True)
class Rect:
    """An integer terminal rectangle (cells)."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


@dataclass
class PaneNode:
    """Leaf node: a single pane."""

    pane_id: str


@dataclass
class SplitNode:
    """Internal node: a split of two children at ``ratio`` (first child's share)."""

    direction: Direction
    ratio: float
    first: Node
    second: Node


Node = PaneNode | SplitNode


@dataclass(frozen=True)
class PaneInfo:
    """A pane's computed outer rectangle for a given area."""

    pane_id: str
    rect: Rect
    is_focused: bool


@dataclass(frozen=True)
class SplitBorder:
    """A draggable split divider: ``pos`` is the x (HORIZONTAL) or y (VERTICAL) line."""

    pos: int
    direction: Direction
    ratio: float
    area: Rect
    path: tuple[bool, ...]  # route from root: False = first child, True = second child


@dataclass(frozen=True)
class LayoutTemplate:
    """A built-in pane layout template."""

    id: str
    label: str
    pane_count: int
    description: str
    builder: Callable[[list[str]], Node]

    def record(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "label": self.label,
            "pane_count": self.pane_count,
            "description": self.description,
        }


def split_rect(area: Rect, direction: Direction, ratio: float) -> tuple[Rect, Rect]:
    """Divide ``area`` into (first, second) child rectangles at ``ratio``."""
    ratio = clamp_ratio(ratio)
    if direction == Direction.HORIZONTAL:
        if area.width >= 2:
            first_w = max(1, min(area.width - 1, round(area.width * ratio)))
        else:
            first_w = area.width
        first = Rect(area.x, area.y, first_w, area.height)
        second = Rect(area.x + first_w, area.y, area.width - first_w, area.height)
    else:
        if area.height >= 2:
            first_h = max(1, min(area.height - 1, round(area.height * ratio)))
        else:
            first_h = area.height
        first = Rect(area.x, area.y, area.width, first_h)
        second = Rect(area.x, area.y + first_h, area.width, area.height - first_h)
    return first, second


def _range_overlap(start1: int, len1: int, start2: int, len2: int) -> int:
    """Length of the overlap between ``[start1, start1+len1)`` and ``[start2, …)``."""
    lo = max(start1, start2)
    hi = min(start1 + len1, start2 + len2)
    return max(0, hi - lo)


class TileLayout:
    """A BSP layout tree with a focused pane."""

    def __init__(self, root: Node, focus: str) -> None:
        self.root = root
        self.focus = focus

    # ----- construction -----
    @classmethod
    def single(cls, pane_id: str) -> TileLayout:
        return cls(PaneNode(pane_id), pane_id)

    # ----- queries -----
    def pane_ids(self) -> list[str]:
        out: list[str] = []
        self._collect_ids(self.root, out)
        return out

    def _collect_ids(self, node: Node, out: list[str]) -> None:
        if isinstance(node, PaneNode):
            out.append(node.pane_id)
        else:
            self._collect_ids(node.first, out)
            self._collect_ids(node.second, out)

    def contains(self, pane_id: str) -> bool:
        return pane_id in self.pane_ids()

    def panes(self, area: Rect) -> list[PaneInfo]:
        """Compute every pane's rectangle for ``area`` (in layout order)."""
        out: list[PaneInfo] = []
        self._collect_panes(self.root, area, out)
        return out

    def _collect_panes(self, node: Node, area: Rect, out: list[PaneInfo]) -> None:
        if isinstance(node, PaneNode):
            out.append(PaneInfo(node.pane_id, area, node.pane_id == self.focus))
            return
        first_rect, second_rect = split_rect(area, node.direction, node.ratio)
        self._collect_panes(node.first, first_rect, out)
        self._collect_panes(node.second, second_rect, out)

    def splits(self, area: Rect) -> list[SplitBorder]:
        """Compute every split divider for ``area`` (for mouse-drag hit testing)."""
        out: list[SplitBorder] = []
        self._collect_splits(self.root, area, (), out)
        return out

    def _collect_splits(self, node: Node, area: Rect, path: tuple[bool, ...], out: list[SplitBorder]) -> None:
        if isinstance(node, PaneNode):
            return
        first_rect, second_rect = split_rect(area, node.direction, node.ratio)
        pos = second_rect.x if node.direction == Direction.HORIZONTAL else second_rect.y
        out.append(SplitBorder(pos, node.direction, node.ratio, area, path))
        self._collect_splits(node.first, first_rect, path + (False,), out)
        self._collect_splits(node.second, second_rect, path + (True,), out)

    # ----- focus -----
    def focus_pane(self, pane_id: str) -> bool:
        if self.contains(pane_id):
            self.focus = pane_id
            return True
        return False

    # ----- mutations -----
    def split_focused(self, new_pane_id: str, direction: Direction, ratio: float = 0.5) -> bool:
        return self.split_pane(self.focus, new_pane_id, direction, ratio)

    def split_pane(self, target: str, new_pane_id: str, direction: Direction, ratio: float = 0.5) -> bool:
        """Replace ``target``'s leaf with a split of (target, new_pane_id)."""
        replaced = False

        def rebuild(node: Node) -> Node:
            nonlocal replaced
            if isinstance(node, PaneNode):
                if node.pane_id == target:
                    replaced = True
                    return SplitNode(direction, clamp_ratio(ratio), PaneNode(target), PaneNode(new_pane_id))
                return node
            node.first = rebuild(node.first)
            node.second = rebuild(node.second)
            return node

        self.root = rebuild(self.root)
        if replaced:
            self.focus = new_pane_id
        return replaced

    def close_focused(self) -> bool:
        return self.close_pane(self.focus)

    def close_pane(self, target: str) -> bool:
        """Remove ``target``; its sibling subtree bubbles up. Refuse if it's the last pane."""
        ids = self.pane_ids()
        if target not in ids or len(ids) <= 1:
            return False
        idx = ids.index(target)
        remaining = [pid for pid in ids if pid != target]
        new_focus = remaining[min(idx, len(remaining) - 1)]
        new_root = self._remove(self.root, target)
        assert new_root is not None  # guaranteed: len(ids) > 1
        self.root = new_root
        if self.focus == target or not self.contains(self.focus):
            self.focus = new_focus
        return True

    def _remove(self, node: Node, target: str) -> Node | None:
        if isinstance(node, PaneNode):
            return None if node.pane_id == target else node
        first = self._remove(node.first, target)
        second = self._remove(node.second, target)
        if first is None and second is None:
            return None
        if first is None:
            return second  # sibling bubbles up
        if second is None:
            return first
        node.first = first
        node.second = second
        return node

    def swap_panes(self, a: str, b: str) -> bool:
        if a == b:
            return False
        ids = self.pane_ids()
        if a not in ids or b not in ids:
            return False

        def swap(node: Node) -> None:
            if isinstance(node, PaneNode):
                if node.pane_id == a:
                    node.pane_id = b
                elif node.pane_id == b:
                    node.pane_id = a
                return
            swap(node.first)
            swap(node.second)

        swap(self.root)
        return True

    def set_ratio_at(self, path: tuple[bool, ...], ratio: float) -> bool:
        node: Node = self.root
        for step in path:
            if not isinstance(node, SplitNode):
                return False
            node = node.second if step else node.first
        if not isinstance(node, SplitNode):
            return False
        node.ratio = clamp_ratio(ratio)
        return True

    # ----- navigation -----
    def find_in_direction(self, nav: NavDirection, area: Rect) -> str | None:
        """Return the pane id of the nearest geometric neighbour in ``nav``."""
        infos = self.panes(area)
        focused = next((i for i in infos if i.pane_id == self.focus), None)
        if focused is None:
            return None
        f = focused.rect
        scored: list[tuple[tuple[int, int, float, int], str]] = []
        for order, info in enumerate(infos):
            if info.pane_id == self.focus:
                continue
            r = info.rect
            if nav == NavDirection.LEFT:
                if r.right <= f.x:
                    overlap = _range_overlap(r.y, r.height, f.y, f.height)
                    if overlap > 0:
                        scored.append(((f.x - r.right, -overlap, abs(r.center_y - f.center_y), order), info.pane_id))
            elif nav == NavDirection.RIGHT:
                if r.x >= f.right:
                    overlap = _range_overlap(r.y, r.height, f.y, f.height)
                    if overlap > 0:
                        scored.append(((r.x - f.right, -overlap, abs(r.center_y - f.center_y), order), info.pane_id))
            elif nav == NavDirection.UP:
                if r.bottom <= f.y:
                    overlap = _range_overlap(r.x, r.width, f.x, f.width)
                    if overlap > 0:
                        scored.append(((f.y - r.bottom, -overlap, abs(r.center_x - f.center_x), order), info.pane_id))
            else:  # DOWN
                if r.y >= f.bottom:
                    overlap = _range_overlap(r.x, r.width, f.x, f.width)
                    if overlap > 0:
                        scored.append(((r.y - f.bottom, -overlap, abs(r.center_x - f.center_x), order), info.pane_id))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0])
        return scored[0][1]

    def focus_in_direction(self, nav: NavDirection, area: Rect) -> bool:
        neighbour = self.find_in_direction(nav, area)
        if neighbour is None:
            return False
        self.focus = neighbour
        return True

    def resize_focused(self, nav: NavDirection, delta: float, area: Rect) -> bool:
        """Grow/shrink the focused pane toward ``nav`` by adjusting the adjacent split.

        ``RIGHT``/``DOWN`` grow the focused pane; ``LEFT``/``UP`` shrink it.
        """
        direction = Direction.HORIZONTAL if nav in (NavDirection.LEFT, NavDirection.RIGHT) else Direction.VERTICAL
        sign = 1.0 if nav in (NavDirection.RIGHT, NavDirection.DOWN) else -1.0
        infos = self.panes(area)
        focused = next((i for i in infos if i.pane_id == self.focus), None)
        if focused is None:
            return False
        f = focused.rect
        chosen: SplitBorder | None = None
        chosen_in_first = True
        for sb in self.splits(area):
            if sb.direction != direction:
                continue
            if direction == Direction.HORIZONTAL:
                if _range_overlap(sb.area.y, sb.area.height, f.y, f.height) <= 0:
                    continue
                if f.right == sb.pos:  # focused is the first child; divider on its right edge
                    chosen, chosen_in_first = sb, True
                    break
                if f.x == sb.pos:  # focused is the second child; divider on its left edge
                    chosen, chosen_in_first = sb, False
            else:
                if _range_overlap(sb.area.x, sb.area.width, f.x, f.width) <= 0:
                    continue
                if f.bottom == sb.pos:
                    chosen, chosen_in_first = sb, True
                    break
                if f.y == sb.pos:
                    chosen, chosen_in_first = sb, False
        if chosen is None:
            return False
        # Growing the focused pane: if it's the first child, raise the ratio; if it's
        # the second child, lower it (the divider moves away from the focused pane).
        new_ratio = chosen.ratio + sign * delta if chosen_in_first else chosen.ratio - sign * delta
        return self.set_ratio_at(chosen.path, new_ratio)

    # ----- (de)serialization -----
    def to_dict(self) -> dict[str, Any]:
        return {"root": _node_to_dict(self.root), "focus": self.focus}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TileLayout:
        root = _node_from_dict(data["root"])
        focus = str(data.get("focus") or "")
        layout = cls(root, focus)
        if not layout.contains(focus):
            ids = layout.pane_ids()
            layout.focus = ids[0] if ids else ""
        return layout


def layout_template_records() -> list[dict[str, str | int]]:
    """Return the built-in templates in display order."""
    return [template.record() for template in LAYOUT_TEMPLATES]


def layout_template_record(template_id: str) -> dict[str, str | int]:
    """Return one template's public metadata or raise ``ValueError``."""
    return _require_template(template_id).record()


def build_template_layout(template_id: str, pane_ids: list[str]) -> TileLayout:
    """Build a template split tree for ``pane_ids``.

    Templates are intentionally safe: they require enough panes for the named
    shape but do not delete extra panes. Extra panes are preserved in a simple
    trailing horizontal chain so applying a smaller template never destroys a
    running session.
    """
    template = _require_template(template_id)
    if len(pane_ids) < template.pane_count:
        raise ValueError(
            f"layout template {template.id!r} requires {template.pane_count} pane(s), got {len(pane_ids)}"
        )
    root = template.builder(list(pane_ids[: template.pane_count]))
    for pane_id in pane_ids[template.pane_count :]:
        root = SplitNode(Direction.HORIZONTAL, 0.75, root, PaneNode(pane_id))
    return TileLayout(root, pane_ids[0])


def _require_template(template_id: str) -> LayoutTemplate:
    normalized = str(template_id or "").strip().lower()
    for template in LAYOUT_TEMPLATES:
        if template.id == normalized:
            return template
    raise ValueError(f"unknown layout template: {template_id}")


def _columns_2(ids: list[str]) -> Node:
    return SplitNode(Direction.HORIZONTAL, 0.5, PaneNode(ids[0]), PaneNode(ids[1]))


def _rows_2(ids: list[str]) -> Node:
    return SplitNode(Direction.VERTICAL, 0.5, PaneNode(ids[0]), PaneNode(ids[1]))


def _grid_2x2(ids: list[str]) -> Node:
    top = SplitNode(Direction.HORIZONTAL, 0.5, PaneNode(ids[0]), PaneNode(ids[1]))
    bottom = SplitNode(Direction.HORIZONTAL, 0.5, PaneNode(ids[2]), PaneNode(ids[3]))
    return SplitNode(Direction.VERTICAL, 0.5, top, bottom)


def _main_left(ids: list[str]) -> Node:
    side = SplitNode(Direction.VERTICAL, 0.5, PaneNode(ids[1]), PaneNode(ids[2]))
    return SplitNode(Direction.HORIZONTAL, 0.65, PaneNode(ids[0]), side)


def _main_top(ids: list[str]) -> Node:
    bottom = SplitNode(Direction.HORIZONTAL, 0.5, PaneNode(ids[1]), PaneNode(ids[2]))
    return SplitNode(Direction.VERTICAL, 0.6, PaneNode(ids[0]), bottom)


LAYOUT_TEMPLATES: tuple[LayoutTemplate, ...] = (
    LayoutTemplate("single", "Single pane", 1, "One focused pane fills the tab.", lambda ids: PaneNode(ids[0])),
    LayoutTemplate("columns-2", "Two columns", 2, "Two equal side-by-side panes.", _columns_2),
    LayoutTemplate("rows-2", "Two rows", 2, "Two equal stacked panes.", _rows_2),
    LayoutTemplate("grid-2x2", "2x2 grid", 4, "Four panes in an even grid.", _grid_2x2),
    LayoutTemplate("main-left", "Main left", 3, "Large primary pane with a right-side stack.", _main_left),
    LayoutTemplate("main-top", "Main top", 3, "Large primary pane above two lower panes.", _main_top),
)


def _node_to_dict(node: Node) -> dict[str, Any]:
    if isinstance(node, PaneNode):
        return {"kind": "pane", "pane_id": node.pane_id}
    return {
        "kind": "split",
        "direction": node.direction.value,
        "ratio": node.ratio,
        "first": _node_to_dict(node.first),
        "second": _node_to_dict(node.second),
    }


def _node_from_dict(data: dict[str, Any]) -> Node:
    if data.get("kind") == "pane":
        return PaneNode(str(data["pane_id"]))
    return SplitNode(
        Direction(data["direction"]),
        clamp_ratio(float(data["ratio"])),
        _node_from_dict(data["first"]),
        _node_from_dict(data["second"]),
    )
