#!/usr/bin/env python3
"""
Librus2mail - Moduł 4: Raport postępów i motywacji dla ucznia (Student Report).
Działa w 100% lokalnie/offline na bazie danych ze storage/.
Oblicza metryki motywacyjne (Supermoce, Szybki awans, Tarcza ochronna, Odznaki)
i renderuje jeden z trzech dedykowanych wiekowo szablonów:
- kids (klasy 4-6)
- teens (klasy 7-8)
- youth (szkoła średnia / liceum)
"""

import argparse
import logging
import sys

from .base_logger import setup_logging
from .config import read_config
from .librus_collector import configure_mail_provider
from .mail_sender import (
    MailSender,
    render_standalone_html,
    resolve_output_path,
)
from .storage import create_storage
from .student_analyzer import StudentAnalyzer
from .updates_notifier import prepare_timetable_summary

logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Librus2mail - Moduł raportowania i motywacji dla ucznia (działanie offline na bazie storage)."
    )
    parser.add_argument(
        "-c", "--config",
        dest="config_path",
        default="config.yaml",
        help="Ścieżka do pliku konfiguracyjnego YAML (domyślnie: config.yaml)",
    )
    parser.add_argument(
        "-s", "--storage-dir",
        dest="storage_dir",
        default=None,
        help="Ścieżka do katalogu pamięci stanu i bazy ocen (nadpisuje ustawienie z config.yaml)",
    )
    parser.add_argument(
        "-u", "--user",
        dest="user_filter",
        default=None,
        help="Filtruj wykonanie tylko do konkretnego loginu lub nazwy ucznia",
    )
    parser.add_argument(
        "-d", "--days",
        dest="days",
        type=int,
        default=None,
        help="Ogranicz analizę do ocen z ostatnich N dni",
    )
    parser.add_argument(
        "-t", "--template",
        dest="template_type",
        choices=["kids", "teens", "youth"],
        default=None,
        help="Wymuś wariant szablonu: 'kids' (klasy 4-6), 'teens' (klasy 7-8), 'youth' (liceum/technikum)",
    )
    parser.add_argument(
        "--actual-date",
        dest="actual_date",
        default=None,
        help="Ustaw stałą datę referencyjną (YYYY-MM-DD) do symulacji i testów",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tryb symulacji: generuje analizę i wyświetla podsumowanie w konsoli bez wysyłania e-maila",
    )
    parser.add_argument(
        "-o", "--output", "--output-html", "--save-html",
        dest="output_html",
        default=None,
        help="Ścieżka do pliku lub katalogu, w którym zostanie zapisany wygenerowany raport HTML",
    )
    return parser.parse_args()


def run_student_reports(
    config_path: str = "config.yaml",
    storage_dir: str | None = None,
    days: int | None = None,
    output_html: str | None = None,
    user_filter: str | None = None,
    template_type: str | None = None,
    dry_run: bool = False,
    actual_date: str | None = None,
) -> dict[str, dict]:
    """
    Główna funkcja orkiestrująca generowanie raportów ucznia.
    Działa całkowicie w trybie offline, korzystając z bazy ocen zapisanych w storage/.
    """
    config = read_config(config_path)
    effective_storage_dir = storage_dir or config.get("storage_dir", "storage")
    storage = create_storage(effective_storage_dir)

    configured_users = config.get("librus_users", [])

    # Wykrywanie profili w storage
    stored_logins = storage.list_stored_logins() if hasattr(storage, "list_stored_logins") else []
    config_logins = {str(u.get("librus_login")) for u in configured_users}
    has_overlap = any(login in config_logins for login in stored_logins)

    # Jeśli baza storage nie ma wspólnych kont z config.yaml (np. wskazano -s examples/storage),
    # lub brak kont w config.yaml, załaduj profile bezpośrednio ze storage
    if (not has_overlap or not configured_users) and stored_logins:
        auto_users = []
        for s_login in stored_logins:
            s_name = storage.get_student_name(s_login) or f"Uczeń ({s_login})"
            auto_users.append({
                "librus_login": str(s_login),
                "librus_login_name": s_name,
            })
        logger.info(
            f"Załadowano profile uczniów odnalezione w '{effective_storage_dir}': "
            f"{[u['librus_login_name'] for u in auto_users]}"
        )
        available_users = auto_users
    else:
        available_users = configured_users

    # Filtrowanie użytkowników
    if user_filter:
        filter_val = str(user_filter).strip().lower()
        matched = [
            u for u in available_users
            if filter_val in str(u.get("librus_login", "")).lower()
            or filter_val in str(u.get("librus_login_name", "")).lower()
        ]
        if not matched and available_users is not configured_users:
            cfg_matched = [
                u for u in configured_users
                if filter_val in str(u.get("librus_login", "")).lower()
                or filter_val in str(u.get("librus_login_name", "")).lower()
            ]
            if cfg_matched and any(storage.get_grades_history(str(u.get("librus_login", ""))) for u in cfg_matched):
                matched = cfg_matched
            elif len(available_users) == 1:
                matched = available_users
                logger.info(
                    f"Konto '{user_filter}' nie posiada danych w '{effective_storage_dir}'. "
                    f"Użyto jedynego dostępnego profilu ze storage: {available_users[0]['librus_login_name']} ({available_users[0]['librus_login']})."
                )
        if not matched:
            # Sprawdzenie czy istnieje plik stanu w storage (np. konto testowe/przykładowe)
            if storage.has_existing_data(user_filter) or storage.get_grades_history(user_filter):
                s_name = storage.get_student_name(user_filter) if hasattr(storage, "get_student_name") else None
                student_name = s_name or f"Uczeń ({user_filter})"
                matched = [{
                    "librus_login": str(user_filter),
                    "librus_login_name": student_name,
                }]
                logger.info(
                    f"Użytkownik '{user_filter}' nie figuruje w konfiguracji, ale odnaleziono dane w '{effective_storage_dir}'. "
                    f"Załadowano profil '{student_name}'."
                )
        if not matched:
            logger.warning(f"Nie znaleziono ucznia pasującego do filtra: '{user_filter}' w '{effective_storage_dir}'")
            return {}
        users = matched
    else:
        users = available_users

    if not users:
        logger.warning("Brak skonfigurowanych profili uczniów do wygenerowania raportu.")
        return {}

    mail_sender = None
    if not dry_run and not output_html:
        try:
            mail_sender = configure_mail_provider(config)
        except Exception as e:
            logger.warning(f"Nie udało się skonfigurować wysyłki poczty e-mail: {e}")

    results = {}

    for user_config in users:
        login = str(user_config.get("librus_login", ""))
        name = user_config.get("librus_login_name") or storage.get_student_name(login) or login
        student_report_cfg = user_config.get("student_report") or {}

        # Weryfikacja czy raport dla ucznia jest włączony dla tego profilu
        # Aktywne gdy:
        # - podano explicite --template, --output-html lub --dry-run z CLI (tryb debug/test)
        # - lub w configu istnieje sekcja student_report z włączoną opcją enabled != false
        is_cli_override = bool(output_html or dry_run or template_type or user_filter)
        is_cfg_enabled = bool(student_report_cfg and student_report_cfg.get("enabled", True))

        if not is_cli_override and not is_cfg_enabled:
            logger.info(f"Pominięto profil {name} ({login}) - brak sekcji 'student_report' w konfiguracji.")
            continue

        logger.info(f"--- Generowanie raportu ucznia dla: {name} ({login}) ---")

        # 1. Pobranie bazy ocen ze storage
        grades = storage.get_grades_history(login)
        if not grades:
            logger.warning(
                f"Brak zapisanych ocen w pamięci ({effective_storage_dir}/) dla ucznia {name} ({login}).\n"
                f"Uruchom najpierw pobieranie danych ze szkoły: 'librus_collector.py'."
            )
            continue

        # 2. Wybór wariantu szablonu
        chosen_template = (
            template_type
            or student_report_cfg.get("template")
            or user_config.get("student_template")
            or "kids"
        )
        if chosen_template not in ("kids", "teens", "youth"):
            logger.warning(f"Nieznany typ szablonu '{chosen_template}', używam 'kids'")
            chosen_template = "kids"

        # 3. Analiza ocen i wyliczenie metryk motywacyjnych
        analyzer = StudentAnalyzer(
            grades=grades,
            student_name=name,
            actual_date=actual_date,
            days=days,
        )
        metrics = analyzer.calculate_metrics()

        logger.info(
            f"{name} ({login}): Wyliczono metryki [szablon: {chosen_template}] - "
            f"średnia: {metrics.overall_avg}, supermoce: {len(metrics.strengths)}, "
            f"szanse na awans: {len(metrics.quick_wins)}, odznaki: {len(metrics.achievements)}"
        )

        # 3.5 Przygotowanie zestawienia terminarza (sprawdziany i wyzwania)
        timetable_summary = None
        if user_config.get("read_timetable", True) and hasattr(storage, "get_timetable_history"):
            raw_timetable = storage.get_timetable_history(login)
            timetable_summary = prepare_timetable_summary(raw_timetable, reference_date=actual_date)

        # 4. Renderowanie treści HTML
        html_content = MailSender.create_mail_content_for_student_report(
            metrics=metrics,
            template_type=chosen_template,
            timetable=timetable_summary,
        )
        email_title = MailSender.create_student_report_title(
            metrics=metrics,
            template_type=chosen_template,
        )

        saved_path = None
        # 5. Zapis do pliku HTML (jeśli zażądano)
        if output_html:
            target_file = resolve_output_path(
                output_path=output_html,
                user_login=login,
                total_users=len(users),
                default_prefix=f"raport_ucznia_{chosen_template}",
            )
            try:
                standalone_html = render_standalone_html(title=email_title, body_html=html_content)
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(standalone_html)
                logger.info(f"✅ Zapisano raport ucznia HTML: {target_file}")
                saved_path = target_file
            except Exception as e:
                logger.error(f"Nie udało się zapisać pliku HTML '{target_file}': {e}")

        # 6. Tryb dry-run / podgląd w konsoli
        if dry_run:
            print("\n" + "=" * 60)
            print(f"RAPORT UCZNIA: {name} (Konto: {login})")
            print(f"Wariant szablonu: {chosen_template.upper()}")
            print(f"Okres analizy: {metrics.period_start_str} – {metrics.period_end_str}" + (f" (ostatnie {metrics.period_days} dni)" if metrics.period_days else ""))
            print(f"Średnia ogólna: {metrics.overall_avg}")
            print(f"Forma: {metrics.trend_description}")
            if metrics.period_comparison and metrics.period_comparison.has_comparison:
                pc = metrics.period_comparison
                if pc.has_prev_data and pc.current_avg is not None and pc.prev_avg is not None:
                    diff_sign = "+" if (pc.avg_diff or 0) > 0 else ""
                    print(f"Porównanie okres do okresu ({pc.current_start_str}–{pc.current_end_str} vs {pc.prev_start_str}–{pc.prev_end_str}):")
                    print(f"  - Średnia okresowa: {pc.current_avg} (poprzednio: {pc.prev_avg}, zmiana: {diff_sign}{pc.avg_diff} pkt)")
                    print(f"  - Bilans ocen: {pc.current_count} (poprzednio: {pc.prev_count}) | Oceny b.dobre: {pc.current_top_count}")
            if metrics.honor_roll:
                hr = metrics.honor_roll
                print(f"Czerwony pasek: {hr.headline} ({hr.progress_pct}% celu)")
                if hr.opportunities:
                    print("  Dźwignie średniej:")
                    for opp in hr.opportunities:
                        print(f"    • {opp.subject}: śr. {opp.current_avg} -> cel: {opp.target_grade}.0 (brak: {opp.gap_to_target} pkt)")
            if metrics.strengths:
                print("Supermoce:")
                for s in metrics.strengths:
                    print(f"  - {s.subject}: {s.avg} ({s.highlight})")
            if metrics.quick_wins:
                print("Szybki awans:")
                for qw in metrics.quick_wins:
                    print(f"  - {qw.subject}: {qw.hint}")
            if metrics.achievements:
                print("Zdobyte odznaki:")
                for ach in metrics.achievements:
                    print(f"  - {ach.icon} {ach.title}: {ach.description}")
            if metrics.recent_grades:
                period_tag = f"w ostatnim okresie ({len(metrics.recent_grades)})" if metrics.period_days else f"wszystkie ({len(metrics.recent_grades)})"
                print(f"Oceny zdobyte {period_tag}:")
                for rg in metrics.recent_grades:
                    comment_info = f" | Komentarz: {rg['comment']}" if rg.get('comment') else ""
                    teacher_info = f" ({rg['teacher']})" if rg.get('teacher') else ""
                    print(f"  - {rg['date_str']} | {rg['subject']}: {rg['grade']} [{rg['category']}]{comment_info}{teacher_info}")
            if timetable_summary and timetable_summary.get('has_any'):
                print("Nadchodzące sprawdziany i wyzwania:")
                if timetable_summary.get('immediate_tests'):
                    print(f"  🔔 {timetable_summary.get('immediate_label')}:")
                    for t in timetable_summary['immediate_tests']:
                        desc = f" — {t['description']}" if t.get('description') else ""
                        les = f" (Lekcja {t.get('lesson_no')})" if t.get('lesson_no') else ""
                        print(f"    • [{t.get('category', 'Sprawdzian')}] {t.get('subject')}{les}{desc}")
                if timetable_summary.get('upcoming_days'):
                    for day in timetable_summary['upcoming_days']:
                        for t in day.get('tests', []):
                            desc = f" — {t['description']}" if t.get('description') else ""
                            les = f" (Lekcja {t.get('lesson_no')})" if t.get('lesson_no') else ""
                            print(f"    • {day['weekday']} ({day['date_str']}): [{t.get('category')}] {t.get('subject')}{les}{desc}")
            print("=" * 60 + "\n")

        # 7. Wysyłka e-mail do ucznia
        email_sent = False
        target_email = student_report_cfg.get("email") or student_report_cfg.get("receivers")
        if not dry_run and target_email and mail_sender:
            receivers = [target_email] if isinstance(target_email, str) else list(target_email)
            try:
                email_sent = mail_sender.send_student_report(
                    receivers=receivers,
                    title=email_title,
                    mail_content=html_content,
                )
                if email_sent:
                    logger.info(f"✅ Wysłano raport ucznia ({chosen_template}) do {receivers}")
            except Exception as e:
                logger.error(f"Błąd podczas wysyłania raportu ucznia do {receivers}: {e}")

        results[login] = {
            "name": name,
            "metrics": metrics,
            "template": chosen_template,
            "html_path": saved_path,
            "email_sent": email_sent,
        }

    return results


def main():
    args = parse_args()
    setup_logging()
    try:
        run_student_reports(
            config_path=args.config_path,
            storage_dir=args.storage_dir,
            days=args.days,
            output_html=args.output_html,
            user_filter=args.user_filter,
            template_type=args.template_type,
            dry_run=args.dry_run,
            actual_date=args.actual_date,
        )
    except FileNotFoundError as e:
        logger.error(f"Błąd konfiguracji: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Nieoczekiwany błąd podczas generowania raportów ucznia: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
