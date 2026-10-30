import datetime as dt

import pytest

from src.schedule import TZ, next_mass_within

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def at(y, mo, d, h, mi, s=0, tz=TZ):
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=tz)


def m(dow: int, hhmm: str) -> tuple[int, int, str]:
    h, mi = map(int, hhmm.split(":"))
    return dow, h * 60 + mi, hhmm


# Các ngày dùng trong test (kiểm tra thứ để test không sai vì nhầm lịch).
WED_DATE = (2026, 10, 21)
SAT_DATE = (2026, 10, 24)
SUN_DATE = (2026, 10, 25)


def test_dates_are_the_expected_weekdays():
    assert dt.date(*WED_DATE).weekday() == WED
    assert dt.date(*SAT_DATE).weekday() == SAT
    assert dt.date(*SUN_DATE).weekday() == SUN


def test_mass_later_today():
    r = next_mass_within([m(WED, "5:00"), m(WED, "17:30")], at(*WED_DATE, 16, 0))
    assert r.time == "17:30" and r.minutes_until == 90 and not r.tomorrow


def test_only_same_weekday_counts():
    assert next_mass_within([m(THU, "17:30")], at(*WED_DATE, 16, 0)) is None


def test_window_boundary_inclusive():
    masses = [m(WED, "18:00")]
    assert next_mass_within(masses, at(*WED_DATE, 16, 0)).minutes_until == 120
    assert next_mass_within(masses, at(*WED_DATE, 15, 59)) is None  # 121 phút


def test_mass_starting_now_counts_but_started_mass_does_not():
    masses = [m(WED, "17:30"), m(WED, "19:00")]
    assert next_mass_within(masses, at(*WED_DATE, 17, 30)).minutes_until == 0
    r = next_mass_within(masses, at(*WED_DATE, 17, 30, 20))  # lễ 17:30 đã bắt đầu 20 giây
    assert r.time == "19:00" and r.minutes_until == 89


def test_picks_earliest_of_several():
    masses = [m(WED, "18:30"), m(WED, "17:00"), m(WED, "17:45")]
    assert next_mass_within(masses, at(*WED_DATE, 16, 0)).time == "17:00"


def test_minutes_rounded_down():
    r = next_mass_within([m(WED, "17:00")], at(*WED_DATE, 16, 58, 30))
    assert r.minutes_until == 1


def test_no_masses():
    assert next_mass_within([], at(*WED_DATE, 16, 0)) is None


# ---------- qua nửa đêm ----------

def test_after_midnight_saturday_to_sunday():
    r = next_mass_within([m(SUN, "0:30"), m(SAT, "5:00")], at(*SAT_DATE, 23, 0))
    assert r.time == "00:30" and r.minutes_until == 90 and r.tomorrow
    assert r.starts_at.date() == dt.date(*SUN_DATE)


def test_after_midnight_sunday_wraps_to_monday():
    r = next_mass_within([m(MON, "0:15"), m(SUN, "5:00")], at(*SUN_DATE, 22, 30))
    assert r.time == "00:15" and r.minutes_until == 105 and r.tomorrow
    assert r.starts_at.weekday() == MON


def test_next_morning_too_far():
    assert next_mass_within([m(SUN, "4:30")], at(*SAT_DATE, 23, 0)) is None  # 330 phút


def test_today_mass_beats_tomorrow():
    r = next_mass_within([m(SUN, "0:30"), m(SAT, "23:45")], at(*SAT_DATE, 23, 0))
    assert r.time == "23:45" and not r.tomorrow


# ---------- Chúa Nhật ----------

def test_sunday_morning():
    masses = [m(SUN, "5:00"), m(SUN, "6:30"), m(SUN, "8:00"), m(SAT, "6:30")]
    r = next_mass_within(masses, at(*SUN_DATE, 5, 30))
    assert r.time == "06:30" and r.minutes_until == 60


def test_sunday_evening_after_last_mass():
    assert next_mass_within([m(SUN, "18:00"), m(MON, "5:00")], at(*SUN_DATE, 19, 0)) is None


# ---------- múi giờ ----------

def test_utc_time_is_converted_to_vietnam():
    # 00:00 UTC Chúa Nhật = 07:00 giờ Việt Nam
    r = next_mass_within([m(SUN, "8:00")], at(*SUN_DATE, 0, 0, tz=dt.timezone.utc))
    assert r.minutes_until == 60 and r.starts_at.utcoffset() == dt.timedelta(hours=7)


def test_utc_saturday_evening_is_already_sunday_in_vietnam():
    # 17:30 UTC Thứ Bảy = 00:30 Chúa Nhật ở Việt Nam
    r = next_mass_within([m(SUN, "1:00"), m(SAT, "18:00")], at(*SAT_DATE, 17, 30, tz=dt.timezone.utc))
    assert r.time == "01:00" and r.minutes_until == 30 and not r.tomorrow


def test_naive_time_is_vietnam_time():
    r = next_mass_within([m(WED, "17:30")], dt.datetime(*WED_DATE, 16, 0))
    assert r.minutes_until == 90


def test_invalid_window():
    with pytest.raises(ValueError):
        next_mass_within([], at(*WED_DATE, 16, 0), window_min=0)
