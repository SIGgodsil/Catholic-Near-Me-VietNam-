"""Thu thập danh sách giáo xứ và giờ lễ từ trang Tổng Giáo phận Sài Gòn (tgpsaigon.net) bằng Scrapling.

Chạy từ thư mục gốc dự án:
    python scripts\\scrape_tgpsaigon.py             # toàn bộ (~225 request, khoảng 4-5 phút)
    python scripts\\scrape_tgpsaigon.py --limit 3   # chạy thử 3 giáo xứ đầu
    python scripts\\scrape_tgpsaigon.py --offline   # chỉ đọc lại HTML đã lưu, không gọi mạng

Nguồn (trang tĩnh, không cần trình duyệt):
    /gioi-thieu-giao-xu/                 -> danh sách giáo hạt (a#deaneryName, data-id)
    /ArchDiocese/LoadParish?id=<giáo hạt> -> bảng giáo xứ: tên, địa chỉ, link
    /gioi-thieu-giao-xu/<slug>           -> địa chỉ, bổn mạng, điện thoại, năm thành lập, bảng giờ lễ

Đầu ra (data/raw/tgpsg/):
    parishes.csv    mỗi giáo xứ một dòng, khóa parish_url
    mass_times.csv  mỗi giờ lễ một dòng, nối với parishes.csv qua parish_url
    html/           bản HTML gốc của lần chạy gần nhất, để parse lại hoặc đối chiếu khi trang đổi
Không thu thập danh sách linh mục (thông tin cá nhân, ứng dụng không cần).
"""
import argparse
import csv
import html as htmllib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

from scrapling.parser import Selector

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "raw" / "tgpsg"
HTML_DIR = OUT_DIR / "html"

BASE = "https://tgpsaigon.net"
LIST_URL = f"{BASE}/gioi-thieu-giao-xu/"
DEANERY_URL = f"{BASE}/ArchDiocese/LoadParish"
DELAY_S = 1.0  # trang của giáo phận, không cần vội
USER_AGENT = "CatholicNearMe/0.1 (du an ca nhan tim gio le; thu thap cham, 1 request/giay)"

DAYS = {
    "chua nhat": "Sunday", "thu hai": "Monday", "thu ba": "Tuesday", "thu tu": "Wednesday",
    "thu nam": "Thursday", "thu sau": "Friday", "thu bay": "Saturday",
}
INFO_FIELDS = {"dia chi": "address", "bon mang": "patron", "dien thoai": "phone", "nam thanh lap": "founded"}

PARISH_FIELDS = [
    "parish_url", "parish_name", "deanery_id", "deanery_name", "list_address",
    "address", "patron", "phone", "founded", "mass_count", "unparsed", "scraped_at",
]
MASS_FIELDS = ["parish_url", "parish_name", "day_of_week", "mass_time", "mass_note", "scraped_at"]


def ascii_key(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(s or "")).strip()


def slug(url: str) -> str:
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] or "index"


# ---------- parse (thuần, không gọi mạng; test dùng các hàm này) ----------

def parse_deaneries(page: Selector) -> list[dict]:
    out = []
    for a in page.css("a#deaneryName"):
        if a.attrib.get("data-id"):
            out.append({"deanery_id": a.attrib["data-id"], "deanery_name": clean(unquote(a.attrib.get("name") or ""))})
    return out


def parse_deanery_parishes(page: Selector) -> list[dict]:
    out = []
    for cell in page.css("td.parishname"):
        href = cell.css("a::attr(href)").get()
        row = cell.parent
        tds = row.css("td") if row is not None else []
        if not href or len(tds) < 3:
            continue
        out.append({
            "parish_url": urljoin(BASE, href.strip()),
            "parish_name": clean(" ".join(cell.css("a ::text").getall())),
            "list_address": clean(" ".join(tds[2].css("::text").getall())),
        })
    return out


_TIME = re.compile(r"(?<!\d)(\d{1,2})\s*[:hg.]\s*(\d{2})(?!\d)")


def parse_mass_cell(text: str) -> tuple[str, str] | None:
    """'16:30 tiếng Anh' -> ('16:30', 'tiếng Anh'); '`17:30' -> ('17:30', ''). Không có giờ hợp lệ -> None."""
    m = _TIME.search(text)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    note = (text[: m.start()] + " " + text[m.end():]).strip(" `'\"-–:,.()")
    return f"{int(m.group(1))}:{m.group(2)}", clean(note)


def parse_parish_detail(page: Selector) -> tuple[dict, list[tuple[str, str, str]]]:
    """Trả về (thông tin, [(ngày, giờ, ghi chú)]). Ô không đọc được giờ được ghi vào info['unparsed']."""
    info = {}
    for li in page.css(".parish-content-detail-modal li"):
        label = ascii_key(" ".join(li.css("b ::text").getall())).rstrip(":").strip()
        if label in INFO_FIELDS:
            full = clean(" ".join(li.css("::text").getall()))
            label_text = clean(" ".join(li.css("b ::text").getall()))
            info[INFO_FIELDS[label]] = full[len(label_text):].strip() if full.startswith(label_text) else full

    masses: dict[tuple[str, str], str] = {}
    unparsed: list[str] = []
    for table in page.css(".parish-content-detail-modal table"):
        heads = [DAYS.get(ascii_key(clean(" ".join(th.css("::text").getall())))) for th in table.css("thead th")]
        if not heads or not all(heads):
            continue  # không phải bảng giờ lễ (vd bảng linh mục)
        for row in table.css("tbody tr"):
            for day, td in zip(heads, row.css("td")):
                for p in td.css("p"):
                    text = clean(" ".join(p.css("::text").getall()))
                    if not text:
                        continue
                    hit = parse_mass_cell(text)
                    if hit is None:
                        unparsed.append(f"{day}: {text}")
                        continue
                    t, note = hit
                    if note or (day, t) not in masses:
                        masses[(day, t)] = note
    if unparsed:
        info["unparsed"] = " | ".join(unparsed)
    order = list(DAYS.values())
    out = [(d, t, n) for (d, t), n in masses.items()]
    return info, sorted(out, key=lambda x: (order.index(x[0]), int(x[1].split(":")[0]), int(x[1].split(":")[1])))


# ---------- fetch ----------

class Source:
    """Lấy HTML: từ mạng (lưu lại vào html/) hoặc chỉ từ bản đã lưu (--offline)."""

    def __init__(self, offline: bool):
        self.offline = offline
        self.session = None
        self.last = 0.0
        self.requests = 0
        if not offline:
            from scrapling.fetchers import FetcherSession
            self.session = FetcherSession(stealthy_headers=False, timeout=30, retries=2).__enter__()

    def get(self, url: str, name: str, params: dict | None = None) -> Selector:
        path = HTML_DIR / f"{name}.html"
        if self.offline:
            if not path.exists():
                raise FileNotFoundError(f"Chưa có bản lưu {path}; chạy lại không kèm --offline.")
            return Selector(path.read_text(encoding="utf-8"), url=url)
        wait = DELAY_S - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        page = self.session.get(url, params=params, headers={"User-Agent": USER_AGENT})
        self.last = time.monotonic()
        self.requests += 1
        if page.status != 200:
            raise RuntimeError(f"{url} trả về {page.status}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page.html_content, encoding="utf-8")
        return page

    def close(self):
        if self.session is not None:
            self.session.__exit__(None, None, None)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="chỉ lấy chi tiết N giáo xứ đầu (chạy thử)")
    ap.add_argument("--offline", action="store_true", help="parse lại HTML đã lưu, không gọi mạng")
    args = ap.parse_args(argv)

    scraped_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    if args.offline and (HTML_DIR / "_list.html").exists():  # giữ thời điểm tải thật, không phải lúc parse lại
        mtime = (HTML_DIR / "_list.html").stat().st_mtime
        scraped_at = datetime.fromtimestamp(mtime, timezone.utc).astimezone().isoformat(timespec="seconds")
    src = Source(args.offline)
    problems: list[str] = []
    parishes: list[dict] = []
    try:
        deaneries = parse_deaneries(src.get(LIST_URL, "_list"))
        print(f"{len(deaneries)} giáo hạt")
        seen = set()
        for d in deaneries:
            rows = parse_deanery_parishes(src.get(DEANERY_URL, f"_deanery_{d['deanery_id']}", {"id": d["deanery_id"]}))
            if not rows:
                problems.append(f"Giáo hạt {d['deanery_name']}: không đọc được giáo xứ nào")
            for r in rows:
                if r["parish_url"] in seen:
                    problems.append(f"Trùng link: {r['parish_name']} ({r['parish_url']})")
                    continue
                seen.add(r["parish_url"])
                parishes.append(d | r)
            print(f"  {d['deanery_name']}: {len(rows)} giáo xứ")

        targets = parishes[: args.limit] if args.limit else parishes
        masses: list[dict] = []
        for i, p in enumerate(targets, 1):
            try:
                info, times = parse_parish_detail(src.get(p["parish_url"], slug(p["parish_url"])))
            except Exception as e:  # một trang lỗi không làm hỏng cả lần chạy
                problems.append(f"{p['parish_name']}: {e}")
                info, times = {}, []
            p.update(info, mass_count=len(times), scraped_at=scraped_at)
            if info.get("unparsed"):
                problems.append(f"{p['parish_name']}: không đọc được giờ: {info['unparsed']}")
            masses += [{"parish_url": p["parish_url"], "parish_name": p["parish_name"],
                        "day_of_week": day, "mass_time": t, "mass_note": note, "scraped_at": scraped_at}
                       for day, t, note in times]
            if not times:
                problems.append(f"{p['parish_name']}: không có bảng giờ lễ")
            print(f"  [{i}/{len(targets)}] {p['parish_name']}: {len(times)} giờ lễ")
    finally:
        src.close()

    suffix = "" if not args.limit else "_sample"
    write_csv(OUT_DIR / f"parishes{suffix}.csv", PARISH_FIELDS, [{k: p.get(k, "") for k in PARISH_FIELDS} for p in targets])
    write_csv(OUT_DIR / f"mass_times{suffix}.csv", MASS_FIELDS, masses)
    print(f"\n{len(targets)} giáo xứ, {len(masses)} giờ lễ, {src.requests} request -> {OUT_DIR}")
    if problems:
        print(f"{len(problems)} vấn đề:")
        for p in problems:
            print("  -", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
