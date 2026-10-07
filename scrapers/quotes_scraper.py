"""Quotes to Scrape: selectors and parsing for this one site."""
from __future__ import annotations

import config
from scrapers.base_scraper import BaseScraper, utc_now_iso


class QuotesScraper(BaseScraper):
    source_name = config.SOURCE_QUOTES
    start_url = config.QUOTES_START_URL
    record_selector = "div.quote"

    def parse_record(self, quote, page_url: str) -> dict:
        text = quote.select_one("span.text")
        author = quote.select_one("small.author")
        tags = [tag.get_text() for tag in quote.select("a.tag")]    # zero or more

        return {
            "text_raw": text.get_text() if text else None,
            "author_raw": author.get_text() if author else None,
            "tags_raw": tags,
            "page_url": page_url,           # we store the page the quote appeared on
            "scraped_at": utc_now_iso(),
        }
