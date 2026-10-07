import logging
import os

import yaml

logger = logging.getLogger(__name__)


def read_config(config_file='config.yaml'):
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

    with open(config_file, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config


def get_reports_schedules(config: dict) -> list[dict]:
    """Zwraca znormalizowaną listę harmonogramów raportów postępów z konfiguracji."""
    if not isinstance(config, dict):
        return []
    sched_reports = config.get('schedule', {}).get('reports')
    if isinstance(sched_reports, list):
        return [dict(r) for r in sched_reports if isinstance(r, dict)]
    if isinstance(sched_reports, dict) and sched_reports:
        # Kompatybilność wsteczna z formatem pojedynczego słownika
        single = dict(sched_reports)
        if 'name' not in single:
            single['name'] = 'Raport tygodniowy' if single.get('weekday') else 'Raport postępów'
        if 'frequency' not in single:
            single['frequency'] = 'weekly'
        return [single]
    return []

