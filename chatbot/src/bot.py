import re
import time
from dataclasses import dataclass, field

from .answer import (MAX_DETAILED, describe_place_filter, describe_time_filter, hit_markdown, hits_table,
                     llm_intro, template_intro)
from .config import OLLAMA_MODEL
from .context import Context, ContextInfo, apply_context, has_entity
from .db import ChurchHit, Filters, search, suggest_names
from .extract import extract
from .normalize import norm


@dataclass
class BotResponse:
    text: str
    hits: list[ChurchHit] = field(default_factory=list)
    table: list[dict] = field(default_factory=list)
    status: str = "ok"          # ok | not_found | clarify | out_of_scope
    debug: dict = field(default_factory=dict)
    context: Context | None = None   # truyền lại vào answer() ở lượt sau


SCOPE_NOTE = "Dữ liệu hiện có 80 nhà thờ thuộc Tổng Giáo phận Sài Gòn (nguồn tgpsaigon.net)."


def _has_time(f: Filters) -> bool:
    return bool(f.days) or f.time_from is not None or f.time_to is not None


def _context_note(f: Filters, info: ContextInfo, prev_hits: int) -> str:
    parts = []
    if info.restricted:
        parts.append(f"trong {prev_hits} nhà thờ ở câu trả lời trước" if prev_hits > 1 else "cùng nhà thờ ở câu trước")
    elif info.entity:
        parts.append(f.name or describe_place_filter(f) or f.diocese or "")
    if info.days or info.time:
        parts.append(describe_time_filter(f))
    parts = [p for p in parts if p]
    return f"_Hiểu theo câu trước: {', '.join(parts)}._" if parts else ""


def answer(question: str, use_llm_intro: bool = False, model: str = OLLAMA_MODEL,
           context: Context | None = None) -> BotResponse:
    t0 = time.time()
    f, debug = extract(question, model)
    debug["t_extract"] = round(time.time() - t0, 1)

    if not has_entity(f) and re.search(
            r"\bgan\s+(?:toi|day|nha|minh|em|chau|nhat|khu nay|cho nay)\b|\b(?:quanh|xung quanh|lan can)\s+(?:day|toi|nha)\b",
            norm(question)):
        resp = BotResponse("Mình chưa biết vị trí của bạn. Bạn cho mình biết quận, phường hoặc tên đường "
                           "để mình tìm nhà thờ gần đó nhé.", status="clarify")
    else:
        f, info = apply_context(question, f, context)
        if info.any():
            debug["context"] = info.__dict__
            debug["final"] = {k: v for k, v in f.__dict__.items() if v not in (None, [])}
        resp = _answer(question, f, use_llm_intro, model)
        note = _context_note(f, info, len(context.hit_ids) if context else 0)
        if note and resp.status != "clarify":
            resp.text = f"{note}\n\n{resp.text}"
        if resp.status in ("ok", "not_found"):
            resp.context = Context(f, [h.id for h in resp.hits])
    # Câu hỏi lại/ngoài phạm vi không làm mất ngữ cảnh cũ.
    if resp.context is None:
        resp.context = context
    resp.debug = {**debug, **resp.debug, "t_total": round(time.time() - t0, 1)}
    return resp


def _answer(question: str, f: Filters, use_llm_intro: bool, model: str) -> BotResponse:
    # Không xét thứ/giờ ở đây: "hôm nay thời tiết..." vẫn sinh ra bộ lọc ngày từ luật.
    if f.intent == "khac" and not has_entity(f):
        return BotResponse("Mình chỉ hỗ trợ tra cứu nhà thờ và giờ lễ. " + SCOPE_NOTE, status="out_of_scope")

    if not has_entity(f) and f.intent in ("gio_le", "thong_tin") and not _has_time(f):
        return BotResponse("Bạn muốn xem giờ lễ của nhà thờ/giáo xứ nào? Bạn có thể hỏi theo tên "
                           "(vd: “giờ lễ Tân Định”) hoặc theo khu vực (vd: “lễ sáng Chúa Nhật ở Gò Vấp”).",
                           status="clarify")

    result = search(f)
    if result.unknown:
        text = f"Không tìm thấy {', '.join(result.unknown)} trong dữ liệu. {SCOPE_NOTE}"
        if result.name_missing:
            sugg = suggest_names(f.name)
            if sugg:
                text += f"\n\nCác tên có trong dữ liệu gần giống nhất (chưa chắc là nơi bạn hỏi): {', '.join(sugg)}."
        return BotResponse(text, status="not_found", debug={"unknown": result.unknown})

    if not result.hits:
        cond = " – ".join(x for x in (f.name or "", describe_place_filter(f), describe_time_filter(f)) if x)
        return BotResponse(f"Không có nhà thờ nào trong dữ liệu có lễ phù hợp với điều kiện: {cond}.",
                           status="not_found")

    hits = result.hits
    parts = []
    approx = [h for h in hits if h.match == "approx"]
    if f.name and approx:
        parts.append(f"Không có tên chính xác “{f.name}” trong dữ liệu; kết quả gần nhất là "
                     f"{', '.join(h.name for h in approx)}. Bạn kiểm tra lại có đúng nhà thờ bạn cần không nhé.")
    intro = llm_intro(question, f, hits, model) if use_llm_intro else None
    parts.append(intro or template_intro(f, hits))
    parts += result.notes
    if len(hits) <= MAX_DETAILED:
        parts += [hit_markdown(h) for h in hits]
    else:
        parts.append(f"Danh sách {len(hits)} nhà thờ ở bảng bên dưới.")
    return BotResponse("\n\n".join(parts), hits, hits_table(hits), debug={"llm_intro_used": bool(intro)})
