#!/usr/bin/env python3
import argparse
import logging
import re
import sys
from datetime import datetime, timedelta
from time import sleep

from .base_logger import setup_logging
from .config import read_config
from .librus import Librus
from .librus_collector import configure_mail_provider
from .mail_sender import (
    MailSender,
    render_standalone_html,
    resolve_output_path,
)
from .progress_analyzer import ProgressAnalyzer
from .storage import create_storage

logger = logging.getLogger(__name__)



def parse_args():
    parser = argparse.ArgumentParser(
        description="Librus2mail - Moduł raportowania i analizy postępów dziecka w nauce (na podstawie danych ze storage)."
    )
    parser.add_argument(
        '-c', '--config',
        dest='config_path',
        default='config.yaml',
        help='Ścieżka do pliku konfiguracyjnego YAML (domyślnie: config.yaml)'
    )
    parser.add_argument(
        '-s', '--storage-dir',
        dest='storage_dir',
        default=None,
        help='Ścieżka do katalogu pamięci stanu i bazy ocen (nadpisuje ustawienie z config.yaml)'
    )
    parser.add_argument(
        '-u', '--user',
        dest='user_filter',
        default=None,
        help='Filtruj wykonanie tylko do konkretnego loginu lub nazwy ucznia'
    )
    parser.add_argument(
        '-d', '--days',
        dest='days',
        type=int,
        default=None,
        help='Wymuś analizę za ostatnie N dni (nadpisuje datę ostatniego wysłanego raportu)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Tryb symulacji: generuje analizę i wyświetla podsumowanie w konsoli bez wysyłania e-maila'
    )
    parser.add_argument(
        '-o', '--output', '--save-html',
        dest='output_html',
        default=None,
        help='Zapisz wygenerowany raport jako plik HTML pod wskazaną ścieżką (pomija wysyłkę e-mail i nie aktualizuje daty ostatniego raportu)'
    )
    parser.add_argument(
        '--fetch',
        action='store_true',
        help='Opcjonalnie: połącz się z Librusem i pobierz najświeższe oceny przed analizą (domyślnie raport bazuje wyłącznie na lokalnych danych ze storage)'
    )
    parser.add_argument(
        '-f', '--force',
        action='store_true',
        help='Wymuś wysłanie raportu nawet jeśli w danym okresie uczeń nie otrzymał nowych ocen'
    )
    return parser.parse_args()


def print_cli_summary(user_name: str, login: str, analysis: dict):
    print("\n" + "=" * 75)
    print(f"📊 RAPORT POSTĘPÓW: {user_name} (Konto: {login})")
    print(f"🗓️  Okres analizy: {analysis['period_start_str']} – {analysis['period_end_str']}")
    print("=" * 75)

    overall = f"{analysis['overall_avg']:.2f}" if analysis['overall_avg'] is not None else "—"
    period = f"{analysis['period_avg']:.2f}" if analysis['period_avg'] is not None else "—"
    print(f"📈 Średnia ogólna: {overall}")
    print(f"⏱️  Średnia w okresie: {period}")
    print(f"📝 Ocen w okresie: {analysis['period_grades_count']} (łącznie zarejestrowanych: {analysis['total_grades_count']})")
    print(f"⭐ Aktywność: +{analysis['activity_pluses']} / -{analysis['activity_minuses']} | Nieprzygotowania: {analysis['unprepared_count']}")

    # Porównanie z poprzednim okresem (Dynamika i Forma)
    pc = analysis.get('period_comparison')
    if pc and pc.get('enabled'):
        print(f"\n📈 Dynamika i forma ucznia: {pc['badge_icon']} {pc['badge_text']}")
        print(f"  🗓️  Porównanie: {pc['period_start_str']}–{pc['period_end_str']} vs {pc['prev_period_start_str']}–{pc['prev_period_end_str']}")
        print(f"  💡 {pc['headline']}")
        if pc.get('has_prev_data'):
            p_avg = f"{pc['prev_avg']:.2f}" if pc['prev_avg'] is not None else "—"
            c_avg = f"{pc['current_avg']:.2f}" if pc['current_avg'] is not None else "—"
            diff_str = f"{pc['avg_diff']:+.2f}" if pc['avg_diff'] is not None else "—"
            print(f"  • Średnia w okresie:  {p_avg} ➔ {c_avg} ({diff_str} pkt)")
            print(f"  • Liczba ocen:        {pc['prev_count']} ➔ {pc['current_count']} ({pc['count_diff']:+d})")
            print(f"  • Oceny 5–6 / 1–2:    {pc['prev_high_count']} / {pc['prev_low_count']} ➔ {pc['current_high_count']} / {pc['current_low_count']}")
            if pc.get('overall_shift') is not None and pc.get('overall_before_period') is not None:
                print(f"  • Średnia ogólna:     {pc['overall_before_period']:.2f} ➔ {pc['overall_after_period']:.2f} ({pc['overall_shift']:+.2f} pkt)")
        if pc.get('takeaways'):
            for t in pc['takeaways']:
                clean_t = re.sub(r'<[^>]+>', '', t)
                print(f"    - {clean_t}")

    # Symulator Czerwonego Paska
    hr = analysis.get('honor_roll', {})
    if hr.get('message'):
        print(f"\n🏅 Świadectwo z wyróżnieniem: {hr['message']}")

    # Sukcesy i Uwagi
    if analysis.get('insights_strengths'):
        print("\n🌟 Sukcesy:")
        for s in analysis['insights_strengths']:
            clean = re.sub(r'<[^>]+>', '', s)
            print(f"  • {clean}")

    if analysis.get('insights_warnings'):
        print("\n⚠️  Uwagi i obszary do poprawy:")
        for w in analysis['insights_warnings']:
            clean = re.sub(r'<[^>]+>', '', w)
            print(f"  • {clean}")

    # Szanse i Zagrożenia na granicy ocen
    b_opps = analysis.get('borderline_opportunities', [])
    b_risks = analysis.get('borderline_risks', [])
    if b_opps or b_risks:
        print("\n🎯 Analiza progów ocen (Kalkulator szans i zagrożeń):")
        for o in b_opps:
            print(f"  [SZANSA] {o['subject']}: {o['advice']}")
        for r in b_risks:
            print(f"  [RYZYKO] {r['subject']}: {r['warning']}")

    # Styl nauki i wpływ wag
    ls = analysis.get('learning_style', {})
    wi = analysis.get('weight_impact', {})
    if ls.get('exams_avg') is not None or wi.get('arithmetic_avg') is not None:
        print("\n🔍 Styl nauki i wpływ wag ocen:")
        if ls.get('exams_avg') is not None and ls.get('daily_avg') is not None:
            print(f"  • Sprawdziany (waga >= 2): {ls['exams_avg']:.2f} ({ls['exams_count']} ocen) | Praca bieżąca (waga 1): {ls['daily_avg']:.2f} ({ls['daily_count']} ocen)")
            print(f"    Diagnoza: {ls['diagnosis']}")
        if wi.get('description'):
            print(f"  • Efekt wagowy: {wi['description']}")

    # Ciche przedmioty
    dormant = analysis.get('dormant_subjects', [])
    if dormant:
        active_dormant = [d for d in dormant if d.get('days_ago')]
        if active_dormant:
            print("\n⏱️  Ciche przedmioty (brak ocen od >= 30 dni):")
            for d in active_dormant[:3]:
                print(f"  • {d['subject']}: ostatnia ocena {d['last_date_str']} ({d['days_ago']} dni temu)")

    print("\n📚 Podsumowanie przedmiotów:")
    print(f"{'Przedmiot':<25} | {'Śr. okres':<10} | {'Śr. całk.':<10} | {'Trend':<14} | {'Prognoza':<15}")
    print("-" * 82)
    for s in analysis['subjects']:
        subj = s['subject'][:24]
        so = f"{s['overall_avg']:.2f}" if s['overall_avg'] is not None else "—"
        sp = f"{s['period_avg']:.2f}" if s['period_avg'] is not None else "—"
        tr = s['trend_label']
        pr = s['predicted_grade']
        print(f"{subj:<25} | {sp:<10} | {so:<10} | {tr:<14} | {pr:<15}")

    if analysis.get('period_grades'):
        print(f"\n📝 Nowe oceny w okresie ({len(analysis['period_grades'])}):")
        for g in analysis['period_grades']:
            print(f"  • {g['subject']}: {g['grade']} (waga: {g.get('weight', '-')}, data: {g.get('date', '-')}, kat: {g.get('category', '-')})")

    # Przewodnik rodzica (Legenda)
    legend = analysis.get('legend', {})
    if legend:
        print("\n📖 Przewodnik rodzica (Jak czytać wskaźniki):")
        print(f"  • Progi ocen: {legend.get('thresholds')}")
        print(f"  • Trendy: {legend.get('trends')}")
        print(f"  • Styl nauki: {legend.get('learning_style')}")
        print(f"  • Wagi ocen: {legend.get('weight_impact')}")

    print("=" * 75 + "\n")


def run_progress_reports(
    config_path: str | None = None,
    storage_dir: str | None = None,
    user_filter: str | None = None,
    days: int | None = None,
    dry_run: bool = False,
    save_html: str | None = None,
    fetch_live: bool = False,
    force: bool = False,
):
    if (
        config_path is None
        and storage_dir is None
        and user_filter is None
        and days is None
        and not dry_run
        and save_html is None
        and not fetch_live
        and not force
    ):
        args = parse_args()
        config_path = args.config_path
        storage_dir = args.storage_dir
        user_filter = args.user_filter
        days = args.days
        dry_run = args.dry_run
        save_html = args.output_html
        fetch_live = args.fetch
        force = args.force
    else:
        config_path = config_path or 'config.yaml'

    try:
        config = read_config(config_path)
    except FileNotFoundError:
        sys.exit(1)

    # Sprawdzenie czy moduł raportów jest włączony w configu
    report_cfg = config.get('progress_report', {})
    if not report_cfg.get('enabled', True) and not force:
        logger.info("Moduł progress_report jest wyłączony w konfiguracji ('enabled: false'). Użyj flagi --force, aby go wymusić.")
        return

    effective_storage_dir = storage_dir or config.get('storage_dir', 'storage')
    storage = create_storage(storage_dir=effective_storage_dir)

    mail_sender = None
    if not dry_run and not save_html:
        try:
            mail_sender = configure_mail_provider(config)
        except Exception as e:
            logger.error(f"Błąd konfiguracji dostawcy poczty (sekcja 'mail' w configu): {e}")
            sys.exit(1)

    users = config.get('librus_users', [])
    if user_filter:
        filter_val = str(user_filter).strip().lower()
        matched = [
            u for u in users
            if filter_val in str(u.get('librus_login', '')).lower()
            or filter_val in str(u.get('librus_login_name', '')).lower()
        ]
        if not matched:
            # Sprawdzenie czy istnieje plik stanu w storage (np. konto testowe/archiwalne/przykładowe)
            if storage.has_existing_data(user_filter) or storage.get_grades_history(user_filter):
                default_receivers = users[0].get('notification_receivers', []) if users else []
                custom_name = storage.get_student_name(user_filter) if hasattr(storage, 'get_student_name') else None
                student_name = custom_name or f"Uczeń ({user_filter})"
                matched = [{
                    'librus_login': str(user_filter),
                    'librus_login_name': student_name,
                    'notification_receivers': default_receivers,
                }]
                logger.info(f"Użytkownik '{user_filter}' nie figuruje w pliku konfiguracyjnym, ale odnaleziono dane w storage. Załadowano profil '{student_name}'.")
            else:
                logger.error(f"Nie znaleziono użytkownika pasującego do filtru: '{user_filter}' w katalogu '{effective_storage_dir}'")
                sys.exit(1)
        users = matched
    else:
        # Jeśli nie podano filtru użytkownika, sprawdzamy czy użytkownicy z config.yaml posiadają dane w storage.
        # W przypadku wskazania zewnętrznego storage_dir bez wspólnych kont, automatycznie pobieramy znalezione profile.
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

    raw_delay = config.get('delay_between_users_s', config.get('user_delay_s', 3))
    try:
        delay = float(raw_delay)
    except (ValueError, TypeError):
        delay = 3.0

    for idx, user_config in enumerate(users):
        login = str(user_config.get('librus_login', ''))
        name = user_config.get('librus_login_name') or login
        logger.info(f"--- Generowanie raportu postępów dla ucznia: {name} ({login}) ---")

        # 1. Opcjonalne pobieranie ocen z Librusa (tylko na żądanie --fetch)
        librus = None
        if fetch_live:
            if idx > 0 and delay > 0:
                logger.info(
                    f"Odczekuję {int(delay) if delay.is_integer() else delay}s przed pobraniem danych dla kolejnego konta..."
                )
                sleep(delay)
            try:
                user_copy = dict(user_config)
                user_copy['read_grades'] = True
                librus = Librus(user_copy, storage=storage)
                logger.info(f"Loguję do Librus Synergia dla {name} (flaga --fetch)...")
                librus.login()
                logger.info("Pobieram najświeższe oceny z dziennika...")
                librus.fetch_grades()
            except Exception as e:
                logger.error(f"Błąd podczas pobierania ocen z Librusa dla {name} ({login}): {e}")

        # 2. Pobranie bazy ocen ze storage (działanie w 100% lokalne/offline)
        grades = storage.get_grades_history(login)
        if not grades and librus and hasattr(librus, 'grades') and librus.grades:
            grades = librus.grades

        if not grades:
            logger.warning(
                f"Brak zapisanych ocen w pamięci (storage/) dla ucznia {name} ({login}).\n"
                f"  -> Upewnij się, że usługa 'librus_collector.py' została uruchomiona z włączonym 'read_grades: true',\n"
                f"  -> lub uruchom raport jednorazowo z flagą '--fetch', aby pobrać oceny z Librusa."
            )
            continue

        # 3. Ustalenie zakresu dat
        now = datetime.now()
        period_start = None

        if days is not None:
            period_start = now - timedelta(days=days)
            logger.info(f"Zakres raportu: ostatnie {days} dni (od {period_start.strftime('%Y-%m-%d %H:%M')})")
        else:
            last_report_iso = storage.get_last_progress_report_date(login)
            if last_report_iso:
                try:
                    period_start = datetime.fromisoformat(last_report_iso)
                    logger.info(f"Zakres raportu: od ostatniego wygenerowania ({period_start.strftime('%Y-%m-%d %H:%M')})")
                except Exception as e:
                    logger.warning(f"Nie udało się sparsować daty ostatniego raportu ({last_report_iso}): {e}")

            if period_start is None:
                days_back = report_cfg.get('days_back', 7)
                period_start = now - timedelta(days=days_back)
                logger.info(f"Brak wcześniejszego raportu w bazie. Używam domyślnego okresu wstecz: {days_back} dni (od {period_start.strftime('%Y-%m-%d %H:%M')})")

        # 4. Uruchomienie analizy (ProgressAnalyzer)
        analysis = ProgressAnalyzer.analyze(
            grades=grades,
            period_start=period_start,
            period_end=now
        )

        # 5. Weryfikacja czy są nowe oceny do zaraportowania
        if analysis['period_grades_count'] == 0 and not force and not dry_run and not save_html:
            logger.info(
                f"Uczeń {name} ({login}): Brak nowych ocen w analizowanym okresie ({analysis['period_start_str']} – {analysis['period_end_str']}). "
                f"Raport nie został wysłany. (Użyj flagi --force, aby wymusić wysyłkę raportu bez nowych ocen)."
            )
            continue

        # 6. Zapis do pliku HTML (jeśli podano --save-html / -o)
        if save_html:
            out_file = resolve_output_path(save_html, login, len(users))
            body_html = MailSender.create_mail_content_for_progress_report(user_config, analysis)
            title = MailSender._create_progress_report_title(user_config, analysis)
            full_html = render_standalone_html(title, body_html)
            try:
                with open(out_file, 'w', encoding='utf-8') as f:
                    f.write(full_html)
                logger.info(f"Zapisano raport HTML dla ucznia {name} ({login}) -> {out_file}")
                print(f"✅ Zapisano raport HTML: {out_file}")
            except Exception as e:
                logger.error(f"Nie udało się zapisać pliku HTML '{out_file}': {e}")

        # 7. Tryb Dry-Run lub wysyłka pocztowa
        if dry_run:
            logger.info("Tryb DRY-RUN: prezentacja wyników analizy w terminalu (bez wysyłki maila):")
            print_cli_summary(name, login, analysis)
        elif not save_html:
            logger.info(f"Wysyłam raport postępów dla ucznia {name} ({login})...")
            sent = mail_sender.send_progress_report(user_config, analysis)
            if sent:
                storage.save_last_progress_report_date(login, now.isoformat())
                logger.info(f"Raport postępów dla {name} ({login}) został pomyślnie wysłany!")
            else:
                logger.error(f"Wysyłka raportu postępów dla {name} ({login}) nie powiodła się.")


def main():
    """Główny punkt wejścia CLI dla generatora raportów postępów."""
    setup_logging()
    run_progress_reports()


if __name__ == '__main__':
    main()
