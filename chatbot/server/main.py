"""Backend web. Chạy (trong thư mục chatbot):
    .venv\\Scripts\\python.exe -m uvicorn server.main:app --host 127.0.0.1 --port 8000
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from src.bot import SCOPE_NOTE
from src.db import churches
from src.nearby import DEFAULT_RADIUS_KM, find_nearby

from .nominatim import GeocodeError, geocode

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

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


@app.get("/api/geocode")
def geocode_address(q: str = Query(min_length=3, max_length=200)) -> dict:
    try:
        return {"results": geocode(q)}
    except GeocodeError as e:
        raise HTTPException(502, str(e)) from e


# Đặt sau cùng để không che các route /api.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
