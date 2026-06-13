import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pyherdr.config.theme import (
    BUILTIN_THEMES,
    DEFAULT_THEME,
    OCEAN_BLUE,
    THEME_NAMES,
    ThemeConfig,
    theme_names,
    theme_registry,
)


class ThemeTests(unittest.TestCase):
    def test_default_theme_is_ocean_blue(self):
        self.assertEqual(DEFAULT_THEME, "ocean-blue")
        self.assertIs(BUILTIN_THEMES[DEFAULT_THEME], OCEAN_BLUE)
        self.assertEqual(THEME_NAMES[0], DEFAULT_THEME)
        self.assertEqual(ThemeConfig().resolve(), OCEAN_BLUE)

    def test_unknown_theme_falls_back_to_default(self):
        self.assertEqual(ThemeConfig(name="missing-theme").resolve(), OCEAN_BLUE)

    def test_theme_registry_includes_plugin_themes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "theme.py").write_text(
                "def themes():\n"
                "    return {'ops-dark': {\n"
                "        'accent': '#00ffff', 'panel_bg': '#101820', 'surface0': '#17232d',\n"
                "        'surface1': '#20313d', 'surface_dim': '#0b1117', 'overlay0': '#5d7788',\n"
                "        'overlay1': '#7894a7', 'text': '#e8f7ff', 'subtext0': '#a8c4d4',\n"
                "        'mauve': '#c4a7ff', 'green': '#70e08d', 'yellow': '#ffd166',\n"
                "        'red': '#ff6b8a', 'blue': '#5abfff', 'teal': '#2dd4bf', 'peach': '#ffb86b',\n"
                "    }}\n",
                encoding="utf-8",
            )
            manifest = root / "plugin.json"
            manifest.write_text(
                '{"name":"ops-themes","version":"1.0.0","kind":"theme","entrypoint":"theme.py"}',
                encoding="utf-8",
            )

            registry = theme_registry([str(manifest)])
            names = theme_names([str(manifest)])

        self.assertEqual(registry["ops-dark"].accent, "#00ffff")
        self.assertIn("ops-dark", names)
        self.assertEqual(ThemeConfig(name="ops-dark").resolve(registry).accent, "#00ffff")
