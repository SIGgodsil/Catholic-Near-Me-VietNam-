"""Proxy Nominatim: tham số đúng chính sách, có cache, giãn cách ≥ 1 giây. Không gọi mạng thật."""
import httpx
import pytest

from server import nominatim


class FakeResponse:
    status_code = 200

    def json(self):
        return [{"display_name": "Chợ Bến Thành, TP.HCM", "lat": "10.7725", "lon": "106.698"}]


@pytest.fixture
def calls(monkeypatch):
    log = {"get": [], "sleep": []}
    monkeypatch.setattr(nominatim, "_cache", type(nominatim._cache)())
    monkeypatch.setattr(nominatim, "_last_request", 0.0)
    monkeypatch.setattr(nominatim.httpx, "get", lambda url, **kw: log["get"].append(kw) or FakeResponse())
    monkeypatch.setattr(nominatim.time, "sleep", lambda s: log["sleep"].append(s))
    return log


def test_request_follows_policy(calls):
    res = nominatim.geocode("Chợ Bến Thành")
    assert res == [{"label": "Chợ Bến Thành, TP.HCM", "lat": 10.7725, "lon": 106.698}]
    kw = calls["get"][0]
    assert kw["params"]["countrycodes"] == "vn"
    assert kw["headers"]["User-Agent"].startswith("CatholicNearMe/")


def test_cache_ignores_case_and_spaces(calls):
    nominatim.geocode("Chợ Bến Thành")
    nominatim.geocode("  chợ   bến thành ")
    assert len(calls["get"]) == 1


def test_waits_between_requests(calls):
    nominatim.geocode("địa chỉ một")
    nominatim.geocode("địa chỉ hai")
    assert len(calls["get"]) == 2
    assert calls["sleep"] and 0.9 < calls["sleep"][-1] <= 1.0


def test_rate_limited_by_server(calls, monkeypatch):
    class TooMany(FakeResponse):
        status_code = 429
    monkeypatch.setattr(nominatim.httpx, "get", lambda url, **kw: TooMany())
    with pytest.raises(nominatim.GeocodeError, match="quá tải"):
        nominatim.geocode("bất kỳ")


def test_network_error(calls, monkeypatch):
    def boom(url, **kw):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(nominatim.httpx, "get", boom)
    with pytest.raises(nominatim.GeocodeError, match="Internet"):
        nominatim.geocode("bất kỳ")
