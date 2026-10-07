"""Record validation. Returns a LIST OF PROBLEMS (empty list = valid) so the report can say why."""
from __future__ import annotations

import math

import config

VALID_SOURCES = {config.SOURCE_BOOKS, config.SOURCE_QUOTES}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_record(rec: dict) -> list[str]:
    problems: list[str] = []
    source = rec.get("source")

    if source not in VALID_SOURCES:
        problems.append("unknown_source")
    if not rec.get("name_or_title"):
        problems.append("missing_name")
    if not str(rec.get("source_url") or "").startswith(("http://", "https://")):
        problems.append("invalid_url")

    price = rec.get("price")
    if price is not None:
        if not _is_number(price) or price < 0:
            problems.append("invalid_price")
    elif source == config.SOURCE_BOOKS:        # a book without a price is incomplete
        problems.append("missing_price")

    rating = rec.get("rating")
    if rating is not None:
        if isinstance(rating, bool) or not isinstance(rating, int) or rating not in (1, 2, 3, 4, 5):
            problems.append("invalid_rating")
    elif source == config.SOURCE_BOOKS:
        problems.append("missing_rating")

    if source == config.SOURCE_QUOTES and not rec.get("author"):
        problems.append("missing_author")

    return problems
