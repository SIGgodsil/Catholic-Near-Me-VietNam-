#!/usr/bin/env python3
"""Collect parish entries from the TGPSG deanery listing."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


LIST_URL = "https://tgpsaigon.net/gioi-thieu-giao-xu/"
DOMAIN = "https://tgpsaigon.net"
DEFAULT_OUTPUT = Path("data/processed/tgpsaigon_parishes.csv")
OUTPUT_FIELDS = (
    "deanery_name",
    "deanery_id",
    "parish_name",
    "parish_address",
    "parish_url",
    "verification_status",
)


class ScraperError(ValueError):
    """A page, parsing, or output error that should be shown to the user."""


def normalize_url(href: str, base_url: str = DOMAIN) -> str:
    """Return an absolute URL for a parish link."""
    return urljoin(base_url.rstrip("/") + "/", href.strip())


def make_parish_record(
    deanery_name: str, deanery_id: str, parish_name: str, parish_address: str, href: str
) -> dict[str, str]:
    """Build one normalized record from values read from the source list."""
    return {
        "deanery_name": deanery_name.strip(),
        "deanery_id": str(deanery_id).strip(),
        "parish_name": parish_name.strip(),
        "parish_address": parish_address.strip(),
        "parish_url": normalize_url(href),
        "verification_status": "source_listed",
    }


def deduplicate_parishes(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the first parish for each case-insensitive deanery/name pair."""
    result = []
    seen = set()
    for row in rows:
        key = (row["deanery_name"].casefold(), row["parish_name"].casefold())
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def parse_parishes(html: str, deanery_name: str, deanery_id: str) -> list[dict[str, str]]:
    """Parse parish rows from a captured listing fragment (used by unit tests)."""
    soup = BeautifulSoup(html, "html.parser")
    cells = soup.select("td.parishname")
    if not cells:
        raise ScraperError("No td.parishname parish entries found.")
    records = []
    for cell in cells:
        link = cell.find("a", href=True)
        row = cell.find_parent("tr")
        row_cells = row.find_all("td", recursive=False) if row else []
        if link is None or len(row_cells) <= 2:
            continue
        records.append(make_parish_record(
            deanery_name, deanery_id, link.get_text(" ", strip=True),
            row_cells[2].get_text(" ", strip=True), link["href"],
        ))
    if not records:
        raise ScraperError("No usable parish rows with a name link and third td address.")
    return records


def scrape_parishes() -> tuple[list[dict[str, str]], list[str], int]:
    """Use the page's deanery links and parish table; return rows, errors, processed count."""
    records: list[dict[str, str]] = []
    errors: list[str] = []
    processed = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=60000)
            deaneries = page.locator("a#deaneryName")
            count = deaneries.count()
            if count != 14:
                errors.append(f"Expected 14 deanery links, found {count}.")
            links = [
                {
                    "name": deaneries.nth(i).inner_text().strip(),
                    "id": deaneries.nth(i).get_attribute("data-id") or "",
                }
                for i in range(count)
            ]
            for index, deanery in enumerate(links):
                label = deanery["name"] or f"link #{index + 1}"
                try:
                    row_locator = page.locator("table tbody tr")
                    previous = row_locator.all_inner_texts()
                    deaneries.nth(index).click(timeout=15000)
                    page.wait_for_function(
                        "old => { const rows = [...document.querySelectorAll('table tbody tr')]; "
                        "return rows.length > 0 && JSON.stringify(rows.map(r => r.innerText)) "
                        "!== JSON.stringify(old); }",
                        arg=previous,
                        timeout=20000,
                    )
                    parish_cells = page.locator("td.parishname")
                    if parish_cells.count() == 0:
                        raise ScraperError("Updated table has no td.parishname entries.")
                    found = 0
                    for parish_index in range(parish_cells.count()):
                        cell = parish_cells.nth(parish_index)
                        link = cell.locator("a[href]")
                        row = cell.locator("xpath=ancestor::tr[1]")
                        cells = row.locator("td")
                        if link.count() == 0 or cells.count() <= 2:
                            errors.append(
                                f"{label}: parish row {parish_index + 1} lacks a name link or third td."
                            )
                            continue
                        name = link.first.inner_text().strip()
                        address = cells.nth(2).inner_text().strip()
                        href = link.first.get_attribute("href") or ""
                        if not name or not href:
                            errors.append(f"{label}: parish row {parish_index + 1} has an empty name or href.")
                            continue
                        records.append(make_parish_record(
                            deanery["name"], deanery["id"], name, address, href
                        ))
                        found += 1
                    processed += 1
                    if found == 0:
                        errors.append(f"{label}: no usable parish entries found.")
                except (PlaywrightError, ScraperError) as exc:
                    errors.append(f"{label} (data-id={deanery['id']}): {exc}")
                    processed += 1
        finally:
            browser.close()
    return deduplicate_parishes(records), errors, processed


def write_parishes(output_path: Path, rows: list[dict[str, str]]) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect TGPSG parish list entries.")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        rows, errors, processed = scrape_parishes()
        write_parishes(args.output, rows)
    except (OSError, PlaywrightError, ScraperError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Deaneries processed: {processed}")
    print(f"Parishes collected: {len(rows)}")
    print(f"Errors: {len(errors)}")
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    print(f"CSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
