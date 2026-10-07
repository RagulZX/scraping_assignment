import config
from processing.deduplication import find_duplicates, make_fingerprint


def book(title):
    return {"source": config.SOURCE_BOOKS, "name_or_title": title, "author": None}


def quote(text, author="Jane Austen"):
    return {"source": config.SOURCE_QUOTES, "name_or_title": text, "author": author}


def test_duplicates_ignore_case_and_spaces():
    records = [book("Example Book Title"), book("  Example Book Title "), book("EXAMPLE BOOK TITLE")]
    unique, dupes = find_duplicates(records)
    assert len(unique) == 1 and len(dupes) == 2
    assert unique[0]["name_or_title"] == "Example Book Title"        # first occurrence is kept


def test_duplicates_ignore_punctuation():
    unique, dupes = find_duplicates([book("Hello, World!"), book("hello world")])
    assert len(unique) == 1 and len(dupes) == 1


def test_different_books_are_not_duplicates():
    unique, dupes = find_duplicates([book("Book A"), book("Book B")])
    assert len(unique) == 2 and dupes == []


def test_same_text_in_different_sources_is_not_a_duplicate():
    assert make_fingerprint(book("Same")) != make_fingerprint(
        {"source": config.SOURCE_QUOTES, "name_or_title": "Same", "author": None})


def test_quotes_use_author_and_first_50_characters():
    long_a = "x" * 60 + " ending one"
    long_b = "X" * 60 + " ending two"          # differs only after 50 characters
    assert len(find_duplicates([quote(long_a), quote(long_b)])[1]) == 1
    assert len(find_duplicates([quote("same text"), quote("same text", author="Someone Else")])[1]) == 0


def test_fields_do_not_blur_together():
    # "ab" + "c" must not equal "a" + "bc"
    assert make_fingerprint(quote("c", author="ab")) != make_fingerprint(quote("bc", author="a"))
