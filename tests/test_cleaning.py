import pytest
from processing.cleaning import (
    clean_price, clean_rating, clean_tags, clean_text, normalize_url, strip_quotes,
)


def test_clean_text_collapses_all_whitespace():
    assert clean_text("  Hello \n\t World\xa0! ") == "Hello World !"


def test_clean_text_empty_becomes_none():
    assert clean_text("   \n ") is None
    assert clean_text(None) is None


def test_strip_quotes_curly_and_straight():
    assert strip_quotes("\u201cThe world is a book.\u201d") == "The world is a book."
    assert strip_quotes('"plain quotes"') == "plain quotes"
    assert strip_quotes("no quotes") == "no quotes"


@pytest.mark.parametrize("raw,expected", [
    ("£51.77", 51.77), ("Â£51.77", 51.77), (" £1,234.50 ", 1234.5), ("10", 10.0),
    ("-3.5", -3.5), ("free", None), ("", None), (None, None),
])
def test_clean_price(raw, expected):
    assert clean_price(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("star-rating Three", 3), ("Five", 5), ("one", 1), ("4", 4), ("star-rating", None),
    ("star-rating Seven", None), (None, None),
])
def test_clean_rating(raw, expected):
    assert clean_rating(raw) == expected


def test_clean_tags_lowercase_sorted_deduplicated():
    assert clean_tags(["Love", " life ", "LOVE"]) == "life;love"
    assert clean_tags([]) is None
    assert clean_tags(None) is None


def test_normalize_url():
    assert normalize_url("/a/b", base="https://x.com/page") == "https://x.com/a/b"
    assert normalize_url(" https://x.com/ ") == "https://x.com/"
    assert normalize_url("ftp://x.com/") is None
    assert normalize_url("not a url") is None
    assert normalize_url(None) is None
