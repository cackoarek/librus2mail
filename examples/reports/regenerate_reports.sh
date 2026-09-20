#!/bin/bash

./venv/bin/python librus_updates_notifier.py -u 8979296 -s examples/storage --actual-date 2026-09-18 --days 7 -o examples/reports/powiadomienie_collector.html && \
./venv/bin/python librus_progress_report.py -u 8979296 -s examples/storage --actual-date 2026-09-18 --days 7 -o examples/reports/raport_8979296.html --force && \
./venv/bin/python librus_student_report.py -u 8979296 -s examples/storage --actual-date 2026-09-18 --days 7 -t kids -o examples/reports/raport_kids.html && \
./venv/bin/python librus_student_report.py -u 8979296 -s examples/storage --actual-date 2026-09-18 --days 7 -t teens -o examples/reports/raport_teens.html && \
./venv/bin/python librus_student_report.py -u 8979296 -s examples/storage --actual-date 2026-09-18 --days 7 -t youth -o examples/reports/raport_youth.html
