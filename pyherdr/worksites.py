from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

WORKSITE_HEADING = re.compile(r"^###\s+(WS-\d{3})\s+(.+?)\s*$")
OUTCOME_LINE = re.compile(r"^-\s+\[(?P<checked>[ xX])\]\s+Outcome:\s*(?P<outcome>.+?)\s*$")
FIELD_LINE = re.compile(r"^-\s+(?P<name>Status|Owner|Linked PR|PR|Scope|Validation):\s*(?P<value>.+?)\s*$")
FORBIDDEN_PUBLIC_ROADMAP_TERMS = (
    "MEGA_PLAN",
    "GUI_GAP_PLAN",
    "PORTING_",
    "PORTING",
    "CLAUDE.md",
    "AGENTS.md",
    "GhostC",
    "Zmux",
    "local-only",
    "worksite",
)
PUBLIC_ROADMAP_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Available Now",
        (
            "WS-025",
            "WS-026",
            "WS-027",
            "WS-031",
            "WS-032",
            "WS-033",
            "WS-034",
            "WS-039",
            "WS-041",
            "WS-047",
            "WS-051",
            "WS-053",
            "WS-054",
            "WS-063",
            "WS-064",
            "WS-065",
            "WS-066",
            "WS-067",
            "WS-068",
            "WS-096",
            "WS-099",
            "WS-100",
            "WS-103",
            "WS-104",
            "WS-105",
            "WS-106",
            "WS-110",
        ),
    ),
    (
        "Next",
        (
            "WS-012",
            "WS-014",
            "WS-015",
            "WS-016",
            "WS-019",
            "WS-021",
            "WS-028",
            "WS-036",
            "WS-040",
            "WS-042",
            "WS-043",
            "WS-045",
            "WS-046",
            "WS-078",
            "WS-079",
            "WS-080",
            "WS-107",
            "WS-108",
            "WS-109",
        ),
    ),
    (
        "Later",
        (
            "WS-044",
            "WS-060",
            "WS-061",
            "WS-112",
            "WS-113",
            "WS-114",
            "WS-115",
            "WS-116",
            "WS-117",
            "WS-118",
            "WS-119",
            "WS-120",
            "WS-121",
        ),
    ),
)
PUBLIC_ROADMAP_TITLES = {
    "WS-104": "Multiplexer Scenario",
    "WS-105": "Polished Agent UX Scenario",
}


@dataclass(frozen=True)
class Worksite:
    id: str
    title: str
    status: str
    checked: bool
    outcome: str = ""
    scope: str = ""
    owner: str = ""
    linked_pr: str = ""
    validation: str = ""

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "checked": self.checked,
            "outcome": self.outcome,
            "scope": self.scope,
            "owner": self.owner,
            "linked_pr": self.linked_pr,
            "validation": self.validation,
        }


@dataclass(frozen=True)
class WorksiteIssue:
    worksite_id: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"worksite_id": self.worksite_id, "message": self.message}


def parse_worksites(markdown: str) -> list[Worksite]:
    blocks: list[tuple[str, str, list[str]]] = []
    current_id = ""
    current_title = ""
    current_lines: list[str] = []
    for line in markdown.splitlines():
        heading = WORKSITE_HEADING.match(line)
        if heading:
            if current_id:
                blocks.append((current_id, current_title, current_lines))
            current_id = heading.group(1)
            current_title = heading.group(2)
            current_lines = []
            continue
        if current_id:
            current_lines.append(line)
    if current_id:
        blocks.append((current_id, current_title, current_lines))
    return [_parse_worksite_block(worksite_id, title, lines) for worksite_id, title, lines in blocks]


def check_worksite_tracking(worksites: Iterable[Worksite]) -> list[WorksiteIssue]:
    issues: list[WorksiteIssue] = []
    for worksite in worksites:
        if worksite.status != "active":
            continue
        if not worksite.owner:
            issues.append(WorksiteIssue(worksite.id, "active worksite is missing Owner"))
        if not worksite.linked_pr:
            issues.append(WorksiteIssue(worksite.id, "active worksite is missing Linked PR"))
    return issues


def worksite_summary(worksites: Iterable[Worksite]) -> dict[str, int]:
    items = list(worksites)
    summary = {"total": len(items), "done": 0, "active": 0, "blocked": 0, "open": 0, "unknown": 0, "issues": 0}
    issues = check_worksite_tracking(items)
    for worksite in items:
        if worksite.status in summary and worksite.status != "total":
            summary[worksite.status] += 1
        else:
            summary["unknown"] += 1
    summary["issues"] = len(issues)
    return summary


def public_roadmap_markdown(worksites: Iterable[Worksite]) -> str:
    """Render a curated public roadmap without internal tracker details."""
    by_id = {worksite.id: worksite for worksite in worksites}
    lines = [
        "# PyHerdr Roadmap",
        "",
        "This is a public, user-facing snapshot of where PyHerdr is headed.",
        "It focuses on product capabilities instead of implementation trackers.",
        "",
    ]
    for heading, ids in PUBLIC_ROADMAP_GROUPS:
        rows = [_public_row(by_id[worksite_id]) for worksite_id in ids if worksite_id in by_id]
        rows = [row for row in rows if row]
        if not rows:
            continue
        lines.extend([f"## {heading}", ""])
        lines.extend(rows)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _parse_worksite_block(worksite_id: str, title: str, lines: list[str]) -> Worksite:
    checked = False
    outcome = ""
    fields: dict[str, str] = {}
    for line in lines:
        outcome_match = OUTCOME_LINE.match(line)
        if outcome_match:
            checked = outcome_match.group("checked").lower() == "x"
            outcome = outcome_match.group("outcome").strip()
            continue
        field_match = FIELD_LINE.match(line)
        if field_match:
            fields[field_match.group("name").lower()] = field_match.group("value").strip()
    explicit_status = fields.get("status", "").lower()
    status = _normalize_status(explicit_status) if explicit_status else ("done" if checked else "open")
    linked_pr = fields.get("linked pr") or fields.get("pr") or ""
    return Worksite(
        id=worksite_id,
        title=title,
        status=status,
        checked=checked,
        outcome=outcome,
        scope=fields.get("scope", ""),
        owner=fields.get("owner", ""),
        linked_pr=linked_pr,
        validation=fields.get("validation", ""),
    )


def _public_row(worksite: Worksite) -> str:
    title = _public_text(PUBLIC_ROADMAP_TITLES.get(worksite.id, worksite.title))
    outcome = _public_text(worksite.outcome)
    if not title or not outcome:
        return ""
    return f"- **{title}** — {outcome}"


def _public_text(value: str) -> str:
    text = value.replace("`", "").strip()
    for forbidden in FORBIDDEN_PUBLIC_ROADMAP_TERMS:
        if forbidden.lower() in text.lower():
            return ""
    return text


def _normalize_status(value: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    aliases = {
        "in progress": "active",
        "wip": "active",
        "todo": "open",
        "pending": "open",
        "complete": "done",
        "completed": "done",
    }
    return aliases.get(normalized, normalized or "unknown")
