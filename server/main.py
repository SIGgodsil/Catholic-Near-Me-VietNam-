"""Backend web. Chạy từ thư mục gốc dự án: scripts\\run.ps1
(hoặc: python -m uvicorn server.main:app --host 127.0.0.1 --port 8000)
"""
import datetime as dt
import logging
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.answer import MAX_DETAILED
from src.bot import SCOPE_NOTE, answer
from src.config import GEMINI_API_KEY, GEMINI_MODEL
from src.db import churches
from src.llm import LLMError
from src.nearby import DEFAULT_RADIUS_KM, find_nearby
from src.schedule import TZ, UPCOMING_WINDOW_MIN, now_vn

from .nominatim import GeocodeError, geocode
from .sessions import SessionStore

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

log = logging.getLogger("catholic_near_me")

app = FastAPI(title="Catholic Near Me")
sessions = SessionStore()

LLM_DOWN = ("Trợ lý đang tạm nghỉ vì không kết nối được với mô hình AI. "
            "Bạn vẫn dùng bản đồ bình thường; hãy thử hỏi lại sau ít phút.")
LLM_QUOTA = ("Hôm nay trợ lý đã trả lời quá nhiều câu hỏi nên tạm nghỉ. "
             "Bạn vẫn dùng bản đồ bình thường; hãy thử hỏi lại sau.")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "churches": len(churches()), "scope_note": SCOPE_NOTE,
            "llm": "ok" if GEMINI_API_KEY else "no_key", "model": GEMINI_MODEL}


@app.get("/api/churches/nearby")
def nearby(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius_km: float = Query(DEFAULT_RADIUS_KM, gt=0, le=20),
    at: dt.datetime | None = Query(None, description="Giả lập thời điểm để thử (ISO 8601, không có múi giờ = giờ VN)"),
) -> dict:
    now = (at.replace(tzinfo=TZ) if at.tzinfo is None else at.astimezone(TZ)) if at else now_vn()
    found = find_nearby(lat, lon, radius_km, now)
    return {
        "center": {"lat": lat, "lon": lon},
        "server_time": now.isoformat(timespec="seconds"),
        "upcoming_window_min": UPCOMING_WINDOW_MIN,
        "radius_km": radius_km,
        "count": len(found),
        "scope_note": SCOPE_NOTE,
        "churches": found,
    }


@app.get("/api/geocode")
def geocode_address(q: str = Query(min_length=3, max_length=200)) -> dict:
    try:
        return {"results": geocode(q)}
    except GeocodeError as e:
        raise HTTPException(502, str(e)) from e


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: str | None = Field(None, max_length=64)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class ResetRequest(BaseModel):
    session_id: str = Field(max_length=64)


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """Chatbot chỉ trả lời từ dataset. Vị trí (nếu có) dùng cho câu hỏi "gần tôi"; chatbot không điều khiển bản đồ."""
    sid = req.session_id if req.session_id and re.fullmatch(r"[0-9a-f]{32}", req.session_id) else sessions.new_id()
    near = (req.lat, req.lon) if req.lat is not None and req.lon is not None else None
    try:
        r = answer(req.message.strip(), context=sessions.get(sid), near=near)
    except LLMError as e:
        log.warning("Gemini lỗi: %s", e)
        raise HTTPException(503, LLM_QUOTA if e.quota else LLM_DOWN) from e
    except Exception as e:
        log.exception("Lỗi khi trả lời câu hỏi")
        raise HTTPException(500, "Xin lỗi, mình gặp lỗi khi xử lý câu hỏi này. Bạn thử hỏi cách khác nhé.") from e
    sessions.put(sid, r.context)
    return {
        "session_id": sid,
        "status": r.status,
        "reply": r.text,
        "table": r.table if len(r.table) > MAX_DETAILED else [],
    }


@app.post("/api/chat/reset")
def chat_reset(req: ResetRequest) -> dict:
    sessions.drop(req.session_id)
    return {"ok": True}


# Đặt sau cùng để không che các route /api.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
