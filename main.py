#!/usr/bin/env python3
"""
Główny punkt wejścia - alias dla librus_collector.py.
Dla zachowania pełnej kompatybilności wstecznej uruchamia usługę zbierania danych i powiadomień.
Możesz również uruchamiać bezpośrednio: python librus_collector.py
"""
import sys
from librus_collector import configure_mail_provider, run_collector

if __name__ == '__main__':
    config_file = sys.argv[1] if len(sys.argv) > 1 else 'config.yaml'
    run_collector(config_file)
