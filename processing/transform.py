"""Turns each site's raw dictionary into the common record layout (see README, 'Data model')."""
from __future__ import annotations

import config
from processing.cleaning import (
    clean_price, clean_rating, clean_tags, clean_text, normalize_url, strip_quotes,
)


def _value_or_raw(cleaned, raw):
    """If a value was present but could not be converted, keep the text so validation can reject it
    (and report *why*) instead of silently turning it into an empty cell."""
    return cleaned if cleaned is not None or not clean_text(raw) else clean_text(raw)


def transform_book(raw: dict) -> dict:
    price_raw, rating_raw = raw.get("price_raw"), raw.get("rating_raw")
    return {
        "source": config.SOURCE_BOOKS,
        "source_url": normalize_url(raw.get("url_raw")),
        "name_or_title": clean_text(raw.get("title_raw")),
        "category": clean_text(raw.get("category_raw")),
        "price": _value_or_raw(clean_price(price_raw), price_raw),
        "rating": _value_or_raw(clean_rating(rating_raw), rating_raw),
        "author": None,
        "tags": None,
        "description": clean_text(raw.get("description_raw")),
        "scraped_at": raw.get("scraped_at"),
    }


def transform_quote(raw: dict) -> dict:
    return {
        "source": config.SOURCE_QUOTES,
        "source_url": normalize_url(raw.get("page_url")),
        "name_or_title": strip_quotes(raw.get("text_raw")),
        "category": None,                      # quotes have no category; left empty, not invented
        "price": None,
        "rating": None,
        "author": clean_text(raw.get("author_raw")),
        "tags": clean_tags(raw.get("tags_raw")),
        "description": None,
        "scraped_at": raw.get("scraped_at"),
    }
