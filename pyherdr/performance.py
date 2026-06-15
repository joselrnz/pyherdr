"""Performance baseline collection and reporting.

The live resource monitor answers "what is hot right now?". A baseline answers
"what does this scenario normally cost?" by recording several stats snapshots
and reducing them into stable CPU/RAM/process summaries.
"""

from __future__ import annotations

import json
import platform
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ApiRequester = Callable[[dict[str, Any]], dict[str, Any]]
Sleeper = Callable[[float], None]
Clock = Callable[[], float]


def collect_baseline(
    request: ApiRequester,
    *,
    scenario: str = "manual",
    duration_seconds: float = 30.0,
    interval_seconds: float = 1.5,
    sleep: Sleeper = time.sleep,
    clock: Clock = time.monotonic,
) -> dict[str, Any]:
    """Collect stats/state snapshots and return a serializable baseline."""
    duration_seconds = max(0.0, float(duration_seconds))
    interval_seconds = max(0.1, float(interval_seconds))
    started = clock()
    samples: list[dict[str, Any]] = []
    index = 0
    while True:
        elapsed = max(0.0, clock() - started)
        samples.append(collect_sample(request, elapsed_seconds=elapsed, index=index))
        index += 1
        remaining = duration_seconds - (clock() - started)
        if remaining <= 0:
            break
        sleep(min(interval_seconds, remaining))
    return build_baseline(scenario, samples, duration_seconds, interval_seconds)


def collect_sample(request: ApiRequester, *, elapsed_seconds: float, index: int) -> dict[str, Any]:
    """Collect one stats/state sample from the running PyHerdr server."""
    stats_response = request({"id": f"perf-stats-{index}", "method": "stats.get", "params": {}})
    state_response = request({"id": f"perf-state-{index}", "method": "state.get", "params": {}})
    stats_result = _result(stats_response)
    state_result = _result(state_response)
    labels, agents = _pane_metadata(state_result.get("state", {}))
    stats = stats_result.get("stats", {}) if stats_result.get("available", False) else {}
    entries = _pane_entries(stats, labels, agents)
    total_cpu = sum(entry["cpu_percent"] for entry in entries)
    total_rss = sum(entry["rss_bytes"] for entry in entries)
    process_count = sum(entry["num_procs"] for entry in entries)
    warnings = [
        warning
        for entry in entries
        for warning in ([entry["error"]] if entry.get("error") else []) + list(entry.get("warnings", []))
    ]
    return {
        "index": index,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "available": bool(stats_result.get("available", False)),
        "pane_count": len(labels),
        "running_pane_count": len(entries),
        "process_count": process_count,
        "total_cpu_percent": round(total_cpu, 1),
        "total_rss_bytes": total_rss,
        "warnings": warnings,
        "top_panes": entries[:8],
    }


def build_baseline(
    scenario: str,
    samples: list[dict[str, Any]],
    duration_seconds: float,
    interval_seconds: float,
) -> dict[str, Any]:
    """Reduce raw samples into a saved baseline payload."""
    cpu_values = [float(sample.get("total_cpu_percent", 0.0)) for sample in samples]
    rss_values = [int(sample.get("total_rss_bytes", 0)) for sample in samples]
    process_values = [int(sample.get("process_count", 0)) for sample in samples]
    pane_values = [int(sample.get("pane_count", 0)) for sample in samples]
    warnings = [warning for sample in samples for warning in sample.get("warnings", [])]
    return {
        "type": "performance_baseline",
        "schema_version": 1,
        "scenario": scenario,
        "created_at": datetime.now(UTC).isoformat(),
        "platform": platform_summary(),
        "requested": {
            "duration_seconds": round(float(duration_seconds), 3),
            "interval_seconds": round(float(interval_seconds), 3),
        },
        "summary": {
            "samples": len(samples),
            "cpu_percent": _series_summary(cpu_values),
            "rss_bytes": _series_summary(rss_values),
            "process_count": _series_summary(process_values),
            "pane_count": _series_summary(pane_values),
            "warning_count": len(warnings),
        },
        "warnings": warnings[:50],
        "samples": samples,
    }


def write_baseline(path: Path, baseline: dict[str, Any]) -> Path:
    """Write a baseline JSON file, creating parents as needed."""
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def load_baseline(path: Path) -> dict[str, Any]:
    """Load a saved baseline JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def render_baseline_report(baseline: dict[str, Any]) -> str:
    """Render a compact terminal dashboard for a saved baseline."""
    summary = baseline.get("summary", {})
    cpu = summary.get("cpu_percent", {})
    rss = summary.get("rss_bytes", {})
    procs = summary.get("process_count", {})
    panes = summary.get("pane_count", {})
    latest = (baseline.get("samples") or [{}])[-1]
    lines = [
        f"performance baseline · {baseline.get('scenario', 'manual')}",
        f"samples {summary.get('samples', 0)} · platform {baseline.get('platform', {}).get('system', '?')}",
        "",
        f"CPU   avg {_num(cpu.get('avg'))}%   p95 {_num(cpu.get('p95'))}%   peak {_num(cpu.get('max'))}%",
        (
            f"RAM   avg {_fmt_bytes(int(rss.get('avg', 0)))}   "
            f"p95 {_fmt_bytes(int(rss.get('p95', 0)))}   "
            f"peak {_fmt_bytes(int(rss.get('max', 0)))}"
        ),
        f"PROC  avg {_num(procs.get('avg'), decimals=0)}   peak {_num(procs.get('max'), decimals=0)}",
        f"PANES avg {_num(panes.get('avg'), decimals=0)}   peak {_num(panes.get('max'), decimals=0)}",
        "",
        "hot panes at final sample",
    ]
    top_panes = latest.get("top_panes", []) or []
    if not top_panes:
        lines.append("  no running pane processes sampled")
    for entry in top_panes:
        lines.append(
            "  "
            f"{entry.get('label', entry.get('pane_id', '?'))}: "
            f"CPU {_num(entry.get('cpu_percent'))}% · "
            f"RAM {_fmt_bytes(int(entry.get('rss_bytes', 0)))} · "
            f"{entry.get('num_procs', 0)} proc(s)"
        )
    warning_count = int(summary.get("warning_count", 0))
    if warning_count:
        lines.extend(
            [
                "",
                f"warnings: {warning_count}",
                *[f"  {warning}" for warning in baseline.get("warnings", [])[:5]],
            ]
        )
    return "\n".join(lines)


def platform_summary() -> dict[str, str]:
    """Return stable platform fields useful for comparing baselines."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


def _result(response: dict[str, Any]) -> dict[str, Any]:
    error = response.get("error")
    if error:
        raise RuntimeError(str(error.get("message") or error))
    result = response.get("result")
    return result if isinstance(result, dict) else {}


def _pane_metadata(state: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    labels: dict[str, str] = {}
    agents: dict[str, str] = {}
    for workspace in state.get("workspaces", []) or []:
        workspace_label = str(workspace.get("label") or workspace.get("id") or "workspace")
        for tab in workspace.get("tabs", []) or []:
            tab_label = str(tab.get("label") or tab.get("id") or "tab")
            for pane in tab.get("panes", []) or []:
                pane_id = str(pane.get("pane_id") or pane.get("id") or "")
                if not pane_id:
                    continue
                pane_label = str(pane.get("title") or pane_id)
                labels[pane_id] = f"{workspace_label} · {tab_label} · {pane_label}"
                agents[pane_id] = str(pane.get("agent") or pane.get("title") or tab_label)
    return labels, agents


def _pane_entries(stats: dict[str, Any], labels: dict[str, str], agents: dict[str, str]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for pane_id, stat in stats.items():
        if not isinstance(stat, dict):
            continue
        entries.append(
            {
                "pane_id": pane_id,
                "label": labels.get(pane_id, pane_id),
                "agent": stat.get("agent") or agents.get(pane_id, ""),
                "pid": stat.get("pid"),
                "cpu_percent": float(stat.get("cpu_percent", 0.0)),
                "rss_bytes": int(stat.get("rss_bytes", 0)),
                "num_procs": int(stat.get("num_procs", 0)),
                "output_lines_per_second": stat.get("output_lines_per_second", stat.get("output_rate", "")),
                "error": stat.get("error", ""),
                "warnings": list(stat.get("warnings", []) or []),
            }
        )
    entries.sort(key=lambda row: (row["cpu_percent"], row["rss_bytes"]), reverse=True)
    return entries


def _series_summary(values: list[float] | list[int]) -> dict[str, float]:
    if not values:
        return {"min": 0.0, "avg": 0.0, "p95": 0.0, "max": 0.0}
    numeric = sorted(float(value) for value in values)
    return {
        "min": round(numeric[0], 3),
        "avg": round(sum(numeric) / len(numeric), 3),
        "p95": round(_percentile(numeric, 95), 3),
        "max": round(numeric[-1], 3),
    }


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile / 100.0
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def _fmt_bytes(value: int) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    amount = float(max(0, value))
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} GiB"


def _num(value: Any, *, decimals: int = 1) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return f"{number:.{decimals}f}"
