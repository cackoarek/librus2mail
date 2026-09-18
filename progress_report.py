#!/usr/bin/env python3
"""Root CLI entrypoint and backward-compatibility wrapper for `librus2mail.progress_report`."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.progress_report import (  # noqa: F401, E402
    main,
    parse_args,
    run_progress_reports,
)

if __name__ == "__main__":
    main()
