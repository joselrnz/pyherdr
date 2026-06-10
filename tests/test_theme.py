import unittest

from pyherdr.config.theme import BUILTIN_THEMES, DEFAULT_THEME, OCEAN_BLUE, THEME_NAMES, ThemeConfig


class ThemeTests(unittest.TestCase):
    def test_default_theme_is_ocean_blue(self):
        self.assertEqual(DEFAULT_THEME, "ocean-blue")
        self.assertIs(BUILTIN_THEMES[DEFAULT_THEME], OCEAN_BLUE)
        self.assertEqual(THEME_NAMES[0], DEFAULT_THEME)
        self.assertEqual(ThemeConfig().resolve(), OCEAN_BLUE)

    def test_unknown_theme_falls_back_to_default(self):
        self.assertEqual(ThemeConfig(name="missing-theme").resolve(), OCEAN_BLUE)

