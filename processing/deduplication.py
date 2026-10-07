"""Duplicate detection using a normalised fingerprint.

Identity rules (the README documents the same rules):
  Books : source + title
  Quotes: source + author + first 50 characters of the (normalised) quote text
Each part is normalised first: Unicode NFKC, case-folded, punctuation removed, spaces collapsed.
Duplicates are REMOVED (first occurrence wins) and counted/logged.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

import config


def _normalize(value) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = re.sub(r"[^\w\s]", "", text)          # drop punctuation
    return " ".join(text.split())                # collapse whitespace


def fingerprint_key(rec: dict) -> str:
    source = _normalize(rec.get("source"))
    title = _normalize(rec.get("name_or_title"))
    if rec.get("source") == config.SOURCE_QUOTES:
        return "|".join([source, _normalize(rec.get("author")), title[:50]])
    return "|".join([source, title])             # '|' keeps fields from blurring together


def make_fingerprint(rec: dict) -> str:
    return hashlib.sha256(fingerprint_key(rec).encode("utf-8")).hexdigest()


def find_duplicates(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (unique_records, duplicate_records). Order is preserved; first occurrence is kept."""
    seen: set[str] = set()
    unique, dupes = [], []
    for rec in records:
        fp = make_fingerprint(rec)
        if fp in seen:
            dupes.append(rec)
        else:
            seen.add(fp)
            unique.append(rec)
    return unique, dupes
