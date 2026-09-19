"""Librus2mail - Monitor dziennika Librus Synergia z powiadomieniami e-mail i raportami postępów."""

import logging

from .base_logger import logger, setup_logging
from .collect_and_notify import run_pipeline
from .config import read_config
from .gmail_sender import GmailSender
from .librus import Librus, NotLogged
from .librus_collector import LibrusCollector, configure_mail_provider, run_collector
from .mail_sender import MailSender
from .progress_analyzer import (
    ProgressAnalyzer,
    get_predicted_grade,
    parse_grade_date,
    parse_numeric_grade,
    parse_weight,
)
from .progress_report import run_progress_reports
from .smtp_sender import SmtpSender
from .storage import BaseStorage, FileStorage, create_storage
from .updates_notifier import UpdatesNotifier, run_notifier

logging.getLogger(__name__).addHandler(logging.NullHandler())

__version__ = "1.0.1"

__all__ = [
    "logger",
    "setup_logging",
    "read_config",
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
]
