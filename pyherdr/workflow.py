from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any
from uuid import uuid4

from .session import session_runtime_dir

REDACTED = "[redacted]"
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "passwd", "authorization", "api_key", "apikey")
ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(token|secret|password|passwd|authorization|api[_-]?key)\s*=\s*([^ \t\r\n;&]+)"
)


@dataclass(frozen=True)
class WorkflowEvent:
    """A redacted audit event used to build workflow and call-flow graphs."""

    id: str
    timestamp: float
    kind: str
    message: str = ""
    source: str = ""
    target: str = ""
    worksite: str = ""
    agent: str = ""
    pane_id: str = ""
    status: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)


def default_workflow_log_path() -> Path:
    return session_runtime_dir() / "workflow.jsonl"


def new_event(
    kind: str,
    *,
    message: str = "",
    source: str = "",
    target: str = "",
    worksite: str = "",
    agent: str = "",
    pane_id: str = "",
    status: str = "",
    details: dict[str, Any] | None = None,
    artifacts: list[str] | None = None,
    event_id: str | None = None,
    timestamp: float | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        id=event_id or uuid4().hex,
        timestamp=timestamp if timestamp is not None else time.time(),
        kind=kind.strip() or "event",
        message=message.strip(),
        source=source.strip(),
        target=target.strip(),
        worksite=worksite.strip(),
        agent=agent.strip(),
        pane_id=pane_id.strip(),
        status=status.strip(),
        details=redact(details or {}),
        artifacts=[str(item) for item in artifacts or []],
    )


def redact(value: Any) -> Any:
    """Return a copy of ``value`` with obvious secrets removed."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if _is_sensitive_key(text_key):
                redacted[text_key] = REDACTED
            else:
                redacted[text_key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", value)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def event_to_dict(event: WorkflowEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "timestamp": event.timestamp,
        "kind": event.kind,
        "message": event.message,
        "source": event.source,
        "target": event.target,
        "worksite": event.worksite,
        "agent": event.agent,
        "pane_id": event.pane_id,
        "status": event.status,
        "details": redact(event.details),
        "artifacts": list(event.artifacts),
    }


def event_from_dict(payload: dict[str, Any]) -> WorkflowEvent:
    return new_event(
        str(payload.get("kind") or "event"),
        message=str(payload.get("message") or ""),
        source=str(payload.get("source") or ""),
        target=str(payload.get("target") or ""),
        worksite=str(payload.get("worksite") or ""),
        agent=str(payload.get("agent") or ""),
        pane_id=str(payload.get("pane_id") or ""),
        status=str(payload.get("status") or ""),
        details=payload.get("details") if isinstance(payload.get("details"), dict) else {},
        artifacts=[str(item) for item in payload.get("artifacts", []) if item],
        event_id=str(payload.get("id") or uuid4().hex),
        timestamp=float(payload.get("timestamp") or time.time()),
    )


def append_event(
    event: WorkflowEvent,
    *,
    path: Path | None = None,
    max_events: int = 1000,
) -> Path:
    target = path or default_workflow_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    events = read_events(target)
    events.append(event)
    if max_events > 0 and len(events) > max_events:
        events = events[-max_events:]
    target.write_text(
        "".join(json.dumps(event_to_dict(item), sort_keys=True) + "\n" for item in events),
        encoding="utf-8",
    )
    return target


def read_events(path: Path | None = None, *, limit: int | None = None) -> list[WorkflowEvent]:
    target = path or default_workflow_log_path()
    if not target.exists():
        return []
    events: list[WorkflowEvent] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(event_from_dict(payload))
    if limit is None or limit < 0:
        return events
    if limit == 0:
        return []
    return events[-limit:]


def build_graph(events: list[WorkflowEvent]) -> dict[str, Any]:
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []

    def add_node(node_id: str, label: str, kind: str) -> None:
        nodes.setdefault(node_id, {"id": node_id, "label": label, "kind": kind})

    def add_edge(start: str, end: str, label: str) -> None:
        edge = {"from": start, "to": end, "label": label}
        if edge not in edges:
            edges.append(edge)

    for event in events:
        event_id = f"event:{event.id}"
        add_node(event_id, event.message or event.kind, "event")
        if event.worksite:
            node_id = f"worksite:{event.worksite}"
            add_node(node_id, event.worksite, "worksite")
            add_edge(node_id, event_id, "contains")
        if event.agent:
            node_id = f"agent:{event.agent}"
            add_node(node_id, event.agent, "agent")
            add_edge(node_id, event_id, "performed")
        if event.pane_id:
            node_id = f"pane:{event.pane_id}"
            add_node(node_id, event.pane_id, "pane")
            add_edge(node_id, event_id, "emitted")
        if event.source:
            node_id = f"source:{event.source}"
            add_node(node_id, event.source, "source")
            add_edge(node_id, event_id, "calls")
        if event.target:
            node_id = f"target:{event.target}"
            add_node(node_id, event.target, "target")
            add_edge(event_id, node_id, "targets")
        if event.status:
            node_id = f"status:{event.status}"
            add_node(node_id, event.status, "status")
            add_edge(event_id, node_id, "status")
        for artifact in event.artifacts:
            node_id = f"artifact:{artifact}"
            add_node(node_id, artifact, "artifact")
            add_edge(event_id, node_id, "produces")

    return {"nodes": nodes, "edges": edges}


def graph_to_mermaid(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes", {})
    edges = graph.get("edges", [])
    lines = ["flowchart TD"]
    for node_id in sorted(nodes):
        node = nodes[node_id]
        lines.append(f"  {_mermaid_id(node_id)}[{json.dumps(str(node.get('label', node_id)))}]")
    for edge in edges:
        label = str(edge.get("label", ""))
        start = _mermaid_id(str(edge.get("from", "")))
        end = _mermaid_id(str(edge.get("to", "")))
        if not start or not end:
            continue
        lines.append(f"  {start} -->|{_escape_mermaid_label(label)}| {end}")
    return "\n".join(lines)


def graph_to_svg(graph: dict[str, Any]) -> str:
    """Render a workflow graph as a standalone SVG with boxes and arrows."""
    nodes = {
        str(node_id): node
        for node_id, node in graph.get("nodes", {}).items()
        if isinstance(node, dict)
    }
    edges = [edge for edge in graph.get("edges", []) if isinstance(edge, dict)]
    if not nodes:
        return _empty_svg()

    box_width = 220
    box_height = 58
    x_gap = 82
    y_gap = 24
    margin = 34
    layers = _svg_layers(nodes)
    layer_keys = sorted(layers)
    max_rows = max(len(layers[layer]) for layer in layer_keys)
    width = margin * 2 + len(layer_keys) * box_width + max(0, len(layer_keys) - 1) * x_gap
    height = margin * 2 + max_rows * box_height + max(0, max_rows - 1) * y_gap

    positions: dict[str, tuple[int, int]] = {}
    for x_index, layer in enumerate(layer_keys):
        for y_index, node_id in enumerate(layers[layer]):
            x = margin + x_index * (box_width + x_gap)
            y = margin + y_index * (box_height + y_gap)
            positions[node_id] = (x, y)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" aria-label="PyHerdr workflow graph">'
        ),
        "<defs>",
        (
            '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" '
            'orient="auto" markerUnits="strokeWidth">'
        ),
        '<path d="M0,0 L0,6 L9,3 z" fill="#38bdf8" />',
        "</marker>",
        "</defs>",
        '<rect width="100%" height="100%" fill="#04111a" />',
    ]

    for edge in edges:
        start = str(edge.get("from", ""))
        end = str(edge.get("to", ""))
        if start not in positions or end not in positions:
            continue
        sx, sy = positions[start]
        ex, ey = positions[end]
        start_x = sx + box_width
        start_y = sy + box_height // 2
        end_x = ex
        end_y = ey + box_height // 2
        mid_x = (start_x + end_x) // 2
        path = f"M {start_x} {start_y} C {mid_x} {start_y}, {mid_x} {end_y}, {end_x - 6} {end_y}"
        parts.append(
            f'<path d="{path}" fill="none" stroke="#38bdf8" stroke-width="2" '
            'stroke-opacity="0.62" marker-end="url(#arrow)" />'
        )
        label = str(edge.get("label") or "")
        if label:
            parts.append(
                f'<text x="{mid_x}" y="{(start_y + end_y) // 2 - 6}" text-anchor="middle" '
                'font-family="ui-monospace, Consolas, monospace" font-size="11" fill="#95b9cc">'
                f"{escape(label)}</text>"
            )

    for node_id, node in nodes.items():
        x, y = positions[node_id]
        kind = str(node.get("kind", "node"))
        label = str(node.get("label", node_id))
        fill, stroke = _svg_node_colors(kind)
        parts.append(
            f'<rect x="{x}" y="{y}" width="{box_width}" height="{box_height}" rx="8" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="2" />'
        )
        parts.append(
            f'<text x="{x + 14}" y="{y + 20}" font-family="ui-monospace, Consolas, monospace" '
            f'font-size="11" fill="#95b9cc">{escape(kind)}</text>'
        )
        for index, line in enumerate(_svg_label_lines(label), start=0):
            weight = "700" if index == 0 else "400"
            parts.append(
                f'<text x="{x + 14}" y="{y + 40 + index * 15}" '
                'font-family="ui-monospace, Consolas, monospace" '
                f'font-size="14" font-weight="{weight}" fill="#d8f3ff">{escape(line)}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def _empty_svg() -> str:
    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="220" viewBox="0 0 640 220">',
            '<rect width="100%" height="100%" fill="#04111a" />',
            (
                '<text x="320" y="110" text-anchor="middle" '
                'font-family="ui-monospace, Consolas, monospace" font-size="18" fill="#95b9cc">'
                "No workflow events recorded yet</text>"
            ),
            "</svg>",
        ]
    )


def _svg_layers(nodes: dict[str, dict[str, str]]) -> dict[int, list[str]]:
    order = {
        "worksite": 0,
        "agent": 1,
        "source": 1,
        "pane": 1,
        "event": 2,
        "target": 3,
        "status": 3,
        "artifact": 3,
    }
    layers: dict[int, list[str]] = {}
    for node_id, node in nodes.items():
        layer = order.get(str(node.get("kind", "node")), 2)
        layers.setdefault(layer, []).append(node_id)
    for node_ids in layers.values():
        node_ids.sort(key=lambda item: (str(nodes[item].get("kind", "")), str(nodes[item].get("label", "")), item))
    return layers


def _svg_node_colors(kind: str) -> tuple[str, str]:
    colors = {
        "worksite": ("#082333", "#38bdf8"),
        "agent": ("#09271f", "#2dd4bf"),
        "source": ("#09271f", "#2dd4bf"),
        "pane": ("#102235", "#5abfff"),
        "event": ("#102033", "#ffd166"),
        "target": ("#161d33", "#b4a7ff"),
        "status": ("#142618", "#64d28b"),
        "artifact": ("#261d12", "#ffb86b"),
    }
    return colors.get(kind, ("#0b2635", "#4f7186"))


def _svg_label_lines(label: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", label.strip()) or "(empty)"
    if len(normalized) <= 24:
        return [normalized]
    return [normalized[:24].rstrip(), normalized[24:45].rstrip() + ("…" if len(normalized) > 45 else "")]


def _mermaid_id(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", value)
    if not cleaned:
        return ""
    if cleaned[0].isdigit():
        return f"n_{cleaned}"
    return cleaned


def _escape_mermaid_label(value: str) -> str:
    return value.replace("|", "/").replace("\n", " ")
