"""Lấy tọa độ cho các giáo xứ trong danh sách TGPSG qua Google Places API (Text Search, bản New).

Chạy từ thư mục gốc dự án:
    $env:GOOGLE_MAPS_API_KEY = "..."           # key của bạn, không ghi vào file nào
    python scripts\\geocode_google.py --limit 5  # chạy thử 5 giáo xứ
    python scripts\\geocode_google.py            # chạy hết
    python scripts\\geocode_google.py --dry-run  # chỉ in truy vấn, không gọi API

Đầu vào (chỉ đọc): data/raw/tgpsaigon_parishes.csv, khóa là parish_url.
Đầu ra: data/interim/parish_coords_google.csv, mỗi giáo xứ một dòng kèm độ tin cậy.
Response thô được cache ở data/interim/google_places_cache.json để chạy lại không tốn thêm request.
Lưu ý điều khoản Google Maps Platform về thời hạn lưu tọa độ và việc hiển thị trên bản đồ không phải Google.
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ROOT, SOURCE_CSV
from src.geo import haversine_km
from src.normalize import norm

PARISHES_CSV = ROOT / "data" / "raw" / "tgpsaigon_parishes.csv"
OUT_CSV = ROOT / "data" / "interim" / "parish_coords_google.csv"
CACHE_JSON = ROOT / "data" / "interim" / "google_places_cache.json"

API_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location,places.types"
# TP.HCM sau sáp nhập (gồm cả Bình Dương, Bà Rịa - Vũng Tàu cũ), rộng hơn một chút để không cắt mất giáo xứ ven biên.
HCM_RECT = {"low": {"latitude": 10.30, "longitude": 106.30}, "high": {"latitude": 11.50, "longitude": 107.60}}
PAGE_SIZE = 5
REQUEST_GAP_S = 0.2

CHURCH_TYPES = {"church", "place_of_worship"}
NAME_OK = 80  # điểm rapidfuzz tối thiểu để coi tên khớp

_PREFIX = re.compile(r"^(?:nha tho|giao xu|giao ho|gx|nt|church|parish|catholic)\s+")

OUT_FIELDS = [
    "parish_url", "parish_name", "deanery_name", "parish_address",
    "latitude", "longitude", "confidence", "name_score", "is_church",
    "google_place_id", "google_name", "google_address", "google_types",
    "query_used", "osm_distance_m",
]


def core_name(s: str | None) -> str:
    """'Nhà thờ Giáo xứ Tân Định' -> 'tan dinh'. Bỏ hết các tiền tố lặp nhau."""
    s = norm(s)
    while (t := _PREFIX.sub("", s)) != s:
        s = t
    return s


def split_address(address: str) -> tuple[str, str | None]:
    """'2287 Phạm Thế Hiển, P. Bình Đông (2287 Phạm Thế Hiển, Phường 6, Quận 8)' -> (địa chỉ chính, địa chỉ trong ngoặc)."""
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", address.strip())
    if m:
        return m.group(1).strip(" ,"), m.group(2).strip(" ,")
    return address.strip(), None


def queries_for(parish: dict) -> list[str]:
    main, alt = split_address(parish["parish_address"])
    name = parish["parish_name"].strip()
    qs = [f"Nhà thờ Giáo xứ {name}, {main}"]
    if alt:
        qs.append(f"Nhà thờ Giáo xứ {name}, {alt}")
    qs.append(f"Nhà thờ {name} TP Hồ Chí Minh")
    return qs


def score_place(parish_name: str, place: dict) -> tuple[int, bool]:
    a = core_name(parish_name)
    b = core_name((place.get("displayName") or {}).get("text"))
    # token_sort chứ không phải token_set: token_set cho "Bình An" khớp 100 với "Bình An Thượng" (giáo xứ khác).
    score = int(fuzz.token_sort_ratio(a, b)) if a and b else 0
    return score, bool(CHURCH_TYPES & set(place.get("types") or []))


def pick(parish_name: str, places: list[dict]) -> tuple[dict, int, bool, str] | None:
    """Chọn ứng viên tốt nhất và gán độ tin cậy: high / medium / low."""
    best = None
    for p in places:
        if "location" not in p:
            continue
        score, church = score_place(parish_name, p)
        key = (score >= NAME_OK and church, church, score)
        if best is None or key > best[0]:
            best = (key, p, score, church)
    if best is None:
        return None
    _, p, score, church = best
    if church and score >= NAME_OK:
        conf = "high"
    elif church or score >= NAME_OK:
        conf = "medium"
    else:
        conf = "low"
    return p, score, church, conf


class PlacesClient:
    def __init__(self, api_key: str | None, cache_path: Path = CACHE_JSON, http: httpx.Client | None = None,
                 sleep=time.sleep):
        self.api_key = api_key
        self.cache_path = cache_path
        self.cache: dict[str, list[dict]] = (
            json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        )
        self.http = http or httpx.Client(timeout=20)
        self.sleep = sleep
        self.requests = 0

    def search(self, query: str) -> list[dict]:
        if query in self.cache:
            return self.cache[query]
        if not self.api_key:
            raise SystemExit("Thiếu biến môi trường GOOGLE_MAPS_API_KEY.")
        if self.requests:
            self.sleep(REQUEST_GAP_S)
        resp = self.http.post(
            API_URL,
            headers={"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": FIELD_MASK},
            json={
                "textQuery": query,
                "languageCode": "vi",
                "regionCode": "VN",
                "pageSize": PAGE_SIZE,
                "locationRestriction": {"rectangle": HCM_RECT},
            },
        )
        self.requests += 1
        if resp.status_code != 200:
            # Không in header để key không lọt ra log.
            raise SystemExit(f"Google Places trả về {resp.status_code}: {resp.text[:300]}")
        places = resp.json().get("places", [])
        self.cache[query] = places
        self.save()
        return places

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.cache_path)


def locate(parish: dict, client: PlacesClient) -> dict:
    row = {k: parish.get(k, "") for k in ("parish_url", "parish_name", "deanery_name", "parish_address")}
    rank = {"low": 0, "medium": 1, "high": 2}
    found = None
    for q in queries_for(parish):
        hit = pick(parish["parish_name"], client.search(q))
        if hit and (found is None or rank[hit[3]] > rank[found[0][3]]):
            found = (hit, q)
        if found and found[0][3] == "high":
            break  # truy vấn sau chỉ tốn thêm request
    if not found:
        return row | {"confidence": "none", "query_used": ""}
    (p, score, church, conf), q = found
    loc = p["location"]
    return row | {
        "latitude": round(loc["latitude"], 7), "longitude": round(loc["longitude"], 7),
        "confidence": conf, "name_score": score, "is_church": int(church),
        "google_place_id": p.get("id", ""), "google_name": (p.get("displayName") or {}).get("text", ""),
        "google_address": p.get("formattedAddress", ""), "google_types": "|".join(p.get("types") or []),
        "query_used": q,
    }


def osm_coords() -> dict[str, tuple[float, float]]:
    """Tọa độ OSM của 80 giáo xứ đang có, để đo độ lệch so với Google."""
    out = {}
    if SOURCE_CSV.exists():
        with open(SOURCE_CSV, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("latitude") and r.get("tgpsg_parish_url"):
                    out[r["tgpsg_parish_url"]] = (float(r["latitude"]), float(r["longitude"]))
    return out


def read_parishes(path: Path = PARISHES_CSV) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="chỉ xử lý N giáo xứ đầu tiên (chạy thử)")
    ap.add_argument("--dry-run", action="store_true", help="in truy vấn, không gọi API")
    ap.add_argument("--out", type=Path, default=OUT_CSV)
    args = ap.parse_args(argv)

    parishes = read_parishes()[: args.limit]
    if args.dry_run:
        for p in parishes:
            print(p["parish_name"], "->", " || ".join(queries_for(p)))
        return

    client = PlacesClient(os.getenv("GOOGLE_MAPS_API_KEY"))
    osm = osm_coords()
    rows = []
    for i, p in enumerate(parishes, 1):
        row = locate(p, client)
        if row.get("latitude") != "" and row.get("latitude") is not None and p["parish_url"] in osm:
            lat, lon = osm[p["parish_url"]]
            row["osm_distance_m"] = round(haversine_km(lat, lon, row["latitude"], row["longitude"]) * 1000)
        rows.append(row)
        print(f"[{i}/{len(parishes)}] {row['confidence']:6} {p['parish_name']} -> {row.get('google_name', '')}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    counts = {c: sum(r["confidence"] == c for r in rows) for c in ("high", "medium", "low", "none")}
    dists = sorted(r["osm_distance_m"] for r in rows if r.get("osm_distance_m") not in (None, ""))
    print(f"\nĐã ghi {args.out} ({len(rows)} giáo xứ). Độ tin cậy: {counts}. Request mới tới Google: {client.requests}.")
    if dists:
        print(f"So với OSM ({len(dists)} giáo xứ): trung vị lệch {dists[len(dists) // 2]} m, "
              f"lệch > 200 m: {sum(d > 200 for d in dists)}.")


if __name__ == "__main__":
    main()
