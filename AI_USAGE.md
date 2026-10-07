# AI Usage

## AI tools used

| Tool | Used for |
| --- | --- |
| Claude (Anthropic), via claude.ai | Generated the first full version of the project (scrapers, processing, `main.py`, tests, README) from the assignment brief and the reference guide, and ran offline tests in its own sandbox. Also helped with PowerShell commands, packaging the ZIP and understanding the output files. |

## Representative prompts

1. Pasted the reference guide and the assignment brief with no extra instruction.
2. Pasted "17. Important Rules" so the design would respect them.
3. Answered "yes" when asked whether the Books scraper should visit each book's detail page (with a `--skip-details` flag for quick runs).
4. Asked whether the log showed the scraper moving through pages one by one.
5. Asked whether the project met the six requirements in section 1.1 of the reference guide (follow the "next" link, common layout, cleaning, validation, duplicate detection, three output files).
6. Asked where to check `reconciliation.ok`, the CSV row count and sample rows against the websites.
7. Asked how to zip and send the project.

## Which parts were AI-assisted

Essentially all of the first draft of the code and documentation was written by Claude. I then ran the full
pipeline on the real websites, checked the output files against each other and against the live sites,
investigated the duplicate that was found, and prepared the submission myself.

## Design decisions in the generated code (I can explain each one)

* `robots.txt` is fetched and obeyed (`BaseScraper._load_robots`). `RobotFileParser.parse()` must be followed by
  `.modified()`, otherwise `can_fetch()` returns `False` for everything. The real sites returned HTTP 404 for it,
  which means no restrictions are declared.
* Pagination follows `li.next > a` with `urljoin`; no page numbers are hard-coded. A `visited` set and a page limit
  (`MAX_PAGES`) prevent endless loops.
* The 0.5 s pause is enforced as "minimum gap since the last request" (`_wait_politely`), so it also covers the
  ~1,000 book detail requests.
* A failed listing page stops that source but keeps its earlier records; the report marks it `partial`. The other
  source still runs because each source has its own `try/except` in `main.py`.
* The fingerprint joins fields with `|` and normalises each field separately (so "ab" + "c" differs from
  "a" + "bc"), using NFKC + casefold + punctuation removal. Books use source + title; quotes use source + author +
  the first 50 characters of the normalised quote text. Duplicates are removed (first occurrence kept) and logged.
* A value that is present but cannot be converted is kept as text so validation can reject it with a reason
  (`_value_or_raw`) instead of silently becoming an empty cell.
* Extra validation rules (`missing_price`, `missing_rating`, `missing_author`) on top of the five in the brief.
* Quotes use the listing-page URL as `source_url`.
* The summary report includes a reconciliation check: collected - rejected - duplicates = final, per source.

## Important changes after reviewing the AI output

* Corrected the README's estimated run time from 10-15 minutes to about 20 minutes, based on my real run.
* No changes to the Python code were needed after running it on the real websites.

## Incorrect or incomplete AI suggestions discovered

* The first setup instructions used `&&` and `source venv/bin/activate` (macOS/Linux syntax). They failed in
  Windows PowerShell; the correct activation command is `venv\Scripts\Activate.ps1`.
* The README estimated a full run at 10-15 minutes. My real run took about 20 minutes (1218.5 s), because each
  listing page also opens 20 book pages one at a time with a 0.5 s pause (about 21 s per page).
* Claude's sandbox could not reach the practice sites, so it could only test against a local mock copy. The live
  selectors and `robots.txt` behaviour were first confirmed by my own run, which worked on both sites.
* The reference guide expected 0 duplicates on these sites, but my run found 1 (see below).

## How the final solution was tested and verified

* **Unit and offline end-to-end tests:** `pytest -q` runs 38 tests (cleaning, validation, deduplication, and runs
  against a local mock server covering pagination, detail pages, `robots.txt`, a failing page, a dead source and
  `--skip-details`). Claude's sandbox: 38 passed. On my machine: 38 passed
* **Full run on the real sites** (`python main.py`, started 2026-10-06 07:54 UTC, duration 1218.5 s):
  * 50 book pages and 10 quote pages fetched, 0 pages failed, 0 detail-page failures, 0 skipped records.
  * `collected_per_source`: Books 1000, Quotes 100. Nothing rejected by validation.
  * `source_health`: Books `ok`, Quotes `ok`.
  * `reconciliation.ok` is `true`: Books 1000 - 0 - 1 = 999, Quotes 100 - 0 - 0 = 100, total 1099.
* **Output consistency:** `final_record_count` in `summary_report.json` is 1099 and the CSV also has 1099 data rows
  (counted with `Import-Csv`).
* **Manual spot-check:** I compared 5 rows against the live websites (title, price, rating,
  category, description for books; text, author and tags for quotes) and they matched.
* **Duplicate found:** the log reported 1 duplicate in the Books source: 'The Star-Touched Queen' (https://books.toscrape.com/cataloguethe-star-touched-queen_642/index.html).
  The first occurrence was kept. The
  duplicate logic is also covered by unit tests using deliberately duplicated data (different case, spacing and
  punctuation).