"""Small, pure cleaning functions: value in, cleaned value out. No internet, no files."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

RATING_MAP = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def clean_text(value) -> str | None:
    """Collapse spaces/tabs/newlines/non-breaking spaces; empty result becomes None."""
    if value is None:
        return None
    text = str(value).replace("\xa0", " ").replace("\u200b", "")
    text = " ".join(text.split())
    return text or None


def strip_quotes(value) -> str | None:
    """Remove the curly (or straight) quotation marks wrapped around a quote."""
    text = clean_text(value)
    if text is None:
        return None
    if text[0] in "\u201c\"":
        text = text[1:]
    if text and text[-1] in "\u201d\"":
        text = text[:-1]
    return clean_text(text)


def clean_price(raw) -> float | None:
    """'£51.77' -> 51.77.  Returns None if no number can be found."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"-?\d+(?:\.\d+)?", str(raw).replace(",", ""))
    return float(match.group()) if match else None


def clean_rating(raw) -> int | None:
    """'star-rating Three' / 'Three' / '3' -> 3.  Range is checked later by validation."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    for token in str(raw).lower().replace("-", " ").split():
        if token in RATING_MAP:
            return RATING_MAP[token]
        if token.isdigit():
            return int(token)
    return None


def clean_tags(tags) -> str | None:
    """['Love', 'life '] -> 'life;love' (lowercase, de-duplicated, sorted, ';'-joined)."""
    if tags is None:
        return None
    if isinstance(tags, str):
        tags = re.split(r"[;,]", tags)
    cleaned = {clean_text(t).lower() for t in tags if clean_text(t)}
    return ";".join(sorted(cleaned)) or None


def normalize_url(url, base: str | None = None) -> str | None:
    """Make a URL absolute and check it is http(s). Returns None if it cannot be used."""
    text = clean_text(url)
    if text is None:
        return None
    if base:
        text = urljoin(base, text)
    parts = urlparse(text)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return text
