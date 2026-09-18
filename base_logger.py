"""Root wrapper for `librus2mail.base_logger`."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.base_logger import (  # noqa: F401, E402
    DEFAULT_FORMAT,
    LOG_FILE_NAME,
    LOGGER_NAME,
    logger,
    setup_logging,
)

__all__ = ["logger", "setup_logging", "LOG_FILE_NAME", "LOGGER_NAME", "DEFAULT_FORMAT"]
