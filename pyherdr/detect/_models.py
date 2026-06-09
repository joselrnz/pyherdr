"""Agent identity and the detection result (ported from herdr src/detect/mod.rs)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..domain.status import AgentStatus


class Agent(StrEnum):
    """An AI coding agent PyHerdr can recognize in a pane. Values are labels."""

    PI = "pi"
    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"
    CURSOR = "cursor"
    ANTIGRAVITY = "agy"
    CLINE = "cline"
    OPENCODE = "opencode"
    GITHUB_COPILOT = "copilot"
    KIMI = "kimi"
    KIRO = "kiro"
    DROID = "droid"
    AMP = "amp"
    GROK = "grok"
    HERMES = "hermes"
    KILO = "kilo"
    QODERCLI = "qodercli"


@dataclass(frozen=True)
class AgentDetection:
    """Screen-derived agent state plus confidence metadata (herdr AgentDetection)."""

    state: AgentStatus
    skip_state_update: bool = False
    visible_blocker: bool = False
    visible_idle: bool = False
    visible_working: bool = False


# Binary/label aliases -> Agent, mirroring herdr identify_agent / parse_agent_label.
_LOOKUP: dict[str, Agent] = {
    "pi": Agent.PI,
    "claude": Agent.CLAUDE,
    "claude-code": Agent.CLAUDE,
    "codex": Agent.CODEX,
    "gemini": Agent.GEMINI,
    "cursor": Agent.CURSOR,
    "cursor-agent": Agent.CURSOR,
    "agy": Agent.ANTIGRAVITY,
    "antigravity": Agent.ANTIGRAVITY,
    "antigravity-cli": Agent.ANTIGRAVITY,
    "cline": Agent.CLINE,
    "opencode": Agent.OPENCODE,
    "open-code": Agent.OPENCODE,
    "copilot": Agent.GITHUB_COPILOT,
    "github-copilot": Agent.GITHUB_COPILOT,
    "ghcs": Agent.GITHUB_COPILOT,
    "kimi": Agent.KIMI,
    "kimi-code": Agent.KIMI,
    "kimi code": Agent.KIMI,
    "kiro": Agent.KIRO,
    "kiro-cli": Agent.KIRO,
    "droid": Agent.DROID,
    "amp": Agent.AMP,
    "amp-local": Agent.AMP,
    "grok": Agent.GROK,
    "grok-build": Agent.GROK,
    "hermes": Agent.HERMES,
    "hermes-agent": Agent.HERMES,
    "kilo": Agent.KILO,
    "kilo-code": Agent.KILO,
    "kilo code": Agent.KILO,
    "qodercli": Agent.QODERCLI,
    "qoderclicn": Agent.QODERCLI,
    "qoder": Agent.QODERCLI,
    "qodercn": Agent.QODERCLI,
}


def _normalized_lookup_name(name: str) -> str:
    normalized = name.strip().lower()
    if normalized.endswith(".exe"):
        normalized = normalized[: -len(".exe")]
    return normalized


def agent_label(agent: Agent) -> str:
    """Return the short label for an agent."""
    return agent.value


def parse_agent_label(name: str) -> Agent | None:
    """Resolve an agent from a label/alias, or ``None``."""
    return _LOOKUP.get(_normalized_lookup_name(name))


def identify_agent(process_name: str) -> Agent | None:
    """Identify the agent from a process/binary name, or ``None`` for shells."""
    return _LOOKUP.get(_normalized_lookup_name(process_name))


def identify_agent_in_command(command: str) -> Agent | None:
    """Identify the agent from a command line by inspecting argv[0]'s basename."""
    parts = command.split()
    if not parts:
        return None
    basename = parts[0].replace("\\", "/").rsplit("/", 1)[-1]
    return identify_agent(basename)


# Re-export for callers that want detection's state vocabulary.
__all__ = [
    "Agent",
    "AgentDetection",
    "AgentStatus",
    "agent_label",
    "identify_agent",
    "identify_agent_in_command",
    "parse_agent_label",
]
