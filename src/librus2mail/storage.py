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

    @abstractmethod
    def list_stored_logins(self) -> list[str]:
        """Zwraca listę loginów odnalezionych w bazie pamięci stanu."""
        pass

    @abstractmethod
    def get_stored_messages(self, user_login: str) -> list[dict]:
        """Zwraca listę zarejestrowanych wiadomości ze storage."""
        pass

    @abstractmethod
    def get_stored_notifications(self, user_login: str) -> list[dict]:
        """Zwraca listę zarejestrowanych ogłoszeń ze storage."""
        pass

    @abstractmethod
    def save_messages_details(self, user_login: str, messages: list[dict]) -> None:
        """Zapisuje szczegóły wiadomości w storage."""
        pass

    @abstractmethod
    def save_notifications_details(self, user_login: str, notifications: list[dict]) -> None:
        """Zapisuje szczegóły ogłoszeń w storage."""
        pass

    @abstractmethod
    def get_last_collect_time(self, user_login: str) -> str | None:
        """Zwraca znacznik czasu (ISO) ostatniej synchronizacji danych z Librusa."""
        pass

    @abstractmethod
    def save_last_collect_time(self, user_login: str, date_iso: str) -> None:
        """Zapisuje znacznik czasu (ISO) ostatniej synchronizacji danych z Librusa."""
        pass

    @abstractmethod
    def get_last_notify_time(self, user_login: str) -> str | None:
        """Zwraca znacznik czasu (ISO) ostatniego wysłanego/wygenerowanego powiadomienia."""
        pass

    @abstractmethod
    def save_last_notify_time(self, user_login: str, date_iso: str) -> None:
        """Zapisuje znacznik czasu (ISO) ostatniego wysłanego/wygenerowanego powiadomienia."""
        pass

    @abstractmethod
    def save_timetable_entries(self, user_login: str, entries: list[dict]) -> None:
        """Zapisuje wpisy z terminarza (sprawdziany, kartkówki, nieobecności)."""
        pass

    @abstractmethod
    def get_timetable_history(self, user_login: str) -> list[dict]:
        """Zwraca listę wszystkich zarejestrowanych wpisów z terminarza."""
        pass

    @abstractmethod
    def get_last_timetable_sync(self, user_login: str) -> str | None:
        """Zwraca znacznik czasu (ISO) ostatniej synchronizacji terminarza lub None."""
        pass

    @abstractmethod
    def save_last_timetable_sync(self, user_login: str, date_iso: str) -> None:
        """Zapisuje znacznik czasu (ISO) ostatniej synchronizacji terminarza."""
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

    def save_messages_details(self, user_login: str, messages: list[dict]) -> None:
        """Zapisuje listę wiadomości ze szczegółami w storage."""
        if not messages:
            return
        file_path = self._get_file_path(user_login)
        temp_path = f"{file_path}.tmp"
        data = {}
        if os.path.isfile(file_path):
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        existing = {m.get('id'): m for m in data.get('messages_history', []) if m.get('id')}
        now_iso = datetime.now().isoformat()
        for m in messages:
            mid = m.get('id')
            if mid:
                if mid in existing:
                    existing[mid].update({k: v for k, v in m.items() if v})
                else:
                    m_copy = dict(m)
                    m_copy['added_at'] = m_copy.get('added_at') or now_iso
                    existing[mid] = m_copy
        data['messages_history'] = list(existing.values())
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania historii wiadomości do {file_path}: {e}")

    def save_notifications_details(self, user_login: str, notifications: list[dict]) -> None:
        """Zapisuje listę ogłoszeń ze szczegółami w storage."""
        if not notifications:
            return
        file_path = self._get_file_path(user_login)
        temp_path = f"{file_path}.tmp"
        data = {}
        if os.path.isfile(file_path):
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        existing = {n.get('id'): n for n in data.get('notifications_history', []) if n.get('id')}
        now_iso = datetime.now().isoformat()
        for n in notifications:
            nid = n.get('id')
            if nid:
                if nid in existing:
                    existing[nid].update({k: v for k, v in n.items() if v})
                else:
                    n_copy = dict(n)
                    n_copy['added_at'] = n_copy.get('added_at') or now_iso
                    existing[nid] = n_copy
        data['notifications_history'] = list(existing.values())
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania historii ogłoszeń do {file_path}: {e}")

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

    def get_last_collect_time(self, user_login: str) -> str | None:
        """Zwraca znacznik czasu (ISO) ostatniej synchronizacji danych z Librusa."""
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            return data.get('last_collect_time') or data.get('last_updated')
        except Exception as e:
            logger.error(f"Błąd podczas odczytu last_collect_time z {file_path}: {e}")
            return None

    def save_last_collect_time(self, user_login: str, date_iso: str) -> None:
        """Zapisuje znacznik czasu (ISO) ostatniej synchronizacji danych z Librusa."""
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
        data['last_collect_time'] = date_iso
        data['last_updated'] = date_iso
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
            logger.debug(f"Zapisano last_collect_time do {file_path}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania last_collect_time do {file_path}: {e}")

    def get_last_notify_time(self, user_login: str) -> str | None:
        """Zwraca znacznik czasu (ISO) ostatniego wysłanego/wygenerowanego powiadomienia."""
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            return data.get('last_notify_time') or data.get('last_update_create')
        except Exception as e:
            logger.error(f"Błąd podczas odczytu last_notify_time z {file_path}: {e}")
            return None

    def save_last_notify_time(self, user_login: str, date_iso: str) -> None:
        """Zapisuje znacznik czasu (ISO) ostatniego wysłanego/wygenerowanego powiadomienia."""
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
        data['last_notify_time'] = date_iso
        data['last_update_create'] = date_iso
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
            logger.debug(f"Zapisano last_notify_time do {file_path}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania last_notify_time do {file_path}: {e}")

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

    def list_stored_logins(self) -> list[str]:
        """Zwraca listę loginów odnalezionych na podstawie plików *.json w katalogu storage_dir."""
        if not os.path.isdir(self.storage_dir):
            return []
        logins = []
        try:
            for fname in os.listdir(self.storage_dir):
                if fname.endswith('.json') and not fname.endswith('.tmp'):
                    logins.append(fname[:-5])
        except Exception as e:
            logger.error(f"Błąd podczas listowania plików w {self.storage_dir}: {e}")
        return sorted(logins)

    def get_stored_messages(self, user_login: str) -> list[dict]:
        """Zwraca listę wiadomości zapisanych w storage (ze szczegółami jeśli dostępne)."""
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            if 'messages_history' in data and isinstance(data['messages_history'], list):
                return data['messages_history']
            messages = []
            import re
            for item in data.get('known_messages', []):
                s = str(item).strip()
                m = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', s)
                if m:
                    dt = m.group(1)
                    title = s[:m.start()].strip() or "Wiadomość"
                    sender = s[m.end():].strip() or "-"
                else:
                    dt = ""
                    title = s
                    sender = "-"
                messages.append({
                    'id': s,
                    'title': title,
                    'sender': sender,
                    'datetime': dt,
                    'body': '',
                })
            return messages
        except Exception as e:
            logger.error(f"Błąd podczas odczytu wiadomości ze storage ({file_path}): {e}")
            return []

    def get_stored_notifications(self, user_login: str) -> list[dict]:
        """Zwraca listę ogłoszeń zapisanych w storage."""
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            if 'notifications_history' in data and isinstance(data['notifications_history'], list):
                return data['notifications_history']
            notifications = []
            import re
            for item in data.get('known_notifications', []):
                s = str(item).strip()
                m = re.search(r'(\d{4}-\d{2}-\d{2})$', s)
                if m:
                    dt = m.group(1)
                    rest = s[:m.start()].strip()
                else:
                    dt = ""
                    rest = s
                notifications.append({
                    'id': s,
                    'title': rest,
                    'sender': "Szkoła",
                    'datetime': dt,
                    'body': '',
                })
            return notifications
        except Exception as e:
            logger.error(f"Błąd podczas odczytu ogłoszeń ze storage ({file_path}): {e}")
            return []

    def save_timetable_entries(self, user_login: str, entries: list[dict]) -> None:
        """Zapisuje listę wpisów z terminarza (sprawdziany, kartkówki, nieobecności) w storage."""
        if not entries:
            return
        file_path = self._get_file_path(user_login)
        temp_path = f"{file_path}.tmp"
        data = {}
        if os.path.isfile(file_path):
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}

        existing = {e.get('id'): e for e in data.get('timetable_history', []) if e.get('id')}
        now_iso = datetime.now().isoformat()
        for e in entries:
            eid = e.get('id')
            if eid:
                if eid in existing:
                    existing[eid].update({k: v for k, v in e.items() if v is not None})
                    existing[eid]['updated_at'] = now_iso
                else:
                    e_copy = dict(e)
                    e_copy['added_at'] = e_copy.get('added_at') or now_iso
                    e_copy['updated_at'] = now_iso
                    existing[eid] = e_copy

        data['timetable_history'] = list(existing.values())
        data['timetable_last_sync'] = now_iso
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania terminarza do {file_path}: {e}")

    def get_timetable_history(self, user_login: str) -> list[dict]:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            th = data.get('timetable_history', [])
            if isinstance(th, dict):
                return list(th.values())
            elif isinstance(th, list):
                return th
            return []
        except Exception as e:
            logger.error(f"Błąd podczas odczytu timetable_history z {file_path}: {e}")
            return []

    def get_last_timetable_sync(self, user_login: str) -> str | None:
        file_path = self._get_file_path(user_login)
        if not os.path.isfile(file_path):
            return None
        try:
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            return data.get('timetable_last_sync')
        except Exception:
            return None

    def save_last_timetable_sync(self, user_login: str, date_iso: str) -> None:
        file_path = self._get_file_path(user_login)
        temp_path = f"{file_path}.tmp"
        data = {}
        if os.path.isfile(file_path):
            try:
                with open(file_path, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}
        data['timetable_last_sync'] = date_iso
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception as e:
            logger.error(f"Błąd podczas zapisu timetable_last_sync do {file_path}: {e}")


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

