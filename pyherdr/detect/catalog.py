"""Structured catalog of registered terminal-state detectors."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ..domain.status import AgentStatus
from ._models import Agent
from .agents import _DETECTORS


@dataclass(frozen=True)
class DetectorSignal:
    """A named screen signal that can drive a detector status."""

    status: AgentStatus
    name: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {"status": self.status.value, "name": self.name, "description": self.description}


@dataclass(frozen=True)
class DetectorCatalogEntry:
    """Audit row for a named detector and its confidence metadata hooks."""

    agent: Agent
    agent_name: str
    source_module: str
    detector_function: str
    herdr_source: str
    herdr_function: str
    statuses: tuple[AgentStatus, ...]
    signals: tuple[DetectorSignal, ...]
    confidence_fields: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    @property
    def source_function(self) -> str:
        return f"{self.source_module}.{self.detector_function}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent.value,
            "agent_name": self.agent_name,
            "source_module": self.source_module,
            "source_function": self.source_function,
            "detector_function": self.detector_function,
            "herdr_source": self.herdr_source,
            "herdr_function": self.herdr_function,
            "statuses": [status.value for status in self.statuses],
            "signals": [signal.as_dict() for signal in self.signals],
            "confidence_fields": list(self.confidence_fields),
            "metadata": dict(self.metadata),
        }


BLOCKED = AgentStatus.BLOCKED
WORKING = AgentStatus.WORKING
IDLE = AgentStatus.IDLE

SOURCE_MODULE = "pyherdr.detect.agents"
CONFIDENCE_FIELDS = ("skip_state_update", "visible_blocker", "visible_idle", "visible_working")


def _signal(status: AgentStatus, name: str, description: str) -> DetectorSignal:
    return DetectorSignal(status=status, name=name, description=description)


def _metadata(**items: str) -> Mapping[str, str]:
    return MappingProxyType(items)


_HERDR_SOURCES: dict[Agent, str] = {
    Agent.PI: "src/detect/agents/pi.rs",
    Agent.CLAUDE: "src/detect/agents/claude_code.rs",
    Agent.CODEX: "src/detect/agents/codex.rs",
    Agent.GEMINI: "src/detect/agents/gemini.rs",
    Agent.CURSOR: "src/detect/agents/cursor.rs",
    Agent.ANTIGRAVITY: "src/detect/agents/antigravity.rs",
    Agent.CLINE: "src/detect/agents/cline.rs",
    Agent.OPENCODE: "src/detect/agents/opencode.rs",
    Agent.GITHUB_COPILOT: "src/detect/agents/github_copilot.rs",
    Agent.KIMI: "src/detect/agents/kimi.rs",
    Agent.KIRO: "src/detect/agents/kiro.rs",
    Agent.DROID: "src/detect/agents/droid.rs",
    Agent.AMP: "src/detect/agents/amp.rs",
    Agent.GROK: "src/detect/agents/grok.rs",
    Agent.HERMES: "src/detect/agents/hermes.rs",
    Agent.KILO: "src/detect/agents/kilo.rs",
    Agent.QODERCLI: "src/detect/agents/qodercli.rs",
}

_SIGNALS: dict[Agent, tuple[DetectorSignal, ...]] = {
    Agent.PI: (
        _signal(WORKING, "working_marker", "literal Working... marker is present"),
        _signal(IDLE, "default_idle", "no Pi working marker is present"),
    ),
    Agent.CLAUDE: (
        _signal(BLOCKED, "visible_blocker", "Claude permission or question UI is visible"),
        _signal(WORKING, "working_chrome", "Claude spinner, interrupt footer, or running-shell chrome is visible"),
        _signal(IDLE, "prompt_box", "Claude prompt/input box is visible"),
    ),
    Agent.CODEX: (
        _signal(BLOCKED, "strong_blocked", "permission or confirmation prompt visible in the current Codex screen"),
        _signal(WORKING, "working_status", "Codex working status, approval review, or background wait is live"),
        _signal(IDLE, "current_prompt", "Codex input prompt is visible"),
    ),
    Agent.GEMINI: (
        _signal(BLOCKED, "confirmation_prompt", "Gemini confirmation or apply/allow prompt is visible"),
        _signal(WORKING, "cancel_hint", "Gemini escape-to-cancel hint is visible"),
        _signal(IDLE, "default_idle", "no Gemini blocked or working signal is present"),
    ),
    Agent.CURSOR: (
        _signal(BLOCKED, "approval_prompt", "Cursor approval or run-command prompt is visible"),
        _signal(WORKING, "spinner_or_stop_hint", "Cursor active spinner or ctrl+c stop hint is visible"),
        _signal(IDLE, "default_idle", "no Cursor blocked or working signal is present"),
    ),
    Agent.ANTIGRAVITY: (
        _signal(BLOCKED, "permission_prompt", "Antigravity permission/request prompt is visible"),
        _signal(WORKING, "spinner", "Antigravity thinking spinner or active status is visible"),
        _signal(IDLE, "default_idle", "no Antigravity blocked or working signal is present"),
    ),
    Agent.CLINE: (
        _signal(BLOCKED, "tool_permission", "Cline tool or mode confirmation prompt is visible"),
        _signal(WORKING, "default_working", "Cline defaults to working when not blocked or idle"),
        _signal(IDLE, "ready_message", "Cline ready-for-message text is visible"),
    ),
    Agent.OPENCODE: (
        _signal(BLOCKED, "permission_or_question", "OpenCode permission or structured question prompt is visible"),
        _signal(WORKING, "interrupt_or_progress", "OpenCode interrupt footer or progress run is visible"),
        _signal(IDLE, "default_idle", "no OpenCode blocked or working signal is present"),
    ),
    Agent.GITHUB_COPILOT: (
        _signal(BLOCKED, "selection_prompt", "GitHub Copilot selection/submit prompt with cancel hint is visible"),
        _signal(WORKING, "cancel_hint", "GitHub Copilot cancel hint without a selection prompt is visible"),
        _signal(IDLE, "default_idle", "no GitHub Copilot blocked or working signal is present"),
    ),
    Agent.KIMI: (
        _signal(BLOCKED, "visible_blocker", "Kimi approval or question panel is visible"),
        _signal(WORKING, "working_status", "Kimi active glyph or working status is visible"),
        _signal(IDLE, "editor_box", "Kimi editor/input box is visible"),
    ),
    Agent.KIRO: (
        _signal(BLOCKED, "approval_prompt", "Kiro approval prompt with close/selection chrome is visible"),
        _signal(WORKING, "working_text", "Kiro working text or spinner is visible"),
        _signal(IDLE, "default_idle", "no Kiro blocked or working signal is present"),
    ),
    Agent.DROID: (
        _signal(BLOCKED, "execute_selection", "Droid execute prompt with selection controls is visible"),
        _signal(WORKING, "stop_hint", "Droid spinner or escape-to-stop hint is visible"),
        _signal(IDLE, "default_idle", "no Droid blocked or working signal is present"),
    ),
    Agent.AMP: (
        _signal(BLOCKED, "approval_actions", "Amp tool or command approval actions are visible"),
        _signal(WORKING, "cancel_hint", "Amp escape-to-cancel hint is visible"),
        _signal(IDLE, "default_idle", "no Amp blocked or working signal is present"),
    ),
    Agent.GROK: (
        _signal(BLOCKED, "permission_scope", "Grok permission scope or yes/no prompt is visible"),
        _signal(WORKING, "spinner_or_cancel", "Grok spinner or cancel/interject footer is visible"),
        _signal(IDLE, "default_idle", "no Grok blocked or working signal is present"),
    ),
    Agent.HERMES: (
        _signal(BLOCKED, "dangerous_command", "Hermes dangerous-command approval prompt is visible"),
        _signal(WORKING, "interrupt_hint", "Hermes interrupt/cancel hint is visible"),
        _signal(IDLE, "default_idle", "no Hermes blocked or working signal is present"),
    ),
    Agent.KILO: (
        _signal(BLOCKED, "opencode_permission", "Kilo delegates OpenCode permission/question detection"),
        _signal(WORKING, "interrupt_hint", "Kilo interrupt hint or delegated OpenCode working signal is visible"),
        _signal(IDLE, "default_idle", "no Kilo blocked or working signal is present"),
    ),
    Agent.QODERCLI: (
        _signal(BLOCKED, "permission_required", "Qoder CLI permission prompt is visible"),
        _signal(WORKING, "loading_or_cancel", "Qoder CLI loading/cancel status is visible"),
        _signal(IDLE, "idle_or_rewind", "Qoder CLI idle prompt or rewind hint is visible"),
    ),
}

_CONFIDENCE_METADATA: dict[Agent, Mapping[str, str]] = {
    Agent.CLAUDE: _metadata(
        confidence_blocker="claude_has_visible_blocker",
        confidence_idle="claude_has_prompt_box",
        confidence_working="claude_has_working_chrome",
        skip_state_update="claude_is_transcript_viewer",
    ),
    Agent.CODEX: _metadata(
        confidence_blocker="codex_has_visible_blocker",
        confidence_idle="codex_has_prompt",
        confidence_working="codex_has_visible_working",
        skip_state_update="codex_is_transcript_viewer",
    ),
    Agent.KIMI: _metadata(
        confidence_blocker="kimi_has_visible_blocker",
        confidence_idle="kimi_has_prompt_box",
        confidence_working="kimi_working_status",
    ),
    Agent.KILO: _metadata(delegates_to="opencode"),
}


def _entry(agent: Agent) -> DetectorCatalogEntry:
    signals = _SIGNALS[agent]
    return DetectorCatalogEntry(
        agent=agent,
        agent_name=agent.value,
        source_module=SOURCE_MODULE,
        detector_function=_DETECTORS[agent].__name__,
        herdr_source=_HERDR_SOURCES[agent],
        herdr_function="detect",
        statuses=tuple(dict.fromkeys(signal.status for signal in signals)),
        signals=signals,
        confidence_fields=CONFIDENCE_FIELDS,
        metadata=_CONFIDENCE_METADATA.get(agent, MappingProxyType({})),
    )


_CATALOG: tuple[DetectorCatalogEntry, ...] = tuple(_entry(agent) for agent in Agent)


def detector_catalog() -> tuple[DetectorCatalogEntry, ...]:
    """Return detector audit rows in `Agent` declaration order."""
    return _CATALOG


def get_detector_catalog_entry(agent: Agent) -> DetectorCatalogEntry:
    """Return the catalog row for one known agent."""
    for entry in _CATALOG:
        if entry.agent is agent:
            return entry
    msg = f"no detector catalog entry for {agent.value!r}"
    raise KeyError(msg)


def detector_catalog_table() -> list[dict[str, Any]]:
    """Return JSON-friendly detector audit rows for docs/API use."""
    return [entry.as_dict() for entry in _CATALOG]


__all__ = [
    "DetectorCatalogEntry",
    "DetectorSignal",
    "detector_catalog",
    "detector_catalog_table",
    "get_detector_catalog_entry",
]
