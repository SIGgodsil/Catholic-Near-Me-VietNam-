"""Lễ sắp diễn ra theo giờ Việt Nam. Lịch lễ là lịch tuần cố định (dataset không có lễ trọng, lễ theo mùa)."""
import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")  # Windows cần gói tzdata
UPCOMING_WINDOW_MIN = 120


@dataclass(frozen=True)
class NextMass:
    starts_at: dt.datetime
    minutes_until: int     # làm tròn xuống: còn 30 giây thì là 0
    tomorrow: bool

    @property
    def time(self) -> str:
        return self.starts_at.strftime("%H:%M")


def now_vn() -> dt.datetime:
    return dt.datetime.now(TZ)


def next_mass_within(masses: list[tuple[int, int, str]], now: dt.datetime,
                     window_min: int = UPCOMING_WINDOW_MIN) -> NextMass | None:
    """Lễ sớm nhất bắt đầu trong khoảng [now, now + window_min] (tính cả hai biên).

    masses: [(thứ 0=Thứ Hai..6=Chúa Nhật, phút từ 0:00, 'H:MM')]. now không có múi giờ thì hiểu là giờ Việt Nam.
    Lễ đã bắt đầu (dù chỉ vài giây) không tính. Xét cả hôm nay và ngày mai để xử lý trường hợp qua nửa đêm.
    """
    if not 0 < window_min <= 24 * 60:
        raise ValueError("window_min phải trong (0, 1440]")
    now = now.replace(tzinfo=TZ) if now.tzinfo is None else now.astimezone(TZ)
    window = dt.timedelta(minutes=window_min)
    best: NextMass | None = None
    for offset in (0, 1):
        day = now.date() + dt.timedelta(days=offset)
        for dow, minutes, _ in masses:
            if dow != day.weekday():
                continue
            start = dt.datetime.combine(day, dt.time(minutes // 60, minutes % 60), TZ)
            delta = start - now
            if dt.timedelta(0) <= delta <= window and (best is None or start < best.starts_at):
                best = NextMass(start, int(delta.total_seconds() // 60), offset == 1)
    return best
