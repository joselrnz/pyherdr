"""Configuration: settings, themes, and sounds (ported from herdr src/config)."""

from .io import config_path, load_config
from .settings import (
    AdvancedConfig,
    AgentPanelScope,
    Config,
    ExperimentalConfig,
    KeysConfig,
    RemoteConfig,
    SessionConfig,
    ShellMode,
    TerminalConfig,
    ToastConfig,
    ToastDelivery,
    UiConfig,
    UpdateChannel,
    UpdateConfig,
    WorktreesConfig,
)
from .sound import AgentSoundOverrides, AgentSoundSetting, SoundConfig
from .theme import BUILTIN_THEMES, DEFAULT_THEME, CustomThemeColors, Palette, ThemeConfig, parse_color

__all__ = [
    "BUILTIN_THEMES",
    "AdvancedConfig",
    "AgentPanelScope",
    "AgentSoundOverrides",
    "AgentSoundSetting",
    "Config",
    "CustomThemeColors",
    "DEFAULT_THEME",
    "ExperimentalConfig",
    "KeysConfig",
    "Palette",
    "RemoteConfig",
    "SessionConfig",
    "ShellMode",
    "SoundConfig",
    "TerminalConfig",
    "ThemeConfig",
    "ToastConfig",
    "ToastDelivery",
    "UiConfig",
    "UpdateChannel",
    "UpdateConfig",
    "WorktreesConfig",
    "config_path",
    "load_config",
    "parse_color",
]
