# Multi-Source Web Scraping & Data Consolidation

A small ETL pipeline that scrapes **Books to Scrape** (~1,000 books, 50 pages) and **Quotes to Scrape**
(100 quotes, 10 pages), cleans and validates the data, removes duplicates, and writes one tidy CSV plus a
summary report. One command runs everything.

```
Scrape (both sites) -> Clean -> Validate -> Deduplicate -> Consolidate -> Save files
```

## Python version

Python **3.10, 3.11 or 3.12** (developed on 3.12).

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Dependencies** (pinned in `requirements.txt`): `requests` (download pages), `beautifulsoup4` (search the HTML),
`lxml` (fast HTML parser), `pytest` (tests). Everything else is the standard library. No accounts, API keys or
secrets are used anywhere.

## How to run

```bash
python main.py                  # full run, including each book's detail page (about 10-15 minutes)
python main.py --skip-details   # quick run (about 1-2 minutes): category and description stay empty
pytest -q                       # unit + offline end-to-end tests (no internet needed)
```

Other options: `--only books` / `--only quotes`, `--max-pages N`, `--delay SECONDS` (default 0.5),
`--output-dir`, `--log-file`. See `python main.py --help`.

Outputs:

| File | Contents |
| --- | --- |
| `output/final_dataset.csv` | One row per unique, valid record from both sources; same columns on every row |
| `output/summary_report.json` | Counts per source, rejection reasons, duplicates, final count, run time, source health |
| `logs/scraper.log` | Time-stamped log (every request at DEBUG level, pages/warnings/errors at INFO and above; overwritten each run) |

The process exit code is `0` normally and `1` if a source produced no records at all.

## 1. Exploring the websites

| Item | Books to Scrape | Quotes to Scrape |
| --- | --- | --- |
| One record | `article.product_pod` | `div.quote` |
| Main text | `h3 > a`; the **full** title is in its `title` attribute (visible text is cut with `...`) | `span.text` (wrapped in curly quotes) |
| Price | `p.price_color` (`£51.77`) | none |
| Rating | class of `p.star-rating` (`star-rating Three`) | none |
| Author / tags | none | `small.author` / `a.tag` (zero or more) |
| Link | `h3 > a[href]` (relative path; differs between page 1 and later pages) | author page link (not used) |
| Category / description | **only on the book's own page**: breadcrumb `ul.breadcrumb li a` (3rd link) and `#product_description + p` | none |
| Next page | `li.next > a` (relative) | `li.next > a` (relative) |

Both sites are plain server-rendered HTML, so **Requests + BeautifulSoup** is enough; Selenium/Playwright would add
overhead for no benefit.

## 2. How pagination works

`BaseScraper.scrape()` starts at the home page, parses it, looks for `li.next > a`, turns the relative `href` into a full
URL with `urljoin`, and repeats. It stops when there is no "next" link. No page numbers are hard-coded, so the scraper
adapts if the sites gain or lose pages. Safety nets: a `visited` set (no loops) and a page limit (`MAX_PAGES = 500`).

## 3. Data model

Every row has the same ten columns. Fields that do not apply are **empty, never invented**.

| Column | Books | Quotes |
| --- | --- | --- |
| `source` | `Books to Scrape` | `Quotes to Scrape` |
| `source_url` | the book's detail-page URL | the **listing page** the quote appeared on (chosen so the URL is where the data was actually read) |
| `name_or_title` | book title | quote text, without the curly quotes |
| `category` | from the book page (empty with `--skip-details`) | empty |
| `price` | number, e.g. `51.77` (GBP, currency symbol removed) | empty |
| `rating` | integer 1-5 | empty |
| `author` | empty | author name |
| `tags` | empty | `tag1;tag2` (lowercase, sorted, unique) |
| `description` | from the book page, or empty (some books have none) | empty |
| `scraped_at` | UTC ISO timestamp taken when the record was scraped | same |

## 4. Cleaning (`processing/cleaning.py`, `processing/transform.py`)

Small pure functions, tested without internet: `clean_text` (collapse spaces/tabs/newlines/`\xa0`; empty becomes
`None`), `strip_quotes`, `clean_price` (`£51.77` -> `51.77`), `clean_rating` (`Three` -> `3`), `clean_tags`,
`normalize_url`. `transform.py` maps each site's raw dictionary onto the common columns. Pages are decoded as UTF-8
explicitly so `£` is not read as `Â£`.

If a value is present but cannot be converted (e.g. price text with no number), it is kept as text so validation rejects
the record **with a reason** rather than silently turning it into an empty cell.

## 5. Validation (`processing/validation.py`)

`validate_record` returns a list of problems; an empty list means valid. Rules from the brief: `unknown_source`,
`missing_name`, `invalid_url`, `invalid_price` (not a finite number, or negative), `invalid_rating` (not an integer 1-5).
Extra rules for "required fields where applicable": books must have a price and rating (`missing_price`,
`missing_rating`); quotes must have an author (`missing_author`). Rejected records are logged as warnings and counted
by reason in the report; the run continues.

## 6. Deduplication (`processing/deduplication.py`)

A record's **fingerprint** is a SHA-256 hash of its identifying fields after normalisation (Unicode NFKC, case-folded,
punctuation removed, whitespace collapsed), joined with `|`:

* Books: `source | title`
* Quotes: `source | author | first 50 characters of the normalised quote text`

So `"Example Book Title"`, `" Example Book Title "` and `"EXAMPLE BOOK TITLE"` are one record. Fingerprints go into a
`set`; a record whose fingerprint was already seen is a duplicate. **Choice: duplicates are removed** (first occurrence
kept), not flagged, because the output should be one row per real-world item; every removal is logged and counted in
`duplicates_detected`. The practice sites contain no duplicates, so a real run will most likely report 0; the logic is
proven by `tests/test_deduplication.py` and the end-to-end test, which use deliberately duplicated data.

## 7. Error handling and logging

* **Network:** one `requests.Session` with a User-Agent, a 15 s timeout and `Retry` (3 retries, exponential backoff,
  on 429/500/502/503/504; `Retry-After` is honoured).
* **Failed listing page** (after retries): logged as ERROR, that source stops but **keeps the records it already has**
  and is marked `partial` in the report. The other source still runs.
* **Failed book detail page:** logged, the book is kept with empty category/description, counted in `detail_page_failures`.
* **Missing HTML element:** every lookup checks for `None`; a record missing its title or URL is rejected by validation
  with a reason. An unexpected exception while parsing one record skips only that record.
* **Each source** runs in its own `try/except` in `main.py`.
* **Politeness:** 0.5 s minimum between any two requests (sequential, no parallelism); `robots.txt` is read and obeyed.
* **Logging:** console (INFO+) and `logs/scraper.log` (DEBUG+), time-stamped.

## 8. Summary report

`summary_report.json` has `collected_per_source`, `cleaned_per_source`, `rejected_per_source`, `rejected_by_reason`,
`duplicates_per_source`, `duplicates_detected`, `final_per_source`, `final_record_count`, run start/end/duration, a
`source_health` block (status `ok`/`partial`/`failed`, pages fetched/failed, detail failures) and a `reconciliation`
check: **collected - rejected - duplicates = final** for each source. "Cleaned" means records that were successfully
converted to the common layout. A record with several problems counts once in `rejected_per_source` but once per problem
in `rejected_by_reason`.

## 9. Project structure

```
main.py                    # connects the stages, CLI, logging setup
config.py                  # URLs, timeouts, delay, retry settings
scrapers/                  # everything that touches the internet
  base_scraper.py          #   session, retries, delay, robots.txt, pagination loop
  books_scraper.py         #   Books selectors (+ optional detail pages)
  quotes_scraper.py        #   Quotes selectors
processing/                # pure data transformation, no internet
  cleaning.py  transform.py  validation.py  deduplication.py  consolidation.py
tests/                     # unit tests + offline end-to-end tests using a local mock server
```

## Assumptions

* Prices are in GBP (the site shows `£`); the currency is not stored as a column.
* "Rating" is the star rating (1-5) shown on the site.
* A Quotes row's `source_url` is the listing page, not the author page.
* A 403/401 response for `robots.txt` is treated as "off-limits"; a 404 means "no restrictions".

## Known limitations

* Book detail pages add ~1,000 requests, so a full run takes 10-15 minutes (use `--skip-details` for a quick run).
* If a listing page fails after retries, later pages of that source are not scraped (the "next" link is only on the page
  that failed). The report marks the source `partial`.
* The scraper is sequential on purpose (politeness over speed).
* Selectors are specific to the current layout of the two sites; a layout change triggers a "No records matched"
  warning and rejected records rather than a crash.
* The CSV is UTF-8 without a BOM; Excel may need "import as UTF-8" to show non-ASCII characters correctly.

## If this had to run regularly in production

Scheduled runs (cron/Airflow) with alerting on `status != ok`; incremental scraping (skip books already stored, key on
the fingerprint); store results in a database instead of overwriting a CSV; checkpoint/resume for long runs; rotate
logs; configuration through environment variables; contract tests that fail when selectors stop matching.

## AI usage summary

See `AI_USAGE.md`.
