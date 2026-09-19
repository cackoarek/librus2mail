#!/usr/bin/env python3
"""
Zintegrowany potok: LibrusCollector + UpdatesNotifier.
Pobiera świeże dane z portalu Librus Synergia do bazy storage/,
a następnie natychmiast generuje i wysyła powiadomienia e-mail do rodziców.
Może działać w trybie ciągłym (demon) lub pojedynczego strzału (cron).
"""

import argparse
import logging

from .base_logger import setup_logging
from .librus_collector import run_collector
from .progress_report import run_progress_reports
from .updates_notifier import configure_mail_provider, run_notifier

logger = logging.getLogger(__name__)

__all__ = [
    "configure_mail_provider",
    "main",
    "run_collector",
    "run_notifier",
    "run_pipeline",
    "run_progress_reports",
]


def run_pipeline(
    config_path: str = 'config.yaml',
    storage_dir: str | None = None,
    user_filter: str | None = None,
    days: int | None = None,
    hours: int | None = None,
    dry_run: bool = False,
    output_html: str | None = None,
    offline: bool = False,
    collect_only: bool = False,
    notify_only: bool = False,
    report: bool = False,
    force: bool = False,
    fetch: bool = False,
    work_in_loop: bool | None = None,
    once: bool = False,
    loop: bool = False,
):
    """
    Główna funkcja wykonawcza potoku collect-and-notify:
    - Jeśli wybrano --report: uruchamia moduł 3 (raport postępów)
    - Jeśli wybrano --collect-only: uruchamia tylko moduł 1 (pobieranie z Librusa do storage)
    - Jeśli wybrano --notify-only: uruchamia tylko moduł 2 (powiadomienia bieżące)
    - Domyślnie: uruchamia pełny cykl Collector -> Notifier (w pętli lub jednorazowo)
    """
    if report:
        logger.info("Uruchamiam Moduł 3: Raport postępów ucznia (progress_report)...")
        run_progress_reports(
            config_path=config_path,
            storage_dir=storage_dir,
            user_filter=user_filter,
            days=days,
            dry_run=dry_run,
            save_html=output_html,
            fetch_live=fetch,
            force=force,
        )
        return

    if notify_only:
        logger.info("Uruchamiam Moduł 2: Powiadomienia bieżące (updates_notifier)...")
        run_notifier(
            config_path=config_path,
            storage_dir=storage_dir,
            days=days,
            hours=hours,
            dry_run=dry_run,
            output_html=output_html,
            user_filter=user_filter,
            offline=offline,
        )
        return

    if collect_only:
        logger.info("Uruchamiam Moduł 1: Pobieranie danych (collector-only)...")
        run_collector(
            config_path=config_path,
            storage_dir=storage_dir,
            user_filter=user_filter,
            sync_only=True,
            offline=offline,
            work_in_loop=work_in_loop,
            once=once,
            loop=loop,
        )
        return

    # Domyślny potok: Collector -> UpdatesNotifier (zgodny z demonem monitoringu)
    logger.info("Uruchamiam potok monitoringu (Collector -> UpdatesNotifier)...")
    run_collector(
        config_path=config_path,
        storage_dir=storage_dir,
        days=days,
        hours=hours,
        dry_run=dry_run,
        output_html=output_html,
        user_filter=user_filter,
        offline=offline,
        sync_only=False,
        work_in_loop=work_in_loop,
        once=once,
        loop=loop,
    )


def main():
    """Punkt wejścia CLI dla potoku collect_and_notify."""
    parser = argparse.ArgumentParser(
        description="Librus2mail Collect & Notify - Pobieranie danych z Librus Synergia i wysyłka powiadomień."
    )

    # Przełączniki trybu działania (wzajemnie niezależne moduły)
    mode_group = parser.add_argument_group("Tryby modułowe")
    mode_group.add_argument(
        '--collect-only', '--sync-only',
        dest='collect_only',
        action='store_true',
        help="Uruchom tylko Moduł 1 (Collector): pobierz dane ze szkoły do bazy storage bez wysyłania powiadomień"
    )
    mode_group.add_argument(
        '--notify-only',
        dest='notify_only',
        action='store_true',
        help="Uruchom tylko Moduł 2 (Notifier): wygeneruj bieżące powiadomienia z bazy storage (e-mail / terminal / HTML)"
    )
    mode_group.add_argument(
        '--report',
        action='store_true',
        help="Uruchom Moduł 3 (Progress Report): wygeneruj długoterminowy raport analityczny postępów dziecka"
    )

    # Opcje wspólne i parametry
    parser.add_argument(
        '-c', '--config',
        dest='config_opt',
        default=None,
        help="Ścieżka do pliku konfiguracyjnego YAML (np. -c /etc/librus/config.yaml)"
    )
    parser.add_argument(
        '-s', '--storage-dir',
        dest='storage_dir',
        default=None,
        help="Ścieżka do katalogu pamięci stanu (nadpisuje storage_dir z config.yaml)"
    )
    parser.add_argument(
        '-u', '--user',
        dest='user_filter',
        default=None,
        help="Filtruj wykonanie tylko do wskazanego konta ucznia (login Librus lub nazwisko)"
    )
    parser.add_argument(
        '-d', '--days',
        dest='days',
        type=int,
        default=None,
        help="Okres w dniach (dla powiadomienia lub raportu postępów)"
    )
    parser.add_argument(
        '--hours',
        dest='hours',
        type=int,
        default=None,
        help="Okres w godzinach (dla powiadomienia bieżącego)"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Tryb symulacji: wyświetla podgląd w terminalu bez wysyłania e-maili i bez modyfikacji bazy"
    )
    parser.add_argument(
        '-o', '--output', '--save-html',
        dest='output_html',
        default=None,
        help="Zapisz powiadomienie lub raport jako samodzielny plik HTML do podglądu w przeglądarce"
    )
    parser.add_argument(
        '--offline',
        action='store_true',
        help="Tryb offline: odczytuje dane wyłącznie ze wskazanego katalogu storage bez logowania do Librusa"
    )
    parser.add_argument(
        '--fetch',
        action='store_true',
        help="Wymusza pobranie świeżych ocen przez sieć (dla trybu --report)"
    )
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help="Wymusza generowanie raportu nawet przy braku nowych ocen (dla trybu --report)"
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
    run_pipeline(
        config_path=config_path,
        storage_dir=args.storage_dir,
        user_filter=args.user_filter,
        days=args.days,
        hours=args.hours,
        dry_run=args.dry_run,
        output_html=args.output_html,
        offline=args.offline,
        collect_only=args.collect_only,
        notify_only=args.notify_only,
        report=args.report,
        force=args.force,
        fetch=args.fetch,
        once=args.once,
        loop=args.loop,
    )


if __name__ == '__main__':
    main()
