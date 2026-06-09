import unittest

from pyherdr.runtime import TerminalScreen


class TerminalScreenTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
