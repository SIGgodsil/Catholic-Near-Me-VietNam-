"""Đọc CSV gốc (chỉ đọc) và tạo lại data/churches.db.

Chạy từ thư mục gốc dự án: python scripts\\build_db.py [đường_dẫn_csv]
"""
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import DB_PATH, SOURCE_CSV
from src.normalize import DAY_EN, norm, norm_district, norm_name, norm_ward, parse_address, time_to_minutes

SCHEMA = """
CREATE TABLE churches (
    id INTEGER PRIMARY KEY,
    church_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    parish_name TEXT NOT NULL,
    name_norm TEXT NOT NULL,
    address TEXT NOT NULL,
    address_norm TEXT NOT NULL,
    districts TEXT NOT NULL,       -- nhiều giá trị, phân tách bằng '|'
    districts_norm TEXT NOT NULL,
    wards TEXT NOT NULL,
    wards_norm TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    parish_url TEXT,
    mass_url TEXT,
    phone TEXT,                    -- cột tùy chọn, dataset hiện tại chưa có
    email TEXT,
    website TEXT
);
CREATE TABLE masses (
    church_id INTEGER NOT NULL REFERENCES churches(id),
    dow INTEGER NOT NULL,          -- 0 = Thứ Hai ... 6 = Chúa Nhật
    time TEXT NOT NULL,            -- 'H:MM' như dữ liệu gốc
    minutes INTEGER NOT NULL,
    UNIQUE (church_id, dow, minutes)
);
CREATE INDEX idx_masses_dow_min ON masses(dow, minutes);
"""

OPTIONAL_TEXT = ["phone", "email", "website"]
REQUIRED = ["church_id", "display_name", "tgpsg_parish_name", "tgpsg_parish_address", "day_of_week", "mass_time"]


def _opt(r: dict, col: str) -> str | None:
    """Giá trị cột tùy chọn; ô trống hoặc 'nan'/'None' do pandas xuất ra thành NULL."""
    v = (r.get(col) or "").strip()
    return None if v.lower() in ("", "nan", "none", "null") else v


def build(csv_path: Path, db_path: Path) -> None:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    missing = [c for c in REQUIRED if c not in (rows[0] if rows else {})]
    if missing:
        raise SystemExit(f"CSV thiếu cột bắt buộc: {missing}")

    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)

    ids: dict[str, int] = {}
    skipped = 0
    for r in rows:
        key = r["church_id"].strip()
        if not key:
            skipped += 1
            continue
        if key not in ids:
            districts, wards = parse_address(r["tgpsg_parish_address"])
            cur = con.execute(
                "INSERT INTO churches (church_id, name, parish_name, name_norm, address, address_norm,"
                " districts, districts_norm, wards, wards_norm, latitude, longitude, parish_url, mass_url,"
                " phone, email, website) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    key, r["display_name"].strip(), r["tgpsg_parish_name"].strip(),
                    norm_name(r["tgpsg_parish_name"]),
                    r["tgpsg_parish_address"].strip(), norm(r["tgpsg_parish_address"]),
                    "|".join(districts), "|".join(norm_district(d) for d in districts),
                    "|".join(wards), "|".join(norm_ward(w) for w in wards),
                    float(r["latitude"]) if r.get("latitude") else None,
                    float(r["longitude"]) if r.get("longitude") else None,
                    r.get("tgpsg_parish_url", "").strip(), r.get("parish_mass_time_url", "").strip(),
                    *(_opt(r, c) for c in OPTIONAL_TEXT),
                ),
            )
            ids[key] = cur.lastrowid
        day, t = r["day_of_week"].strip(), r["mass_time"].strip()
        if day not in DAY_EN or ":" not in t:
            skipped += 1
            continue
        con.execute(
            "INSERT OR IGNORE INTO masses (church_id, dow, time, minutes) VALUES (?,?,?,?)",
            (ids[key], DAY_EN.index(day), t, time_to_minutes(t)),
        )

    con.commit()
    n_ch = con.execute("SELECT COUNT(*) FROM churches").fetchone()[0]
    n_ms = con.execute("SELECT COUNT(*) FROM masses").fetchone()[0]
    no_district = con.execute("SELECT COUNT(*) FROM churches WHERE districts = ''").fetchone()[0]
    con.close()
    tmp.replace(db_path)
    print(f"Đã tạo {db_path}: {n_ch} nhà thờ, {n_ms} giờ lễ, bỏ qua {skipped} dòng lỗi, "
          f"{no_district} nhà thờ không tách được quận từ địa chỉ.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE_CSV, DB_PATH)
