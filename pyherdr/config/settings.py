"""Top-level config schema (ported from herdr src/config/model.rs).

Pydantic models mirror herdr's `Config` sections and defaults. Loading is
lenient (unknown keys ignored) so newer/older config files still parse.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .sound import SoundConfig
from .theme import ThemeConfig

DEFAULT_MOBILE_WIDTH_THRESHOLD = 64
DEFAULT_MOUSE_SCROLL_LINES = 3
DEFAULT_SCROLLBACK_LIMIT_BYTES = 10_000_000
MAX_TOAST_DELAY_SECONDS = 3600


class UpdateChannel(StrEnum):
    STABLE = "stable"
    PREVIEW = "preview"


class ToastDelivery(StrEnum):
    OFF = "off"
    HERDR = "herdr"
    TERMINAL = "terminal"
    SYSTEM = "system"


class ToastHerdrPosition(StrEnum):
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


class ToastClipboardPosition(StrEnum):
    TOP_LEFT = "top-left"
    TOP_CENTER = "top-center"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_CENTER = "bottom-center"
    BOTTOM_RIGHT = "bottom-right"


class AgentPanelScope(StrEnum):
    CURRENT = "current"
    ALL = "all"


class ShellMode(StrEnum):
    AUTO = "auto"
    LOGIN = "login"
    NON_LOGIN = "non_login"


class ImeCursorShape(StrEnum):
    BLOCK = "block"
    STEADY_BLOCK = "steady_block"
    UNDERLINE = "underline"
    STEADY_UNDERLINE = "steady_underline"
    BAR = "bar"
    STEADY_BAR = "steady_bar"


class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class HerdrToastConfig(_Section):
    position: ToastHerdrPosition = ToastHerdrPosition.BOTTOM_RIGHT


class ClipboardToastConfig(_Section):
    enabled: bool = False
    position: ToastClipboardPosition = ToastClipboardPosition.BOTTOM_CENTER


class ToastConfig(_Section):
    delivery: ToastDelivery = ToastDelivery.OFF
    delay_seconds: int = 5
    herdr: HerdrToastConfig = HerdrToastConfig()
    clipboard: ClipboardToastConfig = ClipboardToastConfig()


class TerminalConfig(_Section):
    default_shell: str = ""
    shell_mode: ShellMode = ShellMode.AUTO
    new_cwd: str = "follow"
    # pyherdr extension: environment variables injected into every pane's shell.
    env: dict[str, str] = Field(default_factory=dict)


class SessionConfig(_Section):
    resume_agents_on_restore: bool = True


class UpdateConfig(_Section):
    channel: UpdateChannel = UpdateChannel.STABLE


class WorktreesConfig(_Section):
    directory: str = ""


class UiConfig(_Section):
    sidebar_width: int = 30
    sidebar_min_width: int = 18
    sidebar_max_width: int = 36
    mobile_width_threshold: int = DEFAULT_MOBILE_WIDTH_THRESHOLD
    mouse_capture: bool = True
    right_click_passthrough_modifier: str = ""
    redraw_on_focus_gained: bool = True
    mouse_scroll_lines: int = DEFAULT_MOUSE_SCROLL_LINES
    confirm_close: bool = True
    prompt_new_tab_name: bool = True
    show_agent_labels_on_pane_borders: bool = False
    agent_panel_scope: AgentPanelScope = AgentPanelScope.ALL
    accent: str = "#f5c2e7"
    toast: ToastConfig = ToastConfig()
    sound: SoundConfig = SoundConfig()


class AdvancedConfig(_Section):
    scrollback_limit_bytes: int = DEFAULT_SCROLLBACK_LIMIT_BYTES


class RemoteConfig(_Section):
    manage_ssh_config: bool = True


class ExperimentalConfig(_Section):
    allow_nested: bool = False
    kitty_graphics: bool = False
    pane_history: bool = False
    force_ime_anchor: bool = False
    ime_cursor_shape: ImeCursorShape = ImeCursorShape.STEADY_BLOCK


class CommandBinding(_Section):
    """A user-defined command bound to a prefix key (``[[keys.commands]]``)."""

    key: str
    command: str
    description: str = ""


class KeysConfig(_Section):
    """Keybinding config: custom prefix, action→key overrides, and commands."""

    prefix: str = "ctrl+b"
    # action name -> prefix key override, e.g. {"new_tab": "t"}.
    bindings: dict[str, str] = Field(default_factory=dict)
    # user commands run in a new tab when their prefix key is pressed.
    commands: list[CommandBinding] = Field(default_factory=list)


class Config(_Section):
    """The top-level PyHerdr/Herdr configuration."""

    onboarding: bool | None = None
    theme: ThemeConfig = ThemeConfig()
    terminal: TerminalConfig = TerminalConfig()
    session: SessionConfig = SessionConfig()
    update: UpdateConfig = UpdateConfig()
    keys: KeysConfig = KeysConfig()
    ui: UiConfig = UiConfig()
    worktrees: WorktreesConfig = WorktreesConfig()
    advanced: AdvancedConfig = AdvancedConfig()
    experimental: ExperimentalConfig = ExperimentalConfig()
    remote: RemoteConfig = RemoteConfig()
