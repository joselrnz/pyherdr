from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

WORKSITE_HEADING = re.compile(r"^###\s+(WS-\d{3})\s+(.+?)\s*$")
OUTCOME_LINE = re.compile(r"^-\s+\[(?P<checked>[ xX])\]\s+Outcome:\s*(?P<outcome>.+?)\s*$")
FIELD_LINE = re.compile(r"^-\s+(?P<name>Status|Owner|Linked PR|PR|Scope|Validation):\s*(?P<value>.+?)\s*$")


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
