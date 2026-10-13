"""Librus2mail - Monitor dziennika Librus Synergia z powiadomieniami e-mail i raportami postępów."""

import logging

from .base_logger import logger, setup_logging
from .collect_and_notify import run_pipeline
from .config import AppSettings, LibrusUserConfig, MailConfig, read_config
from .config_watcher import ConfigWatcher, sleep_with_config_watch
from .date_utils import parse_date_safe, parse_datetime_safe
from .dom_parser import (
    parse_announcements_html,
    parse_grades_html,
    parse_messages_html,
    parse_schedule_html,
    parse_subjects_from_html,
    parse_timetable_html,
)
from .domain_models import (
    Announcement,
    Grade,
    Message,
    Notification,
    ScheduleEntry,
    ScheduleLesson,
    TimetableEntry,
)
from .gmail_sender import GmailSender
from .librus import Librus, NotLogged
from .librus_collector import (
    LibrusCollector,
    calculate_next_wait_seconds,
    configure_mail_provider,
    run_collector,
)
from .mail_sender import MailSender
from .progress_analyzer import (
    ProgressAnalyzer,
    get_predicted_grade,
    parse_grade_date,
    parse_numeric_grade,
    parse_weight,
)
from .progress_report import run_progress_reports
from .scheduler import ReportScheduler
from .smtp_sender import SmtpSender
from .storage import BaseStorage, FileStorage, create_storage
from .student_analyzer import StudentAnalyzer
from .student_report import run_student_reports
from .updates_notifier import UpdatesNotifier, run_notifier

logging.getLogger(__name__).addHandler(logging.NullHandler())

__version__ = "2.3.0"

__all__ = [
    "__version__",
    "logger",
    "setup_logging",
    "read_config",
    "AppSettings",
    "LibrusUserConfig",
    "MailConfig",
    "Grade",
    "Message",
    "Announcement",
    "Notification",
    "TimetableEntry",
    "ScheduleLesson",
    "ScheduleEntry",
    "GmailSender",
    "Librus",
    "NotLogged",
    "run_collector",
    "LibrusCollector",
    "UpdatesNotifier",
    "run_notifier",
    "run_pipeline",
    "configure_mail_provider",
    "MailSender",
    "ProgressAnalyzer",
    "get_predicted_grade",
    "parse_grade_date",
    "parse_numeric_grade",
    "parse_weight",
    "run_progress_reports",
    "SmtpSender",
    "BaseStorage",
    "FileStorage",
    "create_storage",
    "StudentAnalyzer",
    "run_student_reports",
    "parse_datetime_safe",
    "parse_date_safe",
    "ReportScheduler",
    "ConfigWatcher",
    "sleep_with_config_watch",
    "calculate_next_wait_seconds",
    "parse_messages_html",
    "parse_announcements_html",
    "parse_grades_html",
    "parse_subjects_from_html",
    "parse_timetable_html",
    "parse_schedule_html",
]
