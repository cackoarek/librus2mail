"""
Testy jednostkowe normalizacji pól dat w FileStorage i kompatybilności wstecznej.
"""

import json
from datetime import datetime

import pytest

from librus2mail.storage import (
    FIELD_LAST_COLLECT_TIME,
    FIELD_LAST_NOTIFY_TIME,
    FIELD_LAST_PROGRESS_REPORT_DATE,
    FIELD_SCHEDULE_LAST_SYNC,
    FIELD_TIMETABLE_LAST_SYNC,
    FileStorage,
    parse_date_sort_key,
    sort_items_descending,
)


class TestStorageDateNormalization:
    @pytest.fixture
    def storage(self, tmp_path):
        return FileStorage(storage_dir=tmp_path)

    def test_canonical_fields_read_and_write(self, tmp_path, storage):
        """Upewnia się, że odczyt i zapis używają wyłącznie kanonicznych pól dat."""
        storage.save_last_collect_time("test_user", "2026-09-15T12:00:00")
        storage.save_last_notify_time("test_user", "2026-09-15T12:05:00")
        storage.save_last_timetable_sync("test_user", "2026-09-15T12:10:00")
        storage.save_last_schedule_sync("test_user", "2026-09-15T12:15:00")
        storage.save_last_progress_report_date("test_user", "2026-09-15T12:20:00")

        assert storage.get_last_collect_time("test_user") == "2026-09-15T12:00:00"
        assert storage.get_last_notify_time("test_user") == "2026-09-15T12:05:00"
        assert storage.get_last_timetable_sync("test_user") == "2026-09-15T12:10:00"
        assert storage.get_last_schedule_sync("test_user") == "2026-09-15T12:15:00"
        assert storage.get_last_progress_report_date("test_user") == "2026-09-15T12:20:00"

        user_file = tmp_path / "test_user.json"
        saved = json.loads(user_file.read_text(encoding="utf-8"))

        assert saved[FIELD_LAST_COLLECT_TIME] == "2026-09-15T12:00:00"
        assert saved[FIELD_LAST_NOTIFY_TIME] == "2026-09-15T12:05:00"
        assert saved[FIELD_TIMETABLE_LAST_SYNC] == "2026-09-15T12:10:00"
        assert saved[FIELD_SCHEDULE_LAST_SYNC] == "2026-09-15T12:15:00"
        assert saved[FIELD_LAST_PROGRESS_REPORT_DATE] == "2026-09-15T12:20:00"

        # Upewnij się, że stare legacy klucze nie są tworzone w pliku
        assert "last_updated" not in saved
        assert "last_update_create" not in saved
        assert "last_timetable_sync" not in saved
        assert "last_schedule_sync" not in saved

    def test_save_and_get_subjects(self, tmp_path, storage):
        """Weryfikuje zapisywanie i pobieranie listy wszystkich przedmiotów (w tym bez ocen)."""
        storage.save_subjects("student1", ["Matematyka", "Taniec", "Język polski"])
        # Dołącz ocenę z przedmiotu nieobecnego na liście
        storage.save_grades_details("student1", [
            {"id": "g1", "subject": "Historia", "grade": "5"}
        ])

        subjects = storage.get_subjects("student1")
        assert subjects == ["Historia", "Język polski", "Matematyka", "Taniec"]

    def test_parse_date_sort_key_various_formats(self):
        items = [
            {"id": "1", "datetime": "2026-09-10 10:00:00"},
            {"id": "2", "datetime": "2026-09-15T12:00:00Z"},
            {"id": "3", "datetime": "2026-09-12 (sob.)"},
            {"id": "4", "datetime": "14.09.2026 08:30"},
        ]
        sorted_items = sort_items_descending(items)
        assert [x["id"] for x in sorted_items] == ["2", "4", "3", "1"]

        # W czasie letnim (wrzesień, CEST = UTC+2) 12:00Z to 14:00 czasu polskiego
        assert parse_date_sort_key("2026-09-15T12:00:00Z") == datetime(2026, 9, 15, 14, 0, 0)
        assert parse_date_sort_key(None) == datetime.min
        assert parse_date_sort_key("") == datetime.min

    def test_boundary_dates_and_year_transitions(self):
        """Weryfikuje poprawne sortowanie i parsowanie na przełomie lat, dni przestępnych i zmianie czasu."""
        items = [
            {"id": "old_year", "datetime": "2025-12-31 23:59:59"},
            {"id": "new_year", "datetime": "2026-01-01 00:00:01"},
            {"id": "leap_day", "datetime": "2024-02-29 12:00:00"},
            {"id": "summer_time", "datetime": "2026-03-29T03:00:00+02:00"},
            {"id": "winter_time", "datetime": "2026-10-25T03:00:00+01:00"},
        ]
        sorted_items = sort_items_descending(items)
        assert [x["id"] for x in sorted_items] == ["winter_time", "summer_time", "new_year", "old_year", "leap_day"]
        # Sprawdzenie przełomu roku
        assert parse_date_sort_key("2025-12-31 23:59:59") < parse_date_sort_key("2026-01-01 00:00:00")
        # Sprawdzenie daty przestępnej
        assert parse_date_sort_key("2024-02-29 12:00:00") == datetime(2024, 2, 29, 12, 0, 0)
