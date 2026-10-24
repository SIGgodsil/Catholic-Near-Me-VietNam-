"""Backend web. Chạy (trong thư mục chatbot):
    .venv\\Scripts\\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
"""
from fastapi import FastAPI, Query

from src.bot import SCOPE_NOTE
from src.db import churches
from src.nearby import DEFAULT_RADIUS_KM, find_nearby

app = FastAPI(title="Catholic Near Me")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "churches": len(churches())}


@app.get("/api/churches/nearby")
def nearby(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    radius_km: float = Query(DEFAULT_RADIUS_KM, gt=0, le=20),
) -> dict:
    found = find_nearby(lat, lon, radius_km)
    return {
        "center": {"lat": lat, "lon": lon},
        "radius_km": radius_km,
        "count": len(found),
        "scope_note": SCOPE_NOTE,
        "churches": found,
    }
