"""URL detection helpers for terminal output."""

from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+")
_TRAILING_PUNCTUATION = ".,;:!?)"


def extract_urls(text: str) -> list[str]:
    """Return unique HTTP(S) URLs from terminal text in first-seen order."""
    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls
