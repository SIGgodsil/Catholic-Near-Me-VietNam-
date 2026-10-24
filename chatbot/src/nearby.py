"""Tìm nhà thờ quanh một vị trí, trả về dạng dict sẵn sàng cho API/JSON."""
from .answer import schedule_groups
from .db import all_masses, churches
from .geo import within_radius

DEFAULT_RADIUS_KM = 3.0

_EMPTY = {"", "nan", "none", "null"}


def _clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _EMPTY else s


def church_json(c: dict, distance_km: float) -> dict:
    """Chỉ giữ trường có giá trị để giao diện không phải hiện 'None'/'nan'."""
    by_day: dict[int, list[str]] = {}
    for dow, _, t in all_masses().get(c["id"], []):
        by_day.setdefault(dow, []).append(t)
    out = {
        "id": c["id"],
        "name": _clean(c["name"]),
        "parish_name": _clean(c["parish_name"]),
        "address": _clean(c["address"]),
        "lat": c["latitude"],
        "lon": c["longitude"],
        "distance_km": round(distance_km, 3),
        "schedule": [{"days": label, "times": times} for label, times in schedule_groups(by_day)],
        "phone": _clean(c.get("phone")),
        "email": _clean(c.get("email")),
        "website": _clean(c.get("website")),
        "parish_url": _clean(c.get("parish_url")),
        "mass_url": _clean(c.get("mass_url")),
    }
    return {k: v for k, v in out.items() if v not in (None, [])}


def find_nearby(lat: float, lon: float, radius_km: float = DEFAULT_RADIUS_KM) -> list[dict]:
    hits = within_radius(churches(), lat, lon, radius_km, lambda c: (c["latitude"], c["longitude"]))
    return [church_json(c, d) for c, d in hits]
