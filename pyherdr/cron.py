"""Minimal 5-field cron matcher (pure Python, no dependencies).

Fields: ``minute hour day-of-month month day-of-week``. Supports ``*``, lists
(``1,2``), ranges (``1-5``), and steps (``*/5``, ``0-30/10``). Day-of-week is
0-6 with Sunday=0 (``7`` also accepted for Sunday). Names (mon/jan) are not
supported — use numbers. day-of-month and day-of-week are combined with AND.
"""

from __future__ import annotations

from datetime import datetime

_FIELD_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]


def _parse_field(field: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for raw in field.split(","):
        part = raw.strip()
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step <= 0:
                raise ValueError(f"cron step must be positive: {raw!r}")
        if part in ("*", ""):
            start, end = low, high
        elif "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expr: str) -> list[set[int]]:
    """Parse a 5-field cron expression into per-field value sets."""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"cron expression must have 5 fields, got {len(fields)}: {expr!r}")
    return [_parse_field(field, low, high) for field, (low, high) in zip(fields, _FIELD_BOUNDS, strict=True)]


def cron_matches(expr: str, when: datetime) -> bool:
    """Return whether ``when`` (minute resolution) satisfies the cron expression."""
    minute, hour, dom, month, dow = parse_cron(expr)
    cron_dow = (when.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> cron Sun=0..Sat=6
    dow_ok = cron_dow in dow or (cron_dow == 0 and 7 in dow)
    return when.minute in minute and when.hour in hour and when.day in dom and when.month in month and dow_ok
