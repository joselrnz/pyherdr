"""Server-side terminal screen model with scrollback, backed by `pyte`.

A `TerminalScreen` interprets the raw byte stream from a PTY (escape codes,
cursor moves, clears) into a stable grid of text plus scrollback history, so a
detached pane can be re-rendered on reattach.
"""

from __future__ import annotations

import pyte

_ANSI_NAMED = {
    "black": 0,
    "red": 1,
    "green": 2,
    "brown": 3,
    "yellow": 3,
    "blue": 4,
    "magenta": 5,
    "cyan": 6,
    "white": 7,
}


def _color_param(color: str, foreground: bool) -> str:
    """Return the SGR parameter for a pyte colour name/hex (``""`` for default)."""
    if not color or color == "default":
        return ""
    base = 30 if foreground else 40
    name = color.lower()
    if name in _ANSI_NAMED:
        return str(base + _ANSI_NAMED[name])
    if name.startswith("bright") and name[6:] in _ANSI_NAMED:
        return str(base + 60 + _ANSI_NAMED[name[6:]])
    if len(color) == 6:
        try:
            red, green, blue = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
        except ValueError:
            return ""
        return f"{38 if foreground else 48};2;{red};{green};{blue}"
    return ""


def _sgr(char: object, reverse: bool) -> str:
    """Build the SGR parameter list for one pyte cell (cursor → reverse video)."""
    codes: list[str] = []
    if getattr(char, "bold", False):
        codes.append("1")
    if getattr(char, "italics", False):
        codes.append("3")
    if getattr(char, "underscore", False):
        codes.append("4")
    if bool(getattr(char, "reverse", False)) ^ reverse:
        codes.append("7")
    fg = _color_param(str(getattr(char, "fg", "default")), True)
    bg = _color_param(str(getattr(char, "bg", "default")), False)
    if fg:
        codes.append(fg)
    if bg:
        codes.append(bg)
    return ";".join(codes)


class TerminalScreen:
    """A `pyte` history screen wrapped with a simple text-snapshot API."""

    def __init__(self, rows: int = 24, cols: int = 80, history: int = 2000) -> None:
        self._rows = rows
        self._cols = cols
        self._screen = pyte.HistoryScreen(cols, rows, history=history, ratio=0.5)
        self._stream = pyte.Stream(self._screen)

    def feed(self, text: str) -> None:
        """Feed decoded terminal output into the screen."""
        self._stream.feed(text)

    def resize(self, rows: int, cols: int) -> None:
        """Resize the screen grid."""
        self._rows = rows
        self._cols = cols
        self._screen.resize(rows, cols)

    def display(self) -> list[str]:
        """Return the current visible screen as right-stripped lines."""
        return [line.rstrip() for line in self._screen.display]

    def scroll(self, direction: str) -> None:
        """Scroll the visible window through scrollback (``up`` shows older lines)."""
        if direction == "up":
            self._screen.prev_page()
        elif direction == "down":
            self._screen.next_page()

    def render_styled(self, cursor: bool = False) -> str:
        """Return the visible screen as ANSI-styled lines.

        Each cell's colour/bold/italic/underline are emitted as SGR escapes (run-
        length coalesced). When ``cursor`` is set, the cursor cell is drawn in
        reverse video so the client can show a block cursor.
        """
        screen = self._screen
        cur_x, cur_y = screen.cursor.x, screen.cursor.y
        lines: list[str] = []
        for y in range(self._rows):
            row = screen.buffer[y]
            out: list[str] = []
            last: str | None = None
            for x in range(self._cols):
                char = row[x]
                sgr = _sgr(char, cursor and y == cur_y and x == cur_x)
                if sgr != last:
                    out.append(f"\x1b[0;{sgr}m" if sgr else "\x1b[0m")
                    last = sgr
                out.append(char.data if char.data else " ")
            out.append("\x1b[0m")
            lines.append("".join(out))
        return "\n".join(lines)

    def snapshot(self, lines: int | None = None) -> list[str]:
        """Return scrollback history plus the visible screen.

        Trailing blank lines are dropped. When ``lines`` is given, only the most
        recent ``lines`` rows are returned.
        """
        history = [self._render_history_line(row) for row in self._screen.history.top]
        combined = history + self.display()
        while combined and not combined[-1].strip():
            combined.pop()
        if lines is not None and lines >= 0:
            return combined[-lines:]
        return combined

    def _render_history_line(self, row: dict[int, pyte.screens.Char]) -> str:
        """Render one scrolled-off history row to text."""
        if not row:
            return ""
        width = max(self._cols, max(row) + 1)
        return "".join(row[x].data for x in range(width)).rstrip()
