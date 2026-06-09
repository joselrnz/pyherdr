"""Per-agent terminal-state detection, ported from herdr's `src/detect`.

Recognizes which AI coding agent runs in a pane (`identify_agent`) and infers
its state (idle / working / blocked) from the live screen tail (`detect_state`).
"""

from ..domain.status import AgentStatus
from ._models import (
    Agent,
    AgentDetection,
    agent_label,
    identify_agent,
    identify_agent_in_command,
    parse_agent_label,
)
from .agents import detect, detect_state, should_skip_state_update

__all__ = [
    "Agent",
    "AgentDetection",
    "AgentStatus",
    "agent_label",
    "detect",
    "detect_state",
    "identify_agent",
    "identify_agent_in_command",
    "parse_agent_label",
    "should_skip_state_update",
]
