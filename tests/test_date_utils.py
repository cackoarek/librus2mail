"""
Testy jednostkowe modułu date_utils oraz bezpiecznego parsowania dat.
"""

from datetime import date, datetime, timezone

from librus2mail.date_utils import (
    parse_date_safe,
    parse_datetime_safe,
)


class TestDateUtils:
    def test_parse_datetime_safe_none_and_empty(self):
        assert parse_datetime_safe(None) is None
        assert parse_datetime_safe("") is None
        assert parse_datetime_safe("   ") is None
        assert parse_datetime_safe("-") is None
        assert parse_datetime_safe("None") is None
        assert parse_datetime_safe("null") is None
        assert parse_datetime_safe("undefined") is None

    def test_parse_datetime_safe_iso_standard(self):
        dt = parse_datetime_safe("2026-09-16T15:39:20")
        assert dt == datetime(2026, 9, 16, 15, 39, 20)
        assert dt.tzinfo is None

    def test_parse_datetime_safe_iso_with_z_utc(self):
        # W Pythonie 3.10 datetime.fromisoformat nie radzi sobie z 'Z'.
        # parse_datetime_safe musi to obsłużyć bez rzucania wyjątku.
        dt = parse_datetime_safe("2026-09-16T15:39:20Z")
        assert dt is not None
        assert isinstance(dt, datetime)
        assert dt.tzinfo is None  # Domyślnie make_naive=True konwertuje i usuwa tzinfo

    def test_parse_datetime_safe_iso_with_lowercase_z(self):
        dt = parse_datetime_safe("2026-09-16T15:39:20z")
        assert dt is not None
        assert isinstance(dt, datetime)
        assert dt.tzinfo is None

    def test_parse_datetime_safe_iso_with_timezone_offset(self):
        dt = parse_datetime_safe("2026-09-16T15:39:20+02:00")
        assert dt is not None
        assert isinstance(dt, datetime)
        assert dt.tzinfo is None

    def test_parse_datetime_safe_keep_aware_when_requested(self):
        dt = parse_datetime_safe("2026-09-16T15:39:20+02:00", make_naive=False)
        assert dt is not None
        assert dt.tzinfo is not None

    def test_parse_datetime_safe_space_delimiter(self):
        dt = parse_datetime_safe("2026-09-16 15:39:20")
        assert dt == datetime(2026, 9, 16, 15, 39, 20)

        dt_no_sec = parse_datetime_safe("2026-09-16 15:39")
        assert dt_no_sec == datetime(2026, 9, 16, 15, 39, 0)

    def test_parse_datetime_safe_date_only(self):
        dt = parse_datetime_safe("2026-09-16")
        assert dt == datetime(2026, 9, 16, 0, 0, 0)

    def test_parse_datetime_safe_polish_format(self):
        dt = parse_datetime_safe("16.09.2026 15:39:20")
        assert dt == datetime(2026, 9, 16, 15, 39, 20)

        dt2 = parse_datetime_safe("16.09.2026")
        assert dt2 == datetime(2026, 9, 16, 0, 0, 0)

    def test_parse_datetime_safe_with_weekday_annotation(self):
        # Typowy format Librusa przy ocenach: '2026-09-11 (pt.)' lub '11.09.2026 (pt.)'
        dt1 = parse_datetime_safe("2026-09-11 (pt.)")
        assert dt1 == datetime(2026, 9, 11, 0, 0, 0)

        dt2 = parse_datetime_safe("11.09.2026 (pt.)")
        assert dt2 == datetime(2026, 9, 11, 0, 0, 0)

    def test_parse_datetime_safe_existing_datetime_and_date(self):
        now = datetime(2026, 9, 16, 10, 30)
        assert parse_datetime_safe(now) == now

        aware = datetime(2026, 9, 16, 10, 30, tzinfo=timezone.utc)
        naive_res = parse_datetime_safe(aware, make_naive=True)
        assert naive_res.tzinfo is None

        d = date(2026, 9, 16)
        assert parse_datetime_safe(d) == datetime(2026, 9, 16, 0, 0, 0)

    def test_parse_datetime_safe_numeric_timestamp(self):
        # 1789569600 to timestamp dla 2026-09-16 14:40:00 UTC
        ts_sec = 1789569600
        dt_int = parse_datetime_safe(ts_sec)
        assert dt_int is not None
        assert dt_int.year == 2026

        # Milisekundy
        ts_ms = ts_sec * 1000
        dt_ms = parse_datetime_safe(ts_ms)
        assert dt_ms is not None
        assert dt_ms.year == 2026

        # String z timestampem
        dt_str = parse_datetime_safe(str(ts_sec))
        assert dt_str is not None
        assert dt_str.year == 2026

    def test_parse_datetime_safe_alternative_separators(self):
        # Format z ukośnikami
        dt_slash1 = parse_datetime_safe("2026/09/16 15:30:00")
        assert dt_slash1 == datetime(2026, 9, 16, 15, 30, 0)

        dt_slash2 = parse_datetime_safe("16/09/2026 15:30")
        assert dt_slash2 == datetime(2026, 9, 16, 15, 30, 0)

        dt_slash3 = parse_datetime_safe("2026/09/16")
        assert dt_slash3 == datetime(2026, 9, 16, 0, 0, 0)

        # Format z kropkami YYYY.MM.DD
        dt_dot = parse_datetime_safe("2026.09.16 12:00")
        assert dt_dot == datetime(2026, 9, 16, 12, 0, 0)

    def test_parse_datetime_safe_invalid_string(self):
        assert parse_datetime_safe("to-nie-jest-data") is None
        assert parse_datetime_safe("9999-99-99") is None

    def test_parse_date_safe(self):
        assert parse_date_safe(None) is None
        assert parse_date_safe("2026-09-16T15:39:20Z") == date(2026, 9, 16)
        assert parse_date_safe("2026-09-16") == date(2026, 9, 16)
        assert parse_date_safe("16.09.2026") == date(2026, 9, 16)
        assert parse_date_safe("2026/09/16") == date(2026, 9, 16)
        assert parse_date_safe("2026-09-11 (pt.)") == date(2026, 9, 11)
        assert parse_date_safe(datetime(2026, 9, 16, 12, 0)) == date(2026, 9, 16)
        assert parse_date_safe(date(2026, 9, 16)) == date(2026, 9, 16)
        assert parse_date_safe(1789569600) == date(2026, 9, 16)

