#!/usr/bin/env python3
"""Root CLI entrypoint for `librus2mail.student_report` (Moduł 4: Raport ucznia)."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.student_report import (  # noqa: F401, E402
    main,
    parse_args,
    run_student_reports,
)

if __name__ == "__main__":
    main()
