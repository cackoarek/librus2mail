#!/usr/bin/env python3
"""
Moduł 1: LibrusCollector (Zbieranie danych).
Odpowiada wyłącznie za autoryzację i pobieranie surowych danych ze szkoły
(wiadomości, ogłoszenia, oceny) oraz synchronizację z lokalną bazą storage.
"""

import argparse
import logging
import sys
import traceback
from datetime import datetime
from time import sleep
from typing import Any

import requests

from .base_logger import setup_logging
from .config import read_config
from .config_watcher import (
    ConfigWatcher,
)
from .config_watcher import (
    sleep_with_config_watch as _sleep_with_config_watch,
)
from .exceptions import (
    LibrusAuthError,
    LibrusNetworkError,
    LibrusParsingError,
)
from .librus import Librus
from .mail_sender import MailSender
from .scheduler import (
    ReportScheduler,
    should_collect_now,
    trigger_scheduled_reports,
)
from .scheduler import (
    calculate_next_wait_seconds as _calculate_next_wait_seconds,
)
from .storage import BaseStorage, create_storage
from .updates_notifier import (
    UpdatesNotifier,
    configure_mail_provider,
    parse_item_datetime,
    run_notifier,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigWatcher",
    "LibrusCollector",
    "ReportScheduler",
    "calculate_next_wait_seconds",
    "configure_mail_provider",
    "execute_collection_cycle",
    "main",
    "parse_item_datetime",
    "resolve_target_users",
    "run_collector",
    "run_collector_daemon",
    "run_notifier",
    "should_collect_now",
    "sleep_with_config_watch",
    "trigger_scheduled_reports",
]


class LibrusCollector:
    """
    Klasa odpowiedzialna za komunikację z portalem Librus Synergia
    oraz zapisywanie pobranych wiadomości, ogłoszeń i ocen do bazy storage.
    """

    def __init__(
        self,
        config: dict,
        storage: BaseStorage | None = None,
        mail_sender: MailSender | None = None,
    ):
        self.config = config
        self.storage = storage or create_storage(config.get('storage_dir', 'storage'))
        self.mail_sender = mail_sender
        self.parsers: dict[str, Librus] = {}

    def get_or_create_mail_sender(self) -> MailSender | None:
        if self.mail_sender is None:
            try:
                self.mail_sender = configure_mail_provider(self.config)
            except Exception as e:
                logger.warning(f"Nie udało się skonfigurować dostawcy poczty w LibrusCollector: {e}")
                self.mail_sender = None
        return self.mail_sender

    def collect_user(self, user_config: dict) -> dict[str, Any]:
        """Pobiera dane dla wskazanego konta ucznia i synchronizuje z bazą storage."""
        login = str(user_config.get('librus_login', ''))
        name = user_config.get('librus_login_name') or self.storage.get_student_name(login) or login
        step = "inicjalizacja"
        user_key = str(user_config.get('id', login))

        try:
            if user_key not in self.parsers:
                eff_user_config = dict(user_config)
                if 'schedule_retention_days' not in eff_user_config and 'schedule_retention_days' in self.config:
                    eff_user_config['schedule_retention_days'] = self.config['schedule_retention_days']
                self.parsers[user_key] = Librus(eff_user_config, storage=self.storage)
            librus = self.parsers[user_key]

            step = "logowanie"
            max_login_retries = int(self.config.get('login_retries', 2))
            login_retry_delay = float(self.config.get('login_retry_delay_s', 5))
            login_success = False
            last_login_err = None

            for attempt in range(1, max_login_retries + 1):
                try:
                    librus.login()
                    login_success = True
                    break
                except LibrusAuthError as auth_err:
                    logger.error(f"{name} ({login}): Błąd autoryzacji ({auth_err}). Przerywam próby logowania.")
                    last_login_err = auth_err
                    break
                except Exception as log_err:
                    last_login_err = log_err
                    if attempt < max_login_retries:
                        logger.warning(
                            f"{name} ({login}): Próba logowania {attempt}/{max_login_retries} nie powiodła się ({log_err}). "
                            f"Ponawiam próbę za {int(login_retry_delay)}s..."
                        )
                        sleep(login_retry_delay)
                    else:
                        logger.error(
                            f"{name} ({login}): Wszystkie {max_login_retries} próby logowania zakończyły się niepowodzeniem."
                        )

            if not login_success and last_login_err:
                raise last_login_err

            step = "wiadomości"
            sleep(5)
            librus.fetch_messages()

            step = "ogłoszenia"
            sleep(5)
            librus.fetch_notifications()

            if user_config.get('read_grades', True):
                step = "oceny"
                sleep(5)
                librus.fetch_grades()

            if user_config.get('read_timetable', True):
                step = "terminarz"
                sleep(5)
                librus.fetch_timetable()

            if user_config.get('read_schedule', True):
                step = "plan_lekcji"
                sleep(5)
                librus.fetch_schedule()

            if hasattr(self.storage, 'set_student_name'):
                self.storage.set_student_name(login, name)

            librus.save_state()

            if hasattr(self.storage, 'save_last_collect_time'):
                self.storage.save_last_collect_time(login, datetime.now().isoformat())

            new_msgs = librus.get_not_known_messages_and_mark_as_known() if user_config.get('read_messages', True) else []
            new_notifs = librus.get_not_known_notifications_and_mark_as_known()
            new_grades = librus.get_not_known_grades_and_mark_as_known() if user_config.get('read_grades', True) else []

            if hasattr(self.storage, 'clear_last_error'):
                self.storage.clear_last_error(login)

            timetable_count = len(getattr(librus, 'timetable', []))
            schedule_count = len(getattr(librus, 'schedule', []))
            if new_msgs or new_notifs or new_grades:
                logger.info(
                    f"{name} ({login}): Zakończono pobieranie danych ze szkoły. Wykryto nowe wpisy w dzienniku: "
                    f"wiadomości: {len(new_msgs)}, ogłoszenia: {len(new_notifs)}, oceny: {len(new_grades)} "
                    f"(wpisy w terminarzu: {timetable_count}, lekcje w planie: {schedule_count})."
                )
            else:
                logger.info(
                    f"{name} ({login}): Zakończono pobieranie danych ze szkoły. Brak nowych wpisów w dzienniku "
                    f"(wiadomości: 0, ogłoszenia: 0, oceny: 0, wpisy w terminarzu: {timetable_count}, lekcje w planie: {schedule_count})."
                )

            return {
                'success': True,
                'login': login,
                'name': name,
                'user_config': user_config,
                'messages': getattr(librus, 'messages', []),
                'notifications': getattr(librus, 'notifications', []),
                'grades': getattr(librus, 'grades', []),
                'timetable': getattr(librus, 'timetable', []),
                'schedule': getattr(librus, 'schedule', []),
                'new_messages': new_msgs,
                'new_notifications': new_notifs,
                'new_grades': new_grades,
            }
        except (LibrusNetworkError, requests.RequestException) as e:
            logger.warning(f"{name} ({login}): Problem sieciowy na etapie '{step}': {e}")
            return self._handle_collect_error(e, step, login, name, user_config)
        except LibrusAuthError as e:
            logger.error(f"{name} ({login}): Błąd autoryzacji na etapie '{step}': {e}")
            return self._handle_collect_error(e, step, login, name, user_config)
        except LibrusParsingError as e:
            logger.error(f"{name} ({login}): Błąd parsowania HTML na etapie '{step}': {e}", exc_info=True)
            return self._handle_collect_error(e, step, login, name, user_config)
        except Exception as e:
            logger.error(f"{name} ({login}): Błąd podczas pobierania danych na etapie '{step}': {e}", exc_info=True)
            return self._handle_collect_error(e, step, login, name, user_config)

    def _handle_collect_error(
        self, e: Exception, step: str, login: str, name: str, user_config: dict[str, Any]
    ) -> dict[str, Any]:
        tb_str = traceback.format_exc()

        send_errors = self.config.get(
            'send_error_notifications', True
        ) and user_config.get('send_error_notifications', True)

        error_sent = False
        if send_errors:
            try:
                sender = self.get_or_create_mail_sender()
                if sender:
                    cooldown = self.config.get('error_cooldown_s', 3600)
                    error_sent = sender.send_error_notification(
                        user_config=user_config,
                        error=e,
                        step_name=step,
                        details=tb_str,
                        storage=self.storage,
                        cooldown_s=cooldown,
                    )
            except Exception as mail_err:
                logger.error(f"Błąd podczas wysyłania powiadomienia o błędzie dla {login}: {mail_err}")

        if not error_sent and hasattr(self.storage, 'save_last_error'):
            last_err = self.storage.get_last_error(login)
            err_str = f"{type(e).__name__}: {str(e)}"
            if not last_err or last_err.get('error') != err_str:
                self.storage.save_last_error(login, err_str, step=step)

        return {
            'success': False,
            'login': login,
            'name': name,
            'user_config': user_config,
            'error': str(e),
            'step': step,
            'messages': [],
            'notifications': [],
            'grades': [],
            'new_messages': [],
            'new_notifications': [],
            'new_grades': [],
        }

    def collect_all(self, users: list[dict]) -> dict[str, dict[str, Any]]:
        """Pobiera dane dla wszystkich przekazanych kont uczniów."""
        collected = {}
        raw_delay = self.config.get('delay_between_users_s', 10)
        try:
            delay = float(raw_delay)
        except (ValueError, TypeError):
            delay = 10.0

        for idx, u in enumerate(users):
            if idx > 0 and delay > 0:
                logger.info(
                    f"Odczekuję {int(delay) if delay.is_integer() else delay}s przed pobraniem danych dla kolejnego konta..."
                )
                sleep(delay)
            login = str(u.get('librus_login', ''))
            res = self.collect_user(u)
            collected[login] = res
        return collected


def calculate_next_wait_seconds(config: dict, now: datetime | None = None) -> int:
    """Oblicza liczbę sekund do kolejnego cyklu na podstawie harmonogramu pobierania (collection)
    oraz zaplanowanych raportów (schedule.reports), wybierając najbliższe nadchodzące zdarzenie."""
    ref_now = now or datetime.now()
    return _calculate_next_wait_seconds(config, now=ref_now)


def sleep_with_config_watch(
    seconds: int | float,
    config_path: str | None = None,
    poll_interval: float = 5.0,
) -> bool:
    """Śpi przez zadany czas (w sekundach), monitorując czy plik konfiguracji uległ zmianie.

    Zwraca True, jeśli plik został zmodyfikowany (co pozwala natychmiast przeładować ustawienia),
    lub False, jeśli upłynął cały zadany czas oczekiwania.
    """
    return _sleep_with_config_watch(
        seconds=seconds,
        config_path=config_path,
        poll_interval=poll_interval,
        sleep_func=sleep,
    )


def resolve_target_users(
    config: dict,
    storage: BaseStorage,
    user_filter: str | None = None,
    is_simulation: bool = False,
) -> list[dict]:
    """Wyznacza i przygotowuje listę kont uczniów na podstawie konfiguracji, filtrów i stanu storage."""
    users = [dict(u) for u in config.get('librus_users', [])]
    effective_storage_dir = getattr(storage, 'storage_dir', 'storage')

    if user_filter:
        filter_val = str(user_filter).strip().lower()
        matched = [
            u for u in users
            if filter_val in str(u.get('librus_login', '')).lower()
            or filter_val in str(u.get('librus_login_name', '')).lower()
        ]
        if not matched:
            if storage.has_existing_data(user_filter) or storage.get_grades_history(user_filter):
                first_user = users[0] if users else {}
                default_receivers = first_user.get('notification_receivers', [])
                default_one_summary = first_user.get('one_summary_message', config.get('one_summary_message', True))
                default_read_grades = first_user.get('read_grades', config.get('read_grades', True))
                default_read_messages = first_user.get('read_messages', config.get('read_messages', True))
                default_read_timetable = first_user.get('read_timetable', config.get('read_timetable', True))
                default_read_schedule = first_user.get('read_schedule', config.get('read_schedule', True))
                custom_name = storage.get_student_name(user_filter) if hasattr(storage, 'get_student_name') else None
                student_name = custom_name or f"Uczeń ({user_filter})"
                matched = [{
                    'librus_login': str(user_filter),
                    'librus_login_name': student_name,
                    'notification_receivers': default_receivers,
                    'one_summary_message': default_one_summary,
                    'read_grades': default_read_grades,
                    'read_messages': default_read_messages,
                    'read_timetable': default_read_timetable,
                    'read_schedule': default_read_schedule,
                }]
                logger.info(f"Załadowano profil ze storage: '{student_name}'.")
            else:
                logger.error(f"Nie znaleziono użytkownika pasującego do filtru: '{user_filter}' w '{effective_storage_dir}'")
                sys.exit(1)
        users = matched
    elif is_simulation:
        stored_logins = storage.list_stored_logins() if hasattr(storage, 'list_stored_logins') else []
        config_logins = {str(u.get('librus_login')) for u in users}
        has_overlap = any(login in config_logins for login in stored_logins)
        if not has_overlap and stored_logins:
            first_user = users[0] if users else {}
            default_receivers = first_user.get('notification_receivers', [])
            default_one_summary = first_user.get('one_summary_message', config.get('one_summary_message', True))
            default_read_grades = first_user.get('read_grades', config.get('read_grades', True))
            default_read_messages = first_user.get('read_messages', config.get('read_messages', True))
            default_read_timetable = first_user.get('read_timetable', config.get('read_timetable', True))
            default_read_schedule = first_user.get('read_schedule', config.get('read_schedule', True))
            auto_users = []
            for s_login in stored_logins:
                s_name = storage.get_student_name(s_login) or f"Uczeń ({s_login})"
                auto_users.append({
                    'librus_login': str(s_login),
                    'librus_login_name': s_name,
                    'notification_receivers': default_receivers,
                    'one_summary_message': default_one_summary,
                    'read_grades': default_read_grades,
                    'read_messages': default_read_messages,
                    'read_timetable': default_read_timetable,
                    'read_schedule': default_read_schedule,
                })
            logger.info(f"Załadowano profile uczniów odnalezione w '{effective_storage_dir}': {[u['librus_login_name'] for u in auto_users]}")
            users = auto_users

    for idx, user in enumerate(users):
        user['id'] = idx
        user['dry-parse'] = not storage.has_existing_data(str(user.get('librus_login')))

    return users


def execute_collection_cycle(
    collector: LibrusCollector,
    notifier: UpdatesNotifier,
    scheduler: ReportScheduler,
    users: list[dict],
    storage: BaseStorage,
    config_path: str = 'config.yaml',
    effective_storage_dir: str = 'storage',
    days: int | None = None,
    hours: int | None = None,
    dry_run: bool = False,
    output_html: str | None = None,
    offline: bool = False,
    sync_only: bool = False,
    summary: bool | None = None,
    schedule_day_offset: int | None = None,
    work_in_loop: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Wykonuje pojedynczy przebieg cyklu zbierania i powiadomień."""
    ref_now = now or datetime.now()
    collected_data: dict[str, Any] = {}

    should_collect = True
    if work_in_loop and not offline:
        should_collect = scheduler.should_collect_now(users, now=ref_now)

    if should_collect:
        if not offline:
            collected_data = collector.collect_all(users)
        else:
            logger.info(f"Tryb OFFLINE: pomijam połączenie z Librusem, odczytuję dane ze storage ({effective_storage_dir})...")

        if not sync_only:
            for user_config in users:
                login = str(user_config.get('librus_login', ''))
                c_item = collected_data.get(login, {})
                if not offline and c_item.get('success') is False:
                    logger.warning(
                        f"{user_config.get('librus_login_name', login)} ({login}): "
                        "Pominięto generowanie powiadomień o nowościach, ponieważ pobieranie danych ze szkoły zakończyło się błędem."
                    )
                    continue

                notifier.process_user_notifications(
                    user_config=user_config,
                    all_messages=c_item.get('messages'),
                    all_notifications=c_item.get('notifications'),
                    all_grades=c_item.get('grades'),
                    new_messages=c_item.get('new_messages'),
                    new_notifications=c_item.get('new_notifications'),
                    new_grades=c_item.get('new_grades'),
                    days=days,
                    hours=hours,
                    dry_run=dry_run,
                    output_html=output_html,
                    total_users=len(users),
                    summary=summary,
                    schedule_day_offset=schedule_day_offset,
                )
                if user_config.get('dry-parse'):
                    user_config['dry-parse'] = False

    if not offline and not sync_only:
        scheduler.trigger_scheduled_reports(
            config_path=config_path,
            users=users,
            effective_storage_dir=effective_storage_dir,
            now=ref_now,
        )

    return {
        'should_collect': should_collect,
        'collected_data': collected_data,
    }


def run_collector_daemon(
    collector: LibrusCollector,
    notifier: UpdatesNotifier,
    scheduler: ReportScheduler,
    users: list[dict],
    storage: BaseStorage,
    config: dict,
    config_path: str = 'config.yaml',
    effective_storage_dir: str = 'storage',
    sync_only: bool = False,
    summary: bool | None = None,
    schedule_day_offset: int | None = None,
) -> None:
    """Pętla demona kolektora z automatycznym przeładowaniem po zmianie konfiguracji."""
    current_users = users
    current_config = config

    while True:
        try:
            execute_collection_cycle(
                collector=collector,
                notifier=notifier,
                scheduler=scheduler,
                users=current_users,
                storage=storage,
                config_path=config_path,
                effective_storage_dir=effective_storage_dir,
                offline=False,
                sync_only=sync_only,
                summary=summary,
                schedule_day_offset=schedule_day_offset,
                work_in_loop=True,
            )
        except Exception as cycle_err:
            logger.error(f"Nieoczekiwany błąd w cyklu kolektora: {cycle_err}", exc_info=True)

        sleep_s = scheduler.calculate_next_wait_seconds(now=datetime.now())
        logger.info(f"Czekam przez {sleep_s} sekund do kolejnego sprawdzenia")
        try:
            config_changed = sleep_with_config_watch(sleep_s, config_path=config_path)
            if config_changed:
                logger.info(
                    f"Wykryto zmianę pliku konfiguracji '{config_path}'. "
                    "Przeładowuję konfigurację i odświeżam harmonogram..."
                )
                try:
                    current_config = read_config(config_path)
                    new_users = current_config.get('librus_users', [])
                    for idx, user in enumerate(new_users):
                        user['id'] = idx
                        user['dry-parse'] = not storage.has_existing_data(str(user.get('librus_login')))
                    current_users = new_users
                    collector.config = current_config
                    notifier.config = current_config
                    scheduler.config = current_config
                except Exception as reload_err:
                    logger.warning(
                        f"Błąd podczas przeładowywania pliku konfiguracji '{config_path}': {reload_err}",
                        exc_info=True,
                    )
                continue
        except KeyboardInterrupt:
            logger.info("Zatrzymano działanie usługi (Ctrl+C).")
            break


def run_collector(
    config_path: str = 'config.yaml',
    storage_dir: str | None = None,
    days: int | None = None,
    hours: int | None = None,
    dry_run: bool = False,
    output_html: str | None = None,
    user_filter: str | None = None,
    offline: bool = False,
    sync_only: bool = False,
    work_in_loop: bool | None = None,
    once: bool = False,
    loop: bool = False,
    summary: bool | None = None,
    schedule_day_offset: int | None = None,
):
    """
    Główna usługa pobierająca (collector):
    - W trybie sieciowym pobiera dane z Librusa i zapisuje je do bazy storage/.
    - Jeśli sync_only=False (domyślnie), przekazuje zebrane dane do UpdatesNotifier
    w celu wysyłki powiadomień e-mail, podglądu lub zapisu do pliku HTML.
    """
    config = read_config(config_path)

    effective_storage_dir = storage_dir or config.get('storage_dir', 'storage')
    config['storage_dir'] = effective_storage_dir
    storage = create_storage(effective_storage_dir)

    is_simulation = dry_run or bool(output_html) or days is not None or hours is not None or offline
    if is_simulation or once:
        effective_work_in_loop = False
    elif loop:
        effective_work_in_loop = True
    elif work_in_loop is not None:
        effective_work_in_loop = work_in_loop
    else:
        effective_work_in_loop = config.get('work_in_loop', True)

    logger.info(f"Tryb pracy w pętli (work_in_loop): {effective_work_in_loop}")

    users = resolve_target_users(
        config=config,
        storage=storage,
        user_filter=user_filter,
        is_simulation=is_simulation,
    )

    collector = LibrusCollector(config, storage=storage)
    notifier = UpdatesNotifier(config, storage=storage)
    scheduler = ReportScheduler(config, storage=storage)

    if effective_work_in_loop:
        run_collector_daemon(
            collector=collector,
            notifier=notifier,
            scheduler=scheduler,
            users=users,
            storage=storage,
            config=config,
            config_path=config_path,
            effective_storage_dir=effective_storage_dir,
            sync_only=sync_only,
            summary=summary,
            schedule_day_offset=schedule_day_offset,
        )
    else:
        execute_collection_cycle(
            collector=collector,
            notifier=notifier,
            scheduler=scheduler,
            users=users,
            storage=storage,
            config_path=config_path,
            effective_storage_dir=effective_storage_dir,
            days=days,
            hours=hours,
            dry_run=dry_run,
            output_html=output_html,
            offline=offline,
            sync_only=sync_only,
            summary=summary,
            schedule_day_offset=schedule_day_offset,
            work_in_loop=False,
        )
        if is_simulation:
            logger.info("Zakończono symulację / pojedynczy przebieg.")
        else:
            logger.info("Zakończono pojedynczy przebieg (work_in_loop: false). Koniec pracy.")


def main():
    """Punkt wejścia CLI dla usługi collector."""
    parser = argparse.ArgumentParser(
        description="Librus2mail Collector - Pobieranie danych z Librus Synergia i synchronizacja z bazą storage."
    )
    parser.add_argument(
        '-c', '--config',
        dest='config_opt',
        default=None,
        help="Ścieżka do pliku konfiguracyjnego YAML"
    )
    parser.add_argument(
        '-s', '--storage-dir',
        dest='storage_dir',
        default=None,
        help="Ścieżka do katalogu pamięci stanu (nadpisuje config.yaml)"
    )
    parser.add_argument(
        '-u', '--user',
        dest='user_filter',
        default=None,
        help="Filtruj wykonanie tylko do wskazanego konta ucznia"
    )
    parser.add_argument(
        '--sync-only', '--collect-only',
        dest='sync_only',
        action='store_true',
        help="Tylko pobierz i zsynchronizuj dane z Librusem do storage (bez wysyłki powiadomień)"
    )
    parser.add_argument(
        '-d', '--days',
        dest='days',
        type=int,
        default=None,
        help="Okres w dniach dla powiadomienia"
    )
    parser.add_argument(
        '--hours',
        dest='hours',
        type=int,
        default=None,
        help="Okres w godzinach dla powiadomienia"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Tryb symulacji: podgląd w konsoli bez wysyłania maili"
    )
    parser.add_argument(
        '-o', '--output', '--save-html',
        dest='output_html',
        default=None,
        help="Zapisz powiadomienie jako plik HTML pod wskazaną ścieżką"
    )
    parser.add_argument(
        '--offline',
        action='store_true',
        help="Tryb offline: pomija połączenie z Librusem i używa danych ze storage"
    )
    parser.add_argument(
        '--once', '--no-loop',
        dest='once',
        action='store_true',
        help="Wymuś pojedyncze wykonanie i zakończenie procesu (nadpisuje work_in_loop z konfiguracji)"
    )
    parser.add_argument(
        '--loop',
        dest='loop',
        action='store_true',
        help="Wymuś działanie w nieskończonej pętli z interwałem wait_time_s (nadpisuje work_in_loop z konfiguracji)"
    )
    parser.add_argument(
        '--summary',
        dest='summary',
        action='store_true',
        default=None,
        help="Wymuś wysłanie 1 zbiorczego e-maila ze wszystkimi nowościami zamiast osobnych wiadomości, ogłoszeń i ocen"
    )
    parser.add_argument(
        '--schedule-offset', '--schedule-day-offset',
        dest='schedule_day_offset',
        type=int,
        default=None,
        help="Przesunięcie dnia planu lekcji w powiadomieniu (w dniach, domyślnie: 1, czyli następny dzień nauki; 0 = bieżący dzień raportu)"
    )
    parser.add_argument(
        'config',
        nargs='?',
        default=None,
        help="Ścieżka do pliku konfiguracyjnego YAML (domyślnie: config.yaml)"
    )
    args = parser.parse_args()
    config_path = args.config_opt or args.config or 'config.yaml'
    setup_logging()
    run_collector(
        config_path=config_path,
        storage_dir=args.storage_dir,
        days=args.days,
        hours=args.hours,
        dry_run=args.dry_run,
        output_html=args.output_html,
        user_filter=args.user_filter,
        offline=args.offline,
        sync_only=args.sync_only,
        once=args.once,
        loop=args.loop,
        summary=args.summary,
        schedule_day_offset=args.schedule_day_offset,
    )


if __name__ == '__main__':
    main()
