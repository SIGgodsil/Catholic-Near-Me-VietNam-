"""Tìm kiếm có cấu trúc trên SQLite. Mọi giá trị từ LLM chỉ đi vào tham số, không bao giờ vào câu SQL."""
import re
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz

from .config import DB_PATH
from .normalize import norm, norm_district, norm_name, norm_ward

NAME_THRESHOLD = 85
LOC_THRESHOLD = 88

# Toàn bộ dataset là TGP Sài Gòn / TP.HCM: các tên này nghĩa là "không lọc thêm".
CITY_ALIASES = {"sai gon", "saigon", "tp hcm", "tphcm", "hcm", "ho chi minh", "tp ho chi minh",
                "thanh pho ho chi minh", "thanh pho hcm", "sg"}
DIOCESE_ALIASES = CITY_ALIASES | {"tong giao phan sai gon", "tgp sai gon", "giao phan sai gon",
                                  "tong giao phan tp hcm", "tgp sg", "tong giao phan thanh pho ho chi minh"}


@dataclass
class Filters:
    intent: str = "liet_ke"            # gio_le | liet_ke | thong_tin | khac
    name: str | None = None
    district: str | None = None
    ward: str | None = None
    place: str | None = None           # khu vực/tên đường/địa danh khác
    diocese: str | None = None
    days: list[int] = field(default_factory=list)
    time_from: int | None = None       # phút từ 0:00
    time_to: int | None = None
    church_ids: list[int] | None = None   # giới hạn trong kết quả câu trước ("nhà thờ đó", "trong đó")


@dataclass
class ChurchHit:
    id: int
    name: str
    parish_name: str
    address: str
    parish_url: str
    mass_url: str
    match: str = "exact"               # exact | approx
    score: float = 100.0
    masses: dict[int, list[str]] = field(default_factory=dict)


@dataclass
class SearchResult:
    hits: list[ChurchHit]
    unknown: list[str] = field(default_factory=list)   # điều kiện không khớp được dữ liệu, ví dụ "giáo phận Mỹ Tho"
    notes: list[str] = field(default_factory=list)
    name_missing: bool = False   # chỉ khi lý do không tìm thấy là tên nhà thờ thì mới gợi ý tên gần giống


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Chưa có {DB_PATH}. Chạy scripts/build_db.py trước.")
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


@lru_cache(maxsize=1)
def _churches() -> list[dict]:
    with _connect() as con:
        rows = [dict(r) for r in con.execute("SELECT * FROM churches ORDER BY parish_name")]
    for r in rows:
        r["districts_set"] = [d for d in r["districts_norm"].split("|") if d]
        r["wards_set"] = [w for w in r["wards_norm"].split("|") if w]
    return rows


def reload() -> None:
    _churches.cache_clear()


def _contains_words(haystack: str, needle: str) -> bool:
    return bool(needle) and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def _similar_words(a: str, b: str) -> bool:
    """Sai nhẹ theo từng âm tiết. Âm tiết ≤ 3 ký tự phải đúng hẳn, vì đổi 1 chữ là thành tên khác
    ("tan an" ≠ "tan dan"), còn âm tiết dài được sai 1 chữ ("tan dinhh" = "tan dinh").
    Gõ lặp phím luôn được chấp nhận ("go vapp" = "go vap")."""
    a, b = re.sub(r"(.)\1+", r"\1", a), re.sub(r"(.)\1+", r"\1", b)
    if a.replace(" ", "") == b.replace(" ", ""):
        return True
    wa, wb = a.split(), b.split()
    if len(wa) != len(wb):
        return False
    for x, y in zip(wa, wb):
        if x != y and (min(len(x), len(y)) <= 3 or fuzz.ratio(x, y) < 75):
            return False
    return True


def _fuzzy_eq(a: str, b: str) -> bool:
    if a == b:
        return True
    # Chuỗi ngắn hoặc chứa số (quận 1 vs quận 11) phải khớp tuyệt đối.
    if len(a) < 5 or re.search(r"\d", a + b):
        return False
    return _similar_words(a, b) and (fuzz.ratio(a, b) >= LOC_THRESHOLD or
                                     re.sub(r"(.)\1+", r"\1", a) == re.sub(r"(.)\1+", r"\1", b))


def _match_location(church: dict, raw: str, kind: str) -> bool:
    if kind == "district":
        q = norm_district(raw)
        return any(_fuzzy_eq(q, d) for d in church["districts_set"]) or (
            not q.isdigit() and any(_fuzzy_eq(q, w) for w in church["wards_set"]))
    if kind == "ward":
        q = norm_ward(raw)
        return any(_fuzzy_eq(q, w) for w in church["wards_set"]) or (
            not q.isdigit() and _contains_words(church["address_norm"], q))
    # place: quận, phường, hoặc cụm từ trong địa chỉ (tên đường...)
    q = norm(raw)
    if re.match(r"^(?:quan|q)\s*\d", q):
        return _match_location(church, raw, "district")
    if re.match(r"^(?:phuong|p)\s*\d", q):
        return _match_location(church, raw, "ward")
    q = re.sub(r"^(?:quan|phuong|duong|khu vuc|khu)\s+", "", q)
    return (
        any(_fuzzy_eq(q, d) for d in church["districts_set"] + church["wards_set"])
        or _contains_words(church["address_norm"], q)
    )


def _match_name(churches: list[dict], raw: str) -> list[tuple[dict, str, float]]:
    q = norm_name(raw)
    if not q:
        return []
    exact = [(c, "exact", 100.0) for c in churches if c["name_norm"] == q]
    if exact:
        return exact
    # "Vinh Sơn" -> cả "Vinh Sơn - Ông Tạ" và "Vinh Sơn Phaolô"
    prefix = [(c, "approx", 95.0) for c in churches if c["name_norm"].startswith(q + " ")]
    if prefix:
        return prefix
    scored = [(c, "approx", fuzz.ratio(q, c["name_norm"])) for c in churches if _similar_words(q, c["name_norm"])]
    scored = [s for s in scored if s[2] >= NAME_THRESHOLD]
    if not scored:
        return []
    best = max(s[2] for s in scored)
    return sorted([s for s in scored if s[2] >= best - 3], key=lambda s: -s[2])


def suggest_names(raw: str, limit: int = 3) -> list[str]:
    """Tên gần giống (dưới ngưỡng khớp) để gợi ý, không dùng làm kết quả."""
    q = norm_name(raw)
    scored = sorted(((fuzz.WRatio(q, c["name_norm"]), c["name"]) for c in _churches()), reverse=True)
    return [name for score, name in scored[:limit] if score >= 70]


def _masses(church_ids: list[int], f: Filters) -> dict[int, dict[int, list[str]]]:
    if not church_ids:
        return {}
    sql = f"SELECT church_id, dow, time FROM masses WHERE church_id IN ({','.join('?' * len(church_ids))})"
    params: list = list(church_ids)
    if f.days:
        sql += f" AND dow IN ({','.join('?' * len(f.days))})"
        params += f.days
    if f.time_from is not None:
        sql += " AND minutes >= ?"
        params.append(f.time_from)
    if f.time_to is not None:
        sql += " AND minutes <= ?"
        params.append(f.time_to)
    sql += " ORDER BY church_id, dow, minutes"
    out: dict[int, dict[int, list[str]]] = {}
    with _connect() as con:
        for r in con.execute(sql, params):
            out.setdefault(r["church_id"], {}).setdefault(r["dow"], []).append(r["time"])
    return out


def search(f: Filters) -> SearchResult:
    churches = _churches()
    unknown: list[str] = []
    notes: list[str] = []

    if f.diocese:
        if norm(f.diocese) in DIOCESE_ALIASES or norm(f.diocese).endswith("sai gon"):
            notes.append("Toàn bộ dữ liệu thuộc Tổng Giáo phận Sài Gòn.")
        else:
            unknown.append(f"giáo phận “{f.diocese}”")
            return SearchResult([], unknown, notes)

    candidates = churches
    if f.church_ids:
        allowed = set(f.church_ids)
        candidates = [c for c in candidates if c["id"] in allowed]
    for raw, kind, label in ((f.district, "district", "quận"), (f.ward, "ward", "phường"), (f.place, "place", "khu vực")):
        if not raw:
            continue
        if norm(raw) in CITY_ALIASES:
            notes.append("Toàn bộ dữ liệu nằm ở TP.HCM.")
            continue
        candidates = [c for c in candidates if _match_location(c, raw, kind)]
        if not candidates:
            unknown.append(f"{label} “{raw}”")
            return SearchResult([], unknown, notes)

    matched: list[tuple[dict, str, float]] = [(c, "exact", 100.0) for c in candidates]
    if f.name:
        matched = _match_name(candidates, f.name)
        if not matched:
            unknown.append(f"nhà thờ/giáo xứ “{f.name}”")
            return SearchResult([], unknown, notes, name_missing=True)

    masses = _masses([c["id"] for c, _, _ in matched], f)
    has_time_filter = bool(f.days) or f.time_from is not None or f.time_to is not None
    hits = []
    for c, kind, score in matched:
        m = masses.get(c["id"], {})
        # Khi có lọc theo thứ/giờ, nhà thờ không có lễ phù hợp thì loại khỏi danh sách.
        if has_time_filter and not m:
            continue
        hits.append(ChurchHit(c["id"], c["name"], c["parish_name"], c["address"],
                              c["parish_url"], c["mass_url"], kind, score, m))
    return SearchResult(hits, unknown, notes)
