"""Gộp các giáo xứ mới có tọa độ (data/interim/tgpsg_missing_coords.csv) vào dataset complete.

Chạy từ thư mục gốc dự án:
    python scripts\\merge_complete.py                 # ghi đè data/processed/catholic_churches_complete.csv
    python scripts\\merge_complete.py --out <file>    # ghi ra file khác để xem trước

Giữ nguyên các dòng cũ (thứ tự và giá trị), nối các dòng mới vào sau.
Cột = cột của dataset cũ trước, rồi các cột chỉ dataset mới có. Cột nào một bên không có thì để trống.
Dừng lại nếu hai bên trùng church_id / tgpsg_parish_url hoặc dòng mới thiếu tọa độ.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "data" / "processed" / "catholic_churches_complete.csv"
NEW = ROOT / "data" / "interim" / "tgpsg_missing_coords.csv"


def read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OLD)
    args = ap.parse_args()

    old_cols, old = read(OLD)
    new_cols, new = read(NEW)

    for key in ("church_id", "tgpsg_parish_url"):
        dup = {r[key] for r in old} & {r[key] for r in new}
        if dup:
            raise SystemExit(f"Trùng {key} giữa hai dataset: {sorted(dup)[:5]}...")
    no_coords = sorted({r["church_id"] for r in new if not (r["latitude"] and r["longitude"])})
    if no_coords:
        raise SystemExit(f"{len(no_coords)} giáo xứ mới chưa có tọa độ: {no_coords[:5]}...")

    cols = old_cols + [c for c in new_cols if c not in old_cols]
    rows = [{c: r.get(c, "") for c in cols} for r in old + new]

    try:
        with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    except PermissionError:
        raise SystemExit(f"Không ghi được {args.out} (file đang mở trong Excel?). Đóng file rồi chạy lại.")

    n_old = len({r["church_id"] for r in old})
    n_new = len({r["church_id"] for r in new})
    print(f"Cũ: {n_old} giáo xứ, {len(old)} dòng. Mới: {n_new} giáo xứ, {len(new)} dòng.")
    print(f"Đã ghi {args.out}: {n_old + n_new} giáo xứ, {len(rows)} dòng, {len(cols)} cột.")
    print(f"Cột chỉ dataset mới có (dòng cũ để trống): {[c for c in new_cols if c not in old_cols]}")
    print(f"Cột chỉ dataset cũ có (dòng mới để trống): {[c for c in old_cols if c not in new_cols]}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
