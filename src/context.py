"""Ghép bộ lọc của câu hỏi nối tiếp với ngữ cảnh câu trước bằng luật cố định (không đưa lịch sử chat cho LLM)."""
import re
from dataclasses import dataclass, field, replace

from .db import Filters
from .normalize import norm

ENTITY_FIELDS = ("name", "district", "ward", "place", "diocese", "church_ids")

# "nhà thờ đó", "trong đó", "ở đó", "các nhà thờ trên", "mấy nhà thờ này"
_REF_RE = re.compile(
    r"\b(?:nha tho|giao xu|cho|noi|nhung nha tho|cac nha tho|may nha tho)\s+(?:do|day|ay|nay|kia|tren)\b"
    r"|\btrong\s+(?:so\s+)?(?:do|nay|cac nha tho tren|danh sach)\b"
    r"|\bo\s+do\b"
)
# "còn ...", "thế còn ...", "... thì sao", "... thì?", "... nữa?"
_FOLLOW_RE = re.compile(r"^(?:con|the con|vay con|vay|con nhu)\b|\bthi sao\b|\bthi\s*$|\bnua\s*$")
_ALL_RE = re.compile(r"\b(?:tat ca|toan bo|moi nha tho|bat ky nha tho)\b")
# LLM đôi khi trích luôn từ tham chiếu làm tên: "nhà thờ đó" -> ten_nha_tho = "đó"
_REF_NAMES = {"do", "day", "ay", "nay", "kia", "nha tho do", "nha tho nay", "nha tho ay", "giao xu do"}


@dataclass
class Context:
    filters: Filters
    hit_ids: list[int] = field(default_factory=list)


@dataclass
class ContextInfo:
    entity: bool = False        # lấy lại tên/địa điểm câu trước
    restricted: bool = False    # chỉ tìm trong kết quả câu trước
    days: bool = False
    time: bool = False

    def any(self) -> bool:
        return self.entity or self.restricted or self.days or self.time


def has_entity(f: Filters) -> bool:
    return any(getattr(f, k) for k in ENTITY_FIELDS)


def apply_context(question: str, f: Filters, ctx: Context | None) -> tuple[Filters, ContextInfo]:
    info = ContextInfo()
    if f.name and norm(f.name) in _REF_NAMES:
        f = replace(f, name=None)
    if ctx is None:
        return f, info

    q = norm(question)
    is_ref, is_follow = bool(_REF_RE.search(q)), bool(_FOLLOW_RE.search(q))
    if _ALL_RE.search(q) or (f.intent == "khac" and not (is_ref or is_follow)):
        return f, info
    if has_entity(f) and not (is_ref or is_follow):
        return f, info  # câu hỏi mới hoàn toàn

    prev = ctx.filters
    if not has_entity(f):
        f = replace(f, **{k: getattr(prev, k) for k in ENTITY_FIELDS})
        info.entity = has_entity(prev)
        if is_ref and ctx.hit_ids:
            f.church_ids = list(ctx.hit_ids)
            info.restricted = True
    # Hỏi địa chỉ/thông tin thì hiện đầy đủ, không giữ lọc thứ/giờ của câu trước.
    if f.intent != "thong_tin":
        if not f.days and prev.days:
            f.days, info.days = list(prev.days), True
        if f.time_from is None and f.time_to is None and (prev.time_from is not None or prev.time_to is not None):
            f.time_from, f.time_to, info.time = prev.time_from, prev.time_to, True
    return f, info
