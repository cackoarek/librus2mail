#!/usr/bin/env python3
"""Root CLI entrypoint and wrapper for `librus2mail.updates_notifier`."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.updates_notifier import (  # noqa: F401, E402
    UpdatesNotifier,
    configure_mail_provider,
    main,
    parse_item_datetime,
    print_cli_summary,
    run_notifier,
)

if __name__ == "__main__":
    main()
