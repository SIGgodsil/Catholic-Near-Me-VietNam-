"""Tìm tọa độ từ địa chỉ qua Nominatim, theo chính sách dùng server công cộng
(https://operations.osmfoundation.org/policies/nominatim/):
- User-Agent riêng định danh ứng dụng,
- tối đa 1 request/giây (khóa toàn cục),
- cache kết quả, chỉ tìm khi người dùng bấm tìm (không gợi ý theo từng phím gõ),
- giới hạn trong Việt Nam (countrycodes=vn).
"""
import os
import re
import threading
import time
from collections import OrderedDict

import httpx

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
# Có thể thêm email liên hệ qua biến môi trường NOMINATIM_CONTACT, Nominatim khuyến khích điều này.
_contact = os.getenv("NOMINATIM_CONTACT", "").strip()
USER_AGENT = f"CatholicNearMe/0.1 (local hobby app{'; ' + _contact if _contact else ''})"

MIN_INTERVAL_S = 1.0
CACHE_TTL_S = 7 * 24 * 3600
CACHE_MAX = 1000
MAX_RESULTS = 5
# Dữ liệu nhà thờ ở TP.HCM nên ưu tiên kết quả trong vùng này (bounded=0: chỉ ưu tiên, không loại nơi khác).
# Có tác dụng khi địa chỉ mơ hồ, ví dụ "Hai Bà Trưng" có ở nhiều tỉnh.
VIEWBOX = os.getenv("NOMINATIM_VIEWBOX", "106.35,11.20,107.05,10.35")  # lon trái, lat trên, lon phải, lat dưới


class GeocodeError(Exception):
    pass


_lock = threading.Lock()
_last_request = 0.0
_cache: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()


def _key(q: str) -> str:
    return re.sub(r"\s+", " ", q).strip().lower()


def _cached(key: str) -> list[dict] | None:
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL_S:
        _cache.move_to_end(key)
        return hit[1]
    return None


def geocode(query: str) -> list[dict]:
    key = _key(query)
    if (res := _cached(key)) is not None:
        return res
    global _last_request
    with _lock:
        # Một request khác có thể đã lấy cùng truy vấn trong lúc chờ khóa.
        if (res := _cached(key)) is not None:
            return res
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            r = httpx.get(
                NOMINATIM_URL,
                params={"q": query, "format": "jsonv2", "countrycodes": "vn", "limit": MAX_RESULTS,
                        "accept-language": "vi", "viewbox": VIEWBOX, "bounded": 0},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
        except httpx.HTTPError as e:
            raise GeocodeError("Không kết nối được dịch vụ tìm địa chỉ. Kiểm tra kết nối Internet.") from e
        finally:
            _last_request = time.monotonic()
        if r.status_code == 429:
            raise GeocodeError("Dịch vụ tìm địa chỉ đang quá tải, bạn thử lại sau ít phút.")
        if r.status_code != 200:
            raise GeocodeError("Dịch vụ tìm địa chỉ tạm thời không phản hồi.")
        res = [{"label": x["display_name"], "lat": float(x["lat"]), "lon": float(x["lon"])} for x in r.json()]
        _cache[key] = (time.time(), res)
        if len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
        return res
