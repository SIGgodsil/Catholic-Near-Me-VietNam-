"""Câu hỏi -> Filters. LLM trích thực thể; luật cố định kiểm tra và bổ sung thứ/buổi để tránh bộ lọc bịa."""
import datetime as dt
import json
import re
from typing import Literal

import ollama
from pydantic import BaseModel, Field
from rapidfuzz import fuzz

from .config import OLLAMA_HOST, OLLAMA_MODEL
from .db import Filters
from .normalize import norm

DAY_KEYS = ["thu_hai", "thu_ba", "thu_tu", "thu_nam", "thu_sau", "thu_bay", "chu_nhat"]

# Khung giờ của từng buổi (phút). Lễ 17:30 tính là "chiều", từ 18:00 là "tối".
PERIODS = {"sang": (0, 10 * 60 + 59), "trua": (11 * 60, 12 * 60 + 59),
           "chieu": (13 * 60, 17 * 60 + 59), "toi": (18 * 60, 23 * 60 + 59)}


class LLMFilters(BaseModel):
    y_dinh: Literal["gio_le", "liet_ke", "thong_tin", "khac"]
    ten_nha_tho: str | None = Field(None, description="Tên nhà thờ/giáo xứ, bỏ chữ 'nhà thờ', 'giáo xứ'")
    quan: str | None = None
    phuong: str | None = None
    dia_diem: str | None = Field(None, description="Địa danh khác: tên đường, khu vực, tỉnh/thành")
    giao_phan: str | None = None
    thu: list[Literal["thu_hai", "thu_ba", "thu_tu", "thu_nam", "thu_sau", "thu_bay", "chu_nhat"]] = []
    buoi: Literal["sang", "trua", "chieu", "toi"] | None = None
    gio_tu: str | None = Field(None, description="HH:MM")
    gio_den: str | None = Field(None, description="HH:MM")


SYSTEM_PROMPT = """Bạn là bộ phân tích câu hỏi cho chatbot tra cứu nhà thờ Công giáo và giờ lễ.
Nhiệm vụ DUY NHẤT: đọc câu hỏi tiếng Việt (có thể gõ không dấu, sai chính tả) và trả về JSON bộ lọc. Không trả lời câu hỏi.

Các trường:
- y_dinh: "gio_le" (hỏi giờ lễ), "liet_ke" (liệt kê/tìm nhà thờ theo điều kiện), "thong_tin" (hỏi địa chỉ, link, thông tin một nhà thờ), "khac" (không liên quan nhà thờ/giờ lễ).
- ten_nha_tho: tên riêng của nhà thờ/giáo xứ, giữ nguyên cách người dùng viết, bỏ các chữ "nhà thờ", "giáo xứ", "gx".
- quan: quận/huyện/thành phố cấp quận (vd "Gò Vấp", "quận 3", "Thủ Đức"). Nếu người dùng viết "quận 3" thì ghi "quận 3".
- phuong: phường/xã (vd "phường 7", "An Hội Đông").
- dia_diem: địa danh khác không rõ là quận hay phường: tên đường, khu vực, tỉnh/thành phố (vd "Lê Văn Sỹ", "Tân An", "Đà Lạt").
- giao_phan: tên giáo phận nếu có nhắc (vd "Mỹ Tho", "Sài Gòn").
- thu: các ngày được hỏi. "Chúa Nhật" hay "chủ nhật" = chu_nhat. "cuối tuần" = thu_bay + chu_nhat. "ngày thường" = thu_hai..thu_bay. Không nhắc ngày thì để [].
- buoi: "sang", "trua", "chieu", "toi" nếu có nhắc buổi, ngược lại null.
- gio_tu, gio_den: chỉ điền khi có giờ cụ thể, dạng HH:MM. "sau 17h" -> gio_tu "17:00". "trước 7 giờ" -> gio_den "07:00". "khoảng 6h" -> gio_tu "05:30", gio_den "06:30".
Chỉ điền thông tin có trong câu hỏi. Không đoán thêm. Không chắc thì để null.

Ví dụ:
Q: Giờ lễ nhà thờ Tân Định?
{"y_dinh":"gio_le","ten_nha_tho":"Tân Định","quan":null,"phuong":null,"dia_diem":null,"giao_phan":null,"thu":[],"buoi":null,"gio_tu":null,"gio_den":null}
Q: nha tho nao o go vap co le sang chua nhat
{"y_dinh":"liet_ke","ten_nha_tho":null,"quan":"go vap","phuong":null,"dia_diem":null,"giao_phan":null,"thu":["chu_nhat"],"buoi":"sang","gio_tu":null,"gio_den":null}
Q: Liệt kê nhà thờ thuộc giáo phận Mỹ Tho
{"y_dinh":"liet_ke","ten_nha_tho":null,"quan":null,"phuong":null,"dia_diem":null,"giao_phan":"Mỹ Tho","thu":[],"buoi":null,"gio_tu":null,"gio_den":null}
Q: Nhà thờ nào ở Tân An có lễ tối thứ 7?
{"y_dinh":"liet_ke","ten_nha_tho":null,"quan":null,"phuong":null,"dia_diem":"Tân An","giao_phan":null,"thu":["thu_bay"],"buoi":"toi","gio_tu":null,"gio_den":null}
Q: Giáo xứ Phú Nhuận ở đâu?
{"y_dinh":"thong_tin","ten_nha_tho":"Phú Nhuận","quan":null,"phuong":null,"dia_diem":null,"giao_phan":null,"thu":[],"buoi":null,"gio_tu":null,"gio_den":null}
Q: Các nhà thờ ở quận Phú Nhuận
{"y_dinh":"liet_ke","ten_nha_tho":null,"quan":"Phú Nhuận","phuong":null,"dia_diem":null,"giao_phan":null,"thu":[],"buoi":null,"gio_tu":null,"gio_den":null}
Q: chi hoa thu 2 may gio co le
{"y_dinh":"gio_le","ten_nha_tho":"chi hoa","quan":null,"phuong":null,"dia_diem":null,"giao_phan":null,"thu":["thu_hai"],"buoi":null,"gio_tu":null,"gio_den":null}
Q: nhà thờ ở phường 7 quận Tân Bình có lễ sau 18h không
{"y_dinh":"liet_ke","ten_nha_tho":null,"quan":"Tân Bình","phuong":"phường 7","dia_diem":null,"giao_phan":null,"thu":[],"buoi":null,"gio_tu":"18:00","gio_den":null}
Q: Nhà thờ trên đường Lê Văn Sỹ
{"y_dinh":"liet_ke","ten_nha_tho":null,"quan":null,"phuong":null,"dia_diem":"Lê Văn Sỹ","giao_phan":null,"thu":[],"buoi":null,"gio_tu":null,"gio_den":null}
Q: Hôm nay trời có mưa không?
{"y_dinh":"khac","ten_nha_tho":null,"quan":null,"phuong":null,"dia_diem":null,"giao_phan":null,"thu":[],"buoi":null,"gio_tu":null,"gio_den":null}"""

_client = ollama.Client(host=OLLAMA_HOST)


def llm_extract(question: str, model: str = OLLAMA_MODEL) -> LLMFilters:
    resp = _client.chat(
        model=model,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": f"Q: {question}"}],
        format=LLMFilters.model_json_schema(),
        options={"temperature": 0},
        keep_alive="30m",
    )
    return LLMFilters.model_validate_json(resp.message.content)


# ---------- luật cố định ----------

_DAY_PATTERNS = [
    (r"\b(?:thu\s*(?:2|hai)|t2)\b", [0]), (r"\b(?:thu\s*(?:3|ba)|t3)\b", [1]),
    (r"\b(?:thu\s*(?:4|tu)|t4)\b", [2]), (r"\b(?:thu\s*(?:5|nam)|t5)\b", [3]),
    (r"\b(?:thu\s*(?:6|sau)|t6)\b", [4]), (r"\b(?:thu\s*(?:7|bay)|t7)\b", [5]),
    (r"\b(?:chua\s*nhat|chu\s*nhat|cn)\b", [6]), (r"\bcuoi\s*tuan\b", [5, 6]),
    (r"\bngay\s*thuong\b", [0, 1, 2, 3, 4, 5]),
]


def rule_days(question: str, today: dt.date | None = None) -> list[int]:
    q = norm(question)
    today = today or dt.date.today()
    days: set[int] = set()
    # "thứ 2 đến thứ 6"
    rng = re.search(r"thu\s*([2-7])\s*(?:den|toi|-)\s*thu\s*([2-7])", q)
    if rng:
        a, b = int(rng.group(1)) - 2, int(rng.group(2)) - 2
        days.update(range(min(a, b), max(a, b) + 1))
    for pat, ds in _DAY_PATTERNS:
        if re.search(pat, q):
            days.update(ds)
    if re.search(r"\bhom\s*nay\b", q):
        days.add(today.weekday())
    if re.search(r"\bngay\s*mai\b", q):
        days.add((today.weekday() + 1) % 7)
    return sorted(days)


def rule_period(question: str) -> str | None:
    q = question.lower()
    for key, word in (("sang", "sáng"), ("trua", "trưa"), ("chieu", "chiều"), ("toi", "tối")):
        if re.search(rf"(?<!\w){word}(?!\w)", q):
            return key
    # Gõ không dấu: chỉ nhận khi có ngữ cảnh rõ, vì "toi" cũng là "tôi".
    n = norm(question)
    m = re.search(r"\b(?:le|buoi|vao)\s+(sang|trua|chieu|toi)\b", n) or \
        re.search(r"\b(sang|trua|chieu|toi)\s+(?:chua\s*nhat|chu\s*nhat|cn|thu|nay|mai|hom|cuoi|ngay)\b", n)
    return m.group(1) if m else None


_CLOCK = r"(\d{1,2})\s*(?:h|g|gio|:)\s*(\d{2})?"


def rule_times(question: str) -> tuple[int | None, int | None] | None:
    """Giờ cụ thể trong câu: 'trước 5h', 'sau 17:30', 'khoảng 6 giờ', 'từ 5h đến 7h', 'lúc 18h'."""
    q = norm(re.sub(r"(\d{1,2}):(\d{2})", r"\1h\2", question))
    pm = bool(re.search(r"\b(?:chieu|toi)\b", q))

    def mins(h: str, m: str | None) -> int | None:
        hh = int(h)
        if pm and hh < 12:
            hh += 12   # "6h tối" -> 18:00
        return hh * 60 + int(m or 0) if hh <= 23 else None

    if m := re.search(rf"\btu\s+{_CLOCK}\s*(?:den|toi|-)\s*{_CLOCK}", q):
        return mins(m.group(1), m.group(2)), mins(m.group(3), m.group(4))
    if m := re.search(rf"\b(?:truoc|som hon|khong qua)\s+{_CLOCK}", q):
        return None, mins(m.group(1), m.group(2))
    if m := re.search(rf"\b(?:sau|tu|muon hon)\s+{_CLOCK}", q):
        return mins(m.group(1), m.group(2)), None
    if m := re.search(rf"\b(?:khoang|tam|luc|vao)\s+{_CLOCK}", q) or re.search(rf"\b{_CLOCK}\b", q):
        t = mins(m.group(1), m.group(2))
        return (t - 30, t + 30) if t is not None else None
    return None


def _parse_hhmm(s: str | None) -> int | None:
    m = re.fullmatch(r"\s*(\d{1,2})[:h](\d{2})?\s*", s or "")
    if not m or int(m.group(1)) > 23:
        return None
    return int(m.group(1)) * 60 + int(m.group(2) or 0)


def _grounded(value: str | None, question: str) -> str | None:
    """Giữ giá trị LLM trích ra chỉ khi nó thật sự xuất hiện (gần đúng) trong câu hỏi."""
    if not value or not value.strip():
        return None
    v, q = norm(value), norm(question)
    v_core = re.sub(r"^(?:quan|phuong|duong|q|p)\s+", "", v)
    if not v_core:
        return None
    return value.strip() if v_core in q or fuzz.partial_ratio(v_core, q) >= 85 else None


def extract(question: str, model: str = OLLAMA_MODEL) -> tuple[Filters, dict]:
    llm = llm_extract(question, model)
    debug = {"llm": llm.model_dump()}

    days = rule_days(question)
    llm_days = sorted(DAY_KEYS.index(d) for d in llm.thu)
    if not days and llm_days:
        debug["dropped_llm_days"] = llm_days   # LLM thêm ngày mà câu hỏi không nhắc
    period = rule_period(question)
    if llm.buoi and not period:
        debug["dropped_llm_period"] = llm.buoi

    rt = rule_times(question)
    if rt is not None:
        t_from, t_to = rt
        llm_t = (_parse_hhmm(llm.gio_tu), _parse_hhmm(llm.gio_den))
        if llm_t != rt and any(llm_t):
            debug["overridden_llm_times"] = llm_t
    else:
        t_from = t_to = None
        if llm.gio_tu or llm.gio_den:
            debug["dropped_llm_times"] = (llm.gio_tu, llm.gio_den)
    if period:
        p_from, p_to = PERIODS[period]
        t_from = p_from if t_from is None else max(t_from, p_from)
        t_to = p_to if t_to is None else min(t_to, p_to)

    f = Filters(
        intent=llm.y_dinh,
        name=_grounded(llm.ten_nha_tho, question),
        district=_grounded(llm.quan, question),
        ward=_grounded(llm.phuong, question),
        place=_grounded(llm.dia_diem, question),
        diocese=_grounded(llm.giao_phan, question),
        days=days,
        time_from=t_from,
        time_to=t_to,
    )
    for k in ("ten_nha_tho", "quan", "phuong", "dia_diem", "giao_phan"):
        if getattr(llm, k) and not getattr(f, {"ten_nha_tho": "name", "quan": "district", "phuong": "ward",
                                                 "dia_diem": "place", "giao_phan": "diocese"}[k]):
            debug.setdefault("dropped_ungrounded", []).append({k: getattr(llm, k)})
    debug["final"] = json.loads(json.dumps(f.__dict__, ensure_ascii=False))
    return f, debug
