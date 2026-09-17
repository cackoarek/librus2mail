import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from base_logger import logger


class BaseStorage(ABC):
    """Bazowa klasa pamięci stanu aplikacji."""

    @abstractmethod
    def load_known_items(self, user_login: str) -> dict[str, set]:
        """Wczytuje zbiory znanych identyfikatorów (messages, notifications, grades)."""
        pass

    @abstractmethod
    def save_known_items(self, user_login: str, known_messages: set, known_notifications: set, known_grades: set) -> None:
        """Zapisuje zbiory znanych identyfikatorów."""
        pass

    @abstractmethod
    def has_existing_data(self, user_login: str) -> bool:
        """Zwraca True, jeśli istnieją już zapisane dane z poprzednich uruchomień."""
        pass

    @abstractmethod
    def get_last_error(self, user_login: str) -> dict | None:
        """Zwraca informacje o ostatnim błędzie (timestamp, error, step, time_str) lub None."""
        pass

    @abstractmethod
    def save_last_error(self, user_login: str, error_str: str, step: str = "") -> None:
        """Zapisuje informacje o ostatnim błędzie wraz ze znacznikiem czasu."""
        pass

    @abstractmethod
    def clear_last_error(self, user_login: str) -> None:
        """Czyści informację o ostatnim błędzie po udanym sprawdzeniu."""
        pass


class MemoryStorage(BaseStorage):
    """Przechowywanie stanu wyłącznie w pamięci RAM procesu (resetowane po restarcie)."""

    def __init__(self):
        self._cache: dict[str, dict[str, set]] = {}
        self._last_errors: dict[str, dict] = {}

    def has_existing_data(self, user_login: str) -> bool:
        login_str = str(user_login)
        return login_str in self._cache and any(len(s) > 0 for s in self._cache[login_str].values())

    def get_last_error(self, user_login: str) -> dict | None:
        return self._last_errors.get(str(user_login))

    def save_last_error(self, user_login: str, error_str: str, step: str = "") -> None:
        now = datetime.now()
        self._last_errors[str(user_login)] = {
            'error': str(error_str),
            'step': step,
            'timestamp': now.timestamp(),
            'time_str': now.strftime("%Y-%m-%d %H:%M:%S")
        }

    def clear_last_error(self, user_login: str) -> None:
        self._last_errors.pop(str(user_login), None)

    def load_known_items(self, user_login: str) -> dict[str, set]:
        login_str = str(user_login)
        if login_str not in self._cache:
            self._cache[login_str] = {
                'messages': set(),
                'notifications': set(),
                'grades': set()
            }
        return {
            'messages': set(self._cache[login_str]['messages']),
            'notifications': set(self._cache[login_str]['notifications']),
            'grades': set(self._cache[login_str]['grades'])
        }

    def save_known_items(self, user_login: str, known_messages: set, known_notifications: set, known_grades: set) -> None:
        login_str = str(user_login)
        self._cache[login_str] = {
            'messages': set(known_messages),
            'notifications': set(known_notifications),
            'grades': set(known_grades)
        }


class FileStorage(BaseStorage):
    """Trwałe przechowywanie stanu w plikach JSON w wyznaczonym katalogu (np. storage/<login>.json)."""

    def __init__(self, storage_dir: str = 'storage'):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_file_path(self, user_login: str) -> str:
        safe_login = str(user_login).replace('/', '_').replace('\\', '_')
        return os.path.join(self.storage_dir, f"{safe_login}.json")

    def has_existing_data(self, user_login: str) -> bool:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return False
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return bool(data.get('known_messages') or data.get('known_notifications') or data.get('known_grades'))
        except Exception:
            return False

    def load_known_items(self, user_login: str) -> dict[str, set]:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            logger.info(f"Brak pliku stanu dla {user_login} ({file_path}). Zostanie utworzony nowy stan.")
            return {'messages': set(), 'notifications': set(), 'grades': set()}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            messages = set(data.get('known_messages', []))
            notifications = set(data.get('known_notifications', []))
            grades = set(data.get('known_grades', []))
            logger.info(
                f"Wczytano stan z {file_path} dla konta {user_login}: "
                f"wiadomości: {len(messages)}, ogłoszenia: {len(notifications)}, oceny: {len(grades)}"
            )
            return {
                'messages': messages,
                'notifications': notifications,
                'grades': grades
            }
        except Exception as e:
            logger.error(f"Błąd podczas wczytywania pliku stanu {file_path}: {e}")
            return {'messages': set(), 'notifications': set(), 'grades': set()}

    def get_last_error(self, user_login: str) -> dict | None:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('last_error')
        except Exception as e:
            logger.error(f"Błąd podczas odczytu last_error z {file_path}: {e}")
            return None

    def save_last_error(self, user_login: str, error_str: str, step: str = "") -> None:
        file_path = self._get_file_path(user_login)
        temp_path = f"{file_path}.tmp"
        data = {}
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        now = datetime.now()
        data['librus_login'] = str(user_login)
        data['last_error'] = {
            'error': str(error_str),
            'step': step,
            'timestamp': now.timestamp(),
            'time_str': now.strftime("%Y-%m-%d %H:%M:%S")
        }
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania last_error do pliku {file_path}: {e}")

    def clear_last_error(self, user_login: str) -> None:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('last_error') is not None:
                data['last_error'] = None
                temp_path = f"{file_path}.tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, file_path)
        except Exception as e:
            logger.error(f"Błąd podczas czyszczenia last_error w pliku {file_path}: {e}")

    def save_known_items(self, user_login: str, known_messages: set, known_notifications: set, known_grades: set) -> None:
        file_path = self._get_file_path(user_login)
        temp_path = f"{file_path}.tmp"
        data = {}
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data['librus_login'] = str(user_login)
        data['last_updated'] = datetime.now().isoformat()
        data['known_messages'] = sorted(list(known_messages))
        data['known_notifications'] = sorted(list(known_notifications))
        data['known_grades'] = sorted(list(known_grades))
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
            logger.debug(f"Zapisano stan do pliku {file_path} dla {user_login}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania pliku stanu {file_path}: {e}")


def create_storage(storage_type: str = 'RAM', storage_dir: str = 'storage') -> BaseStorage:
    storage_type_normalized = (storage_type or 'RAM').strip().upper()
    if storage_type_normalized == 'FILES':
        return FileStorage(storage_dir=storage_dir)
    return MemoryStorage()
