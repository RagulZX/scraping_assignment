"""Books to Scrape: selectors and parsing for this one site."""
from __future__ import annotations

import logging
from urllib.parse import urljoin

import config
from scrapers.base_scraper import BaseScraper, utc_now_iso

logger = logging.getLogger(__name__)


class BooksScraper(BaseScraper):
    source_name = config.SOURCE_BOOKS
    start_url = config.BOOKS_START_URL
    record_selector = "article.product_pod"

    def __init__(self, session, fetch_details: bool = True, **kwargs):
        super().__init__(session, **kwargs)
        self.fetch_details = fetch_details      # visit each book's page for category + description

    def parse_record(self, article, page_url: str) -> dict:
        # Every lookup is checked for None: a missing element gives an empty field, not a crash.
        link = article.select_one("h3 > a")
        price = article.select_one("p.price_color")
        rating = article.select_one("p.star-rating")

        href = link.get("href") if link else None
        url = urljoin(page_url, href) if href else None
        # The visible link text is cut off with '...'; the full title is in the title attribute.
        title = (link.get("title") or link.get_text()) if link else None

        category = description = None
        if self.fetch_details and url:
            category, description = self._fetch_details(url)

        return {
            "title_raw": title,
            "url_raw": url,
            "price_raw": price.get_text() if price else None,
            "rating_raw": " ".join(rating.get("class", [])) if rating else None,  # 'star-rating Three'
            "category_raw": category,
            "description_raw": description,
            "scraped_at": utc_now_iso(),
        }

    def _fetch_details(self, url: str):
        """Return (category, description) from a book's own page; (None, None) if it fails."""
        soup = self.fetch(url)
        if soup is None:
            self.stats["detail_failures"] += 1
            return None, None
        # Breadcrumb is: Home > Books > <Category> > <Title>
        crumbs = soup.select("ul.breadcrumb li a")
        category = crumbs[2].get_text() if len(crumbs) >= 3 else None
        # The description paragraph sits right after the 'Product Description' heading.
        # Some books genuinely have no description, so None here is normal.
        desc = soup.select_one("#product_description + p")
        return category, desc.get_text() if desc else None
