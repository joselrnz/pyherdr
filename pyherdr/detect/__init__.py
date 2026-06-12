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
from .catalog import (
    DetectorCatalogEntry,
    DetectorSignal,
    detector_catalog,
    detector_catalog_table,
    get_detector_catalog_entry,
)

__all__ = [
    "Agent",
    "AgentDetection",
    "AgentStatus",
    "DetectorCatalogEntry",
    "DetectorSignal",
    "agent_label",
    "detect",
    "detector_catalog",
    "detector_catalog_table",
    "detect_state",
    "get_detector_catalog_entry",
    "identify_agent",
    "identify_agent_in_command",
    "parse_agent_label",
    "should_skip_state_update",
]
