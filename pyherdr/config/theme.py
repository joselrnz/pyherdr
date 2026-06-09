"""Theme palette and color parsing (ported from herdr src/config/theme.rs).

Catppuccin Mocha is the default, matching herdr. Built-in themes provide canonical
palettes; `ThemeConfig` selects one and applies per-token custom overrides.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


def parse_color(value: str) -> str:
    """Normalize a color string to ``#rrggbb`` where possible.

    Accepts hex (``#rgb`` / ``#rrggbb``), ``rgb(r,g,b)``, reset aliases
    (returned as ``""``), or a named color (returned lowercased for the UI).
    """
    text = value.strip().lower()
    if text in ("reset", "default", "none", "transparent"):
        return ""
    if text.startswith("#"):
        body = text[1:]
        if len(body) == 6 and all(ch in "0123456789abcdef" for ch in body):
            return f"#{body}"
        if len(body) == 3 and all(ch in "0123456789abcdef" for ch in body):
            return "#" + "".join(ch * 2 for ch in body)
    if text.startswith("rgb(") and text.endswith(")"):
        parts = [part.strip() for part in text[4:-1].split(",")]
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            r, g, b = (max(0, min(255, int(part))) for part in parts)
            return f"#{r:02x}{g:02x}{b:02x}"
    return text


class Palette(BaseModel):
    """A resolved color palette (named tokens used across the UI)."""

    model_config = ConfigDict(extra="ignore")

    accent: str
    panel_bg: str
    surface0: str
    surface1: str
    surface_dim: str
    overlay0: str
    overlay1: str
    text: str
    subtext0: str
    mauve: str
    green: str
    yellow: str
    red: str
    blue: str
    teal: str
    peach: str


# Catppuccin Mocha — herdr's default theme.
CATPPUCCIN_MOCHA = Palette(
    accent="#f5c2e7",
    panel_bg="#1e1e2e",
    surface0="#313244",
    surface1="#45475a",
    surface_dim="#181825",
    overlay0="#6c7086",
    overlay1="#7f849c",
    text="#cdd6f4",
    subtext0="#a6adc8",
    mauve="#cba6f7",
    green="#a6e3a1",
    yellow="#f9e2af",
    red="#f38ba8",
    blue="#89b4fa",
    teal="#94e2d5",
    peach="#fab387",
)

TOKYO_NIGHT = Palette(
    accent="#bb9af7",
    panel_bg="#1a1b26",
    surface0="#24283b",
    surface1="#414868",
    surface_dim="#16161e",
    overlay0="#565f89",
    overlay1="#737aa2",
    text="#c0caf5",
    subtext0="#a9b1d6",
    mauve="#bb9af7",
    green="#9ece6a",
    yellow="#e0af68",
    red="#f7768e",
    blue="#7aa2f7",
    teal="#73daca",
    peach="#ff9e64",
)

DRACULA = Palette(
    accent="#ff79c6",
    panel_bg="#282a36",
    surface0="#44475a",
    surface1="#6272a4",
    surface_dim="#21222c",
    overlay0="#6272a4",
    overlay1="#7b88b8",
    text="#f8f8f2",
    subtext0="#c8c8c2",
    mauve="#bd93f9",
    green="#50fa7b",
    yellow="#f1fa8c",
    red="#ff5555",
    blue="#8be9fd",
    teal="#8be9fd",
    peach="#ffb86c",
)

NORD = Palette(
    accent="#88c0d0",
    panel_bg="#2e3440",
    surface0="#3b4252",
    surface1="#434c5e",
    surface_dim="#272c36",
    overlay0="#4c566a",
    overlay1="#616e88",
    text="#d8dee9",
    subtext0="#aebacf",
    mauve="#b48ead",
    green="#a3be8c",
    yellow="#ebcb8b",
    red="#bf616a",
    blue="#81a1c1",
    teal="#8fbcbb",
    peach="#d08770",
)

CATPPUCCIN_LATTE = Palette(
    accent="#1e66f5", panel_bg="#eff1f5", surface0="#ccd0da", surface1="#bcc0cc", surface_dim="#e6e9ef",
    overlay0="#9ca0b0", overlay1="#8c8fa1", text="#4c4f69", subtext0="#6c6f85", mauve="#8839ef",
    green="#40a02b", yellow="#df8e1d", red="#d20f39", blue="#1e66f5", teal="#179299", peach="#fe640b",
)

TOKYO_NIGHT_DAY = Palette(
    accent="#2e7de9", panel_bg="#e1e2e7", surface0="#c4c8da", surface1="#a8aecb", surface_dim="#d2d3da",
    overlay0="#8990b3", overlay1="#6870a0", text="#3760bf", subtext0="#6172b0", mauve="#7847bd",
    green="#587539", yellow="#8c6c3e", red="#f52a65", blue="#2e7de9", teal="#118c74", peach="#b15c00",
)

GRUVBOX_DARK = Palette(
    accent="#d79921", panel_bg="#282828", surface0="#3c3836", surface1="#504945", surface_dim="#1d2021",
    overlay0="#928374", overlay1="#a89984", text="#ebdbb2", subtext0="#d5c4a1", mauve="#d3869b",
    green="#b8bb26", yellow="#fabd2f", red="#fb4934", blue="#83a598", teal="#8ec07c", peach="#fe8019",
)

GRUVBOX_LIGHT = Palette(
    accent="#076678", panel_bg="#fbf1c7", surface0="#ebdbb2", surface1="#d5c4a1", surface_dim="#f2e5bc",
    overlay0="#928374", overlay1="#7c6f64", text="#3c3836", subtext0="#504945", mauve="#8f3f71",
    green="#79740e", yellow="#b57614", red="#9d0006", blue="#076678", teal="#427b58", peach="#af3a03",
)

ONE_DARK = Palette(
    accent="#61afef", panel_bg="#282c34", surface0="#2c313a", surface1="#3e4452", surface_dim="#21252b",
    overlay0="#5c6370", overlay1="#737a8f", text="#abb2bf", subtext0="#969cbf", mauve="#c678dd",
    green="#98c379", yellow="#e5c07b", red="#e06c75", blue="#61afef", teal="#56b6c2", peach="#d19a66",
)

ONE_LIGHT = Palette(
    accent="#4078f2", panel_bg="#fafafa", surface0="#f0f0f1", surface1="#e5e5e6", surface_dim="#f5f5f6",
    overlay0="#a0a1a7", overlay1="#686b77", text="#383a42", subtext0="#686b77", mauve="#a626a4",
    green="#50a14f", yellow="#c18401", red="#e45649", blue="#4078f2", teal="#0184bc", peach="#986801",
)

SOLARIZED_DARK = Palette(
    accent="#268bd2", panel_bg="#002b36", surface0="#073642", surface1="#586e75", surface_dim="#00212b",
    overlay0="#586e75", overlay1="#657b83", text="#93a1a1", subtext0="#839496", mauve="#d33682",
    green="#859900", yellow="#b58900", red="#dc322f", blue="#268bd2", teal="#2aa198", peach="#cb4b16",
)

SOLARIZED_LIGHT = Palette(
    accent="#268bd2", panel_bg="#fdf6e3", surface0="#eee8d5", surface1="#93a1a1", surface_dim="#eee8d5",
    overlay0="#93a1a1", overlay1="#586e75", text="#657b83", subtext0="#839496", mauve="#d33682",
    green="#859900", yellow="#b58900", red="#dc322f", blue="#268bd2", teal="#2aa198", peach="#cb4b16",
)

KANAGAWA = Palette(
    accent="#7e9cd8", panel_bg="#1f1f28", surface0="#2a2a37", surface1="#363646", surface_dim="#16161d",
    overlay0="#727169", overlay1="#87876d", text="#dcd7ba", subtext0="#c8c093", mauve="#957fb8",
    green="#76946a", yellow="#c0a36e", red="#c34043", blue="#7e9cd8", teal="#7fb4ca", peach="#ffa066",
)

ROSE_PINE = Palette(
    accent="#c4a7e7", panel_bg="#191724", surface0="#1f1d2e", surface1="#26233a", surface_dim="#16141f",
    overlay0="#6e6a86", overlay1="#908caa", text="#e0def4", subtext0="#c8c4dc", mauve="#c4a7e7",
    green="#31748f", yellow="#f6c177", red="#eb6f92", blue="#31748f", teal="#9ccfd8", peach="#ea9a97",
)

ROSE_PINE_DAWN = Palette(
    accent="#907aa9", panel_bg="#faf4ed", surface0="#f2e9e1", surface1="#fffaf3", surface_dim="#f2e9de",
    overlay0="#9893a5", overlay1="#797593", text="#575279", subtext0="#797593", mauve="#907aa9",
    green="#286983", yellow="#ea9d34", red="#b4637a", blue="#286983", teal="#56949f", peach="#d7827e",
)

VESPER = Palette(
    accent="#ffc799", panel_bg="#101010", surface0="#232323", surface1="#282828", surface_dim="#1c1c1c",
    overlay0="#5c5c5c", overlay1="#7e7e7e", text="#ffffff", subtext0="#a0a0a0", mauve="#ffc799",
    green="#99ffe4", yellow="#ffc799", red="#ff8080", blue="#a0a0a0", teal="#66ddcc", peach="#ffc799",
)

# Display order for the theme picker (canonical names).
THEME_NAMES: list[str] = [
    "catppuccin",
    "catppuccin-latte",
    "tokyo-night",
    "tokyo-night-day",
    "dracula",
    "nord",
    "gruvbox",
    "gruvbox-light",
    "one-dark",
    "one-light",
    "solarized",
    "solarized-light",
    "kanagawa",
    "rose-pine",
    "rose-pine-dawn",
    "vesper",
]

BUILTIN_THEMES: dict[str, Palette] = {
    "catppuccin": CATPPUCCIN_MOCHA,
    "catppuccin-mocha": CATPPUCCIN_MOCHA,
    "mocha": CATPPUCCIN_MOCHA,
    "catppuccin-latte": CATPPUCCIN_LATTE,
    "latte": CATPPUCCIN_LATTE,
    "tokyo-night": TOKYO_NIGHT,
    "tokyonight": TOKYO_NIGHT,
    "tokyo-night-day": TOKYO_NIGHT_DAY,
    "tokyo-day": TOKYO_NIGHT_DAY,
    "dracula": DRACULA,
    "nord": NORD,
    "gruvbox": GRUVBOX_DARK,
    "gruvbox-dark": GRUVBOX_DARK,
    "gruvbox-light": GRUVBOX_LIGHT,
    "one-dark": ONE_DARK,
    "onedark": ONE_DARK,
    "one-light": ONE_LIGHT,
    "onelight": ONE_LIGHT,
    "solarized": SOLARIZED_DARK,
    "solarized-dark": SOLARIZED_DARK,
    "solarized-light": SOLARIZED_LIGHT,
    "kanagawa": KANAGAWA,
    "rose-pine": ROSE_PINE,
    "rosepine": ROSE_PINE,
    "rose-pine-dawn": ROSE_PINE_DAWN,
    "dawn": ROSE_PINE_DAWN,
    "vesper": VESPER,
}

DEFAULT_THEME = "catppuccin"


class CustomThemeColors(BaseModel):
    """Per-token overrides applied on top of the selected base theme."""

    model_config = ConfigDict(extra="ignore")

    accent: str | None = None
    panel_bg: str | None = None
    surface0: str | None = None
    surface1: str | None = None
    surface_dim: str | None = None
    overlay0: str | None = None
    overlay1: str | None = None
    text: str | None = None
    subtext0: str | None = None
    mauve: str | None = None
    green: str | None = None
    yellow: str | None = None
    red: str | None = None
    blue: str | None = None
    teal: str | None = None
    peach: str | None = None


class ThemeConfig(BaseModel):
    """Theme selection: a built-in name plus optional per-token overrides."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    custom: CustomThemeColors | None = None

    def resolve(self) -> Palette:
        """Resolve to a concrete `Palette` (base theme + overrides)."""
        base = BUILTIN_THEMES.get((self.name or DEFAULT_THEME).strip().lower(), CATPPUCCIN_MOCHA)
        if self.custom is None:
            return base
        overrides = {
            token: parse_color(value)
            for token, value in self.custom.model_dump().items()
            if value is not None
        }
        return base.model_copy(update=overrides)
