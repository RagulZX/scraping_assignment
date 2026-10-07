"""Shared networking + pagination code.

Anything that touches the internet lives in scrapers/. The two site-specific
scrapers only describe *what to look for* (selectors) and *how to turn one HTML
element into a raw dictionary*. Fetching, retries, politeness, robots.txt and the
"follow the next link" loop are written once, here.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

import config

logger = logging.getLogger(__name__)


def create_session() -> requests.Session:
    """One Session with a User-Agent and automatic retries for temporary errors."""
    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})
    retries = Retry(
        total=config.RETRY_TOTAL,
        backoff_factor=config.RETRY_BACKOFF,
        status_forcelist=list(config.RETRY_STATUS_CODES),
        # respect_retry_after_header defaults to True, so a 429 "Retry-After" is honoured.
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def utc_now_iso() -> str:
    """Current UTC time, e.g. '2026-10-06T10:15:30+00:00'."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BaseScraper:
    """Fetches pages politely and follows 'next' links until there are none."""

    source_name = ""
    start_url = ""
    record_selector = ""      # CSS selector for ONE record on a listing page

    def __init__(self, session, start_url=None, delay=None, timeout=None, max_pages=None):
        self.session = session
        self.start_url = start_url or self.start_url
        self.delay = config.REQUEST_DELAY if delay is None else max(0.0, delay)
        self.timeout = timeout or config.REQUEST_TIMEOUT
        self.max_pages = max_pages or config.MAX_PAGES
        self.records: list[dict] = []          # raw records (kept even if the run is cut short)
        self.stats = {
            "pages_fetched": 0,
            "pages_failed": 0,
            "requests_failed": 0,
            "records_skipped": 0,
            "detail_failures": 0,
            "complete": False,                 # True only if we reached a page with no 'next' link
        }
        self._last_request_time = None
        self._robots = None

    # ---------- to be provided by each site ----------
    def parse_record(self, element, page_url: str) -> dict | None:
        raise NotImplementedError

    # ---------- networking ----------
    def _wait_politely(self) -> None:
        """Make sure at least `delay` seconds passed since the previous request."""
        if self._last_request_time is not None:
            wait = self.delay - (time.monotonic() - self._last_request_time)
            if wait > 0:
                time.sleep(wait)

    def _load_robots(self) -> RobotFileParser:
        """Download and parse robots.txt. If it is missing or unreachable, allow crawling."""
        robots_url = urljoin(self.start_url, "/robots.txt")
        parser = RobotFileParser()
        self._wait_politely()
        try:
            response = self.session.get(robots_url, timeout=self.timeout)
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
                parser.modified()          # without this, can_fetch() assumes "not loaded" and says no
                logger.info("[%s] Loaded robots.txt", self.source_name)
            elif response.status_code in (401, 403):
                parser.disallow_all = True
                logger.warning("[%s] robots.txt returned %s - treating site as off-limits",
                               self.source_name, response.status_code)
            else:
                parser.allow_all = True
                logger.info("[%s] No robots.txt (HTTP %s) - no restrictions declared",
                            self.source_name, response.status_code)
        except requests.RequestException as exc:
            parser.allow_all = True
            logger.warning("[%s] Could not read robots.txt (%s) - continuing", self.source_name, exc)
        finally:
            self._last_request_time = time.monotonic()
        return parser

    def _robots_allow(self, url: str) -> bool:
        if self._robots is None:
            self._robots = self._load_robots()
        return self._robots.can_fetch(config.ROBOTS_AGENT, url)

    def fetch(self, url: str) -> BeautifulSoup | None:
        """Download one page and parse it. Returns None (and logs) on any failure."""
        if not self._robots_allow(url):
            logger.error("[%s] robots.txt disallows %s - not fetching", self.source_name, url)
            return None
        self._wait_politely()
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()                 # turns 404/500/... into an exception
        except requests.RequestException as exc:
            self.stats["requests_failed"] += 1
            logger.error("[%s] Request failed for %s: %s", self.source_name, url, exc)
            return None
        finally:
            self._last_request_time = time.monotonic()
        response.encoding = "utf-8"                     # otherwise '£' can turn into 'Â£'
        logger.debug("[%s] GET %s -> HTTP %s", self.source_name, url, response.status_code)
        return BeautifulSoup(response.text, "lxml")

    # ---------- pagination ----------
    def scrape(self) -> list[dict]:
        """Walk through every page by following the 'next' link. Never hard-codes page numbers."""
        logger.info("[%s] Starting at %s", self.source_name, self.start_url)
        url = self.start_url
        visited: set[str] = set()
        page = 0
        while url:
            if url in visited:
                logger.warning("[%s] Already visited %s - stopping to avoid a loop", self.source_name, url)
                break
            if page >= self.max_pages:
                logger.warning("[%s] Page limit (%d) reached - stopping early", self.source_name, self.max_pages)
                break
            visited.add(url)
            page += 1
            logger.info("[%s] Page %d: %s", self.source_name, page, url)

            soup = self.fetch(url)
            if soup is None:
                self.stats["pages_failed"] += 1
                logger.error("[%s] Page %d failed - stopping this source, keeping %d records so far",
                             self.source_name, page, len(self.records))
                break
            self.stats["pages_fetched"] += 1
            self._parse_page(soup, url)

            url = self._find_next_url(soup, url)
            if url is None:
                self.stats["complete"] = True
        logger.info("[%s] Finished: %d raw records from %d page(s)",
                    self.source_name, len(self.records), self.stats["pages_fetched"])
        return self.records

    def _parse_page(self, soup: BeautifulSoup, page_url: str) -> None:
        elements = soup.select(self.record_selector)
        if not elements:
            logger.warning("[%s] No records matched '%s' on %s (did the layout change?)",
                           self.source_name, self.record_selector, page_url)
        for element in elements:
            try:
                record = self.parse_record(element, page_url)
            except Exception as exc:                    # one bad record must not stop the page
                self.stats["records_skipped"] += 1
                logger.warning("[%s] Skipped a record on %s: %r", self.source_name, page_url, exc)
                continue
            if record:
                self.records.append(record)

    @staticmethod
    def _find_next_url(soup: BeautifulSoup, current_url: str) -> str | None:
        link = soup.select_one("li.next > a")
        if link is None:
            return None
        href = link.get("href")
        if not href:
            logger.warning("'Next' link on %s has no href - treating as last page", current_url)
            return None
        return urljoin(current_url, href)               # relative link -> full URL
