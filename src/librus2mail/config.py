"""Konfiguracja aplikacji Librus2mail z użyciem Pydantic i pydantic-settings."""

from __future__ import annotations

import collections.abc
import logging
import os
from typing import Any

from .config_models import (
    AppSettings,
    LibrusUserConfig,
    MailConfig,
    NonGmailSettings,
    ScheduleCollectionConfig,
    ScheduleConfig,
    ScheduleReportItemConfig,
    StudentReportConfig,
    WebConfig,
)

logger = logging.getLogger(__name__)


def read_config(config_file: str = 'config.yaml') -> AppSettings:
    """Wczytuje i waliduje konfigurację z pliku YAML z obsługą zmiennych środowiskowych."""
    logger.info(f"Wczytuję konfigurację z {config_file}")
    if not os.path.isfile(config_file):
        error_msg = (
            f"Nie znaleziono pliku konfiguracyjnego '{config_file}'! "
            f"Utwórz plik konfiguracyjny na podstawie szablonu, wykonując: cp config-example.yaml {config_file} "
            f"(lub wersję minimalistyczną: cp config-minimal.yaml {config_file}). "
            f"Więcej informacji na temat konfiguracji znajdziesz w dokumentacji w pliku README.md."
        )
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    return AppSettings.from_yaml(config_file)


def get_reports_schedules(config: Any) -> list[dict]:
    """Zwraca znormalizowaną listę harmonogramów raportów postępów z konfiguracji."""
    if not isinstance(config, (dict, collections.abc.Mapping)):
        return []
    sched = config.get('schedule')
    if not sched or not isinstance(sched, (dict, collections.abc.Mapping)):
        return []
    sched_reports = sched.get('reports')
    if isinstance(sched_reports, list):
        return [dict(r) for r in sched_reports if isinstance(r, (dict, collections.abc.Mapping))]
    if isinstance(sched_reports, (dict, collections.abc.Mapping)) and sched_reports:
        # Kompatybilność wsteczna z formatem pojedynczego słownika
        single = dict(sched_reports)
        if 'name' not in single:
            single['name'] = 'Raport tygodniowy' if single.get('weekday') else 'Raport postępów'
        if 'frequency' not in single:
            single['frequency'] = 'weekly'
        return [single]
    return []


__all__ = [
    "AppSettings",
    "LibrusUserConfig",
    "MailConfig",
    "NonGmailSettings",
    "ScheduleCollectionConfig",
    "ScheduleConfig",
    "ScheduleReportItemConfig",
    "StudentReportConfig",
    "WebConfig",
    "get_reports_schedules",
    "read_config",
]
