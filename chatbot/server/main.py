"""Backend web. Chạy (trong thư mục chatbot):
    .venv\\Scripts\\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
"""
import datetime as dt
import logging
import re
from pathlib import Path

import httpx
import ollama
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.answer import MAX_DETAILED
from src.bot import SCOPE_NOTE, answer
from src.config import OLLAMA_HOST, OLLAMA_MODEL
from src.db import churches
from src.nearby import DEFAULT_RADIUS_KM, find_nearby
from src.schedule import TZ, UPCOMING_WINDOW_MIN, now_vn

from .nominatim import GeocodeError, geocode
from .sessions import SessionStore

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

log = logging.getLogger("catholic_near_me")

app = FastAPI(title="Catholic Near Me")
sessions = SessionStore()

OLLAMA_DOWN = ("Trợ lý đang tạm nghỉ vì không kết nối được với mô hình AI (Ollama). "
               "Bạn vẫn dùng bản đồ bình thường; hãy thử hỏi lại sau ít phút.")
OLLAMA_ERRORS = (ConnectionError, httpx.HTTPError, ollama.ResponseError)


def _ollama_status() -> str:
    """ok | no_model | down. Chỉ gọi Ollama ở localhost, cổng của Ollama không mở ra ngoài."""
    try:
        r = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        names = {m.get("name") for m in r.json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return "down"
    return "ok" if OLLAMA_MODEL in names or f"{OLLAMA_MODEL}:latest" in names else "no_model"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "churches": len(churches()), "scope_note": SCOPE_NOTE,
            "ollama": _ollama_status(), "model": OLLAMA_MODEL}


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
    except OLLAMA_ERRORS as e:
        log.warning("Ollama lỗi: %r", e)
        raise HTTPException(503, OLLAMA_DOWN) from e
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
