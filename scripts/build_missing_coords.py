"""Tạo dataset riêng gồm các giáo xứ TGPSG CHƯA có tọa độ, latitude/longitude để trống để điền sau.

Chạy từ thư mục gốc dự án: python scripts\\build_missing_coords.py

Đầu vào (chỉ đọc):
    data/raw/tgpsg/parishes.csv, data/raw/tgpsg/mass_times.csv   (từ scripts/scrape_tgpsaigon.py)
    data/processed/catholic_churches_complete.csv                (dataset cũ, 80 giáo xứ có tọa độ)
Đầu ra:
    data/interim/tgpsg_missing_coords.csv
    Cùng định dạng với dataset cũ (mỗi giờ lễ một dòng, cùng tên cột chính) để sau này ghép vào được ngay.
    Giáo xứ không có giờ lễ vẫn có một dòng, day_of_week/mass_time để trống.

So sánh với dataset cũ theo parish_url (link trang giới thiệu giáo xứ), không theo tên vì có tên trùng
(vd 3 giáo xứ "Thánh Giuse"). Cũng in ra các giáo xứ cũ có giờ lễ khác với lần thu thập mới.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARISHES = ROOT / "data" / "raw" / "tgpsg" / "parishes.csv"
MASSES = ROOT / "data" / "raw" / "tgpsg" / "mass_times.csv"
OLD = ROOT / "data" / "processed" / "catholic_churches_complete.csv"
OUT = ROOT / "data" / "interim" / "tgpsg_missing_coords.csv"

DAY_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
FIELDS = [
    "church_id", "display_name", "tgpsg_parish_name", "tgpsg_parish_address", "tgpsg_parish_url",
    "deanery_name", "latitude", "longitude", "day_of_week", "mass_time", "mass_note",
    "phone", "patron", "founded", "parish_mass_time_url", "source_list_url", "scraped_at",
]


def read(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def mass_key(day: str, t: str) -> tuple[int, int, int]:
    h, m = t.split(":")
    return DAY_ORDER.index(day), int(h), int(m)


def main() -> int:
    parishes, masses, old = read(PARISHES), read(MASSES), read(OLD)

    old_by_url: dict[str, list[dict]] = defaultdict(list)
    for r in old:
        if r.get("latitude") and r.get("longitude"):
            old_by_url[r["tgpsg_parish_url"].strip()].append(r)

    new_masses: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for m in masses:
        new_masses[m["parish_url"]].append((m["day_of_week"], m["mass_time"], m["mass_note"]))

    has_coords = [p for p in parishes if p["parish_url"] in old_by_url]
    missing = [p for p in parishes if p["parish_url"] not in old_by_url]
    gone = sorted(set(old_by_url) - {p["parish_url"] for p in parishes})

    rows = []
    for p in missing:
        base = {
            "church_id": "tgpsg:" + p["parish_url"].rstrip("/").rsplit("/", 1)[-1],
            "display_name": f"Nhà thờ {p['parish_name']}",
            "tgpsg_parish_name": p["parish_name"],
            "tgpsg_parish_address": p["address"] or p["list_address"],
            "tgpsg_parish_url": p["parish_url"],
            "deanery_name": p["deanery_name"],
            "latitude": "", "longitude": "",
            "phone": p["phone"], "patron": p["patron"], "founded": p["founded"],
            "parish_mass_time_url": p["parish_url"],  # giờ lễ lấy từ chính trang giới thiệu giáo xứ
            "source_list_url": "https://tgpsaigon.net/gioi-thieu-giao-xu/",
            "scraped_at": p["scraped_at"],
        }
        times = sorted(new_masses.get(p["parish_url"], []), key=lambda x: mass_key(x[0], x[1]))
        if not times:
            rows.append(base | {"day_of_week": "", "mass_time": "", "mass_note": ""})
        rows += [base | {"day_of_week": d, "mass_time": t, "mass_note": n} for d, t, n in times]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"Thu thập mới: {len(parishes)} giáo xứ. Dataset cũ: {len(old_by_url)} giáo xứ có tọa độ.")
    print(f"Đã có tọa độ (loại ra): {len(has_coords)}")
    print(f"Chưa có tọa độ (đưa vào dataset mới): {len(missing)} giáo xứ, {len(rows)} dòng -> {OUT}")
    no_mass = [p["parish_name"] for p in missing if not new_masses.get(p["parish_url"])]
    if no_mass:
        print(f"  Trong đó không có giờ lễ: {', '.join(no_mass)}")
    if gone:
        print(f"Có trong dataset cũ nhưng không còn trên trang TGPSG: {gone}")

    changed = []
    for p in has_coords:
        before = {(r["day_of_week"], r["mass_time"]) for r in old_by_url[p["parish_url"]]}
        after = {(d, t) for d, t, _ in new_masses.get(p["parish_url"], [])}
        if before != after:
            changed.append((p["parish_name"], sorted(after - before, key=lambda x: mass_key(*x)),
                            sorted(before - after, key=lambda x: mass_key(*x))))
    print(f"\nGiáo xứ đã có tọa độ nhưng giờ lễ đã đổi so với dataset cũ: {len(changed)}")
    for name, added, removed in changed:
        fmt = lambda xs: ", ".join(f"{d[:3]} {t}" for d, t in xs) or "-"
        print(f"  {name}: thêm [{fmt(added)}]  bỏ [{fmt(removed)}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
