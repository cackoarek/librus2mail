import html
import os
from datetime import datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

_pkg_templates = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'emails')
_root_templates = os.path.join(os.getcwd(), 'templates', 'emails')
TEMPLATES_DIRS = [_pkg_templates]
if os.path.isdir(_root_templates) and _root_templates != _pkg_templates:
    TEMPLATES_DIRS.append(_root_templates)
TEMPLATES_DIR = _pkg_templates if os.path.isdir(_pkg_templates) else _root_templates

jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIRS),
    autoescape=select_autoescape(['html', 'xml'])
)


def resolve_output_path(
    output_path: str,
    user_login: str,
    total_users: int = 1,
    default_prefix: str = "raport"
) -> str:
    """
    Wyznacza docelową ścieżkę pliku HTML na podstawie parametru wyjściowego, loginu ucznia i liczby uczniów:
    - Jeśli output_path to katalog (lub kończy się na / lub \\): tworzy katalog i plik '{default_prefix}_<login>.html'.
    - Jeśli output_path zawiera szablon {login} lub {user}: formatuje go loginem ucznia.
    - Jeśli jest wielu uczniów i podano pojedynczy plik: dodaje '_<login>' przed rozszerzeniem.
    - W przeciwnym razie zwraca bezpośrednio output_path.
    Automatycznie tworzy katalogi nadrzędne, jeśli nie istnieją.
    """
    if os.path.isdir(output_path) or output_path.endswith('/') or output_path.endswith('\\'):
        os.makedirs(output_path, exist_ok=True)
        return os.path.join(output_path, f"{default_prefix}_{user_login}.html")

    if "{login}" in output_path or "{user}" in output_path:
        formatted = output_path.format(login=user_login, user=user_login)
        parent = os.path.dirname(formatted)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return formatted

    if total_users > 1:
        base, ext = os.path.splitext(output_path)
        ext = ext if ext else ".html"
        filename = f"{base}_{user_login}{ext}"
        parent = os.path.dirname(filename)
        if parent:
            os.makedirs(parent, exist_ok=True)
        return filename

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return output_path


def render_standalone_html(title: str, body_html: str) -> str:
    """Tworzy pełny, samodzielny dokument HTML5 gotowy do otwarcia bezpośrednio w przeglądarce."""
    return (
        "<!DOCTYPE html>\n"
        "<html lang=\"pl\">\n"
        "<head>\n"
        "    <meta charset=\"UTF-8\">\n"
        "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        f"    <title>{title}</title>\n"
        "</head>\n"
        "<body style=\"margin: 0; padding: 24px 12px; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;\">\n"
        f"{body_html}\n"
        "</body>\n"
        "</html>\n"
    )


class MailSender:
    def __init__(self, mail_config):
        self.sender_email = mail_config['login']
        self.password = mail_config['password']

    @staticmethod
    def _format_grade_badge(val: str) -> Markup:
        s = str(val).strip() if val is not None else ''
        first_char = s[0] if s else ''
        if first_char in ('5', '6'):
            bg = "#d1fae5"
            color = "#065f46"
            border = "#a7f3d0"
        elif first_char == '4':
            bg = "#dbeafe"
            color = "#1e40af"
            border = "#bfdbfe"
        elif first_char == '3':
            bg = "#fef3c7"
            color = "#92400e"
            border = "#fde68a"
        elif first_char in ('1', '2'):
            bg = "#fee2e2"
            color = "#991b1b"
            border = "#fecaca"
        else:
            bg = "#f3f4f6"
            color = "#374151"
            border = "#e5e7eb"
        return Markup(
            f'<span style="display: inline-block; background-color: {bg}; color: {color}; border: 1px solid {border}; border-radius: 4px; padding: 2px 6px; font-weight: bold; font-size: 13px; margin: 1px;">{html.escape(s)}</span>'
        )

    @staticmethod
    def create_mail_content_for_messages(user_config: dict, messages: list) -> str:
        template = jinja_env.get_template('messages.html')
        return template.render(user_config=user_config, messages=messages)

    @staticmethod
    def create_mail_content_for_notifications(user_config: dict, notifications: list) -> str:
        template = jinja_env.get_template('notifications.html')
        return template.render(user_config=user_config, notifications=notifications)

    @staticmethod
    def create_mail_content_for_grades(user_config: dict, grades: list) -> str:
        template = jinja_env.get_template('grades.html')
        return template.render(user_config=user_config, grades=grades)

    @staticmethod
    def _create_summary_title(
        user_config: dict,
        messages: list = None,
        notifications: list = None,
        grades: list = None,
        timetable: dict = None,
    ) -> str:
        parts = []
        if messages:
            count = len(messages)
            if count == 1:
                parts.append("1 nowa wiadomość")
            elif 2 <= count <= 4 or (count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]):
                parts.append(f"{count} nowe wiadomości")
            else:
                parts.append(f"{count} nowych wiadomości")

        if notifications:
            count = len(notifications)
            if count == 1:
                parts.append("1 nowe ogłoszenie")
            elif 2 <= count <= 4 or (count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]):
                parts.append(f"{count} nowe ogłoszenia")
            else:
                parts.append(f"{count} nowych ogłoszeń")

        if grades:
            grades_summary = ", ".join([f"{g['subject']}: {g['grade']}" for g in grades[:2]])
            if len(grades) > 2:
                grades_summary += f" (+{len(grades) - 2})"
            parts.append(f"nowe oceny ({grades_summary})")

        if timetable and timetable.get('immediate_tests'):
            t_count = len(timetable['immediate_tests'])
            t_suffix = 'y' if 1 < t_count < 5 else ('ów' if t_count >= 5 else '')
            if timetable.get('is_tomorrow') is False:
                day_name = timetable.get('immediate_day_name') or 'poniedziałek'
                parts.append(f"⚠️ {t_count} sprawdzian{t_suffix} w {day_name}")
            else:
                parts.append(f"⚠️ {t_count} sprawdzian{t_suffix} jutro")
        elif timetable and timetable.get('immediate_absences'):
            parts.append("nieobecność nauczyciela")

        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        if not parts:
            return f"{name} - Librus: podsumowanie"
        return f"{name} - Librus: " + ", ".join(parts)

    @staticmethod
    def create_mail_content_for_summary(
        user_config: dict,
        messages: list = None,
        notifications: list = None,
        grades: list = None,
        timetable: dict = None,
    ) -> str:
        template = jinja_env.get_template('summary.html')
        return template.render(
            user_config=user_config,
            messages=messages or [],
            notifications=notifications or [],
            grades=grades or [],
            timetable=timetable,
        )

    def send_mail_with_messages(self, user_config, messages):
        pass

    def send_mail_with_notifications(self, user_config, notifications):
        pass

    def send_mail_with_grades(self, user_config, grades):
        pass

    def send_mail_with_summary(self, user_config, messages=None, notifications=None, grades=None, timetable=None):
        pass

    @classmethod
    def _create_progress_report_title(cls, user_config: dict, analysis: dict) -> str:
        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        p_start = analysis.get('period_start_str', '')
        p_end = analysis.get('period_end_str', '')
        overall_avg = analysis.get('overall_avg')
        avg_text = f"śr. {overall_avg:.2f}" if overall_avg is not None else "brak średniej"
        period_count = analysis.get('period_grades_count', 0)
        return f"📊 Raport postępów: {name} ({p_start} – {p_end}) [{avg_text}, nowe oceny: {period_count}]"

    @classmethod
    def create_mail_content_for_progress_report(cls, user_config: dict, analysis: dict) -> str:
        name = str(user_config.get('librus_login_name') or user_config.get('librus_login', ''))
        login = str(user_config.get('librus_login', ''))
        borderline_opp_map = {o['subject']: o for o in analysis.get('borderline_opportunities', [])}
        borderline_risk_map = {r['subject']: r for r in analysis.get('borderline_risks', [])}
        dormant_items = [d for d in analysis.get('dormant_subjects', []) if d.get('days_ago')]
        learning_style = analysis.get('learning_style') or {}
        weight_impact = analysis.get('weight_impact') or {}
        honor_roll = analysis.get('honor_roll') or {}
        legend = analysis.get('legend') or {}
        distribution_overall = analysis.get('distribution_overall') or {}
        distribution_period = analysis.get('distribution_period') or {}

        template = jinja_env.get_template('progress_report.html')
        return template.render(
            user_name=name,
            user_login=login,
            analysis=analysis,
            learning_style=learning_style,
            weight_impact=weight_impact,
            honor_roll=honor_roll,
            legend=legend,
            distribution_overall=distribution_overall,
            distribution_period=distribution_period,
            borderline_opp_map=borderline_opp_map,
            borderline_risk_map=borderline_risk_map,
            dormant_items=dormant_items,
        )

    @classmethod
    def create_mail_content_for_student_report(
        cls,
        metrics: Any,
        template_type: str = "kids",
    ) -> str:
        tpl_name = f"student_report_{template_type}.html"
        try:
            template = jinja_env.get_template(tpl_name)
        except Exception:
            template = jinja_env.get_template("student_report_kids.html")

        return template.render(
            metrics=metrics,
            now=datetime.now(),
        )

    @staticmethod
    def create_student_report_title(metrics: Any, template_type: str = "kids") -> str:
        name = getattr(metrics, 'student_name', 'Uczeń')
        days = getattr(metrics, 'period_days', None)
        if template_type == "youth":
            return f"📊 Student Performance Dashboard • {name}"
        elif template_type == "teens":
            prefix = "Weekly Briefing" if days == 7 else "Student Briefing"
            return f"⚡ Twój {prefix} • {name}"
        else:
            summary_desc = "Podsumowanie tygodnia" if days == 7 else (f"Podsumowanie okresu ({days} dni)" if days else "Podsumowanie postępów")
            return f"🚀 Twoja Karta Mocy • {summary_desc} dla {name}"

    def send_student_report(
        self,
        receivers: list[str],
        title: str,
        mail_content: str,
    ) -> bool:
        pass

    def send_progress_report(self, user_config: dict, analysis: dict) -> bool:
        pass

    @classmethod
    def _get_error_diagnostics(cls, error: Exception) -> tuple[str, str, str]:
        err_name = type(error).__name__
        err_str = str(error)
        err_lower = err_str.lower()

        if err_name == 'NotLogged' or 'brak dostępu' in err_lower or 'sesja' in err_lower or 'nie zalogowany' in err_lower:
            category = "Błąd autoryzacji / sesji Librus"
            diagnosis = "Sesja w portalu Librus Synergia wygasła lub autoryzacja konta nie powiodła się."
            recommendation = (
                "1. Upewnij się, że login i hasło w pliku konfiguracyjnym są poprawne.<br>"
                "2. <strong>Zaloguj się ręcznie przez przeglądarkę na portal.librus.pl</strong> (lub synergia.librus.pl) – "
                "szkoła lub Librus może wymagać zaakceptowania nowego regulaminu, zgody na przetwarzanie danych, zmiany hasła "
                "lub odczytania obowiązkowej wiadomości dyrekcji/ankiety, co blokuje automatyczny dostęp do dziennika.<br>"
                "3. Upewnij się, że konto nie zostało tymczasowo zablokowane z powodu zbyt wielu nieudanych prób logowania."
            )
        elif (
            'connection' in err_name.lower()
            or 'timeout' in err_name.lower()
            or 'ssl' in err_name.lower()
            or 'http' in err_name.lower()
            or 'resolution' in err_lower
            or 'max retries' in err_lower
            or 'failed to establish a new connection' in err_lower
        ):
            category = "Błąd połączenia sieciowego"
            diagnosis = "Nie udało się nawiązać stabilnego połączenia z serwerami Librus (brak połączenia z siecią, timeout lub błąd SSL/DNS)."
            recommendation = (
                "1. Sprawdź połączenie internetowe na serwerze/komputerze uruchamiającym aplikację.<br>"
                "2. Sprawdź w przeglądarce, czy portal https://synergia.librus.pl działa prawidłowo (możliwa przerwa techniczna Librusa).<br>"
                "3. Jeśli problem występuje regularnie, upewnij się, że zapora sieciowa (firewall) nie blokuje zapytań HTTPS."
            )
        elif err_name in ('AttributeError', 'TypeError', 'KeyError', 'IndexError') or 'parse' in err_lower or 'soup' in err_lower:
            category = "Błąd parsowania danych (zmiana struktury HTML)"
            diagnosis = "Dane ze strony Librusa zostały pobrane, lecz skrypt nie był w stanie wyodrębnić z nich informacji. Prawdopodobnie Librus zaktualizował strukturę HTML dziennika."
            recommendation = (
                "1. Sprawdź szczegółowy log w pliku <code>librus.log</code>.<br>"
                "2. Zaloguj się przez przeglądarkę i sprawdź, czy w dzienniku nie pojawił się niestandardowy komunikat lub okno modalne zastępujące widok danych.<br>"
                "3. Jeśli struktura strony uległa trwałej zmianie, konieczna może być aktualizacja selektorów w kodzie."
            )
        else:
            category = f"Błąd wykonania ({err_name})"
            diagnosis = f"Wystąpił nieoczekiwany błąd podczas pracy aplikacji: {err_str}"
            recommendation = "Sprawdź plik <code>librus.log</code> oraz poniższe szczegóły techniczne w celu zdiagnozowania problemu."

        return category, diagnosis, recommendation

    @staticmethod
    def _create_error_title(user_config: dict, error: Exception, step_name: str = "") -> str:
        step_labels = {
            'inicjalizacja': 'Inicjalizacja',
            'logowanie': 'Logowanie',
            'wiadomości': 'Pobieranie wiadomości',
            'ogłoszenia': 'Pobieranie ogłoszeń',
            'oceny': 'Pobieranie ocen'
        }
        step_desc = step_labels.get(step_name, step_name or "Komunikacja")
        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        login = user_config.get('librus_login', '')
        return f"[ALERT] {name} - Librus: Błąd ({step_desc}) [konto {login}]"

    @classmethod
    def create_mail_content_for_error(
        cls,
        user_config: dict,
        error: Exception,
        step_name: str = "",
        details: str = None,
        cooldown_s: int = 3600
    ) -> str:
        step_labels = {
            'inicjalizacja': 'Inicjalizacja parsera',
            'logowanie': 'Logowanie do portalu Synergia',
            'wiadomości': 'Pobieranie wiadomości',
            'ogłoszenia': 'Pobieranie ogłoszeń',
            'oceny': 'Pobieranie ocen'
        }
        step_label = step_labels.get(step_name, step_name or "Komunikacja z portalem")
        category, diagnosis, recommendation = cls._get_error_diagnostics(error)

        name = str(user_config.get('librus_login_name') or user_config.get('librus_login', ''))
        login = str(user_config.get('librus_login', ''))
        error_msg = f"{type(error).__name__}: {str(error)}"
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cooldown_min = max(1, cooldown_s // 60)

        template = jinja_env.get_template('error_alert.html')
        return template.render(
            user_name=name,
            user_login=login,
            step_label=step_label,
            category=category,
            error_msg=error_msg,
            current_time=current_time,
            diagnosis=diagnosis,
            recommendation=recommendation,
            details=details,
            cooldown_min=cooldown_min,
        )

    @staticmethod
    def should_send_error_notification(storage, user_login: str, error_str: str, cooldown_s: int = 3600) -> bool:
        if not storage:
            return True
        last_err = storage.get_last_error(str(user_login))
        if not last_err:
            return True
        if cooldown_s <= 0:
            return True
        last_timestamp = last_err.get('timestamp', 0)
        last_msg = last_err.get('error', '')
        if error_str != last_msg:
            return True
        now = datetime.now().timestamp()
        if now - last_timestamp >= cooldown_s:
            return True
        return False

    def send_error_notification(
        self,
        user_config: dict,
        error: Exception,
        step_name: str = "",
        details: str = None,
        storage=None,
        cooldown_s: int = 3600
    ) -> bool:
        pass


jinja_env.filters['grade_badge'] = MailSender._format_grade_badge
