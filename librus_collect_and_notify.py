#!/usr/bin/env python3
"""
Librus2mail - Zintegrowany potok: pobieranie danych ze szkoły (Collector)
i natychmiastowa wysyłka powiadomień do rodziców (Updates Notifier).
"""
import os
import sys

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from librus2mail.collect_and_notify import main, run_pipeline  # noqa: F401, E402

if __name__ == '__main__':
    main()
