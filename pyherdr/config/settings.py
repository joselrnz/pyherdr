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
DEFAULT_WORKSPACE_SEARCH_IGNORE = [
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
]


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


class PaneAppearance(StrEnum):
    SUBTLE = "subtle"
    VISIBLE = "visible"
    ACCENT = "accent"


class ShellMode(StrEnum):
    AUTO = "auto"
    LOGIN = "login"
    NON_LOGIN = "non_login"


class ConnectionType(StrEnum):
    LOCAL = "local"
    SSH = "ssh"


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


class ConnectionConfig(_Section):
    type: ConnectionType = ConnectionType.SSH
    host: str = ""
    user: str = ""
    port: int = 22
    key: str = ""
    proxy_jump: str = ""
    extra_args: list[str] = Field(default_factory=list)
    connect_timeout: int = 10
    batch_mode: bool = False
    strict_host_key_checking: str = ""
    server_alive_interval: int = 0
    server_alive_count_max: int = 0
    request_tty: bool = False
    remote_cwd: str = ""
    # Deliberately parsed so validation can reject raw password storage.
    password: str = ""


class ProfilePaneConfig(_Section):
    name: str
    connection: str = ""
    command: str = ""
    cwd: str = ""
    position: str = ""
    tab: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    start_order: int = 0
    health_check: str = ""
    health_match: str = ""
    health_timeout_ms: int = 10000
    health_regex: bool = False


class ProfileConfig(_Section):
    workspace: str = ""
    cwd: str = ""
    layout: str = ""
    env: dict[str, str] = Field(default_factory=dict)
    panes: list[ProfilePaneConfig] = Field(default_factory=list)


class WorkflowStepConfig(_Section):
    pane: str
    send: str = ""
    command: str = ""
    enter: bool = True


class WorkflowConfig(_Section):
    profile: str = ""
    steps: list[WorkflowStepConfig] = Field(default_factory=list)


class LayoutConfig(_Section):
    label: str = ""
    pane_count: int = 0
    layout: dict[str, object] = Field(default_factory=dict)


class WorkspaceConfig(_Section):
    search_roots: list[str] = Field(default_factory=list)
    search_ignore: list[str] = Field(default_factory=lambda: list(DEFAULT_WORKSPACE_SEARCH_IGNORE))
    search_max_depth: int = 3
    search_max_results: int = 80
    search_include_hidden: bool = False
    search_cache_ttl_seconds: int = 300


class UiConfig(_Section):
    sidebar_width: int = 38
    sidebar_min_width: int = 18
    sidebar_max_width: int = 44
    mobile_width_threshold: int = DEFAULT_MOBILE_WIDTH_THRESHOLD
    mouse_capture: bool = True
    right_click_passthrough_modifier: str = ""
    redraw_on_focus_gained: bool = True
    mouse_scroll_lines: int = DEFAULT_MOUSE_SCROLL_LINES
    confirm_close: bool = True
    prompt_new_tab_name: bool = True
    pane_separator: PaneAppearance = PaneAppearance.SUBTLE
    pane_border: PaneAppearance = PaneAppearance.SUBTLE
    show_agent_labels_on_pane_borders: bool = False
    agent_panel_scope: AgentPanelScope = AgentPanelScope.CURRENT
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


class LauncherPresetConfig(_Section):
    """A configured launcher preset shown in the TUI picker."""

    id: str = ""
    label: str = ""
    command: str
    description: str = ""
    agent: str = ""


class LaunchersConfig(_Section):
    """User-defined launcher presets."""

    presets: list[LauncherPresetConfig] = Field(default_factory=list)


class PluginsConfig(_Section):
    """Configured plugin manifest paths."""

    detectors: list[str] = Field(default_factory=list)
    launchers: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    exporters: list[str] = Field(default_factory=list)


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
    launchers: LaunchersConfig = LaunchersConfig()
    plugins: PluginsConfig = PluginsConfig()
    ui: UiConfig = UiConfig()
    workspace: WorkspaceConfig = WorkspaceConfig()
    worktrees: WorktreesConfig = WorktreesConfig()
    advanced: AdvancedConfig = AdvancedConfig()
    experimental: ExperimentalConfig = ExperimentalConfig()
    remote: RemoteConfig = RemoteConfig()
    connections: dict[str, ConnectionConfig] = Field(default_factory=dict)
    layouts: dict[str, LayoutConfig] = Field(default_factory=dict)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)
    workflows: dict[str, WorkflowConfig] = Field(default_factory=dict)
