"""Run the whole job with:  python main.py

Pipeline:  Scrape -> Clean -> Validate -> Deduplicate -> Consolidate -> Save files
Each source runs inside its own try/except, so one failing site never stops the other.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import config
from processing.consolidation import consolidate, write_csv, write_summary
from processing.deduplication import find_duplicates
from processing.transform import transform_book, transform_quote
from processing.validation import validate_record
from scrapers.base_scraper import create_session
from scrapers.books_scraper import BooksScraper
from scrapers.quotes_scraper import QuotesScraper

logger = logging.getLogger("main")


# ----------------------------------------------------------------------------- logging
def setup_logging(log_file: Path) -> None:
    """Console shows INFO and above; the log file also keeps DEBUG (every single request)."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):                  # remove only OUR handlers from a previous call
        if getattr(handler, "_from_main", False):
            root.removeHandler(handler)
            handler.close()
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    file_handler = logging.FileHandler(log_file, mode="w", encoding="utf-8")   # fresh log each run
    file_handler.setLevel(logging.DEBUG)
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    for handler in (file_handler, console):
        handler.setFormatter(fmt)
        handler._from_main = True
        root.addHandler(handler)
    logging.getLogger("urllib3").setLevel(logging.WARNING)   # keep third-party noise out of the log


# ----------------------------------------------------------------------------- pipeline stages
def process_records(raw_records: list[dict], transform) -> tuple[list[dict], dict]:
    """Clean -> validate -> deduplicate one source's raw records. Returns (final_records, counts)."""
    counts = {
        "collected": len(raw_records), "cleaned": 0, "rejected": 0,
        "rejected_by_reason": Counter(), "duplicates": 0, "final": 0,
    }

    cleaned = []
    for raw in raw_records:                               # CLEAN
        try:
            cleaned.append(transform(raw))
        except Exception as exc:
            counts["rejected"] += 1
            counts["rejected_by_reason"]["transform_error"] += 1
            logger.warning("Could not clean a record (%r): %r", exc, raw)
    counts["cleaned"] = len(cleaned)

    valid = []
    for rec in cleaned:                                   # VALIDATE
        problems = validate_record(rec)
        if problems:
            counts["rejected"] += 1
            counts["rejected_by_reason"].update(problems)
            logger.warning("Rejected %r (%s): %s", str(rec.get("name_or_title"))[:60],
                           rec.get("source_url"), ", ".join(problems))
        else:
            valid.append(rec)

    unique, dupes = find_duplicates(valid)                # DEDUPLICATE (duplicates are removed)
    for dupe in dupes:
        logger.info("Duplicate removed: %r (%s)", str(dupe.get("name_or_title"))[:60], dupe.get("source_url"))
    counts["duplicates"] = len(dupes)
    counts["final"] = len(unique)
    counts["rejected_by_reason"] = dict(counts["rejected_by_reason"])
    return unique, counts


def run_source(scraper, transform) -> tuple[list[dict], dict]:
    """Scrape one source, then push its records through the processing stages."""
    error = None
    try:
        scraper.scrape()
    except Exception as exc:                              # unexpected bug: keep what we already have
        logger.exception("[%s] Scraper crashed", scraper.source_name)
        error = f"{type(exc).__name__}: {exc}"

    final, counts = process_records(scraper.records, transform)
    stats = scraper.stats
    if counts["collected"] == 0:
        status = "failed"
    elif error or not stats["complete"] or stats["detail_failures"] or stats["records_skipped"]:
        status = "partial"
    else:
        status = "ok"
    counts["health"] = {
        "status": status,
        "pages_fetched": stats["pages_fetched"],
        "pages_failed": stats["pages_failed"],
        "records_skipped_during_scrape": stats["records_skipped"],
        "detail_page_failures": stats["detail_failures"],
        "error": error,
    }
    logger.info("[%s] status=%s collected=%d rejected=%d duplicates=%d final=%d",
                scraper.source_name, status, counts["collected"], counts["rejected"],
                counts["duplicates"], counts["final"])
    return final, counts


# ----------------------------------------------------------------------------- CLI + main
def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Books to Scrape and Quotes to Scrape into one dataset.")
    p.add_argument("--skip-details", action="store_true",
                   help="do not open each book's page (faster; category and description stay empty)")
    p.add_argument("--only", nargs="+", choices=["books", "quotes"], default=["books", "quotes"],
                   help="run only the listed source(s)")
    p.add_argument("--max-pages", type=int, default=None,
                   help="stop each source after N listing pages (handy for quick tests)")
    p.add_argument("--delay", type=float, default=config.REQUEST_DELAY,
                   help="seconds to pause between requests (default %(default)s)")
    p.add_argument("--output-dir", type=Path, default=config.OUTPUT_DIR)
    p.add_argument("--log-file", type=Path, default=config.LOG_FILE)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_file)
    if args.delay < 0.5:
        logger.warning("Delay of %.2fs is below the recommended 0.5s - please stay polite", args.delay)

    start = datetime.now(timezone.utc)
    t0 = time.monotonic()
    logger.info("Run started (details=%s, sources=%s)", not args.skip_details, ",".join(args.only))

    session = create_session()
    common = {"delay": args.delay, "max_pages": args.max_pages}
    jobs = {
        "books": lambda: (BooksScraper(session, fetch_details=not args.skip_details,
                                       start_url=config.BOOKS_START_URL, **common), transform_book),
        "quotes": lambda: (QuotesScraper(session, start_url=config.QUOTES_START_URL, **common),
                           transform_quote),
    }
    names = {"books": config.SOURCE_BOOKS, "quotes": config.SOURCE_QUOTES}

    per_source: dict[str, dict] = {}
    final_lists: list[list[dict]] = []
    for key in args.only:
        try:                                              # one source failing never stops the other
            scraper, transform = jobs[key]()
            final, counts = run_source(scraper, transform)
        except Exception as exc:
            logger.exception("Source '%s' failed completely", key)
            final = []
            counts = {"collected": 0, "cleaned": 0, "rejected": 0, "rejected_by_reason": {},
                      "duplicates": 0, "final": 0,
                      "health": {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}}
        per_source[names[key]] = counts
        final_lists.append(final)

    all_records = consolidate(*final_lists)
    end = datetime.now(timezone.utc)

    reasons: Counter = Counter()
    for c in per_source.values():
        reasons.update(c["rejected_by_reason"])
    reconciles = all(c["collected"] - c["rejected"] - c["duplicates"] == c["final"] for c in per_source.values())
    summary = {
        "run": {
            "start_time_utc": start.isoformat(timespec="seconds"),
            "end_time_utc": end.isoformat(timespec="seconds"),
            "duration_seconds": round(time.monotonic() - t0, 1),
            "book_detail_pages_fetched": not args.skip_details,
        },
        "collected_per_source": {n: c["collected"] for n, c in per_source.items()},
        "cleaned_per_source": {n: c["cleaned"] for n, c in per_source.items()},
        "rejected_per_source": {n: c["rejected"] for n, c in per_source.items()},
        "rejected_by_reason": dict(reasons),
        "duplicates_per_source": {n: c["duplicates"] for n, c in per_source.items()},
        "duplicates_detected": sum(c["duplicates"] for c in per_source.values()),
        "final_per_source": {n: c["final"] for n, c in per_source.items()},
        "final_record_count": len(all_records),
        "source_health": {
            n: {**c["health"], "rejected_by_reason": c["rejected_by_reason"]} for n, c in per_source.items()
        },
        "reconciliation": {"rule": "collected - rejected - duplicates == final (per source)", "ok": reconciles},
    }
    if not reconciles:
        logger.error("Counts do not reconcile - check the summary report")

    out = Path(args.output_dir)
    write_csv(all_records, out / "final_dataset.csv")
    write_summary(summary, out / "summary_report.json")
    logger.info("Wrote %d rows to %s and the summary to %s", len(all_records),
                out / "final_dataset.csv", out / "summary_report.json")
    logger.info("Run finished in %.1fs", summary["run"]["duration_seconds"])

    failed = [n for n, c in per_source.items() if c["health"]["status"] == "failed"]
    return 1 if failed else 0       # non-zero exit code if any source produced nothing


if __name__ == "__main__":
    sys.exit(main())
