"""Ngữ cảnh hội thoại theo phiên (bộ lọc + kết quả câu trước), lưu trong RAM.
Khởi động lại server thì mất ngữ cảnh, chỉ ảnh hưởng câu hỏi nối tiếp."""
import threading
import time
import uuid
from collections import OrderedDict

from src.context import Context

TTL_S = 2 * 3600
MAX_SESSIONS = 1000


class SessionStore:
    def __init__(self, ttl_s: float = TTL_S, max_items: int = MAX_SESSIONS):
        self.ttl_s, self.max_items = ttl_s, max_items
        self._items: OrderedDict[str, tuple[float, Context | None]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def new_id() -> str:
        return uuid.uuid4().hex

    def get(self, sid: str) -> Context | None:
        with self._lock:
            item = self._items.get(sid)
            if not item or time.monotonic() - item[0] > self.ttl_s:
                self._items.pop(sid, None)
                return None
            return item[1]

    def put(self, sid: str, ctx: Context | None) -> None:
        with self._lock:
            self._items[sid] = (time.monotonic(), ctx)
            self._items.move_to_end(sid)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def drop(self, sid: str) -> None:
        with self._lock:
            self._items.pop(sid, None)
