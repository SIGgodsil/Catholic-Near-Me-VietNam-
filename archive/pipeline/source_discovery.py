#!/usr/bin/env python3
"""Create manually-verifiable website search candidates from an Overpass GeoJSON.

This module deliberately does not scrape sites or invent source URLs.  A real
search integration can implement :class:`SearchProvider` and pass it to
``build_candidates``; the command-line entry point uses ``NoSearchProvider``
until such an integration is configured.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence


OUTPUT_FIELDS = (
    "osm_type",
    "osm_id",
    "church_name",
    "search_query",
    "source_url",
    "source_type",
    "verification_status",
)


@dataclass(frozen=True)
class SearchResult:
    """A result returned by a future, real web-search provider.

    ``url`` must be a URL actually returned by that provider.  Callers remain
    responsible for validating that it belongs to the church in question.
    """

    url: str
    source_type: str = "search_result"
    verification_status: str = "unverified"


class SearchProvider(Protocol):
    """Interface for an approved search API; it performs no scraping."""

    def search(self, query: str) -> Sequence[SearchResult]:
        """Return actual results for *query*, or an empty sequence."""


class NoSearchProvider:
    """Default provider: preserves queries for a human to search manually."""

    def search(self, query: str) -> Sequence[SearchResult]:
        return ()


def build_search_query(church_name: str) -> str:
    """Build one Vietnamese search query for a named church."""
    return f'"{church_name}" giờ lễ giáo xứ giáo phận TP.HCM'


def _osm_reference(feature: dict[str, Any]) -> tuple[str, str]:
    """Extract OSM type and ID from normal Overpass GeoJSON identifiers."""
    properties = feature.get("properties")
    reference = ""
    if isinstance(properties, dict):
        raw_reference = properties.get("@id", "")
        if isinstance(raw_reference, (str, int)):
            reference = str(raw_reference)
    if not reference:
        raw_reference = feature.get("id", "")
        if isinstance(raw_reference, (str, int)):
            reference = str(raw_reference)

    osm_type, separator, osm_id = reference.partition("/")
    if separator and osm_type and osm_id:
        return osm_type, osm_id
    return "", reference


def _rows_for_feature(
    feature: dict[str, Any], provider: SearchProvider
) -> Iterable[dict[str, str]]:
    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return ()

    raw_name = properties.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        return ()

    church_name = raw_name.strip()
    query = build_search_query(church_name)
    osm_type, osm_id = _osm_reference(feature)
    results = tuple(result for result in provider.search(query) if result.url)

    # The fallback row makes every unresolved item explicit for manual work.
    if not results:
        return ({
            "osm_type": osm_type,
            "osm_id": osm_id,
            "church_name": church_name,
            "search_query": query,
            "source_url": "",
            "source_type": "",
            "verification_status": "needs_search",
        },)

    return tuple({
        "osm_type": osm_type,
        "osm_id": osm_id,
        "church_name": church_name,
        "search_query": query,
        "source_url": result.url,
        "source_type": result.source_type,
        "verification_status": result.verification_status,
    } for result in results)


def build_candidates(
    geojson: dict[str, Any], provider: SearchProvider | None = None
) -> list[dict[str, str]]:
    """Return candidate rows for named features in a GeoJSON FeatureCollection.

    Raises ``ValueError`` for malformed top-level GeoJSON.  Features without a
    non-blank ``properties.name`` are skipped.
    """
    if not isinstance(geojson, dict):
        raise ValueError("GeoJSON top level must be an object.")
    features = geojson.get("features")
    if not isinstance(features, list):
        raise ValueError("GeoJSON must contain a 'features' array.")

    active_provider = provider or NoSearchProvider()
    rows: list[dict[str, str]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ValueError(f"Feature at index {index} must be an object.")
        rows.extend(_rows_for_feature(feature, active_provider))
    return rows


def read_geojson(input_path: Path) -> dict[str, Any]:
    """Read and parse a UTF-8 GeoJSON file with useful error messages."""
    try:
        with input_path.open("r", encoding="utf-8-sig") as source_file:
            document = json.load(source_file)
    except FileNotFoundError as exc:
        raise ValueError(f"Input file does not exist: {input_path}") from exc
    except IsADirectoryError as exc:
        raise ValueError(f"Input path is a directory, not a file: {input_path}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"Input file is not valid UTF-8: {input_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Input file is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("GeoJSON top level must be an object.")
    return document


def write_candidates(output_path: Path, rows: Iterable[dict[str, str]]) -> int:
    """Write standard candidate columns and return the row count."""
    try:
        with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
            writer.writeheader()
            count = 0
            for row in rows:
                writer.writerow(row)
                count += 1
    except OSError as exc:
        raise ValueError(f"Cannot write output file {output_path}: {exc}") from exc
    return count


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create source_candidates.csv from named Overpass GeoJSON features. "
            "This command does not search or scrape the web; it exports queries "
            "for manual verification until a real search API is integrated."
        )
    )
    parser.add_argument("geojson_path", type=Path, help="Path to an Overpass GeoJSON file.")
    parser.add_argument(
        "-o", "--output", type=Path, default=Path("source_candidates.csv"),
        help="Output CSV path (default: source_candidates.csv).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = read_geojson(args.geojson_path)
        rows = build_candidates(document)
        count = write_candidates(args.output, rows)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote {count} candidate row(s) to {args.output}.")
    if count == 0:
        print("No named features found; CSV contains headers only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
