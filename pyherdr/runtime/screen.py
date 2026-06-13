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
_PRIVATE_MODE_SHIFT = 5
_ALT_SCREEN_MODES = {47, 1047, 1049}
_MOUSE_REPORTING_MODES = {1000, 1002, 1003}


def _private_mode(mode: int) -> int:
    """Return pyte's internal representation for DEC private modes."""
    return mode << _PRIVATE_MODE_SHIFT


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
    blank = _is_blank_cell(char)
    if getattr(char, "bold", False):
        codes.append("1")
    if getattr(char, "italics", False):
        codes.append("3")
    if getattr(char, "underscore", False) and not blank:
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


def _is_blank_cell(char: object) -> bool:
    data = str(getattr(char, "data", "") or " ")
    return data == " "


class TerminalScreen:
    """A `pyte` history screen wrapped with a simple text-snapshot API."""

    def __init__(self, rows: int = 24, cols: int = 80, history: int = 2000) -> None:
        self._rows = rows
        self._cols = cols
        self._screen = pyte.HistoryScreen(cols, rows, history=history, ratio=0.5)
        self._stream = pyte.Stream(self._screen)
        self._offset_from_bottom = 0

    def feed(self, text: str) -> None:
        """Feed decoded terminal output into the screen."""
        start = self._viewport_start() if self._offset_from_bottom else None
        self._stream.feed(text)
        if start is not None:
            self._set_viewport_start(start)
        else:
            self._offset_from_bottom = 0

    def resize(self, rows: int, cols: int) -> None:
        """Resize the screen grid."""
        start = self._viewport_start() if self._offset_from_bottom else None
        self._rows = rows
        self._cols = cols
        self._screen.resize(rows, cols)
        if start is not None:
            self._set_viewport_start(start)
        else:
            self._offset_from_bottom = 0

    def display(self) -> list[str]:
        """Return the current visible screen as right-stripped lines."""
        if self._offset_from_bottom == 0:
            return self._screen_display()
        return self._viewport_lines()

    def scroll(self, direction: str) -> None:
        """Move the deterministic scrollback viewport."""
        max_offset = self._max_offset()
        page = max(1, self._rows)
        if direction in {"up", "page_up"}:
            self._offset_from_bottom = min(max_offset, self._offset_from_bottom + page)
        elif direction in {"down", "page_down"}:
            self._offset_from_bottom = max(0, self._offset_from_bottom - page)
        elif direction == "top":
            self._offset_from_bottom = max_offset
        elif direction == "bottom":
            self._offset_from_bottom = 0
        self._clamp_offset()

    def viewport(self) -> dict[str, int | bool]:
        """Return deterministic scrollback viewport state for UI/copy-mode math."""
        max_offset = self._max_offset()
        self._clamp_offset()
        return {
            "offset_from_bottom": self._offset_from_bottom,
            "max_offset": max_offset,
            "rows": self._rows,
            "total_lines": len(self._document_lines()),
            "at_top": self._offset_from_bottom == max_offset,
            "at_bottom": self._offset_from_bottom == 0,
        }

    def metadata(self) -> dict[str, bool]:
        """Return terminal mode metadata needed by input routing."""
        modes = self._screen.mode
        return {
            "alt_screen": any(_private_mode(mode) in modes for mode in _ALT_SCREEN_MODES),
            "mouse_reporting": any(_private_mode(mode) in modes for mode in _MOUSE_REPORTING_MODES),
        }

    def render_styled(self, cursor: bool = False) -> str:
        """Return the visible screen as ANSI-styled lines.

        Each cell's colour/bold/italic/underline are emitted as SGR escapes (run-
        length coalesced). When ``cursor`` is set, the cursor cell is drawn in
        reverse video so the client can show a block cursor.
        """
        if self._offset_from_bottom:
            return "\n".join(f"\x1b[0m{line.ljust(self._cols)}\x1b[0m" for line in self._viewport_lines())
        screen = self._screen
        cur_x, cur_y = screen.cursor.x, screen.cursor.y
        lines: list[str] = []
        for y in range(self._rows):
            row = screen.buffer[y]
            out: list[str] = []
            last: str | None = None
            last_cell = self._last_visible_cell(row)
            if cursor and y == cur_y:
                last_cell = max(last_cell, cur_x)
            for x in range(last_cell + 1):
                char = row[x]
                sgr = _sgr(char, cursor and y == cur_y and x == cur_x)
                if sgr != last:
                    out.append(f"\x1b[0;{sgr}m" if sgr else "\x1b[0m")
                    last = sgr
                out.append(char.data if char.data else " ")
            out.append("\x1b[0m")
            lines.append("".join(out))
        return "\n".join(lines)

    def _last_visible_cell(self, row: dict[int, pyte.screens.Char]) -> int:
        """Return the last column with real text, ignoring style-only blanks."""
        for x in range(self._cols - 1, -1, -1):
            if row[x].data and row[x].data != " ":
                return x
        return -1

    def snapshot(self, lines: int | None = None) -> list[str]:
        """Return scrollback history plus the visible screen.

        Trailing blank lines are dropped. When ``lines`` is given, only the most
        recent ``lines`` rows are returned.
        """
        combined = self._document_lines()
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

    def _screen_display(self) -> list[str]:
        return [line.rstrip() for line in self._screen.display]

    def _document_lines(self) -> list[str]:
        history = [self._render_history_line(row) for row in self._screen.history.top]
        return history + self._screen_display()

    def _max_offset(self) -> int:
        return max(0, len(self._document_lines()) - self._rows)

    def _clamp_offset(self) -> None:
        self._offset_from_bottom = max(0, min(self._offset_from_bottom, self._max_offset()))

    def _viewport_start(self) -> int:
        self._clamp_offset()
        return max(0, len(self._document_lines()) - self._rows - self._offset_from_bottom)

    def _set_viewport_start(self, start: int) -> None:
        self._offset_from_bottom = max(0, len(self._document_lines()) - self._rows - max(0, start))
        self._clamp_offset()

    def _viewport_lines(self) -> list[str]:
        document = self._document_lines()
        start = self._viewport_start()
        lines = document[start : start + self._rows]
        while len(lines) < self._rows:
            lines.append("")
        return lines
