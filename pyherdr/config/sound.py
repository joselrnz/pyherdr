"""Sound notification config (ported from herdr src/config/sound.rs)."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from ..detect import Agent


class AgentSoundSetting(StrEnum):
    """Per-agent sound override."""

    DEFAULT = "default"
    ON = "on"
    OFF = "off"


class AgentSoundOverrides(BaseModel):
    """Per-agent sound settings. Droid defaults to off, matching herdr."""

    model_config = ConfigDict(extra="ignore")

    pi: AgentSoundSetting = AgentSoundSetting.DEFAULT
    claude: AgentSoundSetting = AgentSoundSetting.DEFAULT
    codex: AgentSoundSetting = AgentSoundSetting.DEFAULT
    gemini: AgentSoundSetting = AgentSoundSetting.DEFAULT
    cursor: AgentSoundSetting = AgentSoundSetting.DEFAULT
    agy: AgentSoundSetting = AgentSoundSetting.DEFAULT
    cline: AgentSoundSetting = AgentSoundSetting.DEFAULT
    open_code: AgentSoundSetting = AgentSoundSetting.DEFAULT
    github_copilot: AgentSoundSetting = AgentSoundSetting.DEFAULT
    kimi: AgentSoundSetting = AgentSoundSetting.DEFAULT
    kiro: AgentSoundSetting = AgentSoundSetting.DEFAULT
    droid: AgentSoundSetting = AgentSoundSetting.OFF
    amp: AgentSoundSetting = AgentSoundSetting.DEFAULT
    grok: AgentSoundSetting = AgentSoundSetting.DEFAULT
    hermes: AgentSoundSetting = AgentSoundSetting.DEFAULT
    kilo: AgentSoundSetting = AgentSoundSetting.DEFAULT
    qodercli: AgentSoundSetting = AgentSoundSetting.DEFAULT

    def for_agent(self, agent: Agent | None) -> AgentSoundSetting:
        """Return the setting for an agent (DEFAULT when unknown)."""
        if agent is None:
            return AgentSoundSetting.DEFAULT
        return getattr(self, _AGENT_FIELD[agent])


_AGENT_FIELD: dict[Agent, str] = {
    Agent.PI: "pi",
    Agent.CLAUDE: "claude",
    Agent.CODEX: "codex",
    Agent.GEMINI: "gemini",
    Agent.CURSOR: "cursor",
    Agent.ANTIGRAVITY: "agy",
    Agent.CLINE: "cline",
    Agent.OPENCODE: "open_code",
    Agent.GITHUB_COPILOT: "github_copilot",
    Agent.KIMI: "kimi",
    Agent.KIRO: "kiro",
    Agent.DROID: "droid",
    Agent.AMP: "amp",
    Agent.GROK: "grok",
    Agent.HERMES: "hermes",
    Agent.KILO: "kilo",
    Agent.QODERCLI: "qodercli",
}


class SoundConfig(BaseModel):
    """Sound playback configuration for background agent state changes."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    path: str | None = None
    done_path: str | None = None
    request_path: str | None = None
    agents: AgentSoundOverrides = AgentSoundOverrides()

    def allows(self, agent: Agent | None) -> bool:
        """Whether a sound should play for ``agent``."""
        if not self.enabled:
            return False
        return self.agents.for_agent(agent) is not AgentSoundSetting.OFF
