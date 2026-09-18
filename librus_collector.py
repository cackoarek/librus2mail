#!/usr/bin/env python3
"""Root CLI entrypoint and backward-compatibility wrapper for `librus2mail.librus_collector`."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.librus_collector import (  # noqa: F401, E402
    configure_mail_provider,
    run_collector,
)

if __name__ == "__main__":
    config_file = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    run_collector(config_file)
