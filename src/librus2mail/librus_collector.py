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

from .base_logger import setup_logging
from .config import read_config
from .librus import Librus
from .mail_sender import MailSender
from .storage import BaseStorage, create_storage
from .updates_notifier import (
    UpdatesNotifier,
    configure_mail_provider,
    parse_item_datetime,
    print_cli_summary,
    run_notifier,
)

logger = logging.getLogger(__name__)

# Alias wsteczny dla testów i skryptów
print_collector_cli_summary = print_cli_summary

__all__ = [
    "LibrusCollector",
    "configure_mail_provider",
    "main",
    "parse_item_datetime",
    "print_collector_cli_summary",
    "run_collector",
    "run_notifier",
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
                self.parsers[user_key] = Librus(user_config, storage=self.storage)
            librus = self.parsers[user_key]

            step = "logowanie"
            librus.login()

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

            if new_msgs or new_notifs or new_grades:
                logger.info(
                    f"{name} ({login}): Zakończono pobieranie danych ze szkoły. Wykryto nowe wpisy w dzienniku: "
                    f"wiadomości: {len(new_msgs)}, ogłoszenia: {len(new_notifs)}, oceny: {len(new_grades)}."
                )
            else:
                logger.info(
                    f"{name} ({login}): Zakończono pobieranie danych ze szkoły. Brak nowych wpisów w dzienniku "
                    f"(wiadomości: 0, ogłoszenia: 0, oceny: 0)."
                )

            return {
                'success': True,
                'login': login,
                'name': name,
                'user_config': user_config,
                'messages': getattr(librus, 'messages', []),
                'notifications': getattr(librus, 'notifications', []),
                'grades': getattr(librus, 'grades', []),
                'new_messages': new_msgs,
                'new_notifications': new_notifs,
                'new_grades': new_grades,
            }
        except Exception as e:
            logger.error(f"Błąd podczas pobierania danych dla {login} na etapie '{step}': {e}")
            tb_str = traceback.format_exc()

            send_errors = self.config.get(
                'send_error_notifications', self.config.get('end_error_notifications', True)
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
        raw_delay = self.config.get('delay_between_users_s', self.config.get('user_delay_s', 3))
        try:
            delay = float(raw_delay)
        except (ValueError, TypeError):
            delay = 3.0

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

    # Ustalenie trybu pętli
    is_simulation = dry_run or bool(output_html) or days is not None or hours is not None or offline
    if is_simulation or once:
        effective_work_in_loop = False
    elif loop:
        effective_work_in_loop = True
    elif work_in_loop is not None:
        effective_work_in_loop = work_in_loop
    else:
        effective_work_in_loop = config.get('work-in-loop', config.get('work_in_loop', True))

    logger.info(f"Tryb pracy w pętli (work-in-loop): {effective_work_in_loop}")

    # Lista użytkowników
    users = config.get('librus_users', [])
    if user_filter:
        filter_val = str(user_filter).strip().lower()
        matched = [
            u for u in users
            if filter_val in str(u.get('librus_login', '')).lower()
            or filter_val in str(u.get('librus_login_name', '')).lower()
        ]
        if not matched:
            if storage.has_existing_data(user_filter) or storage.get_grades_history(user_filter):
                default_receivers = users[0].get('notification_receivers', []) if users else []
                custom_name = storage.get_student_name(user_filter) if hasattr(storage, 'get_student_name') else None
                student_name = custom_name or f"Uczeń ({user_filter})"
                matched = [{
                    'librus_login': str(user_filter),
                    'librus_login_name': student_name,
                    'notification_receivers': default_receivers,
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
            default_receivers = users[0].get('notification_receivers', []) if users else []
            auto_users = []
            for s_login in stored_logins:
                s_name = storage.get_student_name(s_login) or f"Uczeń ({s_login})"
                auto_users.append({
                    'librus_login': str(s_login),
                    'librus_login_name': s_name,
                    'notification_receivers': default_receivers,
                })
            logger.info(f"Załadowano profile uczniów odnalezione w '{effective_storage_dir}': {[u['librus_login_name'] for u in auto_users]}")
            users = auto_users

    for idx, user in enumerate(users):
        user['id'] = idx
        if storage.has_existing_data(str(user.get('librus_login'))):
            user['dry-parse'] = False
        else:
            user['dry-parse'] = user.get('do_not_send_first_parse', True)

    collector = LibrusCollector(config, storage=storage)
    notifier = UpdatesNotifier(config, storage=storage)

    while True:
        collected_data = {}

        # 1. Pobieranie danych (chyba że tryb offline)
        if not offline:
            collected_data = collector.collect_all(users)
        else:
            logger.info(f"Tryb OFFLINE: pomijam połączenie z Librusem, odczytuję dane ze storage ({effective_storage_dir})...")

        # 2. Powiadomienia (chyba że sync_only)
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
                )
                if user_config.get('dry-parse'):
                    user_config['dry-parse'] = False

        if not effective_work_in_loop:
            if is_simulation:
                logger.info("Zakończono symulację / pojedynczy przebieg.")
            else:
                logger.info("Zakończono pojedynczy przebieg (work-in-loop: false). Koniec pracy.")
            break

        logger.info(f"Czekam przez {config['wait_time_s']} sekund")
        try:
            sleep(config['wait_time_s'])
        except KeyboardInterrupt:
            logger.info("Zatrzymano działanie usługi (Ctrl+C).")
            break


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
        help="Wymuś pojedyncze wykonanie i zakończenie procesu (nadpisuje work-in-loop z konfiguracji)"
    )
    parser.add_argument(
        '--loop',
        dest='loop',
        action='store_true',
        help="Wymuś działanie w nieskończonej pętli z interwałem wait_time_s (nadpisuje work-in-loop z konfiguracji)"
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
    )


if __name__ == '__main__':
    main()
