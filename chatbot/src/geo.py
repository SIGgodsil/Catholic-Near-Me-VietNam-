"""Khoảng cách trên mặt cầu (Haversine) và lọc theo bán kính."""
import math
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")

EARTH_RADIUS_KM = 6371.0088  # bán kính trung bình của Trái Đất (IUGG)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def within_radius(items: Iterable[T], lat: float, lon: float, radius_km: float,
                  coords: Callable[[T], tuple[float | None, float | None]]) -> list[tuple[T, float]]:
    """Các phần tử cách (lat, lon) không quá radius_km (tính cả biên), gần nhất trước.
    Phần tử thiếu tọa độ bị bỏ qua."""
    # Lọc thô bằng khung vĩ/kinh độ để không phải tính Haversine cho mọi điểm (dataset có thể tới 50.000 dòng).
    dlat = math.degrees(radius_km / EARTH_RADIUS_KM)
    max_lat = min(abs(lat) + dlat, 89.9)
    dlon = dlat / math.cos(math.radians(max_lat))
    out = []
    for it in items:
        plat, plon = coords(it)
        if plat is None or plon is None or abs(plat - lat) > dlat or abs(plon - lon) > dlon:
            continue
        d = haversine_km(lat, lon, plat, plon)
        if d <= radius_km:
            out.append((it, d))
    out.sort(key=lambda x: x[1])
    return out
