#!/usr/bin/env python3
"""Punkt wejścia CLI dla interaktywnego panelu webowego Librus2mail."""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.web.app import main  # noqa: E402

if __name__ == '__main__':
    main()

