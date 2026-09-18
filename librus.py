"""Root wrapper for `librus2mail.librus`."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.librus import (  # noqa: F401, E402
    GRADES_URL,
    MESSAGE_BODY_URL,
    MESSAGES_URL,
    NOTIFICATIONS_URL,
    OAUTH_DEFAULT_URL,
    PORTAL_RODZINA_URL,
    USER_AGENT,
    Librus,
    NotLogged,
)

__all__ = [
    "Librus",
    "NotLogged",
    "PORTAL_RODZINA_URL",
    "OAUTH_DEFAULT_URL",
    "MESSAGES_URL",
    "MESSAGE_BODY_URL",
    "NOTIFICATIONS_URL",
    "GRADES_URL",
    "USER_AGENT",
]
