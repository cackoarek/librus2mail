"""Root wrapper for `librus2mail.config`."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.config import read_config  # noqa: F401, E402

__all__ = ["read_config"]
