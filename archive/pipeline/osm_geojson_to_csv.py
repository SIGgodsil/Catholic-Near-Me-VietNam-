#!/usr/bin/env python3
"""Convert the downloaded OSM church GeoJSON to a compact CSV; no network use."""

import csv
import json
import math
from collections import Counter
from pathlib import Path


INPUT_PATH = Path("data/raw/osm_churches.geojson")
OUTPUT_PATH = Path("data/processed/osm_churches.csv")
FIELDS = ("name", "osm_id", "latitude", "longitude")


def valid_point(value):
    """Validate and return a GeoJSON [longitude, latitude] pair."""
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        lon, lat = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lon) and math.isfinite(lat) and -180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def center_point(feature):
    """Read an explicit Overpass center when represented unambiguously."""
    properties = feature.get("properties") or {}
    candidates = (feature.get("center"), properties.get("center"))
    for center in candidates:
        if isinstance(center, dict):
            if "lon" in center and "lat" in center:
                point = valid_point((center["lon"], center["lat"]))
                if point:
                    return point
            point = valid_point(center.get("coordinates"))
            if point:
                return point
        else:
            point = valid_point(center)
            if point:
                return point
    return None


def ring_centroid(ring):
    """Return a planar centroid and area for a polygon ring."""
    points = [valid_point(point) for point in ring] if isinstance(ring, list) else []
    points = [point for point in points if point is not None]
    if len(points) < 3:
        return None
    area2 = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        cross = x1 * y2 - x2 * y1
        area2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area2) < 1e-12:
        return None
    return (cx / (3 * area2), cy / (3 * area2)), abs(area2) / 2


def polygon_centroid(polygon):
    """Use the outer ring centroid for a Polygon coordinate array."""
    if not isinstance(polygon, list) or not polygon:
        return None
    return ring_centroid(polygon[0])


def geometry_point(geometry):
    """Extract a Point or representative Polygon/MultiPolygon position."""
    if not isinstance(geometry, dict):
        return None
    kind, coords = geometry.get("type"), geometry.get("coordinates")
    if kind == "Point":
        return valid_point(coords)
    if kind == "Polygon":
        result = polygon_centroid(coords)
        return result[0] if result else None
    if kind == "MultiPolygon" and isinstance(coords, list):
        parts = [polygon_centroid(polygon) for polygon in coords]
        parts = [part for part in parts if part]
        if not parts:
            return None
        area = sum(part[1] for part in parts)
        if area:
            return (
                sum(part[0][0] * part[1] for part in parts) / area,
                sum(part[0][1] * part[1] for part in parts) / area,
            )
    return None


def convert_feature(feature):
    """Return one CSV row or None when name/coordinates are unusable."""
    properties = feature.get("properties") or {}
    name = properties.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    point = center_point(feature) or geometry_point(feature.get("geometry"))
    if point is None:
        return None
    osm_id = feature.get("id") or properties.get("@id") or properties.get("osm_id") or properties.get("id")
    longitude, latitude = point
    return {
        "name": name.strip(),
        "osm_id": str(osm_id) if osm_id is not None else "",
        "latitude": latitude,
        "longitude": longitude,
    }


def main():
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    features = data.get("features", [])
    if not isinstance(features, list):
        raise ValueError("GeoJSON 'features' must be a list.")
    rows = []
    skipped = 0
    for feature in features:
        row = convert_feature(feature) if isinstance(feature, dict) else None
        if row is None:
            skipped += 1
        else:
            rows.append(row)

    counts = Counter(row["name"].casefold() for row in rows)
    duplicate_groups = sum(count > 1 for count in counts.values())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Input features: {len(features)}")
    print(f"CSV rows: {len(rows)}")
    print(f"Skipped features: {skipped}")
    print(f"Duplicate-name groups (retained): {duplicate_groups}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
