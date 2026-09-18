#!/usr/bin/env python3
import logging
import sys
import traceback
from time import sleep

from .base_logger import setup_logging
from .config import read_config
from .gmail_sender import GmailSender
from .librus import Librus
from .mail_sender import MailSender
from .smtp_sender import SmtpSender
from .storage import create_storage

logger = logging.getLogger(__name__)


def configure_mail_provider(config: dict) -> MailSender:
    mail_config = config['mail']
    if mail_config['use_gmail']:
        return GmailSender(mail_config)
    else:
        return SmtpSender(mail_config)


def run_collector(config_path: str = 'config.yaml'):
    """
    Główna usługa pobierająca (collector / monitor):
    - loguje się do Librus Synergia,
    - monitoruje skrzynkę wiadomości, ogłoszenia i oceny,
    - wysyła bieżące alerty e-mail o nowych wpisach,
    - zapisuje pełną historię ocen i stan do storage (dla modułu progress_report.py).
    """
    try:
        config = read_config(config_path)
    except FileNotFoundError:
        sys.exit(1)

    storage_dir = config.get('storage_dir', 'storage')
    storage = create_storage(storage_dir=storage_dir)

    work_in_loop = config.get('work-in-loop', config.get('work_in_loop', True))
    logger.info(f"Tryb pracy w pętli (work-in-loop): {work_in_loop}")

    for idx, user in enumerate(config['librus_users']):
        user['id'] = idx
        # Jeśli dane z poprzednich uruchomień już istnieją w plikach, pomijamy dry-parse (znamy już historię)
        if storage.has_existing_data(str(user.get('librus_login'))):
            user['dry-parse'] = False
        else:
            user['dry-parse'] = user.get('do_not_send_first_parse', True)

    mail_sender = configure_mail_provider(config)

    librus_parsers: dict[int, Librus] = {}

    # pętla sprawdzania danych
    while True:
        # dla każdego użytkownika przygotowujemy jego mini-konfigurację
        for user_config in config['librus_users']:
            checked = False
            step = "inicjalizacja"

            # próba pobrania danych z Librusa
            try:
                librus_parsers.setdefault(user_config['id'], Librus(user_config, storage=storage))
                librus = librus_parsers.get(user_config['id'])
                step = "logowanie"
                librus.login()
                step = "wiadomości"
                sleep(5)
                librus.fetch_messages()
                step = "ogłoszenia"
                sleep(5)
                librus.fetch_notifications()
                if user_config.get('read_grades', False):
                    step = "oceny"
                    sleep(5)
                    librus.fetch_grades()
                checked = True
            except Exception as e:
                logger.error(
                    f"Błąd w pętli zbierania danych dla {user_config['librus_login']} na etapie '{step}': {e}")
                checked = False

                send_error_notifications = config.get(
                    'send_error_notifications', True
                ) and user_config.get('send_error_notifications', True)

                if send_error_notifications:
                    cooldown = config.get('error_cooldown_s', 3600)
                    tb_str = traceback.format_exc()
                    mail_sender.send_error_notification(
                        user_config=user_config,
                        error=e,
                        step_name=step,
                        details=tb_str,
                        storage=storage,
                        cooldown_s=cooldown
                    )

            # czy udało się pobrać dane z Librusa?
            if checked:
                # Po udanym pobraniu danych czyścimy stan błędu dla tego konta
                if storage:
                    storage.clear_last_error(str(user_config['librus_login']))
                # aktualna lista wszystkich wiadomości
                new_messages = librus.get_not_known_messages_and_mark_as_known()
                # aktualna lista wszystkich ogłoszeń
                new_notifications = librus.get_not_known_notifications_and_mark_as_known()
                # aktualna lista wszystkich ocen (jeśli włączone)
                new_grades = librus.get_not_known_grades_and_mark_as_known() if user_config.get('read_grades', False) else []

                if not user_config['dry-parse']:
                    one_summary = user_config.get('one_summary_message', False)

                    if one_summary:
                        has_any_new = bool(new_messages or new_notifications or new_grades)
                        if has_any_new:
                            logger.info(
                                f"Pojawiły się nowe wpisy (wiadomości: {len(new_messages)}, ogłoszenia: {len(new_notifications)}, oceny: {len(new_grades)}). Wysyłam zbiorcze podsumowanie."
                            )
                            mail_sender.send_mail_with_summary(user_config, new_messages, new_notifications, new_grades)
                        else:
                            logger.info("Brak nowych wiadomości, ogłoszeń i ocen")
                    else:
                        if len(new_messages):
                            logger.info("Pojawiły się nowe wiadomości")
                            mail_sender.send_mail_with_messages(user_config, new_messages)
                        else:
                            logger.info("Brak nowych wiadomości")

                        if len(new_notifications):
                            logger.info("Pojawiły się nowe powiadomienia")
                            mail_sender.send_mail_with_notifications(user_config, new_notifications)
                        else:
                            logger.info("Brak nowych ogłoszeń")

                        if user_config.get('read_grades', False):
                            if len(new_grades):
                                logger.info("Pojawiły się nowe oceny")
                                mail_sender.send_mail_with_grades(user_config, new_grades)
                            else:
                                logger.info("Brak nowych ocen")

                else:
                    logger.info("Zebrano dane jako podstawę. Kolejne wpisy na Librus będą wysyłane mailem.")
                    user_config['dry-parse'] = False

        if not work_in_loop:
            logger.info("Zakończono pojedynczy przebieg (work-in-loop: false). Koniec pracy.")
            break

        logger.info(f"Czekam przez {config['wait_time_s']} sekund")
        sleep(config['wait_time_s'])


def main():
    """Główny punkt wejścia CLI dla usługi monitorującej."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Librus2mail - Usługa ciągłego monitorowania e-dziennika Librus Synergia i wysyłki powiadomień e-mail."
    )
    parser.add_argument(
        'config',
        nargs='?',
        default='config.yaml',
        help="Ścieżka do pliku konfiguracyjnego YAML (domyślnie: config.yaml)"
    )
    args = parser.parse_args()
    setup_logging()
    run_collector(args.config)


if __name__ == '__main__':
    main()
