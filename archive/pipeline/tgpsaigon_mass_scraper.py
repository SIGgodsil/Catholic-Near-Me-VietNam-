#!/usr/bin/env python3
"""Collect TGPSG mass times from its public weekly listing."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Sequence
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


SOURCE_URL = "https://tgpsaigon.net/gio-le/"
DEFAULT_OUTPUT = Path("data/processed/tgpsaigon_mass_times.csv")
DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
FIELDS = ("parish_name", "parish_url", "day_of_week", "mass_time", "source", "verification_status")
TIME_FORMAT = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
NO_MASS_TEXT = "Kh\u00f4ng c\u00f3 l\u1ec5"
ENGLISH_SUFFIX = " ti\u1ebfng Anh"


class ScraperError(ValueError):
    """A fatal page or output error."""


def absolute_parish_url(href: str) -> str:
    """Resolve source links without rewriting their path or query."""
    return urljoin("https://tgpsaigon.net/", href.strip())


def normalize_mass_time(value: str) -> str:
    """Apply only the known source formatting fixes; leave other text intact."""
    normalized = value.strip().strip("`").strip()
    if normalized.casefold().endswith(ENGLISH_SUFFIX.casefold()):
        normalized = normalized[:-len(ENGLISH_SUFFIX)].strip()
    match = re.fullmatch(r"(\d{1,2})\.(\d{2})", normalized)
    if match:
        normalized = f"{match.group(1)}:{match.group(2)}"
    return normalized


def extract_row(row_html: str) -> tuple[list[dict[str, str]], int, list[str]]:
    """Convert one mass-time row HTML fragment to CSV records and diagnostics."""
    soup = BeautifulSoup(row_html, "html.parser")
    row = soup.select_one("tr.mass-time-detail")
    if row is None:
        raise ScraperError("Expected tr.mass-time-detail was not present.")
    cells = row.find_all("td", recursive=False)
    if len(cells) < 9:
        raise ScraperError(f"Expected at least 9 td cells, found {len(cells)}.")
    link = cells[1].find("a", href=True)
    parish_name = link.get_text(" ", strip=True) if link else ""
    if not parish_name or link is None:
        raise ScraperError("Parish name link is missing or empty in the second td.")
    parish_url = absolute_parish_url(link["href"])
    issues = []
    parsed_url = urlparse(parish_url)
    if parsed_url.scheme != "https" or parsed_url.hostname != "tgpsaigon.net":
        issues.append(f"Unusual parish URL for {parish_name}: {parish_url}")

    records = []
    blank_cells = 0
    for day, cell in zip(DAYS, cells[2:9]):
        times = [normalize_mass_time(p.get_text(" ", strip=True)) for p in cell.find_all("p")]
        times = [value for value in times if value]
        no_mass = [value for value in times if " ".join(value.split()).casefold() == NO_MASS_TEXT.casefold()]
        if no_mass:
            records.append({
                "parish_name": parish_name,
                "parish_url": parish_url,
                "day_of_week": day,
                "mass_time": "",
                "source": SOURCE_URL,
                "verification_status": "no_mass",
            })
            times = [value for value in times if value not in no_mass]
        if not times and not no_mass:
            blank_cells += 1
        for value in times:
            if not TIME_FORMAT.fullmatch(value):
                issues.append(f"Unrecognized time format for {parish_name} ({day}): {value!r}")
            records.append({
                "parish_name": parish_name,
                "parish_url": parish_url,
                "day_of_week": day,
                "mass_time": value,
                "source": SOURCE_URL,
                "verification_status": "source_listed",
            })
    return records, blank_cells, issues


def parse_mass_rows(rows_html: list[str]) -> tuple[list[dict[str, str]], int, list[str]]:
    """Parse independent row fragments; isolate malformed rows and duplicates."""
    records = []
    errors = []
    blank_cells = 0
    names: dict[str, str] = {}
    seen_rows = set()
    for index, row_html in enumerate(rows_html, start=1):
        try:
            row_records, blanks, row_issues = extract_row(row_html)
            blank_cells += blanks
            errors.extend(f"Row {index}: {issue}" for issue in row_issues)
            name_key = row_records[0]["parish_name"].casefold() if row_records else ""
            parish_url = row_records[0]["parish_url"] if row_records else ""
            if name_key in names:
                if names[name_key] == parish_url:
                    errors.append(f"Row {index}: duplicate parish and URL skipped: {row_records[0]['parish_name']}")
                    continue
                errors.append(f"Row {index}: duplicate parish name with a different URL: {row_records[0]['parish_name']}")
            else:
                names[name_key] = parish_url
            row_key = (name_key, parish_url)
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)
            records.extend(row_records)
        except ScraperError as exc:
            errors.append(f"Row {index}: {exc}")
    return records, blank_cells, errors


def scrape_mass_times() -> tuple[list[dict[str, str]], int, list[str], int]:
    """Read all listing rows using Playwright; return records and diagnostics."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(SOURCE_URL, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_selector("tr.mass-time-detail", timeout=30000)
            except PlaywrightError as exc:
                raise ScraperError(f"No mass-time rows loaded from {SOURCE_URL}: {exc}") from exc
            row_locator = page.locator("tr.mass-time-detail")
            row_count = row_locator.count()
            rows_html = [row_locator.nth(i).evaluate("el => el.outerHTML") for i in range(row_count)]
        finally:
            browser.close()
    records, blank_cells, errors = parse_mass_rows(rows_html)
    return records, blank_cells, errors, row_count


def write_csv(path: Path, records: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect TGPSG mass times from the weekly listing.")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        records, blank_cells, errors, parish_rows = scrape_mass_times()
        write_csv(args.output, records)
    except (OSError, PlaywrightError, ScraperError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(f"Parish rows processed: {parish_rows}")
    print(f"Mass time records: {sum(row['verification_status'] == 'source_listed' for row in records)}")
    print(f"Empty day cells: {blank_cells}")
    print(f"Errors and warnings: {len(errors)}")
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    print(f"CSV: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
