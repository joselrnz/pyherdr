import json
import unittest
from pathlib import Path

from pyherdr.runtime import TerminalScreen

FIXTURES = Path(__file__).parent / "fixtures" / "terminal"


class TerminalScreenTests(unittest.TestCase):
    def test_terminal_rendering_fixture_preserves_style_and_cursor(self):
        fixture = json.loads((FIXTURES / "styled_cursor.json").read_text(encoding="utf-8"))
        screen = TerminalScreen(rows=fixture["rows"], cols=fixture["cols"])

        screen.feed(fixture["feed"])

        self.assertEqual(screen.display(), fixture["display"])
        self.assertEqual(screen.snapshot(), fixture["snapshot"])
        rendered = screen.render_styled(cursor=True)
        for needle in fixture["styled_contains"]:
            self.assertIn(needle, rendered)

    def test_terminal_scrollback_fixture_preserves_viewport(self):
        fixture = json.loads((FIXTURES / "scrollback_viewport.json").read_text(encoding="utf-8"))
        screen = TerminalScreen(rows=fixture["rows"], cols=fixture["cols"])

        screen.feed(fixture["feed"])
        screen.scroll(fixture["scroll"])

        self.assertEqual(screen.display(), fixture["display"])
        viewport = screen.viewport()
        for key, value in fixture["viewport"].items():
            self.assertEqual(viewport[key], value)

    def test_feed_renders_lines(self):
        screen = TerminalScreen(rows=5, cols=20)
        screen.feed("hello\r\nworld")

        display = screen.display()
        self.assertEqual(display[0], "hello")
        self.assertEqual(display[1], "world")

    def test_clear_sequence_resets_screen(self):
        screen = TerminalScreen(rows=3, cols=10)
        screen.feed("noise here")
        screen.feed("\x1b[2J\x1b[H")

        self.assertTrue(all(line == "" for line in screen.display()))

    def test_snapshot_trims_trailing_blank_lines(self):
        screen = TerminalScreen(rows=5, cols=20)
        screen.feed("one\r\ntwo\r\n")

        self.assertEqual(screen.snapshot(), ["one", "two"])

    def test_snapshot_includes_scrollback_history(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)
        for index in range(10):
            screen.feed(f"line{index}\r\n")

        snapshot = screen.snapshot()
        self.assertIn("line0", snapshot)
        self.assertIn("line9", snapshot)

    def test_snapshot_limits_to_requested_lines(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)
        for index in range(10):
            screen.feed(f"line{index}\r\n")

        self.assertEqual(len(screen.snapshot(lines=2)), 2)

    def test_scrollback_viewport_pages_to_top_and_bottom(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)
        for index in range(8):
            screen.feed(f"line{index}\r\n")

        screen.scroll("top")
        self.assertEqual(screen.display(), ["line0", "line1", "line2"])
        self.assertTrue(screen.viewport()["at_top"])
        self.assertFalse(screen.viewport()["at_bottom"])

        screen.scroll("bottom")
        self.assertIn("line7", screen.display())
        self.assertTrue(screen.viewport()["at_bottom"])

    def test_scrollback_viewport_page_movement_is_clamped(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)
        for index in range(8):
            screen.feed(f"line{index}\r\n")

        screen.scroll("top")
        screen.scroll("up")
        self.assertEqual(screen.display(), ["line0", "line1", "line2"])

        screen.scroll("bottom")
        screen.scroll("down")
        self.assertTrue(screen.viewport()["at_bottom"])
        self.assertIn("line7", screen.display())

    def test_scrollback_viewport_preserves_position_when_unpinned(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)
        for index in range(8):
            screen.feed(f"line{index}\r\n")
        screen.scroll("top")
        before = screen.display()

        screen.feed("line8\r\nline9\r\n")

        self.assertEqual(screen.display(), before)
        self.assertFalse(screen.viewport()["at_bottom"])

    def test_scrollback_viewport_follows_output_at_bottom(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)
        for index in range(3):
            screen.feed(f"line{index}\r\n")
        screen.scroll("bottom")

        screen.feed("line3\r\nline4\r\n")

        self.assertTrue(screen.viewport()["at_bottom"])
        self.assertIn("line4", screen.display())

    def test_snapshot_ignores_scrollback_viewport(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)
        for index in range(8):
            screen.feed(f"line{index}\r\n")
        screen.scroll("top")

        self.assertEqual(screen.snapshot(lines=2), ["line6", "line7"])

    def test_styled_render_uses_scrollback_viewport(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)
        for index in range(8):
            screen.feed(f"line{index}\r\n")
        screen.scroll("top")

        rendered = screen.render_styled()

        self.assertIn("line0", rendered)
        self.assertNotIn("line7", rendered)

    def test_terminal_metadata_tracks_alt_screen_and_mouse_reporting_modes(self):
        screen = TerminalScreen(rows=3, cols=20, history=50)

        self.assertFalse(screen.metadata()["alt_screen"])
        self.assertFalse(screen.metadata()["mouse_reporting"])

        screen.feed("\x1b[?1049h")
        self.assertTrue(screen.metadata()["alt_screen"])
        self.assertFalse(screen.metadata()["mouse_reporting"])

        screen.feed("\x1b[?1000h")
        self.assertTrue(screen.metadata()["mouse_reporting"])

        screen.feed("\x1b[?1000l")
        self.assertFalse(screen.metadata()["mouse_reporting"])

        screen.feed("\x1b[?1049l")
        self.assertFalse(screen.metadata()["alt_screen"])


if __name__ == "__main__":
    unittest.main()
