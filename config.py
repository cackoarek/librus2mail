import os
import yaml
from base_logger import logger


def read_config(config_file='config.yaml'):
    logger.info(f"Wczytuję konfigurację z {config_file}")
    if not os.path.isfile(config_file):
        error_msg = (
            f"Nie znaleziono pliku konfiguracyjnego '{config_file}'! "
            f"Utwórz plik konfiguracyjny na podstawie szablonu, wykonując: cp config.example.yaml {config_file}. "
            f"Więcej informacji na temat konfiguracji znajdziesz w dokumentacji w pliku README.md."
        )
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    with open(config_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    return config

