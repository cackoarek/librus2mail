"""Główna aplikacja webowa Flask dla interfejsu Librus2mail."""

import argparse
import os
import secrets
from datetime import datetime

from flask import (
    Blueprint,
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from librus2mail.base_logger import setup_logging
from librus2mail.config import read_config
from librus2mail.librus_collector import run_collector
from librus2mail.progress_report import run_progress_reports
from librus2mail.student_report import run_student_reports
from librus2mail.updates_notifier import run_notifier

from .auth import LoginRateLimiter, auth_bp, is_auth_enabled, is_authenticated, login_required
from .services import (
    calculate_subject_averages,
    capture_action_execution,
    get_active_student_login,
    get_storage,
    get_student_dashboard_bundle,
    list_students,
    simulate_new_grade,
)

web_bp = Blueprint('web', __name__)


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

    return {
        'all_students': students,
        'active_student': active_student,
        'active_login': active_login,
        'is_auth_enabled': auth_enabled,
        'is_authenticated': authenticated,
        'now': now,
        'app_version': "1.4.0",
    }



@web_bp.route('/student/<login>')
@login_required
def switch_student(login: str):
    """Zmienia aktywnego ucznia w sesji użytkownika."""
    session['active_student_login'] = str(login)
    flash(f"Przełączono aktywny profil ucznia na konto {login}.", "info")
    next_url = request.args.get('next') or url_for('web.dashboard')
    return redirect(next_url)


@web_bp.route('/')
@login_required
def dashboard():
    """Główny pulpit rodzica - podsumowanie dnia i najważniejsze alerty."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    if not active_login:
        return render_template('web/dashboard.html', error="Brak skonfigurowanych uczniów w systemie.")

    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    return render_template('web/dashboard.html', data=data)


@web_bp.route('/plan')
@login_required
def schedule_view():
    """Widok pełnego tygodniowego planu lekcji."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    all_lessons = data.get('all_schedule', [])

    # Grupowanie lekcji po dacie
    by_date: dict[str, list] = {}
    for entry in all_lessons:
        d = entry.get('date')
        if d:
            if d not in by_date:
                by_date[d] = []
            by_date[d].append(entry)

    # Sortowanie lekcji chronologicznie w danym dniu
    for d, l_list in by_date.items():
        l_list.sort(key=lambda x: (int(x.get('lesson_no', 0)) if str(x.get('lesson_no', '')).isdigit() else 99, x.get('time_from', '')))

    weekdays_pl = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
    days_data = []
    for d_str in sorted(by_date.keys()):
        try:
            clean_date = d_str.split()[0] if ' ' in d_str else d_str
            d_obj = datetime.strptime(clean_date, "%Y-%m-%d").date()
            w_name = weekdays_pl[d_obj.weekday()]
        except Exception:
            w_name = ""
        days_data.append({
            'date': d_str,
            'weekday_name': w_name,
            'lessons': by_date[d_str],
            'total_count': len(by_date[d_str]),
            'cancelled_count': sum(1 for x in by_date[d_str] if x.get('is_cancelled')),
            'substitution_count': sum(1 for x in by_date[d_str] if x.get('is_substitution')),
        })

    return render_template('web/schedule.html', data=data, days_data=days_data)


@web_bp.route('/oceny')
@login_required
def grades_view():
    """Widok zestawienia ocen z kalkulatorem średniej."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    grades = storage.get_grades_history(active_login) if hasattr(storage, 'get_grades_history') else []
    subject_averages = calculate_subject_averages(grades)

    return render_template('web/grades.html', data=data, subject_averages=subject_averages)


@web_bp.route('/terminarz')
@login_required
def timetable_view():
    """Widok nadchodzących sprawdzianów i nieobecności nauczycieli."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    return render_template('web/timetable.html', data=data)


@web_bp.route('/wiadomosci')
@login_required
def messages_view():
    """Widok wiadomości i ogłoszeń szkolnych."""
    config = request.app_config
    storage = request.app_storage
    active_login = get_active_student_login(config, storage, session_login=session.get('active_student_login'))

    data = get_student_dashboard_bundle(storage, active_login, config, now=request.app_actual_date)
    return render_template('web/messages.html', data=data)


@web_bp.route('/akcje')
@login_required
def actions_view():
    """Centrum operacyjne - graficzny pulpit dla skryptów z useful-scripts.md."""
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
    days = int(request.form.get('days', 1))
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
    days = int(request.form.get('days', 7))

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
    days = int(request.form.get('days', 7))

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


def create_app(
    config_path: str = 'config.yaml',
    storage_dir: str | None = None,
    web_password: str | None = None,
    no_auth: bool = False,
    secret_key: str | None = None,
    max_login_attempts: int | None = None,
    lockout_duration_s: int | None = None,
    actual_date: datetime | str | None = None,
) -> Flask:
    """Fabryka aplikacji webowej Flask dla Librus2mail."""
    templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    app = Flask(__name__, template_folder=templates_dir)

    # Wczytanie konfiguracji z pliku YAML
    app_config = read_config(config_path) if os.path.isfile(config_path) else {}
    effective_storage = storage_dir or app_config.get('storage_dir', 'storage')
    storage = get_storage(app_config, effective_storage)

    # Konfiguracja hasła i sesji
    web_cfg = app_config.get('web', {}) if isinstance(app_config.get('web'), dict) else {}
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

    parsed_date = None
    if isinstance(actual_date, str):
        parsed_date = datetime.strptime(actual_date, "%Y-%m-%d")
    elif isinstance(actual_date, datetime):
        parsed_date = actual_date

    app.config['SECRET_KEY'] = secret_key or web_cfg.get('secret_key') or os.environ.get('LIBRUS_WEB_SECRET_KEY') or secrets.token_hex(32)
    app.config['WEB_PASSWORD'] = effective_pwd
    app.config['APP_CONFIG'] = app_config
    app.config['CONFIG_PATH'] = config_path
    app.config['STORAGE_DIR'] = effective_storage
    app.config['STORAGE'] = storage
    app.config['ACTUAL_DATE'] = parsed_date

    @app.before_request
    def set_request_context():
        request.app_config = app.config['APP_CONFIG']
        request.app_storage = app.config['STORAGE']
        request.app_config_path = app.config['CONFIG_PATH']
        request.app_storage_dir = app.config['STORAGE_DIR']
        request.app_actual_date = app.config.get('ACTUAL_DATE')

    app.context_processor(inject_common_context)
    app.register_blueprint(auth_bp)
    app.register_blueprint(web_bp)

    return app


def main():
    """Punkt wejścia CLI dla uruchomienia serwera panelu webowego."""
    parser = argparse.ArgumentParser(
        description="Librus2mail Web Dashboard - Interaktywny pulpit rodzica."
    )
    parser.add_argument('-c', '--config', default='config.yaml', help="Ścieżka do pliku konfiguracyjnego YAML")
    parser.add_argument('-s', '--storage-dir', default=None, help="Katalog pamięci stanu storage/")
    parser.add_argument('-u', '--user', default=None, help="Filtr / domyślny login ucznia do wyświetlenia")
    parser.add_argument('-p', '--port', type=int, default=5000, help="Port serwera HTTP (domyślnie: 5000)")
    parser.add_argument('-b', '--bind', '--host', dest='host', default='127.0.0.1', help="Adres nasłuchu (domyślnie: 127.0.0.1; użyj 0.0.0.0 dla sieci lokalnej)")
    parser.add_argument('--password', default=None, help="Hasło rodzica zabezpieczające dostęp do panelu")
    parser.add_argument('--no-auth', action='store_true', help="Wyłącz wymaganie hasła (tylko zaufane środowiska)")
    parser.add_argument('--max-attempts', type=int, default=None, help="Maksymalna liczba prób logowania przed blokadą IP (domyślnie: 5)")
    parser.add_argument('--lockout-duration', type=int, default=None, help="Czas blokady IP w sekundach (domyślnie: 900 = 15 min)")
    parser.add_argument('--actual-date', default=None, help="Referencyjna data symulacji (RRRR-MM-DD) do testów i raportów")
    parser.add_argument('--export-html', default=None, metavar='DIR', help="Eksportuje przykładowe statyczne widoki HTML (login, pulpit, zakładki) do wskazanego katalogu i kończy działanie")
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

    app = create_app(
        config_path=args.config,
        storage_dir=args.storage_dir,
        web_password=args.password,
        no_auth=args.no_auth,
        max_login_attempts=args.max_attempts,
        lockout_duration_s=args.lockout_duration,
        actual_date=args.actual_date,
    )

    auth_status = "WYŁĄCZONA (--no-auth)" if args.no_auth or not app.config.get('WEB_PASSWORD') else "WŁĄCZONA (wymagane hasło rodzica)"
    limiter: LoginRateLimiter = app.config['LOGIN_RATE_LIMITER']
    print("\n" + "=" * 65)
    print("🏫 Librus2mail Web Dashboard uruchomiony pomyślnie!")
    print(f"🌐 Adres URL:       http://{args.host}:{args.port}")
    print(f"🔒 Ochrona hasłem:  {auth_status}")
    print(f"🛡️  Ochrona IP:     Max {limiter.max_attempts} prób, blokada {limiter.lockout_duration_s}s")
    print(f"📂 Baza storage:    {app.config['STORAGE_DIR']}")
    print("=" * 65 + "\n")

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == '__main__':
    main()

