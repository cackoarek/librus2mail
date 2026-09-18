import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


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

    @abstractmethod
    def save_grades_details(self, user_login: str, grades: list[dict]) -> None:
        """Zapisuje szczegółowe informacje o ocenach (waga, data, kategoria, komentarz)."""
        pass

    @abstractmethod
    def get_grades_history(self, user_login: str) -> list[dict]:
        """Zwraca listę wszystkich zarejestrowanych ocen z pełnymi szczegółami."""
        pass

    @abstractmethod
    def get_last_progress_report_date(self, user_login: str) -> str | None:
        """Zwraca datę ostatnio wygenerowanego raportu postępów (ISO format) lub None."""
        pass

    @abstractmethod
    def save_last_progress_report_date(self, user_login: str, date_iso: str) -> None:
        """Zapisuje datę wygenerowanego raportu postępów."""
        pass

    @abstractmethod
    def get_student_name(self, user_login: str) -> str | None:
        """Zwraca zapisaną nazwę ucznia (jeśli występuje w storage) lub None."""
        pass


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
            with open(file_path, encoding='utf-8') as f:
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
            with open(file_path, encoding='utf-8') as f:
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
            with open(file_path, encoding='utf-8') as f:
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
                with open(file_path, encoding='utf-8') as f:
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
            with open(file_path, encoding='utf-8') as f:
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
                with open(file_path, encoding='utf-8') as f:
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

    def save_grades_details(self, user_login: str, grades: list[dict]) -> None:
        file_path = self._get_file_path(user_login)
        temp_path = f"{file_path}.tmp"
        data = {}
        if os.path.isfile(file_path):
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}

        data['librus_login'] = str(user_login)
        data['last_updated'] = datetime.now().isoformat()
        raw_history = data.get('grades_history', {})
        if isinstance(raw_history, list):
            grades_history = {str(g.get('id', '')): g for g in raw_history if g.get('id')}
        elif isinstance(raw_history, dict):
            grades_history = dict(raw_history)
        else:
            grades_history = {}

        now_iso = datetime.now().isoformat()
        for g in grades:
            gid = str(g.get('id', ''))
            if not gid:
                continue
            if gid not in grades_history:
                g_copy = dict(g)
                g_copy['added_at'] = g_copy.get('added_at') or now_iso
                grades_history[gid] = g_copy
            else:
                grades_history[gid].update({k: v for k, v in g.items() if v})

        data['grades_history'] = grades_history

        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
            logger.debug(f"Zapisano historię ocen do pliku {file_path} dla {user_login}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania historii ocen do {file_path}: {e}")

    def get_grades_history(self, user_login: str) -> list[dict]:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            gh = data.get('grades_history', {})
            if isinstance(gh, dict):
                return list(gh.values())
            elif isinstance(gh, list):
                return gh
            return []
        except Exception as e:
            logger.error(f"Błąd podczas odczytu grades_history z {file_path}: {e}")
            return []

    def get_last_progress_report_date(self, user_login: str) -> str | None:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            return data.get('last_progress_report_date')
        except Exception as e:
            logger.error(f"Błąd podczas odczytu last_progress_report_date z {file_path}: {e}")
            return None

    def save_last_progress_report_date(self, user_login: str, date_iso: str) -> None:
        file_path = self._get_file_path(user_login)
        temp_path = f"{file_path}.tmp"
        data = {}
        if os.path.isfile(file_path):
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data['librus_login'] = str(user_login)
        data['last_progress_report_date'] = date_iso
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
            logger.debug(f"Zapisano last_progress_report_date do {file_path}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania last_progress_report_date do {file_path}: {e}")

    def get_student_name(self, user_login: str) -> str | None:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            return data.get('librus_login_name') or data.get('student_name')
        except Exception as e:
            logger.error(f"Błąd podczas odczytu nazwy ucznia z {file_path}: {e}")
            return None


def create_storage(storage_dir: str = 'storage', *args, **kwargs) -> FileStorage:
    """
    Tworzy trwałą pamięć stanu opartą na plikach JSON (FileStorage).
    Dla wstecznej kompatybilności ignoruje dawny parametr storage_type.
    """
    target_dir = kwargs.get('storage_dir')
    if not target_dir:
        if isinstance(storage_dir, str) and storage_dir.upper() in ('FILES', 'RAM'):
            target_dir = args[0] if args else 'storage'
        else:
            target_dir = storage_dir or 'storage'
    return FileStorage(storage_dir=target_dir)

