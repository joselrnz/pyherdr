from __future__ import annotations

import re

from .models import AgentStatus

BLOCKED_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bapproval required\b",
        r"\bpermission required\b",
        r"\bconfirm\b",
        r"\bdo you want to\b",
        r"\bwaiting for input\b",
        r"\bblocked\b",
    )
]

DONE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcompleted\b",
        r"\bdone\b",
        r"\bfinished\b",
        r"\btests? passed\b",
        r"\bbuild succeeded\b",
    )
]

WORKING_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\brunning\b",
        r"\bworking\b",
        r"\bthinking\b",
        r"\bbuilding\b",
        r"\binstalling\b",
        r"\bcompiling\b",
    )
]


def detect_agent_status(text: str) -> AgentStatus:
    """Infer a pane status from recent visible output."""
    recent = "\n".join(text.splitlines()[-40:])
    if _matches_any(BLOCKED_PATTERNS, recent):
        return AgentStatus.BLOCKED
    if _matches_any(DONE_PATTERNS, recent):
        return AgentStatus.DONE
    if _matches_any(WORKING_PATTERNS, recent):
        return AgentStatus.WORKING
    return AgentStatus.IDLE if recent.strip() else AgentStatus.UNKNOWN


def _matches_any(patterns: list[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) for pattern in patterns)
