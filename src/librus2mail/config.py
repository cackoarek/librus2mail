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


def resolve_config_and_storage_paths(
    cli_config: str | None = None,
    cli_storage: str | None = None,
    data_dir: str | None = None,
) -> tuple[str, str | None]:
    """Ustala ścieżki do config.yaml oraz katalogu storage na podstawie parametrów CLI i zmiennych ENV.

    Hierarchia pierwszeństwa:
    1. Parametry przekazane bezpośrednio w CLI dla konkretnych ścieżek:
       - cli_config (np. -c / --config)
       - cli_storage (np. -s / --storage-dir)
    2. Zmienne środowiskowe dla konkretnych ścieżek:
       - LIBRUS_CONFIG_PATH / CONFIG_PATH
       - LIBRUS_STORAGE_DIR / STORAGE_DIR
    3. Bazowy katalog danych (gdy wskazany parametrem CLI --data-dir lub zmienną LIBRUS_DATA_DIR / DATA_DIR):
       - config_path = <data_dir>/config.yaml
       - storage_dir = <data_dir>/storage
    4. Domyślne wartości lokalne:
       - config_path = 'config.yaml'
       - storage_dir = None (wtedy aplikacja użyje domyślnego 'storage' z konfiguracji)
    """
    effective_data_dir = (
        (data_dir.strip() if data_dir and data_dir.strip() else None)
        or os.environ.get('LIBRUS_DATA_DIR', '').strip()
        or os.environ.get('DATA_DIR', '').strip()
        or None
    )

    # 1. Ścieżka konfiguracji (CLI -> ENV config -> data_dir -> domyślna)
    env_config = os.environ.get('LIBRUS_CONFIG_PATH', '').strip() or os.environ.get('CONFIG_PATH', '').strip() or None
    if cli_config and cli_config.strip():
        config_path = cli_config.strip()
    elif env_config:
        config_path = env_config
    elif effective_data_dir:
        config_path = os.path.join(effective_data_dir, 'config.yaml')
    else:
        config_path = 'config.yaml'

    # 2. Ścieżka pamięci stanu storage (CLI -> ENV storage -> data_dir -> domyślna)
    env_storage = os.environ.get('LIBRUS_STORAGE_DIR', '').strip() or os.environ.get('STORAGE_DIR', '').strip() or None
    if cli_storage and cli_storage.strip():
        storage_dir = cli_storage.strip()
    elif env_storage:
        storage_dir = env_storage
    elif effective_data_dir:
        storage_dir = os.path.join(effective_data_dir, 'storage')
    else:
        storage_dir = None

    return config_path, storage_dir


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
    "resolve_config_and_storage_paths",
]
