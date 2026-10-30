"""Ghép câu trả lời từ kết quả truy vấn. Mọi giờ lễ/địa chỉ hiển thị đều lấy trực tiếp từ DB."""
import re

import ollama

from .config import OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_TIMEOUT
from .db import ChurchHit, Filters
from .extract import PERIODS
from .normalize import DAY_LABELS

MAX_DETAILED = 8
PERIOD_LABELS = {"sang": "sáng", "trua": "trưa", "chieu": "chiều", "toi": "tối"}

_client = ollama.Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT)


def fmt_km(km: float) -> str:
    """0.76 -> '760 m', 1.32 -> '1,3 km'."""
    if km < 1:
        return f"{max(10, round(km * 100) * 10)} m"
    return f"{km:.1f}".replace(".", ",") + " km"


def fmt_minutes(m: int) -> str:
    return f"{m // 60}:{m % 60:02d}"


def describe_time_filter(f: Filters) -> str:
    parts = []
    if f.days:
        parts.append(", ".join(DAY_LABELS[d] for d in f.days))
    period = next((k for k, v in PERIODS.items() if v == (f.time_from, f.time_to)), None)
    if period:
        parts.append(f"buổi {PERIOD_LABELS[period]}")
    elif f.time_from is not None and f.time_to is not None:
        parts.append(f"từ {fmt_minutes(f.time_from)} đến {fmt_minutes(f.time_to)}")
    elif f.time_from is not None:
        parts.append(f"từ {fmt_minutes(f.time_from)} trở đi")
    elif f.time_to is not None:
        parts.append(f"trước {fmt_minutes(f.time_to)}")
    return ", ".join(parts)


def describe_place_filter(f: Filters) -> str:
    parts = []
    if f.ward:
        parts.append(f.ward if f.ward.lower().startswith("phường") else f"phường {f.ward}")
    if f.district:
        parts.append(f.district if f.district.lower().startswith("quận") else f"quận/khu vực {f.district}")
    if f.place:
        parts.append(f.place)
    return ", ".join(parts)


def schedule_lines(masses: dict[int, list[str]]) -> list[str]:
    """Gộp các ngày liên tiếp có cùng giờ lễ: 'Thứ Hai – Thứ Sáu: 5:00, 17:30'."""
    return [f"{label}: {', '.join(times)}" for label, times in schedule_groups(masses)]


def schedule_groups(masses: dict[int, list[str]]) -> list[tuple[str, list[str]]]:
    """[('Thứ Hai – Thứ Sáu', ['5:00', '17:30']), ('Chúa Nhật', [...])]"""
    groups, d = [], 0
    while d < 7:
        if d not in masses:
            d += 1
            continue
        end = d
        while end + 1 < 7 and masses.get(end + 1) == masses[d]:
            end += 1
        label = DAY_LABELS[d] if end == d else f"{DAY_LABELS[d]} – {DAY_LABELS[end]}"
        groups.append((label, masses[d]))
        d = end + 1
    return groups


def hit_markdown(h: ChurchHit, show_schedule: bool = True) -> str:
    out = [f"**{h.name}** — {h.address}" + (f" _(cách {fmt_km(h.distance_km)})_" if h.distance_km is not None else "")]
    if show_schedule:
        out += [f"- {line}" for line in schedule_lines(h.masses)] or ["- (không có giờ lễ phù hợp)"]
    if h.mass_url:
        out.append(f"- Nguồn: [{h.mass_url}]({h.mass_url})")
    return "\n".join(out)


def hits_table(hits: list[ChurchHit]) -> list[dict]:
    rows = []
    for h in hits:
        row = {"Nhà thờ": h.name, "Địa chỉ": h.address}
        if h.distance_km is not None:
            row["Khoảng cách"] = fmt_km(h.distance_km)
        rows.append({**row, "Giờ lễ": "; ".join(schedule_lines(h.masses)), "Nguồn": h.mass_url})
    return rows


def template_intro(f: Filters, hits: list[ChurchHit]) -> str:
    cond = " – ".join(x for x in (describe_place_filter(f), describe_time_filter(f)) if x)
    cond = f" ({cond})" if cond else ""
    if f.name and len(hits) == 1:
        return f"Thông tin {hits[0].name}{cond}:"
    return f"Tìm thấy {len(hits)} nhà thờ phù hợp{cond}:"


def llm_intro(question: str, f: Filters, hits: list[ChurchHit], model: str = OLLAMA_MODEL) -> str | None:
    """1–2 câu mở đầu tự nhiên. Bị loại nếu LLM chèn giờ giấc (chỉ bảng dữ liệu được nêu giờ)."""
    base = template_intro(f, hits).rstrip(":")
    resp = _client.chat(
        model=model,
        messages=[
            {"role": "system", "content": (
                "Bạn là trợ lý tra cứu giờ lễ nhà thờ Công giáo. Người dùng hỏi một câu, hệ thống đã tra cứu và có "
                "CÂU GỐC tóm tắt kết quả. Hãy viết lại CÂU GỐC thành 1 câu tiếng Việt tự nhiên, thân thiện, trả lời "
                "đúng ý câu hỏi. Giữ nguyên số lượng và điều kiện; nếu có lọc buổi/thứ thì nói là 'có lễ' vào lúc đó. "
                "KHÔNG thêm giờ lễ, địa chỉ, tên nhà thờ hay thông tin nào không có trong CÂU GỐC. "
                "Chi tiết sẽ được hiển thị ngay bên dưới câu của bạn.")},
            {"role": "user", "content": f"Câu hỏi: {question}\nCÂU GỐC: {base}"},
        ],
        options={"temperature": 0.2, "num_predict": 120},
        keep_alive="30m",
    )
    text = resp.message.content.strip().strip('"')
    # Chỉ chấp nhận các con số đã có trong câu gốc (số lượng, giờ của điều kiện lọc).
    if not text or set(re.findall(r"\d+", text)) - set(re.findall(r"\d+", base)):
        return None
    return text
