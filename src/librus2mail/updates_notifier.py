#!/usr/bin/env python3
"""
Moduł 2: UpdatesNotifier (Powiadomienia bieżące).
Odpowiada za weryfikację najnowszych wpisów (wiadomości, ogłoszeń, ocen),
ich formatowanie (szablony HTML / terminal) oraz wysyłkę e-mail do rodziców
lub zapis do samodzielnego pliku HTML.
Działa w 100% offline na bazie danych ze storage/.
"""

import argparse
import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from .base_logger import setup_logging
from .config import read_config
from .gmail_sender import GmailSender
from .mail_sender import MailSender, render_standalone_html, resolve_output_path
from .smtp_sender import SmtpSender
from .storage import BaseStorage, create_storage

logger = logging.getLogger(__name__)


def prepare_timetable_summary(
    raw_entries: list[dict],
    reference_date: date | None = None
) -> dict[str, Any]:
    """
    Przygotowuje zestawienie nadchodzących sprawdzianów i nieobecności dla powiadomienia:
    - immediate: najbliższy dzień nauki (jutro lub poniedziałek, jeśli dziś jest piątek/weekend)
    - upcoming_days: kolejne dni w horyzoncie tygodnia (do 7 dni w przód)
    """
    if not raw_entries:
        return {'has_any': False}

    if isinstance(reference_date, str):
        try:
            ref_date = datetime.strptime(reference_date[:10], "%Y-%m-%d").date()
        except ValueError:
            ref_date = datetime.now().date()
    elif isinstance(reference_date, datetime):
        ref_date = reference_date.date()
    elif isinstance(reference_date, date):
        ref_date = reference_date
    else:
        ref_date = datetime.now().date()

    weekdays_pl = [
        "poniedziałek", "wtorek", "środa", "czwartek",
        "piątek", "sobota", "niedziela"
    ]

    ref_weekday = ref_date.weekday()
    if ref_weekday == 4:
        immediate_date = ref_date + timedelta(days=3)
        immediate_label = f"Najbliższy dzień nauki (poniedziałek, {immediate_date.strftime('%d.%m')})"
    elif ref_weekday == 5:
        immediate_date = ref_date + timedelta(days=2)
        immediate_label = f"Najbliższy dzień nauki (poniedziałek, {immediate_date.strftime('%d.%m')})"
    elif ref_weekday == 6:
        immediate_date = ref_date + timedelta(days=1)
        immediate_label = f"Jutro (poniedziałek, {immediate_date.strftime('%d.%m')})"
    else:
        immediate_date = ref_date + timedelta(days=1)
        immediate_weekday_name = weekdays_pl[immediate_date.weekday()]
        immediate_label = f"Jutro ({immediate_weekday_name}, {immediate_date.strftime('%d.%m')})"

    horizon_date = ref_date + timedelta(days=7)

    immediate_date_str = immediate_date.isoformat()
    ref_date_str = ref_date.isoformat()
    horizon_date_str = horizon_date.isoformat()

    immediate_tests = []
    immediate_absences = []
    immediate_events = []

    upcoming_by_date = defaultdict(lambda: {'date': '', 'date_str': '', 'weekday': '', 'tests': [], 'absences': [], 'events': []})

    for entry in raw_entries:
        e_date = entry.get('date')
        if not e_date:
            continue

        # Pomijamy wpisy z przeszłości
        if e_date <= ref_date_str:
            continue

        # Wpisy na immediate_date (lub ewentualny weekend)
        if e_date <= immediate_date_str:
            if entry.get('type') == 'absence':
                immediate_absences.append(entry)
            elif entry.get('type') == 'test':
                immediate_tests.append(entry)
            else:
                immediate_events.append(entry)
        elif e_date <= horizon_date_str:
            try:
                d_obj = datetime.strptime(e_date, "%Y-%m-%d").date()
                day_group = upcoming_by_date[e_date]
                day_group['date'] = e_date
                day_group['date_str'] = d_obj.strftime("%d.%m.%Y")
                day_group['weekday'] = weekdays_pl[d_obj.weekday()].capitalize()

                if entry.get('type') == 'absence':
                    day_group['absences'].append(entry)
                elif entry.get('type') == 'test':
                    day_group['tests'].append(entry)
                else:
                    day_group['events'].append(entry)
            except Exception:
                continue

    upcoming_days = [upcoming_by_date[k] for k in sorted(upcoming_by_date.keys())]

    has_any = bool(immediate_tests or immediate_absences or immediate_events or upcoming_days)

    return {
        'has_any': has_any,
        'immediate_label': immediate_label,
        'immediate_date_str': immediate_date.strftime("%d.%m.%Y"),
        'immediate_date': immediate_date_str,
        'immediate_day_name': weekdays_pl[immediate_date.weekday()],
        'is_tomorrow': ref_weekday not in (4, 5),
        'immediate_tests': immediate_tests,
        'immediate_absences': immediate_absences,
        'immediate_events': immediate_events,
        'upcoming_days': upcoming_days,
    }


def should_trigger_timetable_reminder(
    timetable_summary: dict[str, Any] | None,
    now: datetime,
    config: dict | None = None,
) -> tuple[bool, list[dict]]:
    """
    Sprawdza, czy należy wysłać powiadomienie z przypomnieniem o sprawdzianach (Wariant A):
    - Poniedziałek-Czwartek: jeśli jutro jest sprawdzian i nie był jeszcze dziś notyfikowany.
    - Piątek: jeśli w poniedziałek (najbliższy dzień nauki) jest sprawdzian i nie był dziś notyfikowany.
    - Sobota: cisza (brak autonomicznych przypomnień o sprawdzianach).
    - Niedziela: po godzinie niedzielnego alertu (domyślnie 16:00), jeśli w poniedziałek jest sprawdzian
      i nie był jeszcze notyfikowany w niedzielę.

    Zwraca (powinno_wyslac: bool, nienotyfikowane_sprawdziany: list[dict]).
    """
    if not timetable_summary:
        return False, []

    immediate_tests = timetable_summary.get('immediate_tests', [])
    if not immediate_tests:
        return False, []

    weekday = now.weekday()
    # Sobota (5): cisza
    if weekday == 5:
        return False, []

    # Niedziela (6): przypomnienie dopiero od wyznaczonej godziny (domyślnie 16:00)
    if weekday == 6:
        sunday_hour = 16
        if config:
            try:
                sunday_hour = int(config.get('sunday_reminder_hour', 16))
            except (ValueError, TypeError):
                sunday_hour = 16
        if now.hour < sunday_hour:
            return False, []

    # Poniedziałek-Piątek (0-4) oraz Niedziela (od sunday_hour):
    today_iso = now.date().isoformat()
    unnotified_tests = []
    for test in immediate_tests:
        last_notified = test.get('last_notified_at')
        if not last_notified or not str(last_notified).startswith(today_iso):
            unnotified_tests.append(test)

    should_send = len(unnotified_tests) > 0
    return should_send, unnotified_tests


def configure_mail_provider(config: dict) -> MailSender:
    """Tworzy instancję nadawcy poczty (GmailSender lub SmtpSender) na podstawie konfiguracji."""
    mail_config = config['mail']
    if mail_config['use_gmail']:
        return GmailSender(mail_config)
    else:
        return SmtpSender(mail_config)


def parse_item_datetime(item: Any) -> datetime | None:
    """
    Ekstraktuje obiekt datetime z różnorodnych formatów dat występujących w Librusie:
    - Wiadomości: '2026-09-16 15:39:20'
    - Ogłoszenia: '2026-09-15'
    - Oceny: '2026-09-08 (wt.)' lub '2026-09-08' lub 'added_at' w formacie ISO
    """
    if not item:
        return None

    raw_str = ""
    if isinstance(item, dict):
        raw_str = (
            item.get('datetime')
            or item.get('added_at')
            or item.get('date')
            or item.get('data')
            or ""
        )
    elif isinstance(item, str):
        raw_str = item

    raw_str = str(raw_str).strip()
    if not raw_str:
        return None

    # 1. ISO format (np. 2026-09-16T15:39:20)
    try:
        return datetime.fromisoformat(raw_str)
    except Exception:
        pass

    # 2. Pełna data i godzina: 'YYYY-MM-DD HH:MM:SS'
    m_full = re.search(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})', raw_str)
    if m_full:
        try:
            return datetime.strptime(f"{m_full.group(1)} {m_full.group(2)}", "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    # 3. Sama data: 'YYYY-MM-DD' (np. ogłoszenia lub oceny z '2026-09-15 (wt.)')
    m_date = re.search(r'(\d{4}-\d{2}-\d{2})', raw_str)
    if m_date:
        try:
            return datetime.strptime(m_date.group(1), "%Y-%m-%d")
        except Exception:
            pass

    return None


def print_cli_summary(
    student_name: str,
    login: str,
    messages: list[dict],
    notifications: list[dict],
    grades: list[dict],
    period_desc: str = "",
    timetable: dict | None = None,
) -> None:
    """Wyświetla estetyczne podsumowanie wykrytych nowości w terminalu (ASCII/tekst)."""
    header = f"📬 POWIADOMIENIE (LIBRUS NOTIFIER): {student_name} ({login})"
    if period_desc:
        header += f" | {period_desc}"
    sep = "=" * min(len(header), 80)
    print(f"\n{sep}\n{header}\n{sep}\n")

    has_timetable = bool(timetable and timetable.get('has_any'))
    if not messages and not notifications and not grades and not has_timetable:
        print("Brak nowych wpisów w wybranym okresie.")
        print(f"\n{sep}\n")
        return

    if timetable and timetable.get('has_any'):
        print("📅 TERMINARZ I NAJBLIŻSZE SPRAWDZIANY:")
        imm_tests = timetable.get('immediate_tests', [])
        imm_abs = timetable.get('immediate_absences', [])
        imm_label = timetable.get('immediate_label', 'Najbliższy dzień')
        print(f"  🔔 {imm_label}:")
        if imm_tests:
            for t in imm_tests:
                desc = f" - {t['description']}" if t.get('description') else ""
                les = f" (Lekcja {t['lesson_no']})" if t.get('lesson_no') else ""
                print(f"    • [{t.get('category', 'Sprawdzian')}] {t.get('subject')}{les}{desc} [{t.get('teacher', '')}]")
        elif not imm_abs:
            print("    • Czyste konto – brak zapowiedzianych sprawdzianów ani kartkówek! 🎉")

        if imm_abs:
            for a in imm_abs:
                print(f"    • [Nieobecność] {a.get('teacher')} ({a.get('time')})")

        upcoming_days = timetable.get('upcoming_days', [])
        if upcoming_days:
            print("  🗓️ W kolejnych dniach (ten tydzień):")
            for d in upcoming_days:
                print(f"    📌 {d['weekday']}, {d['date_str']}:")
                for t in d.get('tests', []):
                    desc = f" - {t['description']}" if t.get('description') else ""
                    les = f" (Lekcja {t['lesson_no']})" if t.get('lesson_no') else ""
                    print(f"      • [{t.get('category', 'Sprawdzian')}] {t.get('subject')}{les}{desc} [{t.get('teacher', '')}]")
                for a in d.get('absences', []):
                    print(f"      • [Nieobecność] {a.get('teacher')} ({a.get('time')})")
        print()

    if messages:
        print(f"✉️  Nowe wiadomości ({len(messages)}):")
        for m in messages:
            dt = m.get('datetime', '-')
            sender = m.get('sender', '-')
            title = m.get('title', '-')
            print(f"  • [{dt}] Od: {sender} | Temat: {title}")
        print()

    if notifications:
        print(f"📢 Nowe ogłoszenia ({len(notifications)}):")
        for n in notifications:
            dt = n.get('datetime', '-')
            title = n.get('title', '-')
            print(f"  • [{dt}] {title}")
        print()

    if grades:
        print(f"📝 Nowe oceny ({len(grades)}):")
        for g in grades:
            subj = g.get('subject', '-')
            val = g.get('grade', '-')
            weight = g.get('weight', '-')
            date = g.get('date', '-')
            cat = g.get('category', '-')
            comm = g.get('comment')
            comm_str = f" | kom: \"{comm}\"" if comm and comm != '-' else ""
            print(f"  • {subj}: {val} (waga: {weight}, data: {date}, kat: {cat}{comm_str})")
        print()

    print(f"{sep}\n")


class UpdatesNotifier:
    """
    Moduł odpowiedzialny za weryfikację i wysyłkę powiadomień o najświeższych wpisach
    (wiadomościach, ogłoszeniach i ocenach) dla skonfigurowanych kont uczniów.
    """

    def __init__(
        self,
        config: dict,
        storage: BaseStorage | None = None,
        mail_sender: MailSender | None = None
    ):
        self.config = config
        self.storage = storage or create_storage(config.get('storage_dir', 'storage'))
        self.mail_sender = mail_sender

    def get_or_create_mail_sender(self) -> MailSender:
        if self.mail_sender is None:
            self.mail_sender = configure_mail_provider(self.config)
        return self.mail_sender

    def filter_by_cutoff(self, items: list[dict], cutoff: datetime) -> list[dict]:
        """Filtruje wpisy, pozostawiając tylko te powstałe w lub po dacie cutoff."""
        res = []
        for item in items:
            dt = parse_item_datetime(item)
            if dt and dt >= cutoff:
                res.append(item)
        return res

    def get_user_stored_items(self, login: str, read_grades: bool = True) -> tuple[list[dict], list[dict], list[dict]]:
        """Odczytuje wszystkie zarejestrowane wiadomości, ogłoszenia i oceny ze storage dla danego ucznia."""
        msgs = self.storage.get_stored_messages(login) if hasattr(self.storage, 'get_stored_messages') else []
        notifs = self.storage.get_stored_notifications(login) if hasattr(self.storage, 'get_stored_notifications') else []
        grades = self.storage.get_grades_history(login) if read_grades else []
        return msgs, notifs, grades

    def process_user_notifications(
        self,
        user_config: dict,
        all_messages: list[dict] | None = None,
        all_notifications: list[dict] | None = None,
        all_grades: list[dict] | None = None,
        new_messages: list[dict] | None = None,
        new_notifications: list[dict] | None = None,
        new_grades: list[dict] | None = None,
        days: int | None = None,
        hours: int | None = None,
        dry_run: bool = False,
        output_html: str | None = None,
        total_users: int = 1,
        summary: bool | None = None,
        actual_date: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Przetwarza powiadomienie dla pojedynczego ucznia:
        - Jeśli podano days lub hours, filtruje wpisy po dacie odcięcia.
        - W przeciwnym razie wykorzystuje podane new_* lub wylicza nowości na podstawie stanu bazy.
        - Generuje plik HTML (-o), wyświetla podsumowanie w konsoli (--dry-run) lub wysyła e-mail.
        """
        login = str(user_config.get('librus_login', ''))
        name = user_config.get('librus_login_name') or self.storage.get_student_name(login) or login

        # 1. Pobranie danych ze storage jeśli nie zostały przekazane
        if all_messages is None or all_notifications is None or (all_grades is None and user_config.get('read_grades', True)):
            stored_msgs, stored_notifs, stored_grades = self.get_user_stored_items(
                login,
                read_grades=user_config.get('read_grades', True)
            )
            all_messages = all_messages if all_messages is not None else stored_msgs
            all_notifications = all_notifications if all_notifications is not None else stored_notifs
            all_grades = all_grades if all_grades is not None else stored_grades

        # 2. Ustalenie, które wpisy są uznawane za "nowe"
        period_desc = ""
        now = actual_date or datetime.now()
        if days is not None or hours is not None:
            delta = timedelta(days=days or 0, hours=hours or 0)
            cutoff = now - delta
            period_desc = f"okres: ostatnie {days or 0} dni, {hours or 0} godz. (od {cutoff.strftime('%Y-%m-%d %H:%M')})"
            logger.info(f"{name} ({login}): Filtrowanie wpisów z okresu ({period_desc})")

            filtered_messages = self.filter_by_cutoff(all_messages, cutoff)
            filtered_notifications = self.filter_by_cutoff(all_notifications, cutoff)
            filtered_grades = self.filter_by_cutoff(all_grades, cutoff) if user_config.get('read_grades', True) else []
        elif new_messages is not None or new_notifications is not None or new_grades is not None:
            # Wpisy przekazane bezpośrednio w pamięci (np. z bieżącej pętli LibrusCollector)
            filtered_messages = new_messages if new_messages is not None else []
            filtered_notifications = new_notifications if new_notifications is not None else []
            filtered_grades = new_grades if new_grades is not None else []
        else:
            # Tryb asynchroniczny / nieregularny:
            # Sprawdzamy watermark ostatniego powiadomienia w bazie storage (last_notify_time / last_update_create)
            last_notify = self.storage.get_last_notify_time(login) if hasattr(self.storage, 'get_last_notify_time') else None
            if last_notify:
                try:
                    cutoff = datetime.fromisoformat(last_notify)
                    period_desc = f"od ostatniego powiadomienia ({cutoff.strftime('%Y-%m-%d %H:%M')})"
                    logger.info(f"{name} ({login}): Filtrowanie wpisów z okresu ({period_desc})")
                    filtered_messages = self.filter_by_cutoff(all_messages, cutoff)
                    filtered_notifications = self.filter_by_cutoff(all_notifications, cutoff)
                    filtered_grades = self.filter_by_cutoff(all_grades, cutoff) if user_config.get('read_grades', True) else []
                except Exception as e:
                    logger.warning(f"Nieprawidłowy format last_notify_time ({last_notify}): {e}")
                    filtered_messages, filtered_notifications, filtered_grades = [], [], []
            else:
                # Pierwsze uruchomienie bez wcześniejszego znacznika powiadomień
                if user_config.get('dry-parse', False) or user_config.get('do_not_send_first_parse', False):
                    period_desc = "pierwsza inicjalizacja (baseline, brak wysyłki)"
                    logger.info(f"{name} ({login}): Pierwsze uruchomienie z do_not_send_first_parse – brak wysyłki historycznych danych.")
                    filtered_messages, filtered_notifications, filtered_grades = [], [], []
                else:
                    cutoff = now - timedelta(days=1)
                    period_desc = "pierwsze powiadomienie (domyślnie ostatnie 24h)"
                    logger.info(f"{name} ({login}): Brak zapisanego znacznika powiadomienia – pobieranie nowości z ostatnich 24h.")
                    filtered_messages = self.filter_by_cutoff(all_messages, cutoff)
                    filtered_notifications = self.filter_by_cutoff(all_notifications, cutoff)
                    filtered_grades = self.filter_by_cutoff(all_grades, cutoff) if user_config.get('read_grades', True) else []

        saved_file = None

        # 2.5 Przygotowanie zestawienia terminarza (sprawdziany, nieobecności)
        all_timetable = self.storage.get_timetable_history(login) if hasattr(self.storage, 'get_timetable_history') else []
        timetable_summary = prepare_timetable_summary(all_timetable, reference_date=now.date()) if user_config.get('read_timetable', True) else None

        # 3. Zapis do pliku HTML (jeśli podano -o / --save-html)
        if output_html:
            out_file = resolve_output_path(output_html, login, total_users, default_prefix="powiadomienie")
            title = MailSender._create_summary_title(user_config, filtered_messages, filtered_notifications, filtered_grades, timetable=timetable_summary)
            body = MailSender.create_mail_content_for_summary(user_config, filtered_messages, filtered_notifications, filtered_grades, timetable=timetable_summary)
            full_html = render_standalone_html(title, body)
            try:
                with open(out_file, 'w', encoding='utf-8') as f:
                    f.write(full_html)
                saved_file = out_file
                logger.info(f"Zapisano powiadomienie HTML dla {name} ({login}) -> {out_file}")
                print(f"✅ Zapisano powiadomienie HTML: {out_file}")
            except Exception as e:
                logger.error(f"Nie udało się zapisać pliku HTML '{out_file}': {e}")

        # 4. Tryb Dry-Run (podgląd w terminalu)
        if dry_run:
            has_new_items = bool(filtered_messages or filtered_notifications or filtered_grades)
            should_send_timetable, unnotified_tests = should_trigger_timetable_reminder(
                timetable_summary, now=now, config=self.config
            )
            if not has_new_items and not should_send_timetable:
                logger.info(f"{name} ({login}): Tryb symulacji (dry-run) – brak nowych ocen, wiadomości ani sprawdzianów na najbliższy dzień nauki.")
            elif should_send_timetable and not has_new_items:
                logger.info(
                    f"{name} ({login}): Tryb symulacji (dry-run) – brak nowych ocen, ale wykryto sprawdzian(y) "
                    f"na najbliższy dzień nauki ({len(unnotified_tests)}). Wysłano by przypomnienie e-mail."
                )
            else:
                logger.info(
                    f"{name} ({login}): Tryb symulacji (dry-run) – wykryto nowe pozycje (wiadomości: {len(filtered_messages)}, "
                    f"ogłoszenia: {len(filtered_notifications)}, oceny: {len(filtered_grades)}). Brak wysyłki e-mail."
                )
            print_cli_summary(name, login, filtered_messages, filtered_notifications, filtered_grades, period_desc, timetable=timetable_summary)

        # 5. Rzeczywista wysyłka pocztowa
        if not dry_run and not output_html:
            has_new_items = bool(filtered_messages or filtered_notifications or filtered_grades)
            should_send_timetable, unnotified_tests = should_trigger_timetable_reminder(
                timetable_summary, now=now, config=self.config
            )

            if user_config.get('dry-parse', False):
                logger.info(
                    f"{name} ({login}): Tryb dry-parse (pierwsze parsowanie/baseline) – "
                    "pomijam wysyłkę powiadomień dla danych historycznych."
                )
                if hasattr(self.storage, 'save_last_notify_time'):
                    self.storage.save_last_notify_time(login, now.isoformat())
                if timetable_summary and timetable_summary.get('immediate_tests') and hasattr(self.storage, 'mark_timetable_entries_notified'):
                    t_ids = [t['id'] for t in timetable_summary['immediate_tests'] if t.get('id')]
                    if t_ids:
                        self.storage.mark_timetable_entries_notified(login, t_ids, notified_at_iso=now.isoformat())
            elif not has_new_items and not should_send_timetable:
                period_info = f" ({period_desc})" if period_desc else ""
                logger.info(
                    f"{name} ({login}): Brak nowych informacji{period_info} (brak nowych ocen, wiadomości ani sprawdzianów na najbliższy dzień nauki) – "
                    "powiadomienie e-mail nie zostało wysłane."
                )
            else:
                sender = self.get_or_create_mail_sender()
                one_summary = summary if summary is not None else user_config.get(
                    'one_summary_message',
                    self.config.get('one_summary_message', False)
                )
                if one_summary or (should_send_timetable and not has_new_items):
                    if should_send_timetable and not has_new_items:
                        logger.info(
                            f"{name} ({login}): Brak nowych ocen/wiadomości, ale wykryto {len(unnotified_tests)} "
                            "sprawdzian(y) na najbliższy dzień nauki. Wysyłam przypomnienie e-mail."
                        )
                    else:
                        logger.info(
                            f"Nowe wpisy dla {name} (wiadomości: {len(filtered_messages)}, "
                            f"ogłoszenia: {len(filtered_notifications)}, oceny: {len(filtered_grades)}). "
                            "Wysyłam zbiorcze podsumowanie e-mail."
                        )
                    sender.send_mail_with_summary(user_config, filtered_messages, filtered_notifications, filtered_grades, timetable=timetable_summary)
                else:
                    if filtered_messages:
                        logger.info(f"Wysyłam e-mail z {len(filtered_messages)} nowymi wiadomościami dla {name}")
                        sender.send_mail_with_messages(user_config, filtered_messages)
                    if filtered_notifications:
                        logger.info(f"Wysyłam e-mail z {len(filtered_notifications)} nowymi ogłoszeniami dla {name}")
                        sender.send_mail_with_notifications(user_config, filtered_notifications)
                    if filtered_grades:
                        logger.info(f"Wysyłam e-mail z {len(filtered_grades)} nowymi ocenami dla {name}")
                        sender.send_mail_with_grades(user_config, filtered_grades)

                if hasattr(self.storage, 'save_last_notify_time'):
                    self.storage.save_last_notify_time(login, now.isoformat())

                if timetable_summary and timetable_summary.get('immediate_tests') and hasattr(self.storage, 'mark_timetable_entries_notified'):
                    t_ids = [t['id'] for t in timetable_summary['immediate_tests'] if t.get('id')]
                    if t_ids:
                        self.storage.mark_timetable_entries_notified(login, t_ids, notified_at_iso=now.isoformat())

        return {
            'login': login,
            'name': name,
            'messages': filtered_messages,
            'notifications': filtered_notifications,
            'grades': filtered_grades,
            'timetable': timetable_summary,
            'output_file': saved_file,
        }


def run_notifier(
    config_path: str = 'config.yaml',
    storage_dir: str | None = None,
    days: int | None = None,
    hours: int | None = None,
    dry_run: bool = False,
    output_html: str | None = None,
    user_filter: str | None = None,
    offline: bool = True,
    collected_data: dict[str, dict] | None = None,
    summary: bool | None = None,
    actual_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Główna funkcja uruchamiająca moduł UpdatesNotifier.
    Działa w 100% offline na bazie danych ze storage/ (chyba że przekazano zebrane dane z pamięci).
    """
    config = read_config(config_path)
    effective_storage_dir = storage_dir or config.get('storage_dir', 'storage')
    config['storage_dir'] = effective_storage_dir
    storage = create_storage(effective_storage_dir)

    notifier = UpdatesNotifier(config, storage=storage)

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
                first_user = users[0] if users else {}
                default_receivers = first_user.get('notification_receivers', [])
                default_one_summary = first_user.get('one_summary_message', config.get('one_summary_message', False))
                default_read_grades = first_user.get('read_grades', config.get('read_grades', True))
                default_read_messages = first_user.get('read_messages', config.get('read_messages', True))
                default_read_timetable = first_user.get('read_timetable', config.get('read_timetable', True))
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
                }]
                logger.info(f"Załadowano profil ze storage dla '{user_filter}': '{student_name}'.")
            else:
                logger.error(f"Nie znaleziono użytkownika pasującego do filtru: '{user_filter}' w '{effective_storage_dir}'")
                return []
        users = matched
    else:
        # Automatyczne wykrywanie profili ze storage jeśli brak pokrycia w configu
        stored_logins = storage.list_stored_logins() if hasattr(storage, 'list_stored_logins') else []
        config_logins = {str(u.get('librus_login')) for u in users}
        has_overlap = any(login in config_logins for login in stored_logins)
        if not has_overlap and stored_logins:
            first_user = users[0] if users else {}
            default_receivers = first_user.get('notification_receivers', [])
            default_one_summary = first_user.get('one_summary_message', config.get('one_summary_message', False))
            default_read_grades = first_user.get('read_grades', config.get('read_grades', True))
            default_read_messages = first_user.get('read_messages', config.get('read_messages', True))
            default_read_timetable = first_user.get('read_timetable', config.get('read_timetable', True))
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
                })
            logger.info(f"Załadowano profile uczniów odnalezione w '{effective_storage_dir}': {[u['librus_login_name'] for u in auto_users]}")
            users = auto_users

    results = []
    for user_config in users:
        login = str(user_config.get('librus_login', ''))
        c_item = (collected_data or {}).get(login, {})
        res = notifier.process_user_notifications(
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
            actual_date=actual_date,
        )
        results.append(res)

    return results


def main():
    """Punkt wejścia CLI dla modułu UpdatesNotifier."""
    parser = argparse.ArgumentParser(
        description="Librus2mail Updates Notifier - Weryfikacja najnowszych wpisów i wysyłka powiadomień / generowanie HTML."
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
        help="Filtruj powiadomienie tylko do wskazanego konta ucznia (login lub nazwisko)"
    )
    parser.add_argument(
        '-d', '--days',
        dest='days',
        type=int,
        default=None,
        help="Okres w dniach: uznaj wpisy z ostatnich N dni za nowe"
    )
    parser.add_argument(
        '--hours',
        dest='hours',
        type=int,
        default=None,
        help="Okres w godzinach: uznaj wpisy z ostatnich N godzin za nowe"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Tryb symulacji: wyświetla podsumowanie w konsoli bez wysyłania e-maili i bez modyfikacji bazy"
    )
    parser.add_argument(
        '-o', '--output', '--save-html',
        dest='output_html',
        default=None,
        help="Zapisz powiadomienie jako samodzielny plik HTML pod wskazaną ścieżką (pomija wysyłkę e-mail)"
    )
    parser.add_argument(
        '--summary',
        dest='summary',
        action='store_true',
        default=None,
        help="Wymuś wysłanie 1 zbiorczego e-maila ze wszystkimi nowościami (zamiast osobnych wiadomości, ogłoszeń i ocen)"
    )
    parser.add_argument(
        '--actual-date',
        dest='actual_date',
        default=None,
        metavar='YYYY-MM-DD',
        help=(
            "Zastępcza data 'teraz' (format: YYYY-MM-DD). "
            "Przydatne przy generowaniu przykładowych raportów z przykładowego storage – "
            "okno czasowe (--days) będzie liczyć wstecz od tej daty zamiast od bieżącej."
        )
    )
    parser.add_argument(
        'config',
        nargs='?',
        default=None,
        help="Ścieżka do pliku konfiguracyjnego YAML (domyślnie: config.yaml)"
    )
    args = parser.parse_args()
    config_path = args.config_opt or args.config or 'config.yaml'

    actual_date: datetime | None = None
    if args.actual_date:
        try:
            actual_date = datetime.strptime(args.actual_date, "%Y-%m-%d")
        except ValueError:
            parser.error(f"Nieprawidłowy format --actual-date: '{args.actual_date}'. Wymagany format: YYYY-MM-DD")

    setup_logging()
    run_notifier(
        config_path=config_path,
        storage_dir=args.storage_dir,
        days=args.days,
        hours=args.hours,
        dry_run=args.dry_run,
        output_html=args.output_html,
        user_filter=args.user_filter,
        offline=True,
        summary=args.summary,
        actual_date=actual_date,
    )


if __name__ == '__main__':
    main()
