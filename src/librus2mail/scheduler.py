"""
Moduł harmonogramu zadań (Scheduler).
Odpowiada za wyliczanie interwałów oczekiwania, sprawdzanie warunków pobierania
danych ze szkoły w trybie dziennym oraz wyzwalanie zaplanowanych raportów postępów.
"""

import collections.abc
import logging
from datetime import datetime, timedelta

from .config import get_reports_schedules
from .date_utils import parse_datetime_safe
from .storage import BaseStorage

logger = logging.getLogger(__name__)

WEEKDAYS_MAP = {
    'monday': 0,
    'tuesday': 1,
    'wednesday': 2,
    'thursday': 3,
    'friday': 4,
    'saturday': 5,
    'sunday': 6,
}

__all__ = [
    "ReportScheduler",
    "calculate_next_wait_seconds",
    "should_collect_now",
    "trigger_scheduled_reports",
]


def calculate_next_wait_seconds(config: dict, now: datetime | None = None) -> int:
    """Oblicza liczbę sekund do kolejnego cyklu na podstawie harmonogramu pobierania (collection)
    oraz zaplanowanych raportów (schedule.reports), wybierając najbliższe nadchodzące zdarzenie."""
    ref_now = now or datetime.now()
    sched = config.get('schedule', {}) if isinstance(config, (dict, collections.abc.Mapping)) else {}
    collection_sched = sched.get('collection', {}) if isinstance(sched, (dict, collections.abc.Mapping)) else {}
    mode = collection_sched.get('mode')

    candidates: list[datetime] = []

    # 1. Najbliższy termin pobierania danych ze szkoły (collection)
    if mode == 'daily':
        time_str = collection_sched.get('time', '16:00')
        days_rule = collection_sched.get('days', 'all')
        try:
            th, tm = map(int, time_str.split(':'))
        except (ValueError, TypeError, AttributeError):
            th, tm = 16, 0

        target = ref_now.replace(hour=th, minute=tm, second=0, microsecond=0)
        if ref_now >= target:
            target += timedelta(days=1)
        if days_rule == 'workdays':
            while target.weekday() >= 5:  # 5=sobota, 6=niedziela
                target += timedelta(days=1)
        candidates.append(target)
    elif mode == 'interval' and 'interval_hours' in collection_sched:
        wait_s = max(300, int(collection_sched['interval_hours']) * 3600)
        candidates.append(ref_now + timedelta(seconds=wait_s))
    else:
        wait_s = max(300, int(config.get('wait_time_s', 3600)))
        candidates.append(ref_now + timedelta(seconds=wait_s))

    # 2. Najbliższy termin każdego włączonego raportu postępów / motywacyjnego (schedule.reports)
    reports_schedules = get_reports_schedules(config)
    for rep in reports_schedules:
        if not rep.get('enabled', True):
            continue

        freq = str(rep.get('frequency', 'weekly')).lower()
        target_time_str = rep.get('time', '17:00')
        try:
            rh, rm = map(int, target_time_str.split(':'))
        except (ValueError, TypeError, AttributeError):
            rh, rm = 17, 0

        if freq == 'monthly':
            dom_rule = str(rep.get('day_of_month', '1')).lower()
            for offset in range(32):
                test_date = (ref_now + timedelta(days=offset)).date()
                matches_dom = False
                if dom_rule == 'last':
                    matches_dom = ((test_date + timedelta(days=1)).day == 1)
                else:
                    try:
                        matches_dom = (test_date.day == int(dom_rule))
                    except (ValueError, TypeError):
                        matches_dom = (test_date.day == 1)

                if matches_dom:
                    test_dt = datetime.combine(test_date, datetime.min.time()).replace(
                        hour=rh, minute=rm, second=0, microsecond=0
                    )
                    if test_dt > ref_now:
                        candidates.append(test_dt)
                        break
        else:  # weekly
            target_weekday = str(rep.get('weekday', 'friday')).lower()
            target_day_num = WEEKDAYS_MAP.get(target_weekday, 4)
            for offset in range(8):
                test_date = (ref_now + timedelta(days=offset)).date()
                if test_date.weekday() == target_day_num:
                    test_dt = datetime.combine(test_date, datetime.min.time()).replace(
                        hour=rh, minute=rm, second=0, microsecond=0
                    )
                    if test_dt > ref_now:
                        candidates.append(test_dt)
                        break

    if not candidates:
        return max(300, int(config.get('wait_time_s', 3600)))

    earliest_target = min(candidates)
    return max(60, int((earliest_target - ref_now).total_seconds()))


def should_collect_now(
    config: dict,
    users: list[dict],
    storage: BaseStorage,
    now: datetime | None = None,
) -> bool:
    """Sprawdza, czy pobieranie danych ze szkoły powinno nastąpić w bieżącym cyklu.

    W trybie 'daily' o stałej porze (np. 16:00/22:00) przy starcie weryfikujemy,
    czy dzisiejsze pobieranie już się odbyło lub czy jeszcze nie nadeszła jego pora.
    """
    sched = config.get('schedule', {}) if isinstance(config, (dict, collections.abc.Mapping)) else {}
    col_sched = sched.get('collection', {}) if isinstance(sched, (dict, collections.abc.Mapping)) else {}
    if col_sched.get('mode') != 'daily':
        return True

    time_str = col_sched.get('time', '16:00')
    try:
        th, tm = map(int, time_str.split(':'))
    except (ValueError, TypeError, AttributeError):
        th, tm = 16, 0

    now_dt = now or datetime.now()
    is_after_time = (now_dt.hour > th or (now_dt.hour == th and now_dt.minute >= tm))

    all_collected_today = True
    all_have_data = True
    for u in users:
        u_login = str(u.get('librus_login', ''))
        if not storage.has_existing_data(u_login):
            all_have_data = False
            all_collected_today = False
            break
        last_col = storage.get_last_collect_time(u_login)
        if not last_col:
            all_collected_today = False
        else:
            last_col_dt = parse_datetime_safe(last_col)
            if not last_col_dt or last_col_dt.date() != now_dt.date() or not (
                last_col_dt.hour > th or (last_col_dt.hour == th and last_col_dt.minute >= tm)
            ):
                all_collected_today = False

    if all_have_data:
        if not is_after_time:
            logger.info(
                f"⏰ Harmonogram 'daily': zaplanowana godzina to {time_str} (aktualna: {now_dt.strftime('%H:%M')}). "
                "Pomijam natychmiastowe pobieranie przy starcie, czekam do wyznaczonej pory."
            )
            return False
        if all_collected_today:
            logger.info(
                f"⏰ Harmonogram 'daily': dzisiejsze pobieranie o {time_str} zostało już zrealizowane. "
                "Pomijam powtórne pobieranie przy starcie, czekam do kolejnego terminu."
            )
            return False

    return True


def trigger_scheduled_reports(
    config: dict,
    config_path: str,
    users: list[dict],
    storage: BaseStorage,
    effective_storage_dir: str,
    now: datetime | None = None,
) -> list[str]:
    """Weryfikuje i wyzwala zaplanowane raporty postępów i motywacyjne dla użytkowników.

    Zwraca listę identyfikatorów wyzwolonych raportów.
    """
    reports_schedules = get_reports_schedules(config)
    if not reports_schedules:
        return []

    ref_now = now or datetime.now()
    triggered: list[str] = []

    for rep in reports_schedules:
        if not rep.get('enabled', True):
            continue

        freq = str(rep.get('frequency', 'weekly')).lower()
        target_time_str = rep.get('time', '17:00')
        try:
            rh, rm = map(int, target_time_str.split(':'))
        except (ValueError, TypeError, AttributeError):
            rh, rm = 17, 0

        time_matches = (ref_now.hour > rh or (ref_now.hour == rh and ref_now.minute >= rm))
        if not time_matches:
            continue

        date_matches = False
        if freq == 'monthly':
            dom_rule = str(rep.get('day_of_month', '1')).lower()
            if dom_rule == 'last':
                date_matches = ((ref_now + timedelta(days=1)).day == 1)
            else:
                try:
                    date_matches = (ref_now.day == int(dom_rule))
                except (ValueError, TypeError):
                    date_matches = (ref_now.day == 1)
        else:  # weekly
            target_weekday = str(rep.get('weekday', 'friday')).lower()
            target_day_num = WEEKDAYS_MAP.get(target_weekday, 4)
            date_matches = (ref_now.weekday() == target_day_num)

        if not date_matches:
            continue

        rep_days = int(rep.get('interval_days', 7))
        rep_name = rep.get('name') or f"Raport ({rep_days} dni)"
        rep_key = f"rep_{freq}_{rep_days}_{target_time_str}"

        for u in users:
            u_login = str(u.get('librus_login'))
            last_rep = storage.get_last_progress_report_date(u_login, report_key=rep_key)
            already_sent_today = False
            if last_rep:
                rep_dt = parse_datetime_safe(last_rep)
                if rep_dt and rep_dt.date() == ref_now.date():
                    already_sent_today = True

            if not already_sent_today:
                logger.info(f"📅 Wyzwalanie zaplanowanego raportu postępów '{rep_name}' dla {u_login} (za {rep_days} dni)...")
                try:
                    from .progress_report import run_progress_reports
                    run_progress_reports(
                        config_path=config_path,
                        storage_dir=effective_storage_dir,
                        user_filter=u_login,
                        days=rep_days,
                        report_key=rep_key,
                    )
                    triggered.append(f"progress:{u_login}:{rep_key}")
                except Exception as rep_err:
                    logger.error(
                        f"Błąd podczas generowania zaplanowanego raportu postępów '{rep_name}': {rep_err}",
                        exc_info=True,
                    )

                # Opcjonalne wyzwolenie raportu motywacyjnego dla samego dziecka, jeśli włączony w profilu ucznia
                st_rep_cfg = u.get('student_report') or {}
                if st_rep_cfg and st_rep_cfg.get('enabled', True) and (st_rep_cfg.get('email') or st_rep_cfg.get('receivers')):
                    logger.info(f"🎓 Wyzwalanie zaplanowanego raportu motywacyjnego dla ucznia {u_login} (za {rep_days} dni)...")
                    try:
                        from .student_report import run_student_reports
                        run_student_reports(
                            config_path=config_path,
                            storage_dir=effective_storage_dir,
                            user_filter=u_login,
                            days=rep_days,
                        )
                        triggered.append(f"student:{u_login}:{rep_key}")
                    except Exception as st_err:
                        logger.error(
                            f"Błąd podczas generowania zaplanowanego raportu motywacyjnego dla {u_login}: {st_err}",
                            exc_info=True,
                        )

    return triggered


class ReportScheduler:
    """Klasa orkiestrująca harmonogramy pobierania oraz raportów."""

    def __init__(self, config: dict, storage: BaseStorage | None = None):
        self.config = config
        self.storage = storage

    def calculate_next_wait_seconds(self, now: datetime | None = None) -> int:
        return calculate_next_wait_seconds(self.config, now=now)

    def should_collect_now(self, users: list[dict], now: datetime | None = None) -> bool:
        if not self.storage:
            return True
        return should_collect_now(self.config, users=users, storage=self.storage, now=now)

    def trigger_scheduled_reports(
        self,
        config_path: str,
        users: list[dict],
        effective_storage_dir: str,
        now: datetime | None = None,
    ) -> list[str]:
        if not self.storage:
            return []
        return trigger_scheduled_reports(
            config=self.config,
            config_path=config_path,
            users=users,
            storage=self.storage,
            effective_storage_dir=effective_storage_dir,
            now=now,
        )
