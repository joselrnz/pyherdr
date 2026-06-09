from __future__ import annotations

from enum import StrEnum


class AgentStatus(StrEnum):
    """Semantic lifecycle state for an agent or pane."""

    BLOCKED = "blocked"
    WORKING = "working"
    DONE = "done"
    IDLE = "idle"
    UNKNOWN = "unknown"

    @property
    def priority(self) -> int:
        """Return the rollup priority used by workspace and tab summaries."""
        return {
            AgentStatus.BLOCKED: 50,
            AgentStatus.WORKING: 40,
            AgentStatus.DONE: 30,
            AgentStatus.IDLE: 20,
            AgentStatus.UNKNOWN: 10,
        }[self]

    @property
    def is_attention_required(self) -> bool:
        """Return whether this status should draw user attention."""
        return self in {AgentStatus.BLOCKED, AgentStatus.DONE}
