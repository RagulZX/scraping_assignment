"""End-to-end tests against a local mock server (no internet needed)."""
import csv
import json

import pytest
import requests

import config
import main
from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper
from tests.conftest import books_site, quotes_site


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr(config, "RETRY_BACKOFF", 0)          # do not wait between retries in tests


def run_main(tmp_path, monkeypatch, books_url, quotes_url, *extra):
    monkeypatch.setattr(config, "BOOKS_START_URL", books_url)
    monkeypatch.setattr(config, "QUOTES_START_URL", quotes_url)
    code = main.main(["--delay", "0", "--output-dir", str(tmp_path / "out"),
                      "--log-file", str(tmp_path / "logs" / "scraper.log"), *extra])
    rows = list(csv.DictReader(open(tmp_path / "out" / "final_dataset.csv", encoding="utf-8")))
    summary = json.load(open(tmp_path / "out" / "summary_report.json", encoding="utf-8"))
    return code, rows, summary


def test_books_scraper_follows_next_links_and_reads_details(serve):
    url = serve(books_site())
    scraper = BooksScraper(requests.Session(), start_url=url, delay=0)
    raw = scraper.scrape()
    assert len(raw) == 5 and scraper.stats["pages_fetched"] == 2 and scraper.stats["complete"]
    assert raw[0]["title_raw"] == "Book One"                       # full title from the title attribute
    assert raw[0]["price_raw"] == "£51.77"                         # £ survived (encoding handled)
    assert raw[0]["category_raw"] == "Poetry"
    assert raw[2]["url_raw"].endswith("/catalogue/book-three_3/index.html")   # relative link resolved
    assert scraper.stats["detail_failures"] == 3                   # three books have no detail page


def test_skip_details_makes_no_detail_requests(serve):
    url = serve(books_site())
    scraper = BooksScraper(requests.Session(), start_url=url, delay=0, fetch_details=False)
    raw = scraper.scrape()
    assert len(raw) == 5 and all(r["category_raw"] is None for r in raw)
    assert scraper.stats["detail_failures"] == 0


def test_failed_page_keeps_earlier_records(serve):
    scraper = QuotesScraper(requests.Session(), start_url=serve(quotes_site(page2_status=500)), delay=0)
    raw = scraper.scrape()
    assert len(raw) == 2 and scraper.stats["pages_failed"] == 1 and not scraper.stats["complete"]


def test_robots_txt_is_respected(serve):
    routes = quotes_site()
    routes["/robots.txt"] = (200, "User-agent: *\nDisallow: /page/\n")
    scraper = QuotesScraper(requests.Session(), start_url=serve(routes), delay=0)
    raw = scraper.scrape()
    assert len(raw) == 2                                           # page 2 is disallowed, so skipped


def test_full_run_numbers_reconcile(tmp_path, monkeypatch, serve):
    code, rows, s = run_main(tmp_path, monkeypatch, serve(books_site()), serve(quotes_site()))
    assert code == 0
    assert s["collected_per_source"] == {config.SOURCE_BOOKS: 5, config.SOURCE_QUOTES: 3}
    assert s["rejected_by_reason"] == {"missing_price": 1}
    assert s["duplicates_per_source"][config.SOURCE_BOOKS] == 1
    assert s["final_record_count"] == len(rows) == 6                # 3 books + 3 quotes
    assert s["reconciliation"]["ok"] is True
    books = [r for r in rows if r["source"] == config.SOURCE_BOOKS]
    quotes = [r for r in rows if r["source"] == config.SOURCE_QUOTES]
    assert {r["name_or_title"] for r in books} == {"Book One", "Book Two", "Book Three"}
    first = next(r for r in books if r["name_or_title"] == "Book One")
    assert first["price"] == "51.77" and first["rating"] == "3"
    assert first["category"] == "Poetry" and first["description"] == "A fine book."
    assert first["author"] == "" and first["tags"] == ""            # not applicable -> empty, not invented
    q = next(r for r in quotes if r["author"] == "Saint Augustine")
    assert q["name_or_title"] == "The world is a book." and q["tags"] == "books;travel"
    assert q["price"] == "" and q["category"] == ""
    assert (tmp_path / "logs" / "scraper.log").read_text(encoding="utf-8").count("Page ") >= 4


def test_one_failed_page_does_not_stop_the_run(tmp_path, monkeypatch, serve):
    code, rows, s = run_main(tmp_path, monkeypatch, serve(books_site()), serve(quotes_site(page2_status=500)))
    assert code == 0
    assert s["source_health"][config.SOURCE_QUOTES]["status"] == "partial"
    assert s["collected_per_source"][config.SOURCE_QUOTES] == 2
    assert s["reconciliation"]["ok"] is True and len(rows) == 5


def test_a_dead_source_does_not_stop_the_other(tmp_path, monkeypatch, serve):
    code, rows, s = run_main(tmp_path, monkeypatch, serve(books_site()), serve(quotes_site(page1_status=500)))
    assert code == 1                                               # signals that a source failed
    assert s["source_health"][config.SOURCE_QUOTES]["status"] == "failed"
    assert {r["source"] for r in rows} == {config.SOURCE_BOOKS}    # books still delivered


def test_skip_details_flag(tmp_path, monkeypatch, serve):
    _, rows, s = run_main(tmp_path, monkeypatch, serve(books_site()), serve(quotes_site()), "--skip-details")
    assert s["run"]["book_detail_pages_fetched"] is False
    assert all(r["category"] == "" for r in rows)
