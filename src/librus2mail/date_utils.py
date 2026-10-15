"""
Narzędzia do bezpiecznego i elastycznego parsowania oraz formatowania dat i znaczników czasu.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

WARSAW_TZ = ZoneInfo("Europe/Warsaw")

CANONICAL_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
CANONICAL_DATE_FORMAT = "%Y-%m-%d"

# Najczęstsze formaty daty w systemie Librus i konfiguracji
DATE_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
)


def parse_datetime_safe(val: Any, make_naive: bool = True) -> datetime | None:
    """
    Bezpiecznie parsuje podaną wartość do obiektu datetime.

    Obsługuje:
    - datetime (opcjonalna konwersja na naive, aby uniknąć błędów TypeError przy porównaniach)
    - date (konwersja do datetime o północy)
    - liczbowe znaczniki czasu unix timestamp (int, float, w sekundach lub milisekundach)
    - stringi ISO 8601 (np. '2026-09-16T15:39:20', '2026-09-16T15:39:20Z', '2026-09-16T15:39:20+02:00')
    - stringi ze spacją ('YYYY-MM-DD HH:MM:SS')
    - formaty z ukośnikami ('YYYY/MM/DD', 'DD/MM/YYYY')
    - samą datę ('YYYY-MM-DD', 'DD.MM.YYYY')
    - tekst z opisem dnia tygodnia w nawiasie (np. '2026-09-11 (pt.)')
    - None, puste stringi, napisy '-'
    """
    if val is None:
        return None

    if isinstance(val, (int, float)):
        try:
            ts = float(val)
            if ts > 1e11:  # milisekundy
                ts /= 1000.0
            return datetime.fromtimestamp(ts)
        except (ValueError, OSError, OverflowError):
            return None

    if isinstance(val, datetime):
        if val.tzinfo is not None:
            val = val.astimezone(WARSAW_TZ)
            if make_naive:
                return val.replace(tzinfo=None)
            return val
        return val

    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())

    val_str = str(val).strip()
    if not val_str or val_str in ("-", "None", "null", "undefined"):
        return None

    # Obsługa stringów będących czystym timestampem numerycznym
    if re.match(r"^\d+(\.\d+)?$", val_str):
        try:
            ts = float(val_str)
            if ts > 1e11:
                ts /= 1000.0
            if 1e8 < ts < 2.5e9:  # bezpieczny zakres timestampów (1973 - 2049)
                return datetime.fromtimestamp(ts)
        except (ValueError, OSError, OverflowError):
            pass

    # Zastąpienie sufiksu 'Z' dla kompatybilności z datetime.fromisoformat w Python < 3.11
    # '2026-09-16T15:39:20Z' -> '2026-09-16T15:39:20+00:00'
    normalized_iso = val_str
    if normalized_iso.endswith(('Z', 'z')):
        normalized_iso = normalized_iso[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized_iso)
        if dt.tzinfo is not None:
            dt = dt.astimezone(WARSAW_TZ)
            if make_naive:
                dt = dt.replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        pass

    # Próba dopasowania do znanych formatów strptime
    for fmt in DATE_PATTERNS:
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            pass

    # Regex: ISO / data ze spacją 'YYYY-MM-DD HH:MM[:SS]'
    m_iso = re.search(r'(\d{4}-\d{2}-\d{2})(?:[T\s](\d{2}:\d{2}(?::\d{2})?))?', val_str)
    if m_iso:
        d_part = m_iso.group(1)
        t_part = m_iso.group(2) or "00:00:00"
        if len(t_part) == 5:
            t_part += ":00"
        try:
            return datetime.strptime(f"{d_part} {t_part}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    # Regex: polski format 'DD.MM.YYYY [HH:MM[:SS]]'
    m_pl = re.search(r'(\d{2})\.(\d{2})\.(\d{4})(?:[T\s](\d{2}:\d{2}(?::\d{2})?))?', val_str)
    if m_pl:
        d_part = f"{m_pl.group(3)}-{m_pl.group(2)}-{m_pl.group(1)}"
        t_part = m_pl.group(4) or "00:00:00"
        if len(t_part) == 5:
            t_part += ":00"
        try:
            return datetime.strptime(f"{d_part} {t_part}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    logger.debug("Nie udało się sparsować daty z wartości: %r", val_str[:50])
    return None


def parse_date_safe(val: Any) -> date | None:
    """Bezpiecznie parsuje wartość do obiektu date."""
    dt = parse_datetime_safe(val)
    return dt.date() if dt else None
