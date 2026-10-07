"""Warstwa usług i logiki biznesowej dla panelu webowego Librus2mail."""

import io
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from librus2mail.mail_sender import MailSender
from librus2mail.progress_analyzer import (
    ProgressAnalyzer,
    parse_numeric_grade,
    parse_weight,
)
from librus2mail.storage import BaseStorage, create_storage
from librus2mail.student_analyzer import StudentAnalyzer
from librus2mail.updates_notifier import (
    parse_item_datetime,
    prepare_schedule_summary,
    prepare_timetable_summary,
)

logger = logging.getLogger(__name__)


def get_storage(config: dict, storage_dir: str | None = None) -> BaseStorage:
    """Zwraca instancję pamięci stanu (storage)."""
    effective_dir = storage_dir or config.get('storage_dir', 'storage')
    return create_storage(effective_dir)


def resolve_student_name(config: dict, storage: BaseStorage, login: str | int) -> str:
    """Ustala pełną nazwę ucznia (z configu lub storage) wraz z identyfikatorem konta."""
    s_login = str(login)
    user_cfg = next(
        (u for u in config.get('librus_users', []) if str(u.get('librus_login', '')) == s_login),
        {}
    )
    base_name = (
        user_cfg.get('librus_login_name')
        or (storage.get_student_name(s_login) if hasattr(storage, 'get_student_name') else None)
        or "Uczeń"
    )
    if user_cfg.get('librus_login_name') and hasattr(storage, 'set_student_name'):
        storage.set_student_name(s_login, user_cfg['librus_login_name'])

    if f"({s_login})" not in base_name:
        return f"{base_name} ({s_login})"
    return base_name


def format_human_timestamp(val: str | datetime | None, now: datetime | None = None) -> str:
    """Konwertuje znacznik czasu (ISO string lub datetime) na przyjazny dla człowieka tekst w języku polskim.

    Przykłady:
      - 'dzisiaj o 12:25 (przed chwilą)'
      - 'dzisiaj o 12:25 (46 min temu)'
      - 'dzisiaj o 09:30 (3 godz. temu)'
      - 'wczoraj o 19:40'
      - 'przedwczoraj o 18:15'
      - '05.10 o 14:20 (2 dni temu)'
      - '28.09.2025 o 10:15'
    """
    if not val:
        return "Brak danych"

    dt: datetime | None = None
    if isinstance(val, datetime):
        dt = val
    else:
        val_str = str(val).strip()
        if not val_str:
            return "Brak danych"
        if val_str.endswith('Z'):
            val_str = val_str[:-1]
        try:
            dt = datetime.fromisoformat(val_str)
        except Exception:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(val_str, fmt)
                    break
                except Exception:
                    pass

    if not dt:
        return str(val)

    ref_now = now or datetime.now()

    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    if ref_now.tzinfo is not None:
        ref_now = ref_now.astimezone().replace(tzinfo=None)

    diff = ref_now - dt
    total_seconds = diff.total_seconds()
    time_str = dt.strftime("%H:%M")

    if total_seconds < 0:
        if dt.date() == ref_now.date():
            return f"dzisiaj o {time_str}"
        return f"{dt.strftime('%d.%m.%Y')} o {time_str}"

    dt_date = dt.date()
    now_date = ref_now.date()
    days_diff = (now_date - dt_date).days

    if days_diff == 0:
        if total_seconds < 60:
            return f"dzisiaj o {time_str} (przed chwilą)"
        if total_seconds < 3600:
            minutes = max(1, int(total_seconds // 60))
            return f"dzisiaj o {time_str} ({minutes} min temu)"
        hours = int(total_seconds // 3600)
        return f"dzisiaj o {time_str} ({hours} godz. temu)"

    if days_diff == 1:
        return f"wczoraj o {time_str}"

    if days_diff == 2:
        return f"przedwczoraj o {time_str}"

    if dt.year == ref_now.year:
        if days_diff <= 30:
            return f"{dt.strftime('%d.%m')} o {time_str} ({days_diff} dni temu)"
        return f"{dt.strftime('%d.%m')} o {time_str}"

    return f"{dt.strftime('%d.%m.%Y')} o {time_str}"


def list_students(config: dict, storage: BaseStorage) -> list[dict[str, Any]]:
    """Zwraca listę wszystkich dostępnych uczniów (z konfiguracji oraz pamięci storage)."""
    students_dict: dict[str, dict[str, Any]] = {}

    for u in config.get('librus_users', []):
        login = str(u.get('librus_login', ''))
        if login:
            name = resolve_student_name(config, storage, login)
            students_dict[login] = {
                'login': login,
                'name': name,
                'configured': True,
                'raw_config': u,
            }

    if hasattr(storage, 'list_stored_logins'):
        for s_login in storage.list_stored_logins():
            if s_login not in students_dict:
                name = resolve_student_name(config, storage, s_login)
                students_dict[s_login] = {
                    'login': s_login,
                    'name': name,
                    'configured': False,
                    'raw_config': {},
                }

    return list(students_dict.values())


def get_active_student_login(
    config: dict,
    storage: BaseStorage,
    requested_login: str | None = None,
    session_login: str | None = None,
) -> str | None:
    """Ustala login aktywnego ucznia na podstawie parametru, sesji lub konfiguracji."""
    students = list_students(config, storage)
    if not students:
        return None

    all_logins = {s['login'] for s in students}

    if requested_login and requested_login in all_logins:
        return requested_login
    if session_login and session_login in all_logins:
        return session_login

    return students[0]['login']


def calculate_subject_averages(grades_history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Wylicza średnie ważone i statystyki per przedmiot na podstawie historii ocen."""
    by_subject = defaultdict(list)
    for g in grades_history:
        subj = g.get('subject', 'Inne')
        by_subject[subj].append(g)

    result = {}
    for subj, g_list in by_subject.items():
        sum_weighted = 0.0
        sum_weights = 0.0
        numeric_count = 0

        for g in g_list:
            n_grade = parse_numeric_grade(g.get('grade'))
            w = parse_weight(g.get('weight'))
            if n_grade is not None:
                numeric_count += 1
                effective_weight = w if w is not None and w > 0 else 1.0
                sum_weighted += n_grade * effective_weight
                sum_weights += effective_weight

        avg = round(sum_weighted / sum_weights, 2) if sum_weights > 0 else None
        sorted_grades = sorted(g_list, key=lambda x: str(x.get('date', '')), reverse=True)

        result[subj] = {
            'subject': subj,
            'grades': sorted_grades,
            'count': len(g_list),
            'numeric_count': numeric_count,
            'average': avg,
            'sum_weights': sum_weights,
        }

    return dict(sorted(result.items(), key=lambda item: item[0]))


def calculate_overall_average(subject_averages: dict[str, dict[str, Any]]) -> float | None:
    """Wylicza ogólną średnią arytmetyczną z ocen ze wszystkich przedmiotów."""
    avgs = [v['average'] for v in subject_averages.values() if v.get('average') is not None]
    if not avgs:
        return None
    return round(sum(avgs) / len(avgs), 2)


def simulate_new_grade(
    grades_history: list[dict[str, Any]],
    subject: str,
    new_grade: float,
    new_weight: float = 1.0,
) -> dict[str, Any]:
    """Symuluje dodanie nowej oceny z wagą i oblicza przewidywaną zmianę średniej ważonej."""
    subject_grades = [g for g in grades_history if g.get('subject', '').strip().lower() == subject.strip().lower()]

    sum_weighted = 0.0
    sum_weights = 0.0

    for g in subject_grades:
        n_grade = parse_numeric_grade(g.get('grade'))
        w = parse_weight(g.get('weight'))
        if n_grade is not None:
            effective_weight = w if w is not None and w > 0 else 1.0
            sum_weighted += n_grade * effective_weight
            sum_weights += effective_weight

    old_avg = round(sum_weighted / sum_weights, 2) if sum_weights > 0 else None

    # Dodanie nowej oceny
    eff_new_weight = max(0.1, new_weight)
    new_sum_weighted = sum_weighted + (new_grade * eff_new_weight)
    new_sum_weights = sum_weights + eff_new_weight
    new_avg = round(new_sum_weighted / new_sum_weights, 2)

    diff = round(new_avg - old_avg, 2) if old_avg is not None else 0.0

    return {
        'subject': subject,
        'old_avg': old_avg,
        'new_avg': new_avg,
        'diff': diff,
        'new_grade': new_grade,
        'new_weight': new_weight,
    }


def get_student_dashboard_bundle(
    storage: BaseStorage,
    login: str,
    config: dict,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Przygotowuje komplet danych dla wybranego ucznia do wyświetlenia na dashboardzie."""
    ref_now = now or datetime.now()

    student_name = resolve_student_name(config, storage, login)
    grades = storage.get_grades_history(login) if hasattr(storage, 'get_grades_history') else []
    timetable = storage.get_timetable_history(login) if hasattr(storage, 'get_timetable_history') else []
    schedule = storage.get_schedule_history(login) if hasattr(storage, 'get_schedule_history') else []
    messages = storage.get_stored_messages(login) if hasattr(storage, 'get_stored_messages') else []
    notifications = storage.get_stored_notifications(login) if hasattr(storage, 'get_stored_notifications') else []
    last_sync = storage.get_last_collect_time(login) if hasattr(storage, 'get_last_collect_time') else None
    last_sync_human = format_human_timestamp(last_sync, now=ref_now)

    # Analityka ocen
    subj_averages = calculate_subject_averages(grades)
    overall_avg = calculate_overall_average(subj_averages)

    # Najnowsze oceny (ostatnie 8)
    recent_grades = sorted(grades, key=lambda x: str(x.get('added_at', '') or x.get('date', '')), reverse=True)[:8]

    # Terminarz i plan lekcji
    timetable_summary = prepare_timetable_summary(timetable, reference_date=ref_now.date())
    day_offset = int(config.get('schedule_day_offset', 1))
    schedule_summary = prepare_schedule_summary(schedule, timetable_entries=timetable, now=ref_now, day_offset=day_offset)
    today_schedule_summary = prepare_schedule_summary(schedule, timetable_entries=timetable, now=ref_now, day_offset=0)

    # Liczba nadchodzących sprawdzianów w horyzoncie
    upcoming_tests_count = len(timetable_summary.get('immediate_tests', [])) + sum(
        len(d.get('tests', [])) for d in timetable_summary.get('upcoming_days', [])
    )

    return {
        'login': login,
        'name': student_name,
        'grades_count': len(grades),
        'subject_averages': subj_averages,
        'overall_average': overall_avg,
        'recent_grades': recent_grades,
        'timetable_summary': timetable_summary,
        'schedule_summary': schedule_summary,
        'today_schedule_summary': today_schedule_summary,
        'upcoming_tests_count': upcoming_tests_count,
        'messages': messages,
        'notifications': notifications,
        'messages_count': len(messages),
        'notifications_count': len(notifications),
        'last_sync': last_sync,
        'last_sync_human': last_sync_human,
        'all_schedule': schedule,
        'all_timetable': timetable,
    }


def capture_action_execution(func, *args, **kwargs) -> tuple[bool, str, Any]:
    """Wspólny wrapper przechwytujący logi i status wykonania akcji CLI."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    success = False
    result = None
    output = ""

    try:
        result = func(*args, **kwargs)
        success = True
    except Exception as e:
        logger.error(f"Błąd podczas wykonywania akcji: {e}", exc_info=True)
        log_capture.write(f"\n❌ Błąd: {type(e).__name__}: {str(e)}\n")
        success = False
    finally:
        root_logger.removeHandler(handler)
        output = log_capture.getvalue()

    return success, output, result


def build_progress_report_html(
    storage: BaseStorage,
    login: str,
    config: dict,
    days: int | None = None,
    now: datetime | None = None,
) -> str:
    """Generuje gotowy HTML raportu postępów dla wybranego ucznia."""
    grades = storage.get_grades_history(login) if hasattr(storage, 'get_grades_history') else []
    if not grades:
        return (
            '<div class="py-16 text-center bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">'
            '<div class="text-4xl mb-3">📝</div>'
            '<h3 class="text-lg font-bold text-slate-800 mb-1">Brak zapisanych ocen w pamięci podręcznej</h3>'
            '<p class="text-sm text-slate-500 max-w-md mx-auto mb-6">'
            'Nie odnaleziono jeszcze historii ocen dla tego ucznia w lokalnej bazie. '
            'Uruchom synchronizację z Librusem, aby pobrać najnowsze oceny.'
            '</p>'
            '<a href="/akcje" class="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-xs font-bold rounded-xl hover:bg-indigo-700 transition shadow-sm">'
            '⚡ Przejdź do synchronizacji'
            '</a>'
            '</div>'
        )

    ref_now = now or datetime.now()
    if days is not None:
        period_start = ref_now - timedelta(days=days)
    else:
        last_report_iso = storage.get_last_progress_report_date(login) if hasattr(storage, 'get_last_progress_report_date') else None
        period_start = None
        if last_report_iso:
            try:
                period_start = datetime.fromisoformat(last_report_iso)
            except Exception:
                period_start = None
        if period_start is None:
            days_back = config.get('progress_report', {}).get('days_back', 7)
            period_start = ref_now - timedelta(days=days_back)

    analysis = ProgressAnalyzer.analyze(
        grades=grades,
        period_start=period_start,
        period_end=ref_now,
    )

    timetable_summary = None
    if hasattr(storage, 'get_timetable_history'):
        raw_timetable = storage.get_timetable_history(login)
        timetable_summary = prepare_timetable_summary(raw_timetable, reference_date=ref_now.date())

    user_cfg = next((u for u in config.get('librus_users', []) if str(u.get('librus_login', '')) == str(login)), None)
    if user_cfg:
        user_cfg = dict(user_cfg)
    else:
        user_cfg = {'librus_login': str(login)}
    user_cfg['librus_login_name'] = resolve_student_name(config, storage, login)

    return MailSender.create_mail_content_for_progress_report(
        user_config=user_cfg,
        analysis=analysis,
        timetable=timetable_summary,
    )


def build_student_report_html(
    storage: BaseStorage,
    login: str,
    config: dict,
    variant: str = 'teens',
    days: int | None = None,
    now: datetime | None = None,
) -> str:
    """Generuje motywacyjny raport ucznia w wybranym stylu (kids, teens, youth)."""
    grades = storage.get_grades_history(login) if hasattr(storage, 'get_grades_history') else []
    if not grades:
        return (
            '<div class="py-16 text-center bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">'
            '<div class="text-4xl mb-3">🌟</div>'
            '<h3 class="text-lg font-bold text-slate-800 mb-1">Brak zapisanych ocen w pamięci podręcznej</h3>'
            '<p class="text-sm text-slate-500 max-w-md mx-auto mb-6">'
            'Nie odnaleziono jeszcze historii ocen dla tego ucznia w lokalnej bazie. '
            'Uruchom synchronizację z Librusem, aby wygenerować kartę motywacyjną ucznia.'
            '</p>'
            '<a href="/akcje" class="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-xs font-bold rounded-xl hover:bg-indigo-700 transition shadow-sm">'
            '⚡ Przejdź do synchronizacji'
            '</a>'
            '</div>'
        )

    clean_variant = variant if variant in ('kids', 'teens', 'youth') else 'teens'
    ref_now = now or datetime.now()
    student_name = resolve_student_name(config, storage, login)
    effective_days = days if days is not None else 7

    analyzer = StudentAnalyzer(
        grades=grades,
        student_name=student_name,
        actual_date=ref_now.strftime('%Y-%m-%d'),
        days=effective_days,
    )
    metrics = analyzer.calculate_metrics()

    timetable_summary = None
    if hasattr(storage, 'get_timetable_history'):
        raw_timetable = storage.get_timetable_history(login)
        timetable_summary = prepare_timetable_summary(raw_timetable, reference_date=ref_now.date())

    return MailSender.create_mail_content_for_student_report(
        metrics=metrics,
        template_type=clean_variant,
        timetable=timetable_summary,
    )


def build_daily_summary_html(
    storage: BaseStorage,
    login: str,
    config: dict,
    target_date: date | str | None = None,
    now: datetime | None = None,
) -> str:
    """Generuje gotowy HTML codziennego podsumowania (notyfikacje, terminarz, plan) dla wskazanego dnia."""
    grades = storage.get_grades_history(login) if hasattr(storage, 'get_grades_history') else []
    messages = storage.get_stored_messages(login) if hasattr(storage, 'get_stored_messages') else []
    notifications = storage.get_stored_notifications(login) if hasattr(storage, 'get_stored_notifications') else []
    timetable = storage.get_timetable_history(login) if hasattr(storage, 'get_timetable_history') else []
    schedule = storage.get_schedule_history(login) if hasattr(storage, 'get_schedule_history') else []

    if isinstance(target_date, str):
        try:
            sel_date = datetime.strptime(target_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            sel_date = now.date() if now else datetime.now().date()
    elif isinstance(target_date, date):
        sel_date = target_date
    elif now:
        sel_date = now.date()
    else:
        sel_date = datetime.now().date()

    ref_now = datetime.combine(sel_date, datetime.min.time().replace(hour=18, minute=0))

    timetable_summary = prepare_timetable_summary(timetable, reference_date=sel_date)
    day_offset = int(config.get('schedule_day_offset', 1))
    schedule_summary = prepare_schedule_summary(schedule, timetable_entries=timetable, now=ref_now, day_offset=day_offset)

    user_cfg = next((u for u in config.get('librus_users', []) if str(u.get('librus_login', '')) == str(login)), None)
    if user_cfg:
        user_cfg = dict(user_cfg)
    else:
        user_cfg = {'librus_login': str(login)}
    user_cfg['librus_login_name'] = resolve_student_name(config, storage, login)

    day_grades = [
        g for g in grades
        if (dt := parse_item_datetime(g)) and dt.date() == sel_date
    ]
    day_messages = [
        m for m in messages
        if (dt := parse_item_datetime(m)) and dt.date() == sel_date
    ]
    day_notifications = [
        n for n in notifications
        if (dt := parse_item_datetime(n)) and dt.date() == sel_date
    ]

    return MailSender.create_mail_content_for_summary(
        user_config=user_cfg,
        messages=day_messages,
        notifications=day_notifications,
        grades=day_grades,
        timetable=timetable_summary,
        schedule=schedule_summary,
    )

