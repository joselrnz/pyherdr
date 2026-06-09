"""Shared text helpers for agent detection (ported from herdr src/detect/mod.rs)."""

from __future__ import annotations

BRAILLE_START = 0x2800
BRAILLE_END = 0x28FF


def is_braille(ch: str) -> bool:
    """Return whether ``ch`` is a Unicode braille pattern (CLI spinner) glyph."""
    return len(ch) == 1 and BRAILLE_START <= ord(ch) <= BRAILLE_END


def has_braille_spinner(content: str) -> bool:
    """Return whether any line starts with a braille spinner glyph."""
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed and is_braille(trimmed[0]):
            return True
    return False


def has_confirmation_prompt(lower_content: str) -> bool:
    """Detect "do you want to" / "would you like to" followed by yes/❯."""
    pos = lower_content.find("do you want to")
    if pos == -1:
        pos = lower_content.find("would you like to")
    if pos == -1:
        return False
    after = lower_content[pos:]
    return "yes" in after or "❯" in after


def has_selection_prompt(content: str) -> bool:
    """Detect a "❯" line that also contains a numbered option like "1."."""
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("❯") and any(c.isdigit() for c in trimmed) and "." in trimmed:
            return True
    return False


def has_interrupt_pattern(lower_content: str) -> bool:
    """Detect real interrupt hints (not unrelated 'esc'/'interrupt' text)."""
    return (
        "esc to interrupt" in lower_content
        or "ctrl+c to interrupt" in lower_content
        or "press esc to interrupt" in lower_content
    )


def status_word_is_active(rest: str) -> bool:
    """Return whether the first word (sans trailing punctuation) ends in 'ing'."""
    parts = rest.split()
    if not parts:
        return False
    word = parts[0]
    end = len(word)
    while end > 0 and not word[end - 1].isalpha():
        end -= 1
    return word[:end].lower().endswith("ing")


def bottom_non_empty_lines(content: str, max_lines: int) -> list[str]:
    """Return up to ``max_lines`` non-empty lines from the bottom, in order."""
    lines = [line for line in reversed(content.splitlines()) if line.strip()][:max_lines]
    lines.reverse()
    return lines


def normalize_lines(lines: list[str]) -> str:
    """Collapse whitespace across lines into a single lowercased string."""
    return " ".join(word for line in lines for word in line.split()).lower()


def is_horizontal_rule(line: str) -> bool:
    """Return whether a line is a box-drawing horizontal rule ("───…")."""
    trimmed = line.strip()
    if not trimmed:
        return False
    rule_chars = 0
    for char in trimmed:
        if char == "─":
            rule_chars += 1
        else:
            break
    if rule_chars == 0:
        return False
    suffix = trimmed[rule_chars:].lstrip()
    return suffix == "" or rule_chars >= 3
