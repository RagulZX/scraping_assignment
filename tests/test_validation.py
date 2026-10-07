import config
from processing.validation import validate_record


def book(**over):
    rec = {"source": config.SOURCE_BOOKS, "source_url": "https://x.com/b", "name_or_title": "T",
           "price": 10.0, "rating": 3}
    rec.update(over)
    return rec


def quote(**over):
    rec = {"source": config.SOURCE_QUOTES, "source_url": "https://x.com/", "name_or_title": "Q",
           "author": "A", "price": None, "rating": None}
    rec.update(over)
    return rec


def test_valid_records_have_no_problems():
    assert validate_record(book()) == []
    assert validate_record(quote()) == []


def test_each_rule_reports_its_reason():
    assert validate_record(book(source="Other")) == ["unknown_source"]
    assert validate_record(book(name_or_title="")) == ["missing_name"]
    assert validate_record(book(source_url="ftp://x")) == ["invalid_url"]
    assert validate_record(book(price=-1)) == ["invalid_price"]
    assert validate_record(book(price="abc")) == ["invalid_price"]
    assert validate_record(book(rating=6)) == ["invalid_rating"]
    assert validate_record(book(rating=0)) == ["invalid_rating"]
    assert validate_record(book(price=None)) == ["missing_price"]
    assert validate_record(book(rating=None)) == ["missing_rating"]
    assert validate_record(quote(author=None)) == ["missing_author"]


def test_multiple_problems_are_all_reported():
    assert set(validate_record(book(name_or_title=None, source_url=None))) == {"missing_name", "invalid_url"}


def test_nan_and_bool_are_not_valid_numbers():
    assert validate_record(book(price=float("nan"))) == ["invalid_price"]
    assert validate_record(book(rating=True)) == ["invalid_rating"]
