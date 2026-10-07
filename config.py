"""Central settings. Everything that might need tuning lives here, in one place."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
LOG_FILE = BASE_DIR / "logs" / "scraper.log"

# Source names. These exact strings appear in the CSV and are checked by validation.
SOURCE_BOOKS = "Books to Scrape"
SOURCE_QUOTES = "Quotes to Scrape"

BOOKS_START_URL = "https://books.toscrape.com/"
QUOTES_START_URL = "https://quotes.toscrape.com/"

# Networking
USER_AGENT = "ScrapingAssignment/1.0 (learning project)"
ROBOTS_AGENT = "ScrapingAssignment"      # name used when checking robots.txt rules
REQUEST_TIMEOUT = 15                      # seconds
REQUEST_DELAY = 0.5                       # polite pause between any two requests
MAX_PAGES = 500                           # safety stop so a pagination bug can never loop forever
RETRY_TOTAL = 3
RETRY_BACKOFF = 1.0                       # waits grow: ~1s, 2s, 4s between retries
RETRY_STATUS_CODES = (429, 500, 502, 503, 504)
