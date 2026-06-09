"""Keyboard input encoding for terminal panes.

Maps logical key names to the byte sequences a terminal sends to a PTY, so
clients can request keystrokes by name (``"enter"``, ``"up"``) instead of
hard-coding escape codes.
"""

from __future__ import annotations

# Named keys -> the text written to the PTY master (xterm-compatible).
_KEY_SEQUENCES: dict[str, str] = {
    "enter": "\r",
    "return": "\r",
    "tab": "\t",
    "backtab": "\x1b[Z",
    "escape": "\x1b",
    "esc": "\x1b",
    "space": " ",
    "backspace": "\x7f",
    "delete": "\x1b[3~",
    "insert": "\x1b[2~",
    "up": "\x1b[A",
    "down": "\x1b[B",
    "right": "\x1b[C",
    "left": "\x1b[D",
    "home": "\x1b[H",
    "end": "\x1b[F",
    "pageup": "\x1b[5~",
    "pagedown": "\x1b[6~",
    "f1": "\x1bOP",
    "f2": "\x1bOQ",
    "f3": "\x1bOR",
    "f4": "\x1bOS",
    "f5": "\x1b[15~",
    "f6": "\x1b[17~",
    "f7": "\x1b[18~",
    "f8": "\x1b[19~",
    "f9": "\x1b[20~",
    "f10": "\x1b[21~",
    "f11": "\x1b[23~",
    "f12": "\x1b[24~",
}


def encode_key(name: str) -> str:
    """Return the byte sequence for a named key (case-insensitive).

    Also accepts ``ctrl+<letter>`` chords, e.g. ``"ctrl+c"`` -> ``"\\x03"``.
    """
    key = name.strip().lower()
    if key.startswith("ctrl+") and len(key) == 6 and key[5].isalpha():
        return encode_ctrl(key[5])
    try:
        return _KEY_SEQUENCES[key]
    except KeyError:
        raise KeyError(f"unknown key: {name}") from None


def encode_ctrl(letter: str) -> str:
    r"""Return the control code for ``Ctrl+<letter>`` (e.g. ``"c"`` -> ``"\x03"``)."""
    if len(letter) != 1 or not letter.isalpha():
        raise ValueError(f"ctrl key must be a single letter: {letter!r}")
    return chr(ord(letter.upper()) - 64)


def encode_text(text: str) -> str:
    """Return literal typed text unchanged."""
    return text


def known_keys() -> list[str]:
    """Return the sorted list of recognized key names."""
    return sorted(_KEY_SEQUENCES)
