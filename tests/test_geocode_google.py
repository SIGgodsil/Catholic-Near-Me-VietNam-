"""Script lấy tọa độ qua Google Places: tách địa chỉ, chấm điểm ứng viên, cache. Không gọi mạng thật."""
import json

import httpx
import pytest

from scripts import geocode_google as gg

PARISH = {
    "parish_url": "https://tgpsaigon.net/gioi-thieu-giao-xu/giao-xu-binh-an-1",
    "parish_name": "Bình An",
    "deanery_name": "Bình An",
    "parish_address": "2287 Phạm Thế Hiển, P. Bình Đông (2287 Phạm Thế Hiển, Phường 6, Quận 8, TP. HCM)",
}


def place(name, types=("church", "place_of_worship"), lat=10.74, lon=106.65):
    return {"id": f"id-{name}", "displayName": {"text": name}, "formattedAddress": "Q8",
            "location": {"latitude": lat, "longitude": lon}, "types": list(types)}


def test_core_name_strips_repeated_prefixes():
    assert gg.core_name("Nhà thờ Giáo xứ Tân Định") == "tan dinh"
    assert gg.core_name("Giáo xứ Bình An") == "binh an"


def test_split_address_new_and_old():
    main, alt = gg.split_address(PARISH["parish_address"])
    assert main == "2287 Phạm Thế Hiển, P. Bình Đông"
    assert alt.startswith("2287 Phạm Thế Hiển, Phường 6, Quận 8")
    assert gg.split_address("100-102 Bến Nguyễn Duy, P.9, Q.8") == ("100-102 Bến Nguyễn Duy, P.9, Q.8", None)


def test_queries_try_new_then_old_address():
    qs = gg.queries_for(PARISH)
    assert len(qs) == 3 and "Bình Đông" in qs[0] and "Quận 8" in qs[1]


def test_pick_prefers_church_with_matching_name():
    places = [place("Quán cà phê Bình An", types=("cafe",)), place("Nhà thờ Bình An Thượng"), place("Giáo xứ Bình An")]
    p, score, church, conf = gg.pick("Bình An", places)
    assert p["displayName"]["text"] == "Giáo xứ Bình An" and conf == "high" and church


def test_pick_confidence_levels():
    assert gg.pick("Bình An", [place("Bình An", types=("establishment",))])[3] == "medium"
    assert gg.pick("Bình An", [place("Chợ Lớn", types=("market",))])[3] == "low"
    assert gg.pick("Bình An", []) is None


class Recorder:
    def __init__(self, places):
        self.places, self.calls = places, []

    def __call__(self, request):
        self.calls.append(request)
        return httpx.Response(200, json={"places": self.places})


@pytest.fixture
def client(tmp_path):
    def make(places, key="test-key"):
        rec = Recorder(places)
        c = gg.PlacesClient(key, tmp_path / "cache.json", httpx.Client(transport=httpx.MockTransport(rec)),
                            sleep=lambda s: None)
        return c, rec
    return make


def test_request_shape_and_cache(client, tmp_path):
    c, rec = client([place("Giáo xứ Bình An")])
    row = gg.locate(PARISH, c)
    assert row["confidence"] == "high" and row["latitude"] == 10.74
    req = rec.calls[0]
    assert req.headers["X-Goog-Api-Key"] == "test-key"
    assert "places.location" in req.headers["X-Goog-FieldMask"]
    body = json.loads(req.content)
    assert body["regionCode"] == "VN" and "rectangle" in body["locationRestriction"]
    assert len(rec.calls) == 1  # khớp "high" ngay truy vấn đầu thì dừng

    c2, rec2 = client([place("Giáo xứ Bình An")])
    assert gg.locate(PARISH, c2)["google_place_id"] == "id-Giáo xứ Bình An"
    assert rec2.calls == []  # lấy từ cache, không gọi lại API


def test_falls_back_to_next_query_and_reports_none(client):
    c, rec = client([])
    assert gg.locate(PARISH, c)["confidence"] == "none"
    assert len(rec.calls) == 3


def test_missing_key_stops_before_request(client):
    c, rec = client([], key=None)
    with pytest.raises(SystemExit):
        c.search("Nhà thờ Bình An")
    assert rec.calls == []
