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


def test_next_mass_marked_in_nearby():
    import datetime as dt

    from src.db import all_masses
    from src.nearby import find_nearby
    from src.schedule import TZ

    c = churches()[0]
    dow, minutes, _ = all_masses()[c["id"]][0]
    # Chọn thời điểm 30 phút trước lễ đầu tiên của nhà thờ này, đúng thứ trong tuần.
    day = dt.date(2026, 10, 19) + dt.timedelta(days=dow)  # 19/10/2026 là Thứ Hai
    start = dt.datetime.combine(day, dt.time(minutes // 60, minutes % 60), TZ)
    found = find_nearby(c["latitude"], c["longitude"], 0.01, now=start - dt.timedelta(minutes=30))
    assert found[0]["id"] == c["id"]
    nm = found[0]["next_mass"]
    assert nm["minutes_until"] == 30 and nm["time"] == start.strftime("%H:%M")


def test_schedule_times_are_hh_mm():
    c = churches()[0]
    body = client.get("/api/churches/nearby", params={"lat": c["latitude"], "lon": c["longitude"]}).json()
    times = [t for ch in body["churches"] for g in ch["schedule"] for t in g["times"]]
    assert times and all(len(t) == 5 and t[2] == ":" for t in times)
    assert body["server_time"].endswith("+07:00")


def test_simulated_time_parameter():
    c = churches()[0]
    params = {"lat": c["latitude"], "lon": c["longitude"], "at": "2026-10-25T16:30"}
    body = client.get("/api/churches/nearby", params=params).json()
    assert body["server_time"] == "2026-10-25T16:30:00+07:00"
