"""Root wrapper for `librus2mail.storage`."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.storage import (  # noqa: F401, E402
    BaseStorage,
    FileStorage,
    create_storage,
)

__all__ = ["BaseStorage", "FileStorage", "create_storage"]
