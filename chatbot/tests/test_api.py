from fastapi.testclient import TestClient

from server.main import app
from src.db import churches

client = TestClient(app)


def test_nearby_returns_church_at_its_own_location_first():
    c = churches()[0]
    r = client.get("/api/churches/nearby", params={"lat": c["latitude"], "lon": c["longitude"]})
    assert r.status_code == 200
    body = r.json()
    assert body["radius_km"] == 3
    assert body["count"] == len(body["churches"]) > 0
    first = body["churches"][0]
    assert first["id"] == c["id"] and first["distance_km"] == 0
    assert all(x["distance_km"] <= 3 for x in body["churches"])
    assert [x["distance_km"] for x in body["churches"]] == sorted(x["distance_km"] for x in body["churches"])


def test_nearby_hides_empty_fields():
    c = churches()[0]
    body = client.get("/api/churches/nearby", params={"lat": c["latitude"], "lon": c["longitude"]}).json()
    for ch in body["churches"]:
        assert "phone" not in ch  # dataset hiện tại chưa có số điện thoại
        assert all(v not in (None, "", "nan", "None") for v in ch.values())
        assert ch["schedule"] and all(g["days"] and g["times"] for g in ch["schedule"])


def test_nearby_empty_far_away():
    body = client.get("/api/churches/nearby", params={"lat": 21.0285, "lon": 105.8542}).json()  # Hà Nội
    assert body["count"] == 0 and body["churches"] == []


def test_nearby_rejects_invalid_coordinates():
    assert client.get("/api/churches/nearby", params={"lat": 100, "lon": 106}).status_code == 422
    assert client.get("/api/churches/nearby", params={"lat": 10.7, "lon": 106.7, "radius_km": 0}).status_code == 422
