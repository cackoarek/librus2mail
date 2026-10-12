"""
Testy jednostkowe i integracyjne dla modułów Scheduler i ConfigWatcher (Faza 3).
"""

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from librus2mail.config_watcher import ConfigWatcher, sleep_with_config_watch
from librus2mail.scheduler import (
    ReportScheduler,
    calculate_next_wait_seconds,
    should_collect_now,
)
from librus2mail.storage import FileStorage


class TestConfigWatcher:
    """Weryfikacja modułu ConfigWatcher."""

    def test_nonexistent_file(self, tmp_path):
        watcher = ConfigWatcher(str(tmp_path / "nonexistent.yaml"))
        assert watcher.get_mtime() is None
        assert watcher.has_changed() is False

    def test_file_modification_detection(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("key: value1\n", encoding="utf-8")

        watcher = ConfigWatcher(str(cfg_path))
        assert watcher.has_changed() is False

        # Zmiana zawartości i mtime
        time.sleep(0.01)
        cfg_path.write_text("key: value2\n", encoding="utf-8")
        assert watcher.has_changed() is True

        watcher.reset()
        assert watcher.has_changed() is False

    def test_sleep_wake_up_on_change(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("initial: true\n", encoding="utf-8")

        def modify_file_callback(_duration):
            time.sleep(0.01)
            cfg_path.write_text("modified: true\n", encoding="utf-8")

        # sleep_func symuluje upływ czasu i zapis
        changed = sleep_with_config_watch(
            seconds=60,
            config_path=str(cfg_path),
            poll_interval=1.0,
            sleep_func=modify_file_callback,
        )
        assert changed is True

    def test_sleep_timeout_without_change(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("unchanged: true\n", encoding="utf-8")

        mock_sleep = MagicMock()
        changed = sleep_with_config_watch(
            seconds=10,
            config_path=str(cfg_path),
            poll_interval=5.0,
            sleep_func=mock_sleep,
        )
        assert changed is False
        assert mock_sleep.call_count == 2


class TestReportScheduler:
    """Weryfikacja wyliczania interwałów i decyzyjności w Schedulerze."""

    def test_calculate_next_wait_seconds_daily_mode(self):
        config = {
            "schedule": {
                "collection": {
                    "mode": "daily",
                    "time": "18:00",
                    "days": "all",
                }
            }
        }
        # O 14:00 do 18:00 brakuje 4h = 14400s
        now_1400 = datetime(2026, 10, 12, 14, 0, 0)
        wait_s = calculate_next_wait_seconds(config, now=now_1400)
        assert wait_s == 4 * 3600

        # Po 18:00 (np. 19:00) kolejny termin to jutro o 18:00 = 23h = 82800s
        now_1900 = datetime(2026, 10, 12, 19, 0, 0)
        wait_s = calculate_next_wait_seconds(config, now=now_1900)
        assert wait_s == 23 * 3600

    def test_should_collect_now_daily_before_scheduled_time(self, tmp_path):
        storage = FileStorage(str(tmp_path))
        user_login = "student1"
        users = [{"librus_login": user_login}]
        config = {
            "schedule": {
                "collection": {
                    "mode": "daily",
                    "time": "16:00",
                }
            }
        }
        # Zapisujemy dane bazowe
        storage.save_known_items(user_login, known_messages={"m1"}, known_notifications=set(), known_grades=set())
        storage.save_last_collect_time(user_login, "2026-10-11T16:05:00")

        # Godzina 15:30 (przed 16:00) -> nie pobieramy jeszcze
        now_1530 = datetime(2026, 10, 12, 15, 30, 0)
        assert should_collect_now(config, users, storage, now=now_1530) is False

    def test_should_collect_now_daily_already_collected_today(self, tmp_path):
        storage = FileStorage(str(tmp_path))
        user_login = "student1"
        users = [{"librus_login": user_login}]
        config = {
            "schedule": {
                "collection": {
                    "mode": "daily",
                    "time": "16:00",
                }
            }
        }
        storage.save_known_items(user_login, known_messages={"m1"}, known_notifications=set(), known_grades=set())
        # Zebrano dziś o 16:05
        storage.save_last_collect_time(user_login, "2026-10-12T16:05:00")

        # Godzina 16:30 -> już zebrano dzisiaj, nie pobieramy ponownie
        now_1630 = datetime(2026, 10, 12, 16, 30, 0)
        assert should_collect_now(config, users, storage, now=now_1630) is False

    def test_should_collect_now_daily_ready_to_collect(self, tmp_path):
        storage = FileStorage(str(tmp_path))
        user_login = "student1"
        users = [{"librus_login": user_login}]
        config = {
            "schedule": {
                "collection": {
                    "mode": "daily",
                    "time": "16:00",
                }
            }
        }
        storage.save_known_items(user_login, known_messages={"m1"}, known_notifications=set(), known_grades=set())
        # Ostatnie pobranie było wczoraj
        storage.save_last_collect_time(user_login, "2026-10-11T16:05:00")

        # Godzina 16:05 dziś -> nadszedł czas pobierania
        now_1605 = datetime(2026, 10, 12, 16, 5, 0)
        assert should_collect_now(config, users, storage, now=now_1605) is True

    def test_should_collect_now_fresh_account_without_data(self, tmp_path):
        storage = FileStorage(str(tmp_path))
        user_login = "new_student"
        users = [{"librus_login": user_login}]
        config = {
            "schedule": {
                "collection": {
                    "mode": "daily",
                    "time": "16:00",
                }
            }
        }
        # Nowe konto bez danych zawsze powinno zostać pobrane od razu
        now_1200 = datetime(2026, 10, 12, 12, 0, 0)
        assert should_collect_now(config, users, storage, now=now_1200) is True

    def test_trigger_scheduled_reports_execution_and_deduplication(self, tmp_path):
        storage = FileStorage(str(tmp_path))
        user_login = "student1"
        users = [
            {
                "librus_login": user_login,
                "student_report": {
                    "enabled": True,
                    "email": "kid@example.com",
                },
            }
        ]
        config = {
            "schedule": {
                "reports": [
                    {
                        "name": "Raport piątkowy",
                        "enabled": True,
                        "frequency": "weekly",
                        "weekday": "friday",
                        "time": "17:00",
                        "interval_days": 7,
                    }
                ]
            }
        }

        # 2026-10-16 to piątek, godzina 17:05
        friday_dt = datetime(2026, 10, 16, 17, 5, 0)

        with patch("librus2mail.progress_report.run_progress_reports") as mock_progress, \
             patch("librus2mail.student_report.run_student_reports") as mock_student:

            scheduler = ReportScheduler(config, storage=storage)

            # 1. Pierwsze wyzwolenie w zaplanowanym oknie czasowym
            triggered = scheduler.trigger_scheduled_reports(
                config_path=str(tmp_path / "config.yaml"),
                users=users,
                effective_storage_dir=str(tmp_path),
                now=friday_dt,
            )

            assert len(triggered) == 2
            assert mock_progress.call_count == 1
            assert mock_student.call_count == 1

            # Udajemy, że run_progress_reports zapisało datę wysyłki raportu w storage
            rep_key = "rep_weekly_7_17:00"
            storage.save_last_progress_report_date(user_login, friday_dt.isoformat(), report_key=rep_key)

            # 2. Kolejne wywołanie tego samego dnia nie powtarza wysyłki
            triggered_again = scheduler.trigger_scheduled_reports(
                config_path=str(tmp_path / "config.yaml"),
                users=users,
                effective_storage_dir=str(tmp_path),
                now=friday_dt + timedelta(minutes=15),
            )
            assert len(triggered_again) == 0
            assert mock_progress.call_count == 1
            assert mock_student.call_count == 1
