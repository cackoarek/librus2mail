"""Główna aplikacja webowa Flask dla interfejsu Librus2mail."""

import argparse
import collections.abc
import functools
import hmac
import importlib.metadata
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    Flask,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from librus2mail.base_logger import setup_logging
from librus2mail.config import get_reports_schedules, read_config
from librus2mail.date_utils import parse_date_safe, parse_datetime_safe
from librus2mail.librus_collector import run_collector
from librus2mail.progress_report import run_progress_reports
from librus2mail.student_report import run_student_reports
from librus2mail.updates_notifier import run_notifier

from .auth import (
    LoginRateLimiter,
    auth_bp,
    get_client_ip,
    is_auth_enabled,
    is_authenticated,
    login_required,
)
from .services import (
    build_daily_summary_html,
    build_progress_report_html,
    build_schedule_day_context,
    build_student_report_html,
    calculate_certificate_summary,
    calculate_goal_optimizer,
    calculate_subject_averages,
    capture_action_execution,
    compute_educational_profile,
    compute_opportunity_matrix,
    compute_subject_stability_benchmark,
    format_human_timestamp,
    get_active_student_login,
    get_storage,
    get_student_dashboard_bundle,
    get_subject_detailed_analytics,
    list_students,
    resolve_student_name,
    save_config_yaml,
    simulate_new_grade,
    test_librus_credentials,
)

web_bp = Blueprint('web', __name__)
logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def get_app_version() -> str:
    """Pobiera dynamicznie wersję aplikacji (git tag -> package __version__ -> metadata)."""
    # 1. Próba odczytania najnowszego tagu z repozytorium git (jeśli uruchomiono w repozytorium git)
    try:
        repo_dir = Path(__file__).resolve().parents[3]
        if (repo_dir / ".git").exists() and shutil.which("git"):
            res = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip().lstrip("v")
    except (OSError, subprocess.SubprocessError):
        pass

    # 2. Odczyt __version__ z librus2mail (aktualizowane automatycznie w CI/CD przez release.yml)
    try:
        import librus2mail
        if hasattr(librus2mail, "__version__") and librus2mail.__version__:
            return str(librus2mail.__version__).lstrip("v")
    except ImportError:
        pass

    # 3. Próba odczytania z metadanych zainstalowanego pakietu (pip install / wheel)
    try:
        return importlib.metadata.version("librus2mail")
    except importlib.metadata.PackageNotFoundError:
        pass

    return "2.0.1"


FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs>
  <linearGradient id="g" x1="0%" y1="100%" x2="100%" y2="0%">
    <stop offset="0%" stop-color="#4f46e5"/>
    <stop offset="100%" stop-color="#0ea5e9"/>
  </linearGradient>
</defs>
<rect width="64" height="64" rx="16" fill="url(#g)"/>
<text x="32" y="34" font-size="34" text-anchor="middle" dominant-baseline="middle">🏫</text>
</svg>"""


@web_bp.route('/favicon.ico')
@web_bp.route('/favicon.svg')
def favicon_view():
    """Zwraca wektorowy favicon w barwach projektu Librus2mail."""
    return Response(FAVICON_SVG, mimetype='image/svg+xml')


def get_or_create_persistent_secret_key(storage_dir: str | Path) -> str:
    """Zwraca lub tworzy trwały klucz SECRET_KEY zapisany w katalogu storage/."""
    key_path = Path(storage_dir) / ".secret_key"
    try:
        if key_path.is_file():
            content = key_path.read_text(encoding="utf-8").strip()
            if len(content) >= 16:
                return content
        new_key = secrets.token_hex(32)
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text(new_key, encoding="utf-8")
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
        return new_key
    except OSError as e:
        logger.warning(f"Nie udało się zapisać trwałego klucza sesji w {key_path}: {e}")
        return secrets.token_hex(32)


def generate_csrf_token() -> str:
    """Generuje i przechowuje token CSRF w bieżącej sesji użytkownika."""
    if current_app and current_app.config.get('STATIC_CSRF_TOKEN'):
        return str(current_app.config['STATIC_CSRF_TOKEN'])
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_hex(32)
        session['_csrf_token'] = token
    return token


def inject_common_context():
    """Wstrzykuje wspólne zmienne do wszystkich szablonów panelu webowego."""
    auth_enabled = is_auth_enabled()
    authenticated = is_authenticated()
    can_access = not auth_enabled or authenticated

    config = getattr(request, 'app_config', {})
    storage = getattr(request, 'app_storage', None)
    students = list_students(config, storage) if (storage and can_access) else []
    active_login = (
        get_active_student_login(config, storage, session_login=session.get('active_student_login'))
        if (storage and can_access)
        else None
    )
    active_student = next((s for s in students if s['login'] == active_login), (students[0] if students else None))

    now = getattr(request, 'app_actual_date', None) or datetime.now()
    csrf_val = generate_csrf_token()

    raw_storage = getattr(current_app, 'config', {}).get('STORAGE') if current_app else None
    if not raw_storage and hasattr(storage, 'parent_storage'):
        raw_storage = storage.parent_storage
    elif not raw_storage:
        raw_storage = storage

    archived_years = (
        raw_storage.list_archived_years(active_login)
        if (raw_storage and active_login and hasattr(raw_storage, 'list_archived_years'))
        else []
    )
    is_archive_mode = bool(getattr(request, 'is_archive_mode', False))
    active_school_year = getattr(request, 'app_active_school_year', None)

    return {
        'all_students': students,
        'active_student': active_student,
        'active_login': active_login,
        'is_auth_enabled': auth_enabled,
        'is_authenticated': authenticated,
        'now': now,
        'app_version': get_app_version(),
        'csrf_token': csrf_val,
        'get_csrf_token': generate_csrf_token,
        'is_archive_mode': is_archive_mode,
        'active_school_year': active_school_year,
        'archived_years': archived_years,
    }



@web_bp.route('/student/<login>')
@login_required
def switch_student(login: str):
    """Zmienia aktywnego ucznia w sesji użytkownika."""
    session['active_student_login'] = str(login)
    flash(f"Przełączono aktywny profil ucznia na konto {login}.", "info")
    next_url = request.args.get('next') or url_for('web.dashboard')
    return redirect(next_url)


@web_bp.route('/school-year/switch')
@login_required
def switch_school_year():
    """Przełącza aktywny rok szkolny (bieżący vs zarchiwizowany)."""
    year = request.args.get('year', '').strip()
    if not year or year.lower() in ('current', 'biezacy', 'bieżący'):
        session.pop('active_school_year', None)
        flash("Powrócono do bieżącego roku szkolnego.", "info")
    else:
        session['active_school_year'] = year
        flash(f"Przełączono widok na zarchiwizowany rok szkolny: {year} (tryb tylko do odczytu).", "warning")
    next_url = request.args.get('next') or url_for('web.dashboard')
    return redirect(next_url)


@web_bp.route('/actions/archive-year', methods=['POST'])
@login_required
def action_archive_year():
    """Archiwizuje bieżący rok szkolny dla aktywnego profilu ucznia (lub wszystkich dzieci)."""
    if getattr(request, 'is_archive_mode', False):
        flash("Nie można archiwizować z poziomu widoku archiwalnego.", "error")
        return redirect(url_for('web.settings_view'))

    config = request.app_config
    raw_storage = current_app.config['STORAGE']
    active_login = get_active_student_login(config, raw_storage, session_login=session.get('active_student_login'))
    if not active_login:
        flash("Brak aktywnego profilu ucznia do zarchiwizowania.", "error")
        return redirect(url_for('web.settings_view'))

    year_label = request.form.get('school_year_label', '').strip()
    if not year_label:
        now = getattr(request, 'app_actual_date', None) or datetime.now()
        year_label = f"{now.year - 1}/{now.year}"

    all_students = list_students(config, raw_storage)
    archive_all = bool(request.form.get('archive_all_students')) and len(all_students) > 1

    targets = all_students if archive_all else [s for s in all_students if s['login'] == active_login]
    if not targets:
        targets = [{'login': active_login, 'name': active_login}]

    archived_names = []
    try:
        for st in targets:
            s_login = st['login']
            s_name = st.get('name') or s_login
            raw_storage.archive_school_year(s_login, year_label)
            archived_names.append(s_name)

        if archive_all and len(targets) > 1:
            names_str = ", ".join(f"'{name}'" for name in archived_names)
            flash(
                f"Pomyślnie zarchiwizowano rok szkolny {year_label} jednocześnie dla wszystkich dzieci: {names_str}. "
                f"Rozpoczęto czysty nowy rok szkolny.",
                "success",
            )
        else:
            active_name = archived_names[0] if archived_names else active_login
            other_students = [s for s in all_students if s['login'] != active_login]
            if other_students:
                other_names = ", ".join(f"'{s['name']}'" for s in other_students)
                flash(
                    f"Pomyślnie zarchiwizowano rok szkolny {year_label} dla ucznia '{active_name}'. "
                    f"Pamiętaj: operacja dotyczyła wyłącznie tego profilu. Przełącz ucznia w menu i powtórz archiwizację dla pozostałych dzieci ({other_names}) "
                    f"lub zaznacz opcję archiwizacji dla wszystkich dzieci.",
                    "success",
                )
            else:
                flash(
                    f"Pomyślnie zarchiwizowano rok szkolny {year_label} dla ucznia '{active_name}'. Rozpoczęto czysty nowy rok szkolny.",
                    "success",
                )
    except Exception as e:
        logger.error(f"Błąd archiwizacji roku szkolnego dla {active_login}: {e}", exc_info=True)
        flash(f"Błąd podczas archiwizacji: {e}", "error")

    return redirect(url_for('web.settings_view'))


@web_bp.route('/')
@login_required
def dashboard():
    """Główny pulpit rodzica - podsumowanie dnia i najważniejsze alerty."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    if not active_login:
        return render_template('web/dashboard.html', error="Brak skonfigurowanych uczniów w systemie.")

    ref_now = request.app_actual_date or datetime.now()
    data = get_student_dashboard_bundle(storage, active_login, config, now=ref_now)

    requested_date = request.args.get('date', '').strip()
    sched_ctx = build_schedule_day_context(
        all_lessons=data.get('all_schedule', []),
        timetable_entries=data.get('all_timetable', []),
        ref_now=ref_now,
        requested_date=requested_date,
        attendance_entries=data.get('attendance_history', []),
    )

    if sched_ctx['selected_day']:
        data['schedule_summary'] = sched_ctx['selected_day']

    return render_template('web/dashboard.html', data=data, sched_ctx=sched_ctx)


@web_bp.route('/plan')
@login_required
def schedule_view():
    """Widok planu lekcji z inteligentnym wyborem bieżącego/najbliższego dnia nauki."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    ref_now = request.app_actual_date or datetime.now()
    data = get_student_dashboard_bundle(storage, active_login, config, now=ref_now)

    requested_date = request.args.get('date', '').strip()
    sched_ctx = build_schedule_day_context(
        all_lessons=data.get('all_schedule', []),
        timetable_entries=data.get('all_timetable', []),
        ref_now=ref_now,
        requested_date=requested_date,
        attendance_entries=data.get('attendance_history', []),
    )

    view_mode = request.args.get('view', 'day').strip()
    if view_mode not in ('day', 'all'):
        view_mode = 'day'

    return render_template(
        'web/schedule.html',
        data=data,
        days_data=sched_ctx['days_data'],
        selected_day=sched_ctx['selected_day'],
        selected_date=sched_ctx['selected_date'],
        default_target_date=sched_ctx['default_target_date'],
        today_date=sched_ctx['today_date'],
        lessons_ongoing=sched_ctx['lessons_ongoing'],
        is_before_lessons=sched_ctx['is_before_lessons'],
        lessons_finished=sched_ctx['lessons_finished'],
        target_reason=sched_ctx['target_reason'],
        prev_date=sched_ctx['prev_date'],
        next_date=sched_ctx['next_date'],
        view_mode=view_mode,
        sched_ctx=sched_ctx,
        sorted_dates=sched_ctx['sorted_dates'],
    )


@web_bp.route('/oceny')
@login_required
def grades_view():
    """Widok zestawienia ocen z kalkulatorem średniej i optymalizatorem celu."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    excluded_subjects = storage.get_excluded_certificate_subjects(active_login) if hasattr(storage, 'get_excluded_certificate_subjects') else []
    all_subjects = storage.get_subjects(active_login) if hasattr(storage, 'get_subjects') else []
    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    raw_sem = (request.args.get('semester') or request.args.get('semestr') or 'all').strip().lower()
    if raw_sem in ('sem1', '1', 'i'):
        active_semester = 'sem1'
    elif raw_sem in ('sem2', '2', 'ii'):
        active_semester = 'sem2'
    else:
        active_semester = 'all'

    sem_split_cfg = config.get('semester_split_date')
    annual_algo_cfg = config.get('annual_grade_algorithm', 'all_year_weighted')

    grades = storage.get_grades_history(active_login) if hasattr(storage, 'get_grades_history') else []
    subject_averages = calculate_subject_averages(
        grades,
        excluded_subjects=excluded_subjects,
        all_subjects=all_subjects,
        semester=active_semester,
        semester_split_date=sem_split_cfg,
        ref_date=request.app_actual_date,
        annual_grade_algorithm=annual_algo_cfg,
    )
    certificate_summary = calculate_certificate_summary(subject_averages, excluded_subjects=excluded_subjects)

    raw_tab = (request.args.get('tab') or '').strip().lower()
    if raw_tab in ('swiadectwo', 'świadectwo'):
        active_tab = 'swiadectwo'
    elif raw_tab in ('optymalizator', 'cel', 'symulator', 'simulator'):
        active_tab = 'optymalizator'
    else:
        active_tab = 'oceny'

    target_param = request.args.get('target')
    target_val = None
    if target_param:
        try:
            target_val = float(str(target_param).replace(',', '.'))
            if not (1.0 <= target_val <= 6.0):
                target_val = None
        except (ValueError, TypeError):
            target_val = None

    goal_optimizer = calculate_goal_optimizer(subject_averages, target_avg=target_val)

    return render_template(
        'web/grades.html',
        data=data,
        subject_averages=subject_averages,
        certificate_summary=certificate_summary,
        active_tab=active_tab,
        active_semester=active_semester,
        semester_split_date=sem_split_cfg,
        annual_grade_algorithm=annual_algo_cfg,
        excluded_subjects=excluded_subjects,
        goal_optimizer=goal_optimizer,
    )


@web_bp.route('/oceny/<path:subject_name>')
@web_bp.route('/przedmiot/<path:subject_name>')
@login_required
def subject_detail_view(subject_name: str):
    """Szczegółowy widok ocen z danego przedmiotu ze statystykami, celem, ryzykiem i wykresem trajektorii."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    excluded_subjects = storage.get_excluded_certificate_subjects(active_login) if hasattr(storage, 'get_excluded_certificate_subjects') else []
    grades = storage.get_grades_history(active_login) if hasattr(storage, 'get_grades_history') else []
    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)

    analytics = get_subject_detailed_analytics(
        grades,
        subject_name,
        excluded_subjects=excluded_subjects,
        semester_split_date=config.get('semester_split_date'),
        ref_date=request.app_actual_date,
    )

    return render_template(
        'web/subject_detail.html',
        data=data,
        analytics=analytics,
        subject_name=subject_name,
        excluded_subjects=excluded_subjects,
    )


@web_bp.route('/terminarz')
@login_required
def timetable_view():
    """Widok nadchodzących sprawdzianów, nieobecności nauczycieli oraz kroniki kalendarium."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    req_view = (request.args.get('view') or request.args.get('tab') or 'upcoming').lower()
    initial_view = 'chronicle' if req_view in ('chronicle', 'kalendarium', 'kronika') else 'upcoming'

    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    return render_template('web/timetable.html', data=data, initial_view=initial_view)


@web_bp.route('/kalendarium')
@login_required
def kalendarium_redirect():
    """Skrót/przekierowanie bezpośrednio do widoku pełnego kalendarium (kroniki) w terminarzu."""
    return redirect(url_for('web.timetable_view', view='chronicle'))


@web_bp.route('/attendance')
@web_bp.route('/frekwencja')
@login_required
def attendance_view():
    """Widok frekwencji, obecności i spóźnień ucznia."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    req_view = request.args.get('view') or request.args.get('mode')
    cfg_view = (
        config.get('attendance_view_mode')
        or (config.get('web') or {}).get('attendance_view_mode')
        or 'heatmap'
    )
    view_mode = req_view if req_view in ('heatmap', 'month') else cfg_view
    if view_mode not in ('heatmap', 'month'):
        view_mode = 'heatmap'

    req_month = request.args.get('month')

    data = get_student_dashboard_bundle(
        storage,
        active_login,
        config,
        now=request.app_actual_date,
        attendance_view_mode=view_mode,
        attendance_selected_month=req_month,
    )
    return render_template('web/attendance.html', data=data)


@web_bp.route('/api/attendance/view-mode', methods=['POST'])
@login_required
def api_attendance_view_mode():
    """Zapisuje preferowany tryb widoku kalendarza frekwencji (heatmap / month) w config.yaml."""
    data = request.get_json(silent=True) or {}
    mode = (request.form.get('mode') or data.get('mode') or '').strip().lower()
    if mode not in ('heatmap', 'month'):
        return jsonify({'success': False, 'message': 'Nieprawidłowy tryb widoku (dozwolone: heatmap, month).'}), 400

    config_path = getattr(request, 'app_config_path', None) or current_app.config.get('CONFIG_PATH') or 'config.yaml'
    try:
        raw_config = read_config(config_path).to_dict() if hasattr(read_config(config_path), 'to_dict') else dict(read_config(config_path))
    except Exception:
        raw_config = {}

    raw_config['attendance_view_mode'] = mode
    if 'web' in raw_config and isinstance(raw_config['web'], dict):
        raw_config['web']['attendance_view_mode'] = mode

    try:
        save_config_yaml(raw_config, config_path)
        current_app.config['APP_CONFIG'] = read_config(config_path)
        return jsonify({'success': True, 'mode': mode, 'message': f'Zapisano tryb widoku: {mode}'})
    except Exception as e:
        logger.error(f"Nie udało się zapisać trybu widoku frekwencji do {config_path}: {e}")
        return jsonify({'success': False, 'message': f'Błąd zapisu konfiguracji: {e}'}), 500


@web_bp.route('/wiadomosci')
@login_required
def messages_view():
    """Widok wiadomości i ogłoszeń szkolnych."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    return render_template('web/messages.html', data=data)


@web_bp.route('/raporty')
@web_bp.route('/raporty/<report_type>')
@login_required
def reports_view(report_type: str = 'podsumowanie'):
    """Widok analityczny i motywacyjny z raportami postępów, ucznia, szans, profilu i stabilności."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    valid_types = ('podsumowanie', 'postepy', 'uczen', 'szanse', 'profil', 'stabilnosc')
    if report_type not in valid_types:
        report_type = 'podsumowanie'

    variant = request.args.get('variant', 'teens').strip().lower()
    if variant not in ('kids', 'teens', 'youth'):
        variant = 'teens'

    days_param = request.args.get('days')
    if days_param and days_param.isdigit():
        days = max(1, int(days_param))
    else:
        days = 7

    ref_now = request.app_actual_date or datetime.now()
    default_date = ref_now.date()
    default_date_str = default_date.strftime("%Y-%m-%d")

    date_param = request.args.get('date')
    selected_date = parse_date_safe(date_param) if date_param else default_date
    if not selected_date:
        selected_date = default_date

    selected_date_str = selected_date.strftime("%Y-%m-%d")
    prev_date_str = (selected_date - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date_str = (selected_date + timedelta(days=1)).strftime("%Y-%m-%d")

    student_name = resolve_student_name(config, storage, active_login) if active_login else "Uczeń"

    # Dane analityczne dla zaawansowanych raportów międzyprzedmiotowych
    opportunities_data = None
    profile_data = None
    stability_data = None

    if active_login and report_type in ('szanse', 'profil', 'stabilnosc'):
        excluded_subjects = storage.get_excluded_certificate_subjects(active_login) if hasattr(storage, 'get_excluded_certificate_subjects') else []
        all_subjects = storage.get_subjects(active_login) if hasattr(storage, 'get_subjects') else []
        grades = storage.get_grades_history(active_login) if hasattr(storage, 'get_grades_history') else []
        subject_averages = calculate_subject_averages(
            grades,
            excluded_subjects=excluded_subjects,
            all_subjects=all_subjects,
            semester_split_date=config.get('semester_split_date'),
            annual_grade_algorithm=config.get('annual_grade_algorithm', 'all_year_weighted'),
            ref_date=request.app_actual_date,
        )

        if report_type == 'szanse':
            opportunities_data = compute_opportunity_matrix(subject_averages)
        elif report_type == 'profil':
            user_overrides = storage.get_subject_categories(active_login) if hasattr(storage, 'get_subject_categories') else {}
            profile_data = compute_educational_profile(subject_averages, user_overrides=user_overrides)
        elif report_type == 'stabilnosc':
            stability_data = compute_subject_stability_benchmark(subject_averages, grades)

    report_html = ""
    if not active_login:
        report_html = (
            '<div class="py-16 text-center bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">'
            '<h3 class="text-lg font-bold text-slate-800 mb-1">Brak skonfigurowanych uczniów w systemie</h3>'
            '</div>'
        )
    elif report_type == 'podsumowanie':
        report_html = build_daily_summary_html(
            storage=storage,
            login=active_login,
            config=config,
            target_date=selected_date,
            now=ref_now,
        )
    elif report_type == 'postepy':
        report_html = build_progress_report_html(
            storage=storage,
            login=active_login,
            config=config,
            days=days,
            now=ref_now,
        )
    elif report_type == 'uczen':
        report_html = build_student_report_html(
            storage=storage,
            login=active_login,
            config=config,
            variant=variant,
            days=days,
            now=ref_now,
        )

    return render_template(
        'web/reports.html',
        active_tab=report_type,
        active_variant=variant,
        days=days,
        report_html=report_html,
        student_name=student_name,
        active_login=active_login,
        selected_date_str=selected_date_str,
        default_date_str=default_date_str,
        prev_date_str=prev_date_str,
        next_date_str=next_date_str,
        opportunities_data=opportunities_data,
        profile_data=profile_data,
        stability_data=stability_data,
    )


@web_bp.route('/akcje')
@login_required
def actions_view():
    """Centrum operacyjne - graficzny pulpit dla skryptów z docs/useful-scripts.md."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    return render_template('web/actions.html', data=data)


# ------------------------------------------------------------------------------
# ENDPOINTY API / AKCJI (HTMX & JSON)
# ------------------------------------------------------------------------------

@web_bp.route('/api/whatif', methods=['POST'])
@login_required
def api_whatif():
    """Kalkulator 'Co jeśli?' dla oceny (zwraca fragment HTMX lub JSON)."""
    storage = request.app_storage
    active_login = get_active_student_login(request.app_config, storage, session_login=session.get('active_student_login'))

    subject = request.form.get('subject', '').strip()
    try:
        new_grade = float(request.form.get('grade', 5.0))
        new_weight = float(request.form.get('weight', 1.0))
        if not (1.0 <= new_grade <= 6.0) or not (0.01 <= new_weight <= 100.0):
            return "<div class='text-red-500 text-sm'>Ocena musi być w przedziale 1–6, a waga dodatnia.</div>", 400
    except (ValueError, TypeError):
        return "<div class='text-red-500 text-sm'>Nieprawidłowa wartość oceny lub wagi.</div>", 400

    grades = storage.get_grades_history(active_login) if hasattr(storage, 'get_grades_history') else []
    sim = simulate_new_grade(grades, subject, new_grade, new_weight)

    old_str = f"{sim['old_avg']:.2f}" if sim['old_avg'] is not None else "brak"
    new_str = f"{sim['new_avg']:.2f}"
    diff_val = sim['diff']
    diff_badge = (
        f"<span class='text-emerald-700 font-bold bg-emerald-100 px-2 py-0.5 rounded'>+{diff_val:.2f}</span>"
        if diff_val >= 0
        else f"<span class='text-rose-700 font-bold bg-rose-100 px-2 py-0.5 rounded'>{diff_val:.2f}</span>"
    )

    html = f"""
    <div class="p-3 bg-indigo-50 border border-indigo-200 rounded-lg text-sm text-indigo-950 flex items-center justify-between">
        <div>
            <strong>Przedmiot:</strong> {sim['subject']}<br>
            <span class="text-xs text-indigo-700">Symulowana ocena: <strong>{new_grade:g}</strong> (waga: {new_weight:g})</span>
        </div>
        <div class="text-right">
            <span class="text-xs text-slate-500">Dotychczas: {old_str}</span> ➔ <strong>Nowa średnia: {new_str}</strong> ({diff_badge})
        </div>
    </div>
    """
    return html


@web_bp.route('/api/grade/update', methods=['POST'])
@login_required
def api_grade_update():
    """Ręczna edycja wartości i/lub wagi oceny."""
    storage = request.app_storage
    active_login = get_active_student_login(request.app_config, storage, session_login=session.get('active_student_login'))

    grade_id = request.form.get('grade_id', '').strip()
    new_grade = request.form.get('grade', '').strip()
    raw_weight = request.form.get('weight', '').strip()

    if not grade_id or not new_grade:
        return jsonify({'success': False, 'message': 'Brak identyfikatora oceny lub wartości oceny.'}), 400

    try:
        w_val = float(raw_weight.replace(',', '.'))
        if w_val < 0:
            return jsonify({'success': False, 'message': 'Waga nie może być ujemna.'}), 400
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Wprowadź prawidłową wagę (liczbę).'}), 400

    formatted_weight = f"{w_val:g}"

    if hasattr(storage, 'update_grade_custom'):
        res = storage.update_grade_custom(active_login, grade_id, new_grade, formatted_weight)
        if not res:
            return jsonify({'success': False, 'message': 'Nie znaleziono oceny w bazie.'}), 404
        return jsonify({'success': True, 'message': f'Ocena została zaktualizowana (ocena: {new_grade}, waga: {formatted_weight}).'})

    return jsonify({'success': False, 'message': 'Magazyn danych nie obsługuje edycji ocen.'}), 500


@web_bp.route('/api/grade/reset', methods=['POST'])
@login_required
def api_grade_reset():
    """Przywrócenie oryginalnej oceny i wagi ze szkoły z Librusa."""
    storage = request.app_storage
    active_login = get_active_student_login(request.app_config, storage, session_login=session.get('active_student_login'))

    grade_id = request.form.get('grade_id', '').strip()
    if not grade_id:
        return jsonify({'success': False, 'message': 'Brak identyfikatora oceny.'}), 400

    if hasattr(storage, 'reset_grade_custom'):
        res = storage.reset_grade_custom(active_login, grade_id)
        if not res:
            return jsonify({'success': False, 'message': 'Nie znaleziono oceny w bazie.'}), 404
        return jsonify({'success': True, 'message': 'Przywrócono oryginalne dane oceny ze szkoły.'})

    return jsonify({'success': False, 'message': 'Magazyn danych nie obsługuje resetowania ocen.'}), 500


@web_bp.route('/api/subject/toggle-certificate', methods=['POST'])
@login_required
def api_subject_toggle_certificate():
    """Włącza lub wyklucza przedmiot z liczenia średniej do świadectwa."""
    storage = request.app_storage
    active_login = get_active_student_login(request.app_config, storage, session_login=session.get('active_student_login'))

    subject = request.form.get('subject', '').strip()
    included_raw = request.form.get('included', 'true').strip().lower()
    included = included_raw in ('true', '1', 'yes', 'on')

    if not subject:
        return jsonify({'success': False, 'message': 'Brak nazwy przedmiotu.'}), 400

    if hasattr(storage, 'set_subject_certificate_inclusion'):
        new_excluded = storage.set_subject_certificate_inclusion(active_login, subject, included=included)
        status_msg = "włączony do" if included else "wykluczony ze"
        return jsonify({
            'success': True,
            'subject': subject,
            'included': included,
            'excluded_subjects': new_excluded,
            'message': f'Przedmiot "{subject}" został {status_msg} średniej ze świadectwa.',
        })

    return jsonify({'success': False, 'message': 'Magazyn danych nie obsługuje wykluczania przedmiotów.'}), 500


@web_bp.route('/api/subject/set-category', methods=['POST'])
@login_required
def api_subject_set_category():
    """Zmienia kategorię edukacyjną przypisaną do przedmiotu."""
    storage = request.app_storage
    active_login = get_active_student_login(request.app_config, storage, session_login=session.get('active_student_login'))

    data = request.get_json(silent=True) or {}
    subject = (request.form.get('subject') or data.get('subject') or '').strip()
    category = (request.form.get('category') or data.get('category') or '').strip().lower()

    if not subject:
        return jsonify({'success': False, 'message': 'Brak nazwy przedmiotu.'}), 400

    if hasattr(storage, 'set_subject_category'):
        updated_cats = storage.set_subject_category(active_login, subject, category_key=category)
        return jsonify({
            'success': True,
            'subject': subject,
            'category': category,
            'categories': updated_cats,
            'message': f'Zaktualizowano kategorię dla przedmiotu "{subject}".',
        })

    return jsonify({'success': False, 'message': 'Magazyn danych nie obsługuje kategorii przedmiotów.'}), 500


@web_bp.route('/api/action/sync', methods=['POST'])
@login_required
def action_sync():
    """Wyzwalacz: Pobierz świeże dane z Librusa (collector --sync-only --once)."""
    config_path = request.app_config_path
    storage_dir = request.app_storage_dir
    login = request.form.get('login') or session.get('active_student_login')

    success, output, _ = capture_action_execution(
        run_collector,
        config_path=config_path,
        storage_dir=storage_dir,
        user_filter=login,
        sync_only=True,
        once=True,
        offline=False,
    )

    status_icon = "✅" if success else "❌"
    msg = f"{status_icon} Synchronizacja konta {login} zakończona ({'sukces' if success else 'błąd'})."
    return render_template('web/action_result.html', title=msg, success=success, output=output)


@web_bp.route('/api/action/notify', methods=['POST'])
@login_required
def action_notify():
    """Wyzwalacz: Wyślij powiadomienie e-mail (updates_notifier)."""
    config_path = request.app_config_path
    storage_dir = request.app_storage_dir
    login = request.form.get('login') or session.get('active_student_login')
    try:
        days = max(1, min(365, int(request.form.get('days', 1))))
    except (ValueError, TypeError):
        days = 1
    is_summary = request.form.get('summary') == '1'
    dry_run = request.form.get('dry_run') == '1'

    success, output, _ = capture_action_execution(
        run_notifier,
        config_path=config_path,
        storage_dir=storage_dir,
        user_filter=login,
        days=days,
        summary=is_summary,
        dry_run=dry_run,
        offline=True,
    )

    status_icon = "✅" if success else "❌"
    mode_str = " (tryb symulacji dry-run)" if dry_run else ""
    msg = f"{status_icon} Generowanie powiadomienia{mode_str} dla {login} zakończone."
    return render_template('web/action_result.html', title=msg, success=success, output=output)


@web_bp.route('/api/action/progress-report', methods=['POST'])
@login_required
def action_progress_report():
    """Wyzwalacz: Wygeneruj raport postępów ucznia."""
    config_path = request.app_config_path
    storage_dir = request.app_storage_dir
    login = request.form.get('login') or session.get('active_student_login')
    try:
        days = max(1, min(365, int(request.form.get('days', 7))))
    except (ValueError, TypeError):
        days = 7

    success, output, _ = capture_action_execution(
        run_progress_reports,
        config_path=config_path,
        storage_dir=storage_dir,
        user_filter=login,
        days=days,
        force=True,
    )

    status_icon = "✅" if success else "❌"
    msg = f"{status_icon} Generowanie raportu postępów dla {login} zakończone."
    return render_template('web/action_result.html', title=msg, success=success, output=output)


@web_bp.route('/api/action/student-report', methods=['POST'])
@login_required
def action_student_report():
    """Wyzwalacz: Wygeneruj raport motywacyjny ucznia."""
    config_path = request.app_config_path
    storage_dir = request.app_storage_dir
    login = request.form.get('login') or session.get('active_student_login')
    template_name = request.form.get('template', 'kids')
    if template_name not in ('kids', 'teens', 'youth'):
        template_name = 'kids'
    try:
        days = max(1, min(365, int(request.form.get('days', 7))))
    except (ValueError, TypeError):
        days = 7

    success, output, _ = capture_action_execution(
        run_student_reports,
        config_path=config_path,
        storage_dir=storage_dir,
        user_filter=login,
        template_name=template_name,
        days=days,
    )

    status_icon = "✅" if success else "❌"
    msg = f"{status_icon} Generowanie raportu ucznia ({template_name}) dla {login} zakończone."
    return render_template('web/action_result.html', title=msg, success=success, output=output)


# ------------------------------------------------------------------------------
# KREATOR PIERWSZEGO URUCHOMIENIA & PANEL USTAWIEŃ (SETUP & SETTINGS)
# ------------------------------------------------------------------------------

def _has_valid_config(app_config: Any) -> bool:
    """Sprawdza, czy konfiguracja zawiera co najmniej jedno aktywne konto ucznia."""
    if not isinstance(app_config, (dict, collections.abc.Mapping)):
        return False
    users = app_config.get('librus_users', [])
    return isinstance(users, list) and len(users) > 0 and any(u.get('librus_login') for u in users)


def parse_schedule_from_form(form: Any, existing_schedule: dict[str, Any] | None = None) -> tuple[dict[str, Any], int]:
    """Parsuje harmonogram z formularza WWW i zwraca (schedule_dict, wait_time_s)."""
    existing_sched = existing_schedule or {}
    existing_col = existing_sched.get('collection', {})

    col_mode = form.get('collection_mode', existing_col.get('mode', 'daily'))
    col_time = form.get('collection_time', existing_col.get('time', '16:00')).strip()
    col_days = form.get('collection_days', existing_col.get('days', 'all')).strip()
    try:
        col_interval = int(form.get('collection_interval_hours', existing_col.get('interval_hours', 1)))
    except (ValueError, TypeError):
        col_interval = 1

    # Parsowanie wielu harmonogramów raportów postępów
    report_indices = sorted(list({
        int(k.split('_')[-1])
        for k in form.keys()
        if (k.startswith('report_name_') or k.startswith('report_frequency_') or k.startswith('report_interval_days_') or k.startswith('report_enabled_'))
        and k.split('_')[-1].isdigit()
    }))

    reports_list: list[dict[str, Any]] = []
    for idx in report_indices:
        r_name = form.get(f'report_name_{idx}', f'Raport #{idx + 1}').strip() or f'Raport #{idx + 1}'
        r_enabled = f'report_enabled_{idx}' in form
        r_freq = form.get(f'report_frequency_{idx}', 'weekly').strip()
        r_weekday = form.get(f'report_weekday_{idx}', 'friday').strip()
        r_dom_raw = form.get(f'report_day_of_month_{idx}', '1').strip()
        r_dom = int(r_dom_raw) if r_dom_raw.isdigit() else r_dom_raw
        r_time = form.get(f'report_time_{idx}', '17:00').strip()
        try:
            r_days = int(form.get(f'report_interval_days_{idx}', 7))
        except (ValueError, TypeError):
            r_days = 7

        rep_entry = {
            'name': r_name,
            'enabled': bool(r_enabled),
            'frequency': r_freq,
            'time': r_time,
            'interval_days': r_days,
        }
        if r_freq == 'monthly':
            rep_entry['day_of_month'] = r_dom
        else:
            rep_entry['weekday'] = r_weekday
        reports_list.append(rep_entry)

    # Kompatybilność wsteczna z pojedynczymi polami legacy
    if not reports_list and ('reports_enabled' in form or 'reports_weekday' in form or 'reports_time' in form or 'reports_interval_days' in form):
        r_enabled = 'reports_enabled' in form
        r_weekday = form.get('reports_weekday', 'friday').strip()
        r_time = form.get('reports_time', '17:00').strip()
        try:
            r_days = int(form.get('reports_interval_days', 7))
        except (ValueError, TypeError):
            r_days = 7
        reports_list.append({
            'name': 'Raport tygodniowy',
            'enabled': bool(r_enabled),
            'frequency': 'weekly',
            'weekday': r_weekday,
            'day_of_month': 1,
            'time': r_time,
            'interval_days': r_days,
        })

    # Jeśli nic nie przesłano w formularzu, zachowaj istniejące raporty
    if not reports_list and existing_sched.get('reports'):
        reports_list = get_reports_schedules(existing_sched)

    if col_mode == 'interval':
        col_cfg = {
            'mode': 'interval',
            'interval_hours': col_interval,
        }
    else:
        col_cfg = {
            'mode': 'daily',
            'time': col_time,
            'days': col_days,
        }

    sched_cfg = {
        'collection': col_cfg,
        'reports': reports_list,
    }

    if col_mode == 'interval':
        wait_time_s = max(300, col_interval * 3600)
    else:
        wait_time_s = 3600

    if 'wait_time_s' in form and 'collection_mode' not in form:
        try:
            wait_time_s = max(300, int(form['wait_time_s']))
        except (ValueError, TypeError):
            pass

    return sched_cfg, wait_time_s


@web_bp.route('/setup')
def setup_view():
    """Kreator pierwszego uruchomienia w kolejnych krokach (gdy brak config.yaml)."""
    config = getattr(request, 'app_config', {})
    if _has_valid_config(config):
        # Jeśli konfiguracja już istnieje, przekieruj do edycji ustawień lub pulpitu
        return redirect(url_for('web.settings_view'))
    return render_template('web/setup.html')


@web_bp.route('/setup', methods=['POST'])
def setup_submit():
    """Zapisuje dane zebrane przez kreator do pliku config.yaml i aktywuje system."""
    form = request.form
    config_path = request.app_config_path or 'config.yaml'

    # 1. Zbieranie kont uczniów
    students: list[dict[str, Any]] = []
    # Wyciągamy indeksy z pól student_login_X
    indices = sorted(list({
        int(k.split('_')[-1])
        for k in form.keys()
        if k.startswith('student_login_') and k.split('_')[-1].isdigit()
    }))

    for idx in indices:
        login = form.get(f'student_login_{idx}', '').strip()
        pwd = form.get(f'student_password_{idx}', '').strip()
        name = form.get(f'student_name_{idx}', '').strip() or f"Uczeń {login}"
        receivers_raw = form.get(f'student_receivers_{idx}', '').strip()
        receivers = [r.strip() for r in receivers_raw.split(',') if r.strip()]

        if login and pwd:
            global_one_summary = (form.get('one_summary_message', '1') == '1')
            if f'student_one_summary_present_{idx}' in form:
                is_one_summary = (f'student_one_summary_{idx}' in form)
            elif f'student_one_summary_{idx}' in form:
                is_one_summary = True
            else:
                is_one_summary = global_one_summary

            st_cfg: dict[str, Any] = {
                'librus_login_name': name,
                'librus_login': login,
                'librus_password': pwd,
                'read_messages': f'student_messages_{idx}' in form,
                'read_grades': f'student_grades_{idx}' in form,
                'read_timetable': f'student_timetable_{idx}' in form,
                'read_schedule': f'student_schedule_{idx}' in form,
                'schedule_day_offset': int(form.get('schedule_day_offset', 1)),
                'one_summary_message': is_one_summary,
                'notification_receivers': receivers or [form.get('mail_login', '').strip()],
            }
            if f'student_report_enabled_{idx}' in form:
                st_email = form.get(f'student_report_email_{idx}', '').strip()
                st_template = form.get(f'student_report_template_{idx}', 'kids').strip()
                if st_template not in ('kids', 'teens', 'youth'):
                    st_template = 'kids'
                st_cfg['student_report'] = {
                    'enabled': True,
                    'email': st_email or (receivers[0] if receivers else form.get('mail_login', '').strip()),
                    'template': st_template,
                }
            students.append(st_cfg)

    if not students:
        flash("Musisz podać co najmniej jedno konto ucznia w Librusie (login i hasło).", "error")
        return redirect(url_for('web.setup_view'))

    # 2. Poczta
    mail_provider = form.get('mail_provider', 'gmail')
    mail_login = form.get('mail_login', '').strip()
    gmail_auth_mode = form.get('gmail_auth_mode', 'app_password')
    gmail_oauth2_file = form.get('gmail_oauth2_file', '').strip()
    mail_pwd = form.get('mail_password', '').strip()

    mail_cfg: dict[str, Any] = {
        'login': mail_login,
        'use_gmail': (mail_provider == 'gmail'),
    }
    if mail_provider == 'gmail':
        if gmail_auth_mode == 'oauth2' and gmail_oauth2_file:
            mail_cfg['oauth2_file'] = gmail_oauth2_file
        else:
            mail_cfg['password'] = mail_pwd
    elif mail_provider == 'smtp':
        mail_cfg['password'] = mail_pwd
        mail_cfg['non_gmail_settings'] = {
            'smtp_host': form.get('smtp_host', 'smtp.example.com').strip(),
            'port': int(form.get('smtp_port', 587)),
        }

    # 3. Harmonogram i automatyzacja
    sched_cfg, wait_time_s = parse_schedule_from_form(form)

    # 4. Parametry ogólne i panel WWW
    web_password = form.get('web_password', '').strip() or None
    web_port = int(form.get('web_port', 5000))
    web_host = form.get('web_host', '127.0.0.1').strip()

    full_config: dict[str, Any] = {
        'librus_users': students,
        'delay_between_users_s': int(form.get('delay_between_users_s', 10)),
        'login_retries': 2,
        'login_retry_delay_s': 5,
        'wait_time_s': wait_time_s,
        'schedule': sched_cfg,
        'schedule_day_offset': int(form.get('schedule_day_offset', 1)),
        'one_summary_message': (form.get('one_summary_message', '1') == '1'),
        'work_in_loop': True if 'collection_mode' in form else ('work_in_loop' in form),
        'storage_dir': getattr(request, 'app_storage_dir', 'storage') or 'storage',
        'send_error_notifications': 'send_error_notifications' in form,
        'error_cooldown_s': 3600,
        'mail': mail_cfg,
        'web': {
            'port': web_port,
            'host': web_host,
            'password': web_password,
            'max_login_attempts': 5,
            'lockout_duration_s': 900,
        },
    }

    try:
        save_config_yaml(full_config, config_path)
    except OSError as e:
        logger.error(f"Nie udało się zapisać konfiguracji do {config_path}: {e}")
        flash(f"Błąd podczas zapisu konfiguracji: {e}", "error")
        return redirect(url_for('web.setup_view'))

    # Natychmiastowe odświeżenie konfiguracji aplikacji w pamięci procesu
    try:
        from flask import current_app
        current_app.config['APP_CONFIG'] = read_config(config_path)
        if not current_app.config.get('NO_AUTH'):
            if web_password:
                current_app.config['WEB_PASSWORD'] = web_password
                session['authenticated'] = True  # Automatycznie zaloguj twórcę konfiguracji
            else:
                current_app.config['WEB_PASSWORD'] = None
    except Exception as e:
        logger.warning(f"Błąd odświeżania konfiguracji po zapisie: {e}")

    flash("Konfiguracja została pomyślnie utworzona i zapisana! Witaj w panelu.", "success")
    return redirect(url_for('web.dashboard'))


@web_bp.route('/ustawienia', methods=['GET', 'POST'])
@login_required
def settings_view():
    """Widok przeglądania i edycji konfiguracji systemu."""
    config = getattr(request, 'app_config', {})
    config_path = getattr(request, 'app_config_path', 'config.yaml')

    if request.method == 'POST':
        form = request.form
        existing_users = config.get('librus_users', []) if isinstance(config.get('librus_users'), list) else []

        # 1. Zbieranie kont uczniów
        updated_users: list[dict[str, Any]] = []
        indices = sorted(list({
            int(k.split('_')[-1])
            for k in form.keys()
            if k.startswith('student_login_') and k.split('_')[-1].isdigit()
        }))

        for i, idx in enumerate(indices):
            login = form.get(f'student_login_{idx}', '').strip()
            new_pwd = form.get(f'student_password_{idx}', '').strip()
            name = form.get(f'student_name_{idx}', '').strip() or f"Uczeń {login}"
            receivers_raw = form.get(f'student_receivers_{idx}', '').strip()
            receivers = [r.strip() for r in receivers_raw.split(',') if r.strip()]

            # Zachowaj dotychczasowe hasło jeśli pole zostało puste
            old_user = next((u for u in existing_users if str(u.get('librus_login')) == login), None)
            if not old_user and i < len(existing_users):
                old_user = existing_users[i]
            effective_pwd = new_pwd or (old_user.get('librus_password') if old_user else '')

            if login:
                global_one_summary = (form.get('one_summary_message', '1') == '1')
                if f'student_one_summary_present_{idx}' in form:
                    is_one_summary = (f'student_one_summary_{idx}' in form)
                elif f'student_one_summary_{idx}' in form:
                    is_one_summary = True
                else:
                    is_one_summary = global_one_summary

                st_cfg: dict[str, Any] = {
                    'librus_login_name': name,
                    'librus_login': login,
                    'librus_password': effective_pwd,
                    'read_messages': f'student_messages_{idx}' in form,
                    'read_grades': f'student_grades_{idx}' in form,
                    'read_timetable': f'student_timetable_{idx}' in form,
                    'read_schedule': f'student_schedule_{idx}' in form,
                    'schedule_day_offset': int(form.get('schedule_day_offset', 1)),
                    'one_summary_message': is_one_summary,
                    'notification_receivers': receivers,
                }
                if f'student_report_enabled_{idx}' in form:
                    st_email = form.get(f'student_report_email_{idx}', '').strip()
                    st_template = form.get(f'student_report_template_{idx}', 'kids').strip()
                    if st_template not in ('kids', 'teens', 'youth'):
                        st_template = 'kids'
                    st_cfg['student_report'] = {
                        'enabled': True,
                        'email': st_email or (receivers[0] if receivers else ''),
                        'template': st_template,
                    }
                updated_users.append(st_cfg)

        if not updated_users:
            flash("Lista kont uczniów nie może być pusta.", "error")
            return redirect(url_for('web.settings_view'))

        # 2. Poczta
        existing_mail = config.get('mail', {}) if isinstance(config.get('mail'), (dict, collections.abc.Mapping)) else {}
        mail_provider = form.get('mail_provider', 'gmail')
        mail_login = form.get('mail_login', '').strip() or existing_mail.get('login', '')
        gmail_auth_mode = form.get('gmail_auth_mode', 'app_password')
        gmail_oauth2_file = form.get('gmail_oauth2_file', '').strip() or existing_mail.get('oauth2_file', '')
        new_mail_pwd = form.get('mail_password', '').strip()
        effective_mail_pwd = new_mail_pwd or existing_mail.get('password', '')

        mail_cfg: dict[str, Any] = {
            'login': mail_login,
            'use_gmail': (mail_provider == 'gmail'),
        }
        if mail_provider == 'gmail':
            if gmail_auth_mode == 'oauth2':
                mail_cfg['oauth2_file'] = gmail_oauth2_file
            else:
                mail_cfg['password'] = effective_mail_pwd
        elif mail_provider == 'smtp':
            mail_cfg['password'] = effective_mail_pwd
            existing_non_gmail = existing_mail.get('non_gmail_settings', {})
            mail_cfg['non_gmail_settings'] = {
                'smtp_host': form.get('smtp_host', '').strip() or existing_non_gmail.get('smtp_host', 'smtp.example.com'),
                'port': int(form.get('smtp_port') or existing_non_gmail.get('port', 587)),
            }

        # 3. Harmonogram i automatyzacja
        existing_sched = config.get('schedule', {}) if isinstance(config.get('schedule'), (dict, collections.abc.Mapping)) else {}
        sched_cfg, wait_time_s = parse_schedule_from_form(form, existing_schedule=existing_sched)

        # 4. Panel WWW i ochrona
        existing_web = config.get('web', {}) if isinstance(config.get('web'), (dict, collections.abc.Mapping)) else {}
        new_web_pwd = form.get('web_password', '').strip()
        effective_web_pwd = new_web_pwd if new_web_pwd else existing_web.get('password')

        new_config = dict(config)
        new_config['librus_users'] = updated_users
        new_config['delay_between_users_s'] = int(form.get('delay_between_users_s', config.get('delay_between_users_s', 10)))
        new_config['wait_time_s'] = wait_time_s
        new_config['schedule'] = sched_cfg
        new_config['schedule_day_offset'] = int(form.get('schedule_day_offset', config.get('schedule_day_offset', 1)))
        new_config.pop('schedule_retention_days', None)
        new_config['one_summary_message'] = (form.get('one_summary_message', '1') == '1')
        new_config['work_in_loop'] = True if 'collection_mode' in form else ('work_in_loop' in form if 'work_in_loop' in form else config.get('work_in_loop', True))
        new_config['send_error_notifications'] = 'send_error_notifications' in form
        new_config['mail'] = mail_cfg
        new_config['web'] = dict(existing_web)
        new_config['web']['port'] = int(form.get('web_port') or existing_web.get('port', 5000))
        new_config['web']['host'] = form.get('web_host', '').strip() or existing_web.get('host', '127.0.0.1')
        new_config['web']['password'] = effective_web_pwd

        # 5. Rok szkolny, semestry i algorytm predykcji ocen rocznych
        sem_split_in = form.get('semester_split_date', '').strip()
        if sem_split_in and re.match(r'^\d{4}-\d{2}-\d{2}$', sem_split_in):
            new_config['semester_split_date'] = sem_split_in
        elif 'semester_split_date' in form:
            new_config['semester_split_date'] = None
        elif 'semester_split_date' in config:
            new_config['semester_split_date'] = config.get('semester_split_date')

        annual_algo_in = form.get('annual_grade_algorithm', '').strip()
        if annual_algo_in in ('all_year_weighted', 'semesters_average', 'progress_favored'):
            new_config['annual_grade_algorithm'] = annual_algo_in
        elif 'annual_grade_algorithm' in config:
            new_config['annual_grade_algorithm'] = config.get('annual_grade_algorithm', 'all_year_weighted')
        else:
            new_config['annual_grade_algorithm'] = 'all_year_weighted'

        # 6. Kalendarium zdarzeń (dedykowana sekcja 'timeline' w konfiguracji)
        existing_timeline = config.get('timeline', {}) if isinstance(config.get('timeline'), (dict, collections.abc.Mapping)) else {}

        selected_event_types: list[str] = []
        for etype in ['grades', 'messages', 'notifications', 'tests', 'attendance']:
            if f'timeline_type_{etype}' in form:
                selected_event_types.append(etype)
        if not selected_event_types and 'timeline_settings_present' not in form:
            selected_event_types = existing_timeline.get('event_types', ['grades', 'messages', 'notifications', 'tests', 'attendance'])

        try:
            timeline_days_in = int(form.get('timeline_days', 5))
            effective_days = max(1, min(14, timeline_days_in))
        except (ValueError, TypeError):
            effective_days = 5

        new_config['timeline'] = {
            'enabled': 'timeline_enabled' in form,
            'days': effective_days,
            'hide_weekends': 'timeline_hide_weekends' in form,
            'reverse_order': 'timeline_reverse_order' in form,
            'event_types': selected_event_types,
        }

        try:
            save_config_yaml(new_config, config_path)
            from flask import current_app
            current_app.config['APP_CONFIG'] = read_config(config_path)
            if not current_app.config.get('NO_AUTH'):
                if effective_web_pwd:
                    current_app.config['WEB_PASSWORD'] = str(effective_web_pwd)
                    session['authenticated'] = True
                else:
                    current_app.config['WEB_PASSWORD'] = None
            flash("Ustawienia zostały pomyślnie zaktualizowane.", "success")
        except (OSError, ValueError) as e:
            logger.error(f"Błąd zapisu ustawień do {config_path}: {e}")
            flash(f"Nie udało się zapisać ustawień: {e}", "error")

        return redirect(url_for('web.settings_view'))

    users = config.get('librus_users', []) if isinstance(config.get('librus_users'), list) else []
    mail = config.get('mail', {}) if isinstance(config.get('mail'), (dict, collections.abc.Mapping)) else {}
    web_cfg = config.get('web', {}) if isinstance(config.get('web'), (dict, collections.abc.Mapping)) else {}

    timeline_cfg = config.get('timeline', {}) if isinstance(config.get('timeline'), (dict, collections.abc.Mapping)) else {}
    if not timeline_cfg:
        timeline_cfg = {
            'enabled': web_cfg.get('timeline_enabled', config.get('timeline_enabled', True)),
            'days': web_cfg.get('timeline_days', config.get('timeline_days', 5)),
            'hide_weekends': web_cfg.get('timeline_hide_weekends', config.get('timeline_hide_weekends', False)),
            'reverse_order': web_cfg.get('timeline_reverse_order', False),
            'event_types': web_cfg.get('timeline_event_types', ['grades', 'messages', 'notifications', 'tests', 'attendance']),
        }

    return render_template(
        'web/settings.html',
        config=config,
        users=users,
        mail=mail,
        web_cfg=web_cfg,
        timeline_cfg=timeline_cfg,
        reports_schedules=get_reports_schedules(config),
        config_path=config_path,
    )


@web_bp.route('/api/test-librus', methods=['POST'])
def api_test_librus():
    """Endpoint API do weryfikacji danych logowania Librus w formularzu setup/ustawienia."""
    login = request.form.get('login', '').strip()
    password = request.form.get('password', '').strip()

    success, message = test_librus_credentials(login, password)
    return jsonify({'success': success, 'message': message})


_collector_thread: threading.Thread | None = None
_collector_lock = threading.Lock()


def start_background_collector(
    config_path: str = 'config.yaml',
    storage_dir: str | None = None,
) -> threading.Thread | None:
    """Uruchamia wątek demona kolektora i harmonogramu w tle."""
    global _collector_thread
    with _collector_lock:
        if _collector_thread is not None and _collector_thread.is_alive():
            logger.info("⏰ Wątek harmonogramu w tle już działa.")
            return _collector_thread

        def _worker() -> None:
            logger.info("⏰ [BackgroundCollector] Wątek harmonogramu w tle został uruchomiony.")
            while True:
                try:
                    if not os.path.exists(config_path):
                        time.sleep(5)
                        continue

                    try:
                        cfg = read_config(config_path)
                    except Exception as cfg_err:
                        logger.warning(
                            f"⏰ [BackgroundCollector] Błąd odczytu konfiguracji '{config_path}': {cfg_err}. Ponowna próba za 15s..."
                        )
                        time.sleep(15)
                        continue

                    users = cfg.get('librus_users', [])
                    if not users or not any(u.get('librus_login') for u in users):
                        time.sleep(5)
                        continue

                    work_in_loop_val = cfg.get('work_in_loop', True)
                    if not work_in_loop_val:
                        logger.info(
                            "⏰ [BackgroundCollector] Harmonogram w tle jest wyłączony w konfiguracji (work_in_loop: false). "
                            "Wątek czuwa i oczekuje na ewentualną zmianę konfiguracji w panelu WWW..."
                        )
                        from librus2mail.config_watcher import sleep_with_config_watch
                        sleep_with_config_watch(30, config_path=config_path)
                        continue

                    logger.info("⏰ [BackgroundCollector] Rozpoczynam główną pętlę pobierania (run_collector)...")
                    run_collector(
                        config_path=config_path,
                        storage_dir=storage_dir,
                    )
                    time.sleep(5)
                except Exception as loop_err:
                    logger.error(
                        f"⏰ [BackgroundCollector] Wystąpił błąd w pętli zbierania: {loop_err}. Wznowienie za 30s...",
                        exc_info=True,
                    )
                    time.sleep(30)

        thread = threading.Thread(
            target=_worker,
            name="LibrusCollectorThread",
            daemon=True,
        )
        thread.start()
        _collector_thread = thread
        return thread


def create_app(
    config_path: str = 'config.yaml',
    storage_dir: str | None = None,
    web_password: str | None = None,
    no_auth: bool = False,
    secret_key: str | None = None,
    max_login_attempts: int | None = None,
    lockout_duration_s: int | None = None,
    actual_date: datetime | str | None = None,
    run_collector_thread: bool = False,
    enable_csrf: bool | None = None,
    behind_proxy: bool | None = None,
    trusted_proxies: set[str] | list[str] | None = None,
    static_csrf_token: str | None = None,
) -> Flask:
    """Fabryka aplikacji webowej Flask dla Librus2mail."""
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    app = Flask(__name__, template_folder=templates_dir)

    # Wczytanie konfiguracji z pliku YAML
    app_config = read_config(config_path) if os.path.isfile(config_path) else {}
    effective_storage = storage_dir or app_config.get('storage_dir', 'storage')
    storage = get_storage(app_config, effective_storage)

    # Konfiguracja hasła i sesji
    web_cfg = app_config.get('web', {}) if isinstance(app_config.get('web'), (dict, collections.abc.Mapping)) else {}
    configured_pwd = web_password or os.environ.get('LIBRUS_WEB_PASSWORD') or web_cfg.get('password')

    if no_auth:
        effective_pwd = None
    else:
        effective_pwd = str(configured_pwd) if configured_pwd else None

    # Konfiguracja ochrony przed atakami brute-force (IP lockout)
    eff_max_attempts = max_login_attempts or int(web_cfg.get('max_login_attempts', 5))
    eff_lockout_s = lockout_duration_s or int(web_cfg.get('lockout_duration_s', 900))
    eff_window_s = int(web_cfg.get('attempt_window_s', 300))
    app.config['LOGIN_RATE_LIMITER'] = LoginRateLimiter(
        max_attempts=eff_max_attempts,
        lockout_duration_s=eff_lockout_s,
        window_s=eff_window_s,
    )

    # Konfiguracja bezpieczeństwa ciasteczek sesyjnych
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = web_cfg.get('session_cookie_samesite', 'Lax')
    cookie_secure = web_cfg.get('cookie_secure')
    if cookie_secure is None:
        cookie_secure = os.environ.get('LIBRUS_WEB_COOKIE_SECURE', '').lower() in ('1', 'true', 'yes')
    app.config['SESSION_COOKIE_SECURE'] = bool(cookie_secure)

    # Konfiguracja zaufanych serwerów proxy (ochrona przed spoofingiem nagłówków X-Forwarded-For)
    if trusted_proxies is not None:
        if isinstance(trusted_proxies, (set, list, tuple)):
            eff_trusted = {str(p).strip() for p in trusted_proxies if str(p).strip()}
        else:
            eff_trusted = {str(trusted_proxies).strip()}
    else:
        raw_trusted = web_cfg.get('trusted_proxies')
        if raw_trusted is None:
            raw_trusted = os.environ.get('LIBRUS_WEB_TRUSTED_PROXIES')
        if isinstance(raw_trusted, str):
            eff_trusted = {p.strip() for p in raw_trusted.split(',') if p.strip()}
        elif isinstance(raw_trusted, (list, set, tuple)):
            eff_trusted = {str(p).strip() for p in raw_trusted if str(p).strip()}
        else:
            eff_trusted = {'127.0.0.1', '::1', 'localhost'}
    app.config['TRUSTED_PROXIES'] = eff_trusted

    # Konfiguracja ProxyFix (obsługa reverse proxy: Nginx, Traefik, Caddy, Docker)
    eff_behind_proxy = (
        behind_proxy
        if behind_proxy is not None
        else (
            web_cfg.get('behind_proxy') is True
            or os.environ.get('LIBRUS_WEB_BEHIND_PROXY', '').lower() in ('1', 'true', 'yes')
        )
    )
    if eff_behind_proxy:
        from werkzeug.middleware.proxy_fix import ProxyFix
        proxy_depth = int(web_cfg.get('proxy_depth') or os.environ.get('LIBRUS_WEB_PROXY_DEPTH', 1))
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_depth,
            x_proto=proxy_depth,
            x_host=proxy_depth,
            x_port=proxy_depth,
            x_prefix=proxy_depth,
        )

    parsed_date = parse_datetime_safe(actual_date) if actual_date else None

    # Trwały SECRET_KEY sesji (zabezpiecza przed wylogowaniem po restarcie procesu)
    app.config['SECRET_KEY'] = (
        secret_key
        or web_cfg.get('secret_key')
        or os.environ.get('LIBRUS_WEB_SECRET_KEY')
        or get_or_create_persistent_secret_key(effective_storage)
    )

    # Ochrona przed atakami CSRF
    eff_csrf = enable_csrf if enable_csrf is not None else web_cfg.get('enable_csrf', True)
    app.config['CSRF_ENABLED'] = bool(eff_csrf)
    app.config['STATIC_CSRF_TOKEN'] = static_csrf_token

    app.config['NO_AUTH'] = no_auth
    app.config['WEB_PASSWORD'] = effective_pwd
    app.config['APP_CONFIG'] = app_config
    app.config['CONFIG_PATH'] = config_path
    app.config['STORAGE_DIR'] = effective_storage
    app.config['STORAGE'] = storage
    app.config['ACTUAL_DATE'] = parsed_date

    @app.before_request
    def set_request_context():
        request.app_config = app.config['APP_CONFIG']
        request.app_config_path = app.config['CONFIG_PATH']
        request.app_storage_dir = app.config['STORAGE_DIR']
        request.app_actual_date = app.config.get('ACTUAL_DATE')

        raw_storage = app.config['STORAGE']
        active_school_year = session.get('active_school_year')
        if active_school_year and hasattr(raw_storage, 'get_archived_view'):
            request.app_active_school_year = str(active_school_year)
            request.is_archive_mode = True
            request.app_storage = raw_storage.get_archived_view(request.app_active_school_year)
        else:
            request.app_active_school_year = None
            request.is_archive_mode = False
            request.app_storage = raw_storage

        # Wymuszenie kreatora /setup gdy brak pliku konfiguracji lub brak skonfigurowanych kont
        if not _has_valid_config(request.app_config):
            allowed_prefixes = ('/setup', '/static', '/favicon', '/api/test-librus')
            if not request.path.startswith(allowed_prefixes):
                return redirect(url_for('web.setup_view'))

    @app.before_request
    def block_archive_mutations():
        """Blokuje modyfikacje stanu w trybie archiwalnym (Read-Only)."""
        if getattr(request, 'is_archive_mode', False) and request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            allowed = ('/school-year/switch', '/student/', '/login', '/logout')
            if not any(request.path.startswith(p) for p in allowed):
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify({'status': 'error', 'message': 'Operacja zablokowana w trybie archiwalnym (tylko do odczytu).'}), 403
                flash("Operacja niedozwolona w trybie archiwalnym (dane są tylko do odczytu).", "error")
                return redirect(request.referrer or url_for('web.dashboard'))

    @app.before_request
    def verify_csrf_protection():
        """Weryfikuje poprawność tokenu CSRF dla wszystkich żądań zmieniających stan (POST, PUT, DELETE)."""
        if not app.config.get('CSRF_ENABLED', True):
            return None
        if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
            return None

        token = request.form.get('csrf_token')
        if not token:
            token = request.headers.get('X-CSRFToken') or request.headers.get('X-CSRF-Token')
        if not token and request.is_json:
            json_body = request.get_json(silent=True)
            if isinstance(json_body, dict):
                token = json_body.get('csrf_token')

        expected_token = (
            current_app.config.get('STATIC_CSRF_TOKEN')
            if (current_app and current_app.config.get('STATIC_CSRF_TOKEN'))
            else session.get('_csrf_token')
        )
        if not expected_token or not token or not hmac.compare_digest(str(token), str(expected_token)):
            logger.warning(
                f"Odrzucono żądanie {request.method} {request.path} z IP {get_client_ip(request)}: nieprawidłowy token CSRF."
            )
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Nieprawidłowy lub brakujący token CSRF.'}), 400
            abort(400, description="Nieprawidłowy lub brakujący token CSRF. Odśwież stronę i spróbuj ponownie.")

    @app.after_request
    def inject_security_headers(response: Response) -> Response:
        """Wstrzykuje standardowe nagłówki bezpieczeństwa HTTP (OWASP) do każdej odpowiedzi."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    @app.template_filter('human_time')
    def human_time_filter(val):
        ref_now = getattr(request, 'app_actual_date', None) or datetime.now()
        return format_human_timestamp(val, now=ref_now)

    app.context_processor(inject_common_context)
    app.register_blueprint(auth_bp)
    app.register_blueprint(web_bp)

    if run_collector_thread:
        start_background_collector(config_path=config_path, storage_dir=effective_storage)

    return app


def main():
    """Punkt wejścia CLI dla uruchomienia serwera panelu webowego."""
    parser = argparse.ArgumentParser(
        description="Librus2mail Web Dashboard - Interaktywny pulpit rodzica."
    )
    parser.add_argument('-c', '--config', default='config.yaml', help="Ścieżka do pliku konfiguracyjnego YAML")
    parser.add_argument('-s', '--storage-dir', default=None, help="Katalog pamięci stanu storage/")
    parser.add_argument('-u', '--user', default=None, help="Filtr / domyślny login ucznia do wyświetlenia")
    parser.add_argument('-p', '--port', type=int, default=None, help="Port serwera HTTP (domyślnie z config.yaml lub 5000)")
    parser.add_argument('-b', '--bind', '--host', dest='host', default=None, help="Adres nasłuchu (domyślnie z config.yaml lub 0.0.0.0 dla serwera)")
    parser.add_argument('--password', default=None, help="Hasło rodzica zabezpieczające dostęp do panelu")
    parser.add_argument('--no-auth', action='store_true', help="Wyłącz wymaganie hasła (tylko zaufane środowiska)")
    parser.add_argument('--max-attempts', type=int, default=None, help="Maksymalna liczba prób logowania przed blokadą IP (domyślnie: 5)")
    parser.add_argument('--lockout-duration', type=int, default=None, help="Czas blokady IP w sekundach (domyślnie: 900 = 15 min)")
    parser.add_argument('--actual-date', default=None, help="Referencyjna data symulacji (RRRR-MM-DD) do testów i raportów")
    parser.add_argument('--export-html', default=None, metavar='DIR', help="Eksportuje przykładowe statyczne widoki HTML (login, pulpit, zakładki) do wskazanego katalogu i kończy działanie")
    parser.add_argument('--no-collector', action='store_true', help="Wyłącz automatyczny wątek harmonogramu/kolektora w tle (użyj np. gdy collector działa w osobnym kontenerze)")
    parser.add_argument('--debug', action='store_true', help="Uruchom serwer w trybie debugowania")

    args = parser.parse_args()
    setup_logging()

    if args.export_html:
        from .export import export_web_views
        files = export_web_views(
            output_dir=args.export_html,
            config_path=args.config,
            storage_dir=args.storage_dir,
            user_login=args.user,
            actual_date=args.actual_date,
        )
        print(f"\n✅ Pomyślnie wyeksportowano {len(files)} widoków HTML do katalogu: {args.export_html}")
        for name, path in sorted(files.items()):
            print(f"  - {name} ({path})")
        return

    no_collector = args.no_collector or os.environ.get("LIBRUS_NO_COLLECTOR", "").lower() in ("1", "true", "yes")
    is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    run_scheduler = not no_collector and (not args.debug or is_reloader_child)

    app = create_app(
        config_path=args.config,
        storage_dir=args.storage_dir,
        web_password=args.password,
        no_auth=args.no_auth,
        max_login_attempts=args.max_attempts,
        lockout_duration_s=args.lockout_duration,
        actual_date=args.actual_date,
        run_collector_thread=run_scheduler,
    )

    cfg_app = app.config.get('APP_CONFIG', {}) if isinstance(app.config.get('APP_CONFIG'), (dict, collections.abc.Mapping)) else {}
    cfg_web = cfg_app.get('web', {}) if isinstance(cfg_app.get('web'), (dict, collections.abc.Mapping)) else {}
    effective_host = args.host or cfg_web.get('host') or '0.0.0.0'
    effective_port = args.port or int(cfg_web.get('port', 5000))

    is_loop_enabled = cfg_app.get('work_in_loop', True) if isinstance(cfg_app, (dict, collections.abc.Mapping)) else True

    auth_status = "WYŁĄCZONA (--no-auth)" if args.no_auth or not app.config.get('WEB_PASSWORD') else "WŁĄCZONA (wymagane hasło rodzica)"
    if not run_scheduler:
        scheduler_status = "WYŁĄCZONY (--no-collector)"
    elif not is_loop_enabled:
        scheduler_status = "WYŁĄCZONY (work_in_loop: false w config.yaml)"
    else:
        scheduler_status = "AKTYWNY (wątek w tle)"

    limiter: LoginRateLimiter = app.config['LOGIN_RATE_LIMITER']
    print("\n" + "=" * 65)
    print("🏫 Librus2mail Web Dashboard uruchomiony pomyślnie!")
    print(f"🌐 Adres URL:       http://{effective_host}:{effective_port}")
    print(f"🔒 Ochrona hasłem:  {auth_status}")
    print(f"🛡️  Ochrona IP:     Max {limiter.max_attempts} prób, blokada {limiter.lockout_duration_s}s")
    print(f"📂 Baza storage:    {app.config['STORAGE_DIR']}")
    print(f"⏰ Harmonogram:     {scheduler_status}")
    print("=" * 65 + "\n")

    app.run(host=effective_host, port=effective_port, debug=args.debug)


if __name__ == '__main__':
    main()

