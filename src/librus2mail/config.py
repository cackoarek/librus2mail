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
    TimelineConfig,
    WebConfig,
)

logger = logging.getLogger(__name__)


def read_config(config_file: str = 'config.yaml') -> AppSettings:
    """Wczytuje i waliduje konfigurację z pliku YAML lub zmiennych środowiskowych (ENV)."""
    logger.info(f"Wczytuję konfigurację z {config_file}")
    if os.path.isfile(config_file):
        return AppSettings.from_yaml(config_file)

    # Sprawdzenie czy aplikację skonfigurowano wyłącznie za pomocą zmiennych środowiskowych (ENV)
    try:
        env_settings = AppSettings()
        if env_settings.librus_users:
            logger.info(
                f"Plik konfiguracyjny '{config_file}' nie został odnaleziony, ale wykryto konfigurację ze zmiennych środowiskowych. "
                "Uruchamiam z konfiguracją ze środowiska (ENV)."
            )
            return env_settings
    except Exception as e:
        logger.debug(f"Próba inicjalizacji konfiguracji wyłącznie z ENV nie powiodła się: {e}")

    error_msg = (
        f"Nie znaleziono pliku konfiguracyjnego '{config_file}' ani kompletnych zmiennych środowiskowych (ENV)! "
        f"Utwórz plik konfiguracyjny na podstawie szablonu, wykonując: cp config-example.yaml {config_file} "
        f"(lub wersję minimalistyczną: cp config-minimal.yaml {config_file}), albo skonfiguruj zmienne środowiskowe (ENV). "
        f"Więcej informacji na temat konfiguracji znajdziesz w dokumentacji w plikach docker/docker-installation.md oraz README.md."
    )
    logger.error(error_msg)
    raise FileNotFoundError(error_msg)


def get_reports_schedules(config: Any) -> list[dict]:
    """Zwraca listę harmonogramów raportów postępów z konfiguracji."""
    if not isinstance(config, (dict, collections.abc.Mapping)):
        return []
    sched = config.get('schedule')
    if not sched or not isinstance(sched, (dict, collections.abc.Mapping)):
        return []
    sched_reports = sched.get('reports')
    if isinstance(sched_reports, list):
        return [dict(r) for r in sched_reports if isinstance(r, (dict, collections.abc.Mapping))]
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
    "TimelineConfig",
    "WebConfig",
    "get_reports_schedules",
    "read_config",
]
