import pytest

from src.geo import haversine_km, within_radius

KM_PER_DEG_LAT = 111.19508  # 2πR/360 với R = 6371.0088 km
CENTER = (10.7798, 106.6990)  # Nhà thờ Đức Bà


def north(km: float, lat: float = CENTER[0], lon: float = CENTER[1]) -> tuple[float, float]:
    return lat + km / KM_PER_DEG_LAT, lon


def coords(p):
    return p["lat"], p["lon"]


# ---------- Haversine ----------

def test_same_point_is_zero():
    assert haversine_km(*CENTER, *CENTER) == 0


def test_one_degree_of_latitude():
    assert haversine_km(0, 0, 1, 0) == pytest.approx(KM_PER_DEG_LAT, abs=1e-3)


def test_one_degree_of_longitude_shrinks_with_latitude():
    assert haversine_km(0, 0, 0, 1) == pytest.approx(KM_PER_DEG_LAT, abs=1e-3)
    assert haversine_km(60, 0, 60, 1) == pytest.approx(KM_PER_DEG_LAT / 2, rel=1e-3)


def test_symmetric():
    a, b = (10.7798, 106.6990), (10.7883, 106.6903)
    assert haversine_km(*a, *b) == pytest.approx(haversine_km(*b, *a))


def test_hanoi_to_saigon():
    assert 1130 < haversine_km(21.0285, 105.8542, 10.8231, 106.6297) < 1145


def test_short_distance_matches_degrees():
    assert haversine_km(*CENTER, *north(2.5)) == pytest.approx(2.5, abs=1e-3)


# ---------- Lọc bán kính 3 km ----------

def make(name: str, latlon: tuple[float | None, float | None]) -> dict:
    return {"name": name, "lat": latlon[0], "lon": latlon[1]}


def test_radius_3km_keeps_inside_and_drops_outside():
    pts = [
        make("2.9km", north(2.9)),
        make("2.999km", north(2.999)),
        make("3.001km", north(3.001)),
        make("5km", north(5)),
        make("tai_cho", CENTER),
    ]
    got = [p["name"] for p, _ in within_radius(pts, *CENTER, 3, coords)]
    assert got == ["tai_cho", "2.9km", "2.999km"]


def test_radius_result_sorted_by_distance_with_distance_values():
    pts = [make("2", north(2)), make("0.5", north(0.5)), make("1", north(1))]
    res = within_radius(pts, *CENTER, 3, coords)
    assert [p["name"] for p, _ in res] == ["0.5", "1", "2"]
    assert [round(d, 2) for _, d in res] == [0.5, 1.0, 2.0]


def test_radius_east_west_at_high_latitude():
    # Khung lọc thô theo kinh độ phải nới ra khi vĩ độ lớn, không được loại nhầm điểm hợp lệ.
    lat, lon = 60.0, 10.0
    east = (lat, lon + 2.9 / (KM_PER_DEG_LAT / 2))
    res = within_radius([make("dong", east)], lat, lon, 3, coords)
    assert len(res) == 1 and res[0][1] == pytest.approx(2.9, abs=0.01)


def test_radius_skips_missing_coordinates():
    pts = [make("thieu", (None, None)), make("co", north(1))]
    assert [p["name"] for p, _ in within_radius(pts, *CENTER, 3, coords)] == ["co"]


def test_radius_nothing_nearby():
    assert within_radius([make("xa", north(10))], *CENTER, 3, coords) == []
