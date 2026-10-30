import re
import unicodedata

_LETTER = "A-Za-zÀ-ỹĐđ"
# "Q. 5", "Q.Gò Vấp", "Q Tân Bình", "Quận 3" — nhưng không khớp "Quang Trung".
_DISTRICT_RE = re.compile(rf"(?<![{_LETTER}])(?:[Qq]uận|Q\.|Q(?=[\s\d]))\s*([^,;().]+)")
# "P.5", "P.Cầu Kho", "Phường An Hội Đông" — nhưng không khớp "TP.HCM", "KP.1", "Phạm".
_WARD_RE = re.compile(rf"(?<![{_LETTER}])(?:[Pp]hường|P\.|P(?=[\s\d]))\s*([^,;().]+)")

_NAME_PREFIX = re.compile(r"^(?:nha tho|giao xu|giao ho|gx|nt)\s+")
_DISTRICT_PREFIX = re.compile(r"^(?:quan|q)\s*")
_WARD_PREFIX = re.compile(r"^(?:phuong|p)\s*")

DAY_LABELS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chúa Nhật"]
DAY_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def strip_accents(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str | None) -> str:
    """Chữ thường, bỏ dấu, chỉ giữ chữ/số, gộp khoảng trắng: 'Tân  An!' -> 'tan an'."""
    s = strip_accents(s or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def norm_name(s: str | None) -> str:
    return _NAME_PREFIX.sub("", norm(s))


def norm_district(s: str | None) -> str:
    s = re.sub(r"\s+cu$", "", norm(s))
    return _DISTRICT_PREFIX.sub("", s) if re.match(r"^(?:quan\s|q\s*\d)", s) else s


def norm_ward(s: str | None) -> str:
    s = norm(s)
    return _WARD_PREFIX.sub("", s) if re.match(r"^(?:phuong\s|p\s*\d)", s) else s


def parse_address(address: str) -> tuple[list[str], list[str]]:
    """Tách (danh sách quận, danh sách phường) từ địa chỉ; địa chỉ có thể ghi cả kiểu cũ và mới."""
    districts = [d.strip() for d in _DISTRICT_RE.findall(address) if d.strip()]
    wards = [w.strip() for w in _WARD_RE.findall(address) if w.strip()]
    districts = [re.sub(r"\s+cũ$", "", d) for d in districts]
    return districts, wards


def time_to_minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)
