"""Tìm nhà thờ quanh một vị trí, trả về dạng dict sẵn sàng cho API/JSON."""
import datetime as dt

from .answer import schedule_groups
from .db import all_masses, churches
from .geo import within_radius
from .schedule import next_mass_within, now_vn

DEFAULT_RADIUS_KM = 3.0

_EMPTY = {"", "nan", "none", "null"}


def _clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _EMPTY else s


def church_json(c: dict, distance_km: float, now: dt.datetime) -> dict:
    """Chỉ giữ trường có giá trị để giao diện không phải hiện 'None'/'nan'."""
    masses = all_masses().get(c["id"], [])
    by_day: dict[int, list[str]] = {}
    for dow, minutes, _ in masses:
        by_day.setdefault(dow, []).append(f"{minutes // 60:02d}:{minutes % 60:02d}")
    nxt = next_mass_within(masses, now)
    out = {
        "id": c["id"],
        "name": _clean(c["name"]),
        "parish_name": _clean(c["parish_name"]),
        "address": _clean(c["address"]),
        "lat": c["latitude"],
        "lon": c["longitude"],
        "distance_km": round(distance_km, 3),
        "schedule": [{"days": label, "times": times} for label, times in schedule_groups(by_day)],
        "next_mass": nxt and {"time": nxt.time, "minutes_until": nxt.minutes_until, "tomorrow": nxt.tomorrow,
                              "starts_at": nxt.starts_at.isoformat()},
        "phone": _clean(c.get("phone")),
        "email": _clean(c.get("email")),
        "website": _clean(c.get("website")),
        "parish_url": _clean(c.get("parish_url")),
        "mass_url": _clean(c.get("mass_url")),
    }
    return {k: v for k, v in out.items() if v not in (None, [])}


def find_nearby(lat: float, lon: float, radius_km: float = DEFAULT_RADIUS_KM,
                now: dt.datetime | None = None) -> list[dict]:
    now = now or now_vn()
    hits = within_radius(churches(), lat, lon, radius_km, lambda c: (c["latitude"], c["longitude"]))
    return [church_json(c, d, now) for c, d in hits]
