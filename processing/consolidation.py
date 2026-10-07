"""Stage 8: join records from all sources and write the output files."""
from __future__ import annotations

import csv
import json
from pathlib import Path

COLUMNS = [
    "source", "source_url", "name_or_title", "category", "price",
    "rating", "author", "tags", "description", "scraped_at",
]


def consolidate(*record_lists: list[dict]) -> list[dict]:
    """Flatten the per-source lists into one list."""
    return [rec for records in record_lists for rec in records]


def write_csv(records: list[dict], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for rec in records:
            writer.writerow({col: rec.get(col) for col in COLUMNS})   # None -> empty cell


def write_summary(stats: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4, ensure_ascii=False)
