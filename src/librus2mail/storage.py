import collections.abc
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def read_json_safe(path: Path | str) -> dict[str, Any]:
    """Bezpiecznie wczytuje dane z pliku JSON; jeśli plik nie istnieje lub jest uszkodzony, zwraca pusty słownik."""
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.error(f"Błąd podczas odczytu pliku JSON {p}: {e}")
        return {}


def write_json_atomic(path: Path | str, data: Any) -> None:
    """Atomowo zapisuje strukturę danych do pliku JSON za pośrednictwem pliku tymczasowego (.tmp)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp_path = p.with_name(f"{p.name}.tmp")
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_path.replace(p)
    except Exception as e:
        logger.error(f"Błąd podczas atomowego zapisu JSON do {p}: {e}")
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def parse_date_sort_key(val: Any) -> datetime:
    """Parsuje ciąg daty lub datę/czas do obiektu datetime w celu precyzyjnego sortowania."""
    if not val:
        return datetime.min
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())

    val_str = str(val).strip()
    if not val_str:
        return datetime.min

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%d",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
    ):
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            pass

    m = re.search(r'(\d{4}-\d{2}-\d{2})(?:[T\s](\d{2}:\d{2}(?::\d{2})?))?', val_str)
    if m:
        d_part = m.group(1)
        t_part = m.group(2) or "00:00:00"
        if len(t_part) == 5:
            t_part += ":00"
        try:
            return datetime.strptime(f"{d_part} {t_part}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    return datetime.min


def sort_items_descending(items: list[Any]) -> list[Any]:
    """Sortuje listę wiadomości lub ogłoszeń od najnowszych do najstarszych (malejąco po dacie)."""
    if not items:
        return []

    def _extract_val(item: Any, key: str) -> Any:
        if isinstance(item, collections.abc.Mapping):
            return item.get(key)
        return getattr(item, key, None)

    return sorted(
        items,
        key=lambda x: (
            parse_date_sort_key(_extract_val(x, 'datetime') or _extract_val(x, 'date')),
            parse_date_sort_key(_extract_val(x, 'added_at')),
            str(_extract_val(x, 'id') or ''),
        ),
        reverse=True,
    )


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
    def get_last_progress_report_date(self, user_login: str, report_key: str | None = None) -> str | None:
        """Zwraca datę ostatnio wygenerowanego raportu postępów (ISO format) lub None."""
        pass

    @abstractmethod
    def save_last_progress_report_date(self, user_login: str, date_iso: str, report_key: str | None = None) -> None:
        """Zapisuje datę wygenerowanego raportu postępów."""
        pass

    @abstractmethod
    def get_student_name(self, user_login: str) -> str | None:
        """Zwraca zapisaną nazwę ucznia (jeśli występuje w storage) lub None."""
        pass

    @abstractmethod
    def set_student_name(self, user_login: str, name: str) -> None:
        """Zapisuje nazwę ucznia w storage."""
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

    @abstractmethod
    def mark_timetable_entries_notified(self, user_login: str, entry_ids: list[str], notified_at_iso: str | None = None) -> None:
        """Oznacza wpisy terminarza jako uwzględnione w wysłanym powiadomieniu (last_notified_at)."""
        pass

    @abstractmethod
    def save_schedule_entries(
        self,
        user_login: str,
        entries: list[dict],
        retention_days: int | None = 30,
        reference_date: datetime | date | None = None,
    ) -> None:
        """Zapisuje listę lekcji i zmian z planu lekcji wraz z opcjonalną retencją starszych wpisów."""
        pass

    @abstractmethod
    def get_schedule_history(self, user_login: str) -> list[dict]:
        """Zwraca listę lekcji z planu lekcji."""
        pass

    @abstractmethod
    def get_last_schedule_sync(self, user_login: str) -> str | None:
        """Zwraca znacznik czasu (ISO) ostatniej synchronizacji planu lekcji lub None."""
        pass

    @abstractmethod
    def save_last_schedule_sync(self, user_login: str, date_iso: str) -> None:
        """Zapisuje znacznik czasu (ISO) ostatniej synchronizacji planu lekcji."""
        pass


class FileStorage(BaseStorage):
    """Trwałe przechowywanie stanu w plikach JSON w wyznaczonym katalogu (np. storage/<login>.json)."""

    def __init__(self, storage_dir: str | Path = 'storage'):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, user_login: str) -> Path:
        safe_login = str(user_login).replace('/', '_').replace('\\', '_')
        return self.storage_dir / f"{safe_login}.json"

    def has_existing_data(self, user_login: str) -> bool:
        path = self._get_file_path(user_login)
        if not path.is_file():
            return False
        data = read_json_safe(path)
        return bool(data.get('known_messages') or data.get('known_notifications') or data.get('known_grades'))

    def load_known_items(self, user_login: str) -> dict[str, set]:
        path = self._get_file_path(user_login)
        if not path.is_file():
            logger.info(f"Brak pliku stanu dla {user_login} ({path}). Zostanie utworzony nowy stan.")
            return {'messages': set(), 'notifications': set(), 'grades': set()}

        data = read_json_safe(path)
        messages = set(data.get('known_messages', []))
        notifications = set(data.get('known_notifications', []))
        grades = set(data.get('known_grades', []))
        logger.info(
            f"Wczytano stan z {path} dla konta {user_login}: "
            f"wiadomości: {len(messages)}, ogłoszenia: {len(notifications)}, oceny: {len(grades)}"
        )
        return {
            'messages': messages,
            'notifications': notifications,
            'grades': grades,
        }

    def get_last_error(self, user_login: str) -> dict | None:
        path = self._get_file_path(user_login)
        return read_json_safe(path).get('last_error')

    def save_last_error(self, user_login: str, error_str: str, step: str = "") -> None:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        now = datetime.now()
        data['librus_login'] = str(user_login)
        data['last_error'] = {
            'error': str(error_str),
            'step': step,
            'timestamp': now.timestamp(),
            'time_str': now.strftime("%Y-%m-%d %H:%M:%S"),
        }
        write_json_atomic(path, data)

    def clear_last_error(self, user_login: str) -> None:
        path = self._get_file_path(user_login)
        if not path.is_file():
            return
        data = read_json_safe(path)
        if data.get('last_error') is not None:
            data['last_error'] = None
            write_json_atomic(path, data)

    def save_known_items(self, user_login: str, known_messages: set, known_notifications: set, known_grades: set) -> None:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
        data['last_updated'] = datetime.now().isoformat()
        data['known_messages'] = sorted(list(known_messages))
        data['known_notifications'] = sorted(list(known_notifications))
        data['known_grades'] = sorted(list(known_grades))
        write_json_atomic(path, data)
        logger.debug(f"Zapisano stan do pliku {path} dla {user_login}")

    def save_grades_details(self, user_login: str, grades: list[dict]) -> None:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
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
        write_json_atomic(path, data)
        logger.debug(f"Zapisano historię ocen do pliku {path} dla {user_login}")

    def save_messages_details(self, user_login: str, messages: list[dict]) -> None:
        """Zapisuje listę wiadomości ze szczegółami w storage."""
        if not messages:
            return
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
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
        data['messages_history'] = sort_items_descending(list(existing.values()))
        write_json_atomic(path, data)

    def save_notifications_details(self, user_login: str, notifications: list[dict]) -> None:
        """Zapisuje listę ogłoszeń ze szczegółami w storage."""
        if not notifications:
            return
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
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
        data['notifications_history'] = sort_items_descending(list(existing.values()))
        write_json_atomic(path, data)

    def get_grades_history(self, user_login: str) -> list[dict]:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        gh = data.get('grades_history', {})
        if isinstance(gh, dict):
            return list(gh.values())
        elif isinstance(gh, list):
            return gh
        return []

    def get_last_progress_report_date(self, user_login: str, report_key: str | None = None) -> str | None:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        if report_key:
            rep_dates = data.get('last_progress_report_dates', {})
            if isinstance(rep_dates, dict) and report_key in rep_dates:
                return rep_dates[report_key]
        return data.get('last_progress_report_date')

    def save_last_progress_report_date(self, user_login: str, date_iso: str, report_key: str | None = None) -> None:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
        data['last_progress_report_date'] = date_iso
        if report_key:
            rep_dates = data.get('last_progress_report_dates')
            if not isinstance(rep_dates, dict):
                rep_dates = {}
            rep_dates[report_key] = date_iso
            data['last_progress_report_dates'] = rep_dates
        write_json_atomic(path, data)
        logger.debug(f"Zapisano last_progress_report_date ({report_key or 'global'}) do {path}")

    def get_last_collect_time(self, user_login: str) -> str | None:
        """Zwraca znacznik czasu (ISO) ostatniej synchronizacji danych z Librusa."""
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        return data.get('last_collect_time') or data.get('last_updated')

    def save_last_collect_time(self, user_login: str, date_iso: str) -> None:
        """Zapisuje znacznik czasu (ISO) ostatniej synchronizacji danych z Librusa."""
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
        data['last_collect_time'] = date_iso
        data['last_updated'] = date_iso
        write_json_atomic(path, data)
        logger.debug(f"Zapisano last_collect_time do {path}")

    def get_last_notify_time(self, user_login: str) -> str | None:
        """Zwraca znacznik czasu (ISO) ostatniego wysłanego/wygenerowanego powiadomienia."""
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        return data.get('last_notify_time') or data.get('last_update_create')

    def save_last_notify_time(self, user_login: str, date_iso: str) -> None:
        """Zapisuje znacznik czasu (ISO) ostatniego wysłanego/wygenerowanego powiadomienia."""
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
        data['last_notify_time'] = date_iso
        data['last_update_create'] = date_iso
        write_json_atomic(path, data)
        logger.debug(f"Zapisano last_notify_time do {path}")

    def get_student_name(self, user_login: str) -> str | None:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        return data.get('librus_login_name') or data.get('student_name')

    def set_student_name(self, user_login: str, name: str) -> None:
        """Zapisuje nazwę ucznia w storage."""
        if not name:
            return
        path = self._get_file_path(user_login)
        if not path.is_file():
            return
        data = read_json_safe(path)
        if data.get('librus_login_name') != name or data.get('student_name') != name:
            data['student_name'] = name
            data['librus_login_name'] = name
            write_json_atomic(path, data)
            logger.debug(f"Zaktualizowano nazwę ucznia '{name}' w {path}")

    def list_stored_logins(self) -> list[str]:
        """Zwraca listę loginów odnalezionych na podstawie plików *.json w katalogu storage_dir."""
        if not self.storage_dir.is_dir():
            return []
        logins = []
        try:
            for p in self.storage_dir.glob("*.json"):
                if p.is_file() and not p.name.endswith('.tmp'):
                    logins.append(p.stem)
        except Exception as e:
            logger.error(f"Błąd podczas listowania plików w {self.storage_dir}: {e}")
        return sorted(logins)

    def get_stored_messages(self, user_login: str) -> list[dict]:
        """Zwraca listę wiadomości zapisanych w storage (ze szczegółami jeśli dostępne)."""
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        if 'messages_history' in data and isinstance(data['messages_history'], list):
            return sort_items_descending(data['messages_history'])
        messages = []
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
        return sort_items_descending(messages)

    def get_stored_notifications(self, user_login: str) -> list[dict]:
        """Zwraca listę ogłoszeń zapisanych w storage."""
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        if 'notifications_history' in data and isinstance(data['notifications_history'], list):
            return sort_items_descending(data['notifications_history'])
        notifications = []
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
        return sort_items_descending(notifications)

    def save_timetable_entries(self, user_login: str, entries: list[dict]) -> None:
        """Zapisuje listę wpisów z terminarza (sprawdziany, kartkówki, nieobecności) w storage."""
        if not entries:
            return
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
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
        write_json_atomic(path, data)

    def get_timetable_history(self, user_login: str) -> list[dict]:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        th = data.get('timetable_history', [])
        if isinstance(th, dict):
            return list(th.values())
        elif isinstance(th, list):
            return th
        return []

    def get_last_timetable_sync(self, user_login: str) -> str | None:
        path = self._get_file_path(user_login)
        return read_json_safe(path).get('timetable_last_sync')

    def save_last_timetable_sync(self, user_login: str, date_iso: str) -> None:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
        data['timetable_last_sync'] = date_iso
        write_json_atomic(path, data)

    def mark_timetable_entries_notified(self, user_login: str, entry_ids: list[str], notified_at_iso: str | None = None) -> None:
        path = self._get_file_path(user_login)
        if not path.is_file():
            return
        data = read_json_safe(path)
        id_set = set(entry_ids)
        stamp = notified_at_iso or datetime.now().isoformat()
        updated = False
        for entry in data.get('timetable_history', []):
            if entry.get('id') in id_set:
                entry['last_notified_at'] = stamp
                updated = True

        if updated:
            write_json_atomic(path, data)

    def save_schedule_entries(
        self,
        user_login: str,
        entries: list[dict],
        retention_days: int | None = 30,
        reference_date: datetime | date | None = None,
    ) -> None:
        """Zapisuje listę wpisów z planu lekcji w storage z automatyczną retencją (domyślnie >30 dni)."""
        if not entries and retention_days is None:
            return
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
        existing = {}
        for e in data.get('schedule_history', []):
            eid = e.get('id') or f"{e.get('date')}_{e.get('lesson_no')}_{e.get('subject')}"
            if eid:
                e['id'] = eid
                existing[eid] = e

        now_iso = datetime.now().isoformat()
        for e in entries or []:
            eid = e.get('id') or f"{e.get('date')}_{e.get('lesson_no')}_{e.get('subject')}"
            if eid:
                e['id'] = eid
                if eid in existing:
                    existing[eid].update({k: v for k, v in e.items() if v is not None})
                    existing[eid]['updated_at'] = now_iso
                else:
                    e_copy = dict(e)
                    e_copy['added_at'] = e_copy.get('added_at') or now_iso
                    e_copy['updated_at'] = now_iso
                    existing[eid] = e_copy

        # Retencja wpisów starszych niż retention_days (domyślnie 30 dni)
        if retention_days is not None and retention_days > 0:
            if reference_date:
                ref_d = reference_date.date() if isinstance(reference_date, datetime) else reference_date
            else:
                ref_d = datetime.now().date()
            cutoff_date_str = (ref_d - timedelta(days=retention_days)).isoformat()

            retained = {}
            for eid, item in existing.items():
                item_date = item.get('date')
                if item_date:
                    if item_date >= cutoff_date_str:
                        retained[eid] = item
                else:
                    retained[eid] = item
            existing = retained

        data['schedule_history'] = sorted(
            existing.values(),
            key=lambda x: (
                x.get('date', ''),
                int(x.get('lesson_no', 0)) if str(x.get('lesson_no', '')).isdigit() else 99,
            ),
        )
        data['schedule_last_sync'] = now_iso
        write_json_atomic(path, data)

    def get_schedule_history(self, user_login: str) -> list[dict]:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        sh = data.get('schedule_history', [])
        if isinstance(sh, dict):
            return list(sh.values())
        elif isinstance(sh, list):
            return sh
        return []

    def get_last_schedule_sync(self, user_login: str) -> str | None:
        path = self._get_file_path(user_login)
        return read_json_safe(path).get('schedule_last_sync')

    def save_last_schedule_sync(self, user_login: str, date_iso: str) -> None:
        path = self._get_file_path(user_login)
        data = read_json_safe(path)
        data['librus_login'] = str(user_login)
        data['schedule_last_sync'] = date_iso
        write_json_atomic(path, data)


def create_storage(storage_dir: str | Path = 'storage', *args, **kwargs) -> FileStorage:
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

