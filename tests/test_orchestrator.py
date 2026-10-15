"""Testy jednostkowe dla modularnej orchestracji (Faza 3 planu naprawczego):
- resolve_target_users: filtrowanie użytkowników, auto-discovery ze storage, obsługa błędów.
- execute_collection_cycle: pojedynczy cykl zbierania, tryby offline, sync_only, obsługa błędów zbierania.
"""

from unittest.mock import MagicMock

import pytest

from librus2mail.librus_collector import (
    execute_collection_cycle,
    resolve_target_users,
)


class DummyStorage:
    def __init__(self, stored_users=None):
        self.storage_dir = "/dummy/storage"
        self.stored_users = stored_users or {}

    def has_existing_data(self, login: str) -> bool:
        return str(login) in self.stored_users

    def get_grades_history(self, login: str) -> list:
        return self.stored_users.get(str(login), {}).get("grades", [])

    def get_student_name(self, login: str) -> str | None:
        return self.stored_users.get(str(login), {}).get("name")

    def list_stored_logins(self) -> list[str]:
        return list(self.stored_users.keys())


class TestResolveTargetUsers:
    def test_resolve_all_users_from_config(self):
        """Brak filtru zwraca wszystkich użytkowników z konfiguracji."""
        config = {
            "librus_users": [
                {"librus_login": "111", "librus_login_name": "Uczeń 1"},
                {"librus_login": "222", "librus_login_name": "Uczeń 2"},
            ]
        }
        storage = DummyStorage({"111": {}, "222": {}})

        users = resolve_target_users(config, storage)
        assert len(users) == 2
        assert users[0]["librus_login"] == "111"
        assert users[0]["id"] == 0
        assert users[0]["dry-parse"] is False
        assert users[1]["librus_login"] == "222"
        assert users[1]["id"] == 1

    def test_filter_by_login(self):
        """Filtrowanie użytkowników po numerze loginu."""
        config = {
            "librus_users": [
                {"librus_login": "111222", "librus_login_name": "Kacper"},
                {"librus_login": "333444", "librus_login_name": "Zosia"},
            ]
        }
        storage = DummyStorage({"111222": {}})

        users = resolve_target_users(config, storage, user_filter="111222")
        assert len(users) == 1
        assert users[0]["librus_login"] == "111222"
        assert users[0]["librus_login_name"] == "Kacper"

    def test_filter_by_name_case_insensitive(self):
        """Filtrowanie użytkowników po nazwisku z ignorowaniem wielkości liter."""
        config = {
            "librus_users": [
                {"librus_login": "111222", "librus_login_name": "Kacper Kowalski"},
                {"librus_login": "333444", "librus_login_name": "Zosia Nowak"},
            ]
        }
        storage = DummyStorage({"111222": {}})

        users = resolve_target_users(config, storage, user_filter="kowalski")
        assert len(users) == 1
        assert users[0]["librus_login"] == "111222"

    def test_filter_fallback_to_storage_profile(self):
        """Gdy filtrowanego użytkownika nie ma w configu, ale jest w bazie storage, tworzony jest profil fallbackowy."""
        config = {
            "librus_users": [
                {
                    "librus_login": "111",
                    "librus_login_name": "Uczeń 1",
                    "notification_receivers": ["parent@example.com"],
                }
            ]
        }
        storage = DummyStorage({"999": {"name": "Profil Historyczny", "grades": [{"id": "g1"}]}})

        users = resolve_target_users(config, storage, user_filter="999")
        assert len(users) == 1
        assert users[0]["librus_login"] == "999"
        assert users[0]["librus_login_name"] == "Profil Historyczny"
        assert users[0]["notification_receivers"] == ["parent@example.com"]

    def test_filter_not_found_raises_exit(self):
        """Brak dopasowania w configu i w bazie storage kończy działanie błędem sys.exit(1)."""
        config = {"librus_users": [{"librus_login": "111", "librus_login_name": "Uczeń 1"}]}
        storage = DummyStorage({})

        with pytest.raises(SystemExit) as exc_info:
            resolve_target_users(config, storage, user_filter="nieistniejacy")
        assert exc_info.value.code == 1

    def test_simulation_auto_discovery_from_storage(self):
        """W trybie symulacji (is_simulation=True), gdy config nie ma wspólnych użytkowników, następuje auto-discovery z bazy storage."""
        config = {
            "librus_users": [
                {
                    "librus_login": "999",
                    "notification_receivers": ["parent@example.com"],
                }
            ]
        }
        storage = DummyStorage({
            "555": {"name": "Autowykryty 1"},
            "666": {"name": "Autowykryty 2"},
        })

        users = resolve_target_users(config, storage, is_simulation=True)
        assert len(users) == 2
        logins = {u["librus_login"] for u in users}
        assert logins == {"555", "666"}


class TestExecuteCollectionCycle:
    def test_execute_cycle_success(self):
        """Pojedynczy pomyślny cykl: pobranie danych i wywołanie powiadomień."""
        mock_collector = MagicMock()
        mock_notifier = MagicMock()
        mock_scheduler = MagicMock()
        mock_storage = DummyStorage()

        users = [{"librus_login": "111", "librus_login_name": "Uczeń 1"}]
        mock_collector.collect_all.return_value = {
            "111": {
                "success": True,
                "login": "111",
                "messages": [{"id": "m1"}],
                "notifications": [],
                "grades": [],
                "new_messages": [{"id": "m1"}],
                "new_notifications": [],
                "new_grades": [],
            }
        }

        result = execute_collection_cycle(
            collector=mock_collector,
            notifier=mock_notifier,
            scheduler=mock_scheduler,
            users=users,
            storage=mock_storage,
            work_in_loop=False,
        )

        assert result["should_collect"] is True
        mock_collector.collect_all.assert_called_once_with(users)
        mock_notifier.process_user_notifications.assert_called_once()
        mock_scheduler.trigger_scheduled_reports.assert_called_once()

    def test_execute_cycle_offline_mode(self):
        """W trybie offline pobieranie z Librusa jest pomijane, powiadomienia korzystają z bazy storage."""
        mock_collector = MagicMock()
        mock_notifier = MagicMock()
        mock_scheduler = MagicMock()
        mock_storage = DummyStorage()

        users = [{"librus_login": "111", "librus_login_name": "Uczeń 1"}]

        result = execute_collection_cycle(
            collector=mock_collector,
            notifier=mock_notifier,
            scheduler=mock_scheduler,
            users=users,
            storage=mock_storage,
            offline=True,
            work_in_loop=False,
        )

        assert result["should_collect"] is True
        mock_collector.collect_all.assert_not_called()
        mock_notifier.process_user_notifications.assert_called_once()
        # W trybie offline nie wyzwalamy zaplanowanych raportów
        mock_scheduler.trigger_scheduled_reports.assert_not_called()

    def test_execute_cycle_sync_only(self):
        """W trybie sync_only pobieranie następuje, ale powiadomienia i raporty są pomijane."""
        mock_collector = MagicMock()
        mock_notifier = MagicMock()
        mock_scheduler = MagicMock()
        mock_storage = DummyStorage()

        users = [{"librus_login": "111", "librus_login_name": "Uczeń 1"}]
        mock_collector.collect_all.return_value = {
            "111": {"success": True, "login": "111"}
        }

        result = execute_collection_cycle(
            collector=mock_collector,
            notifier=mock_notifier,
            scheduler=mock_scheduler,
            users=users,
            storage=mock_storage,
            sync_only=True,
            work_in_loop=False,
        )

        assert result["should_collect"] is True
        mock_collector.collect_all.assert_called_once_with(users)
        mock_notifier.process_user_notifications.assert_not_called()
        mock_scheduler.trigger_scheduled_reports.assert_not_called()

    def test_execute_cycle_skips_notifications_on_user_error(self):
        """Gdy pobieranie dla ucznia zwróciło success=False, powiadomienia dla niego są pomijane."""
        mock_collector = MagicMock()
        mock_notifier = MagicMock()
        mock_scheduler = MagicMock()
        mock_storage = DummyStorage()

        users = [{"librus_login": "111", "librus_login_name": "Uczeń 1"}]
        mock_collector.collect_all.return_value = {
            "111": {"success": False, "login": "111", "error": "Login failed"}
        }

        result = execute_collection_cycle(
            collector=mock_collector,
            notifier=mock_notifier,
            scheduler=mock_scheduler,
            users=users,
            storage=mock_storage,
            work_in_loop=False,
        )

        assert result["should_collect"] is True
        mock_collector.collect_all.assert_called_once_with(users)
        mock_notifier.process_user_notifications.assert_not_called()
