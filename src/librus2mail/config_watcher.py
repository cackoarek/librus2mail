"""
Moduł monitorowania zmian konfiguracji w locie (ConfigWatcher).
Odpowiada za detekcję modyfikacji pliku YAML i bezpieczne uśpienie z natychmiastowym
przebudzeniem w przypadku zapisu nowych ustawień.
"""

import os
import time
from collections.abc import Callable
from typing import Any


class ConfigWatcher:
    """Klasa monitorująca zmiany na dysku wskazanego pliku konfiguracji."""

    def __init__(
        self,
        config_path: str | None = None,
        poll_interval: float = 5.0,
        sleep_func: Callable[[float], Any] | None = None,
    ):
        self.config_path = config_path
        self.poll_interval = poll_interval
        self._sleep_func = sleep_func or time.sleep
        self.initial_mtime = self.get_mtime()

    def get_mtime(self) -> float | None:
        """Pobiera czas ostatniej modyfikacji pliku (mtime) lub None, jeśli plik nie istnieje."""
        if not self.config_path or not os.path.isfile(self.config_path):
            return None
        try:
            return os.path.getmtime(self.config_path)
        except OSError:
            return None

    def has_changed(self) -> bool:
        """Sprawdza, czy plik konfiguracji uległ zmianie od czasu inicjalizacji lub ostatniego resetu."""
        if self.initial_mtime is None:
            # Jeśli plik wcześniej nie istniał, a teraz istnieje – traktujemy jako zmianę
            return self.get_mtime() is not None
        curr = self.get_mtime()
        return curr is not None and curr != self.initial_mtime

    def reset(self) -> None:
        """Aktualizuje punkt odniesienia mtime do bieżącego stanu pliku."""
        self.initial_mtime = self.get_mtime()

    def sleep(self, seconds: int | float, poll_interval: float | None = None) -> bool:
        """
        Śpi przez zadany czas (w sekundach), cyklicznie sprawdzając czy plik konfiguracji uległ zmianie.

        Zwraca True, jeśli plik został zmodyfikowany (pozwalając natychmiast przeładować ustawienia),
        lub False, jeśli upłynął cały zadany czas oczekiwania bez zmian.
        """
        if seconds <= 0:
            return False

        if not self.config_path or not os.path.isfile(self.config_path):
            self._sleep_func(seconds)
            return False

        # Zaktualizuj mtime na początku snu
        self.initial_mtime = self.get_mtime()
        if self.initial_mtime is None:
            self._sleep_func(seconds)
            return False

        interval = float(poll_interval if poll_interval is not None else self.poll_interval)
        remaining = float(seconds)
        step = min(interval, remaining) if interval > 0 else remaining

        while remaining > 0:
            chunk = min(step, remaining)
            self._sleep_func(chunk)
            remaining -= chunk

            if self.has_changed():
                return True

        return False


def sleep_with_config_watch(
    seconds: int | float,
    config_path: str | None = None,
    poll_interval: float = 5.0,
    sleep_func: Callable[[float], Any] | None = None,
) -> bool:
    """
    Śpi przez zadany czas (w sekundach), monitorując czy plik konfiguracji uległ zmianie.

    Zwraca True, jeśli plik został zmodyfikowany (co pozwala natychmiast przeładować ustawienia),
    lub False, jeśli upłynął cały zadany czas oczekiwania.
    """
    watcher = ConfigWatcher(
        config_path=config_path,
        poll_interval=poll_interval,
        sleep_func=sleep_func,
    )
    return watcher.sleep(seconds)
