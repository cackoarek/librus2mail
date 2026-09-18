"""Moduł konfiguracji logowania dla aplikacji Librus2mail.

Zgodnie ze standardami Pythona moduły biblioteczne korzystają z:
    logger = logging.getLogger(__name__)
Konfiguracja handlerów (plik librus.log, konsola) następuje wyłącznie
w punktach wejścia aplikacji (main/CLI) poprzez wywołanie `setup_logging()`.
"""

import logging

LOG_FILE_NAME = "librus.log"
LOGGER_NAME = "librus2mail"
DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def setup_logging(
    log_file: str | None = LOG_FILE_NAME,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    log_to_console: bool = True,
    log_to_file: bool = True,
) -> logging.Logger:
    """Konfiguruje handlery logowania dla aplikacji.

    Należy wywoływać wyłącznie w punktach wejścia aplikacji (CLI / main()),
    a nie w trakcie importowania modułów.
    """
    formatter = logging.Formatter(DEFAULT_FORMAT)

    pkg_logger = logging.getLogger(LOGGER_NAME)
    legacy_logger = logging.getLogger("librus")

    for log in (pkg_logger, legacy_logger):
        log.setLevel(min(console_level, file_level))
        log.handlers.clear()
        log.propagate = False

        if log_to_console:
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            ch.setLevel(console_level)
            log.addHandler(ch)

        if log_to_file and log_file:
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setFormatter(formatter)
            fh.setLevel(file_level)
            log.addHandler(fh)

    return pkg_logger


# Logger pomocniczy bez automatycznie przypisanych handlerów I/O
logger = logging.getLogger(LOGGER_NAME)
