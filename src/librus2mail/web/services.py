"""Warstwa usług i logiki biznesowej dla panelu webowego Librus2mail."""

import io
import logging
import math
import os
import re
import statistics
from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

from librus2mail.date_utils import parse_date_safe, parse_datetime_safe
from librus2mail.mail_sender import MailSender
from librus2mail.progress_analyzer import (
    ProgressAnalyzer,
    get_predicted_grade_tuple,
    parse_grade_date,
    parse_numeric_grade,
    parse_weight,
)
from librus2mail.storage import (
    BaseStorage,
    create_storage,
    sort_grades_descending,
    sort_items_descending,
)
from librus2mail.student_analyzer import StudentAnalyzer
from librus2mail.updates_notifier import (
    parse_item_datetime,
    prepare_schedule_summary,
    prepare_timetable_summary,
)

logger = logging.getLogger(__name__)


def get_storage(config: dict, storage_dir: str | None = None) -> BaseStorage:
    """Zwraca instancję pamięci stanu (storage)."""
    effective_dir = storage_dir or config.get('storage_dir', 'storage')
    return create_storage(effective_dir)


def resolve_student_name(config: dict, storage: BaseStorage, login: str | int) -> str:
    """Ustala pełną nazwę ucznia (z configu lub storage) wraz z identyfikatorem konta."""
    s_login = str(login)
    user_cfg = next(
        (u for u in config.get('librus_users', []) if str(u.get('librus_login', '')) == s_login),
        {}
    )
    base_name = (
        user_cfg.get('librus_login_name')
        or (storage.get_student_name(s_login) if hasattr(storage, 'get_student_name') else None)
        or "Uczeń"
    )
    if user_cfg.get('librus_login_name') and hasattr(storage, 'set_student_name'):
        storage.set_student_name(s_login, user_cfg['librus_login_name'])

    if f"({s_login})" not in base_name:
        return f"{base_name} ({s_login})"
    return base_name


def format_human_timestamp(val: str | datetime | None, now: datetime | None = None) -> str:
    """Konwertuje znacznik czasu (ISO string lub datetime) na przyjazny dla człowieka tekst w języku polskim.

    Przykłady:
      - 'dzisiaj o 12:25 (przed chwilą)'
      - 'dzisiaj o 12:25 (46 min temu)'
      - 'dzisiaj o 09:30 (3 godz. temu)'
      - 'wczoraj o 19:40'
      - 'przedwczoraj o 18:15'
      - '05.10 o 14:20 (2 dni temu)'
      - '28.09.2025 o 10:15'
    """
    if not val:
        return "Brak danych"

    dt = parse_datetime_safe(val, make_naive=True)
    if not dt:
        return str(val)

    ref_now = now or datetime.now()
    if ref_now.tzinfo is not None:
        ref_now = ref_now.astimezone().replace(tzinfo=None)

    diff = ref_now - dt
    total_seconds = diff.total_seconds()
    time_str = dt.strftime("%H:%M")

    if total_seconds < 0:
        if dt.date() == ref_now.date():
            return f"dzisiaj o {time_str}"
        return f"{dt.strftime('%d.%m.%Y')} o {time_str}"

    dt_date = dt.date()
    now_date = ref_now.date()
    days_diff = (now_date - dt_date).days

    if days_diff == 0:
        if total_seconds < 60:
            return f"dzisiaj o {time_str} (przed chwilą)"
        if total_seconds < 3600:
            minutes = max(1, int(total_seconds // 60))
            return f"dzisiaj o {time_str} ({minutes} min temu)"
        hours = int(total_seconds // 3600)
        return f"dzisiaj o {time_str} ({hours} godz. temu)"

    if days_diff == 1:
        return f"wczoraj o {time_str}"

    if days_diff == 2:
        return f"przedwczoraj o {time_str}"

    if dt.year == ref_now.year:
        if days_diff <= 30:
            return f"{dt.strftime('%d.%m')} o {time_str} ({days_diff} dni temu)"
        return f"{dt.strftime('%d.%m')} o {time_str}"

    return f"{dt.strftime('%d.%m.%Y')} o {time_str}"


def list_students(config: dict, storage: BaseStorage) -> list[dict[str, Any]]:
    """Zwraca listę wszystkich dostępnych uczniów (z konfiguracji oraz pamięci storage)."""
    students_dict: dict[str, dict[str, Any]] = {}

    for u in config.get('librus_users', []):
        login = str(u.get('librus_login', ''))
        if login:
            name = resolve_student_name(config, storage, login)
            students_dict[login] = {
                'login': login,
                'name': name,
                'configured': True,
                'raw_config': u,
            }

    if hasattr(storage, 'list_stored_logins'):
        for s_login in storage.list_stored_logins():
            if s_login not in students_dict:
                name = resolve_student_name(config, storage, s_login)
                students_dict[s_login] = {
                    'login': s_login,
                    'name': name,
                    'configured': False,
                    'raw_config': {},
                }

    return list(students_dict.values())


def get_active_student_login(
    config: dict,
    storage: BaseStorage,
    requested_login: str | None = None,
    session_login: str | None = None,
) -> str | None:
    """Ustala login aktywnego ucznia na podstawie parametru, sesji lub konfiguracji."""
    students = list_students(config, storage)
    if not students:
        return None

    all_logins = {s['login'] for s in students}

    if requested_login and requested_login in all_logins:
        return requested_login
    if session_login and session_login in all_logins:
        return session_login

    return students[0]['login']


def calculate_subject_averages(
    grades_history: list[dict[str, Any]],
    excluded_subjects: list[str] | set[str] | None = None,
    all_subjects: list[str] | set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Wylicza średnie ważone i statystyki per przedmiot na podstawie historii ocen (oraz listy wszystkich przedmiotów)."""
    norm_excluded = {s.strip().lower() for s in (excluded_subjects or [])}
    by_subject = defaultdict(list)
    for g in grades_history:
        subj = g.get('subject', 'Inne')
        by_subject[subj].append(g)

    # Upewnij się, że przedmioty bez ocen (np. Taniec, Historia) również są uwzględnione
    if all_subjects:
        for s in all_subjects:
            s_clean = str(s).strip()
            if s_clean and s_clean not in by_subject:
                by_subject[s_clean] = []

    result = {}
    for subj, g_list in by_subject.items():
        sum_weighted = 0.0
        sum_weights = 0.0
        numeric_count = 0

        for g in g_list:
            n_grade = parse_numeric_grade(g.get('grade'))
            w = parse_weight(g.get('weight'))
            if n_grade is not None:
                numeric_count += 1
                effective_weight = w if w is not None and w > 0 else 1.0
                sum_weighted += n_grade * effective_weight
                sum_weights += effective_weight

        avg = round(sum_weighted / sum_weights, 2) if sum_weights > 0 else None
        sorted_grades = sort_grades_descending(g_list)
        is_excluded = subj.strip().lower() in norm_excluded

        result[subj] = {
            'subject': subj,
            'grades': sorted_grades,
            'count': len(g_list),
            'numeric_count': numeric_count,
            'average': avg,
            'sum_weights': sum_weights,
            'sum_weighted': sum_weighted,
            'is_excluded': is_excluded,
        }

    return dict(sorted(result.items(), key=lambda item: item[0]))


def calculate_overall_average(subject_averages: dict[str, dict[str, Any]]) -> float | None:
    """Wylicza ogólną średnią arytmetyczną z ocen ze wszystkich przedmiotów."""
    avgs = [v['average'] for v in subject_averages.values() if v.get('average') is not None]
    if not avgs:
        return None
    return round(sum(avgs) / len(avgs), 2)


GRADE_WORDS = {
    6: "celujący",
    5: "bardzo dobry",
    4: "dobry",
    3: "dostateczny",
    2: "dopuszczający",
    1: "niedostateczny",
}

THRESHOLD_MAP = {
    6: 5.51,
    5: 4.75,
    4: 3.75,
    3: 2.75,
    2: 1.75,
    1: 0.00,
}


def _compute_target_analysis(
    current_avg: float | None,
    current_sum_weighted: float,
    current_sum_weights: float,
    current_grade_num: int | None,
) -> dict[str, Any]:
    """Wylicza analizę możliwości podwyższenia oceny końcowej na kolejny stopień."""
    if current_avg is None or current_grade_num is None:
        return {
            'has_target': False,
            'is_max': False,
            'message': 'Brak ocen liczbowych do wyznaczenia celu.',
            'scenarios': [],
        }

    if current_grade_num >= 6:
        return {
            'has_target': False,
            'is_max': True,
            'target_grade_num': 6,
            'target_grade_label': "6 (celujący)",
            'message': "Uczeń osiągnął już najwyższą możliwą ocenę celującą (6)! 🎉",
            'scenarios': [],
        }

    target_grade_num = current_grade_num + 1
    target_threshold = THRESHOLD_MAP.get(target_grade_num, 4.75)
    target_word = GRADE_WORDS.get(target_grade_num, "")
    target_label = f"{target_grade_num} ({target_word})"
    gap = max(0.0, round(target_threshold - current_avg, 2))

    scenarios: list[dict[str, Any]] = []
    # 1. Scenariusze pojedynczej oceny o wagach 1, 2, 3, 4
    for w in (1.0, 2.0, 3.0, 4.0):
        needed_val = (target_threshold * (current_sum_weights + w) - current_sum_weighted) / w
        if needed_val <= 6.0:
            if needed_val <= 4.75:
                desc = f"1x ocena 5 lub wyższa przy wadze {int(w)}"
            elif needed_val <= 5.0:
                desc = f"1x ocena 5 przy wadze {int(w)}"
            elif needed_val <= 5.5:
                desc = f"1x ocena 5+ lub 6 przy wadze {int(w)}"
            else:
                desc = f"1x ocena 6 (celujący) przy wadze {int(w)}"

            new_avg_sample = round((current_sum_weighted + max(needed_val, 5.0) * w) / (current_sum_weights + w), 2)
            scenarios.append({
                'type': 'single',
                'weight': int(w),
                'needed_grade_raw': round(needed_val, 2),
                'description': desc,
                'sample_result_avg': new_avg_sample,
            })

    # 2. Scenariusze dwóch ocen (np. dwie piątki ze sprawdzianów o wadze 2 lub 3)
    for w in (2.0, 3.0):
        new_w = w * 2
        new_sum = current_sum_weighted + (5.0 * w * 2)
        sim_avg = round(new_sum / (current_sum_weights + new_w), 2)
        if sim_avg >= target_threshold:
            scenarios.append({
                'type': 'multi',
                'weight': int(w),
                'needed_grade_raw': 5.0,
                'description': f"2x ocena 5 (bardzo dobry) o wadze {int(w)} każda",
                'sample_result_avg': sim_avg,
            })

    # Ocena trudności osiągnięcia celu
    if any(s['weight'] <= 2 and s.get('needed_grade_raw', 99) <= 5.0 for s in scenarios if s['type'] == 'single'):
        difficulty = "easy"
        difficulty_label = "Łatwy cel (wystarczy dobra kartkówka lub odpowiedź)"
    elif any(s.get('needed_grade_raw', 99) <= 5.5 for s in scenarios if s['type'] == 'single'):
        difficulty = "realistic"
        difficulty_label = "Realny cel (wymaga b. dobrej oceny ze sprawdzianu)"
    elif scenarios:
        difficulty = "challenging"
        difficulty_label = "Wymagający cel (wymaga maksymalnej oceny lub dwóch sprawdzianów)"
    else:
        difficulty = "hard"
        difficulty_label = "Bardzo trudny cel (wymaga serii bardzo dobrych ocen)"

    return {
        'has_target': True,
        'is_max': False,
        'target_grade_num': target_grade_num,
        'target_grade_label': target_label,
        'target_threshold': target_threshold,
        'gap': gap,
        'difficulty': difficulty,
        'difficulty_label': difficulty_label,
        'scenarios': scenarios,
    }


def _compute_risk_analysis(
    current_avg: float | None,
    current_sum_weighted: float,
    current_sum_weights: float,
    current_grade_num: int | None,
) -> dict[str, Any]:
    """Wylicza margines bezpieczeństwa oraz ryzyko obniżenia oceny końcowej na niższy stopień."""
    if current_avg is None or current_grade_num is None:
        return {
            'has_risk': False,
            'is_min': False,
            'safety_margin': None,
            'message': 'Brak ocen liczbowych do oceny ryzyka.',
            'drop_simulations': [],
        }

    if current_grade_num <= 1:
        return {
            'has_risk': True,
            'is_min': True,
            'safety_margin': 0.0,
            'risk_level': 'critical',
            'risk_label': 'Zagrożenie oceną niedostateczną (1)',
            'message': 'Bieżąca średnia wskazuje na ocenę niedostateczną (1). Wymagana pilna poprawa.',
            'drop_simulations': [],
        }

    current_threshold = THRESHOLD_MAP.get(current_grade_num, 1.75)
    lower_grade_num = current_grade_num - 1
    lower_word = GRADE_WORDS.get(lower_grade_num, "")
    lower_label = f"{lower_grade_num} ({lower_word})"

    safety_margin = round(current_avg - current_threshold, 2)

    if safety_margin < 0.10:
        risk_level = 'critical'
        risk_label = 'Wysokie ryzyko spadku (na granicy progu)'
    elif safety_margin < 0.25:
        risk_level = 'moderate'
        risk_label = 'Umiarkowane ryzyko spadku'
    else:
        risk_level = 'safe'
        risk_label = 'Stabilny margines bezpieczeństwa'

    # Symulacje negatywnych zdarzeń (co jeśli uczeń dostanie słabą ocenę):
    drop_simulations: list[dict[str, Any]] = []
    for test_grade, test_w in [(1.0, 1.0), (1.0, 3.0), (2.0, 2.0)]:
        new_w = current_sum_weights + test_w
        new_sum = current_sum_weighted + (test_grade * test_w)
        sim_avg = round(new_sum / new_w, 2)
        sim_grade_num, sim_grade_label = get_predicted_grade_tuple(sim_avg)
        causes_drop = sim_grade_num < current_grade_num
        drop_simulations.append({
            'test_grade': int(test_grade),
            'test_weight': int(test_w),
            'sim_avg': sim_avg,
            'diff': round(sim_avg - current_avg, 2),
            'causes_drop': causes_drop,
            'sim_grade_num': sim_grade_num,
            'sim_grade_label': sim_grade_label,
            'desc': (
                f"Ocena {int(test_grade)} z wagą {int(test_w)} obniży średnią do {sim_avg}"
                + (f" ⚠️ (spadek do {sim_grade_label})!" if causes_drop else f" (nadal bezpieczna ocena {current_grade_num})")
            ),
        })

    return {
        'has_risk': True,
        'is_min': False,
        'current_threshold': current_threshold,
        'lower_grade_num': lower_grade_num,
        'lower_grade_label': lower_label,
        'safety_margin': safety_margin,
        'risk_level': risk_level,
        'risk_label': risk_label,
        'drop_simulations': drop_simulations,
    }


def _compute_category_analytics(
    matching_grades: list[dict[str, Any]],
    total_sum_weights: float,
) -> dict[str, Any]:
    """Wylicza skuteczność ucznia w rozbiciu na poszczególne kategorie prac (sprawdziany, kartkówki itp.)."""
    cat_map: dict[str, dict[str, Any]] = {}

    for g in matching_grades:
        num_val = parse_numeric_grade(g.get('grade'))
        raw_w = parse_weight(g.get('weight'))
        eff_w = raw_w if (raw_w is not None and raw_w > 0) else (1.0 if num_val is not None else 0.0)

        raw_cat = str(g.get('category') or '').strip()
        cat_name = raw_cat if raw_cat else 'Inne / Bieżące'

        if cat_name not in cat_map:
            cat_map[cat_name] = {
                'name': cat_name,
                'grades_count': 0,
                'numeric_count': 0,
                'sum_weighted': 0.0,
                'sum_weights': 0.0,
                'grades_list': [],
            }

        cat_map[cat_name]['grades_count'] += 1
        if num_val is not None:
            cat_map[cat_name]['numeric_count'] += 1
            cat_map[cat_name]['sum_weighted'] += num_val * eff_w
            cat_map[cat_name]['sum_weights'] += eff_w
            cat_map[cat_name]['grades_list'].append(num_val)

    items: list[dict[str, Any]] = []
    for cat_name, data in cat_map.items():
        w_avg = round(data['sum_weighted'] / data['sum_weights'], 2) if data['sum_weights'] > 0 else None
        a_avg = round(sum(data['grades_list']) / data['numeric_count'], 2) if data['numeric_count'] > 0 else None
        share = round((data['sum_weights'] / total_sum_weights) * 100, 1) if total_sum_weights > 0 else 0.0

        items.append({
            'name': cat_name,
            'grades_count': data['grades_count'],
            'numeric_count': data['numeric_count'],
            'sum_weights': round(data['sum_weights'], 2),
            'weighted_average': w_avg,
            'arithmetic_average': a_avg,
            'weight_share': share,
        })

    # Sortujemy: najpierw te ze średnią ważoną wg sumy wag malejąco
    items.sort(key=lambda x: (x['weighted_average'] is not None, x['sum_weights'], x['grades_count']), reverse=True)

    radar_labels: list[str] = []
    radar_averages: list[float] = []
    radar_counts: list[int] = []
    for it in items:
        if it['weighted_average'] is not None:
            radar_labels.append(it['name'])
            radar_averages.append(it['weighted_average'])
            radar_counts.append(it['grades_count'])

    best_cat = max((it for it in items if it['weighted_average'] is not None), key=lambda x: x['weighted_average'], default=None)
    worst_cat = min((it for it in items if it['weighted_average'] is not None), key=lambda x: x['weighted_average'], default=None)

    insight = ""
    if best_cat and worst_cat and best_cat['name'] != worst_cat['name']:
        diff = round(best_cat['weighted_average'] - worst_cat['weighted_average'], 2)
        if diff >= 0.75:
            insight = (
                f"Wyraźna dysproporcja: najlepsze wyniki w '{best_cat['name']}' (śr. {best_cat['weighted_average']}), "
                f"a największe wyzwanie to '{worst_cat['name']}' (śr. {worst_cat['weighted_average']}). Różnica wynosi aż {diff} pkt."
            )
        else:
            insight = f"Zrównoważona forma w różnych formach sprawdzania wiedzy (średnie od {worst_cat['weighted_average']} do {best_cat['weighted_average']})."
    elif best_cat:
        insight = f"Oceny skupione głównie w kategorii '{best_cat['name']}' ze średnią {best_cat['weighted_average']}."

    return {
        'has_data': bool(items),
        'categories': items,
        'radar_labels': radar_labels,
        'radar_averages': radar_averages,
        'radar_counts': radar_counts,
        'best_category': best_cat,
        'worst_category': worst_cat,
        'insight': insight,
    }


def _compute_impact_analysis(
    timeline_data: list[dict[str, Any]],
    current_avg: float | None,
    current_sum_weighted: float,
    current_sum_weights: float,
) -> dict[str, Any]:
    """Wylicza wpływ poszczególnych ocen na średnią: lokomotywy (ciągnące w górę) i kotwice (ściągające w dół)."""
    if current_avg is None or current_sum_weights <= 0:
        return {'boosters': [], 'draggers': [], 'has_data': False}

    impacted: list[dict[str, Any]] = []

    for item in timeline_data:
        num_val = item.get('numeric_grade')
        w = float(item.get('weight') or 1.0)
        if num_val is None or w <= 0:
            continue

        without_weights = current_sum_weights - w
        without_weighted = current_sum_weighted - (num_val * w)

        if without_weights > 0:
            avg_without = round(without_weighted / without_weights, 2)
            delta = round(current_avg - avg_without, 2)
        else:
            avg_without = current_avg
            delta = 0.0

        # Kalkulacja zysku przy poprawie oceny na 5 (bdb) lub 4 (db)
        sum_with_5 = (current_sum_weighted - (num_val * w)) + (5.0 * w)
        sim_avg_if_5 = round(sum_with_5 / current_sum_weights, 2)
        gain_if_5 = round(sim_avg_if_5 - current_avg, 2)

        sum_with_4 = (current_sum_weighted - (num_val * w)) + (4.0 * w)
        sim_avg_if_4 = round(sum_with_4 / current_sum_weights, 2)
        gain_if_4 = round(sim_avg_if_4 - current_avg, 2)

        impacted.append({
            'id': item.get('id'),
            'grade': item.get('grade'),
            'numeric_grade': num_val,
            'weight': w,
            'category': item.get('category'),
            'date': item.get('date'),
            'comment': item.get('comment'),
            'teacher': item.get('teacher'),
            'delta': delta,
            'avg_without': avg_without,
            'gain_if_5': gain_if_5,
            'gain_if_4': gain_if_4,
            'sim_avg_if_5': sim_avg_if_5,
            'sim_avg_if_4': sim_avg_if_4,
        })

    # Sortujemy:
    # Lokomotywy (boosters): delta > 0, malejąco
    boosters = sorted([x for x in impacted if x['delta'] > 0], key=lambda x: x['delta'], reverse=True)[:3]
    # Kotwice (draggers): delta < 0, rosnąco (najbardziej ujemne)
    draggers = sorted([x for x in impacted if x['delta'] < 0], key=lambda x: x['delta'])[:3]

    return {
        'has_data': bool(boosters or draggers),
        'boosters': boosters,
        'draggers': draggers,
    }


def _compute_consistency_metrics(numeric_vals: list[float]) -> dict[str, Any]:
    """Wylicza odchylenie standardowe oraz wskaźnik stabilności formy (Consistency Score 0-100%)."""
    if not numeric_vals:
        return {
            'has_data': False,
            'stdev': None,
            'score': None,
            'status': 'neutral',
            'label': 'Brak ocen do oceny stabilności',
            'desc': (
                "Wskaźnik stabilności formy (0–100%): Mierzy systematyczność i powtarzalność wyników ucznia "
                "na podstawie odchylenia standardowego ocen. Wymaga co najmniej 1 oceny liczbowej."
            ),
        }

    if len(numeric_vals) == 1:
        return {
            'has_data': True,
            'stdev': 0.0,
            'score': 100,
            'status': 'high',
            'label': 'Wzorcowa (1 ocena)',
            'desc': (
                "Wskaźnik stabilności formy (100% – wzorcowa):\n"
                "Mierzy systematyczność i powtarzalność wyników ucznia na podstawie matematycznego odchylenia standardowego (stdev: 0.00).\n\n"
                "100% oznacza brak wahań ocen. Zarejestrowano dotąd tylko 1 ocenę – stabilność stanowi punkt odniesienia na początek semestru."
            ),
        }

    try:
        stdev = round(statistics.stdev(numeric_vals), 2)
    except statistics.StatisticsError:
        stdev = 0.0

    score = max(0, min(100, int(round((1.0 - (stdev / 2.0)) * 100))))

    if score >= 80:
        status = 'high'
        status_name = 'Wysoka'
        label = f'Wysoka ({score}%)'
        diag_desc = 'Bardzo powtarzalne wyniki. Uczeń uczy się systematycznie i rzadko miewa nieprzewidziane potknięcia.'
    elif score >= 60:
        status = 'moderate'
        status_name = 'Umiarkowana'
        label = f'Umiarkowana ({score}%)'
        diag_desc = 'Dobra, zrównoważona forma z pojedynczymi wahaniami (sporadyczne słabsze lub wybitne oceny).'
    else:
        status = 'low'
        status_name = 'Zmienna'
        label = f'Zmienna ({score}%)'
        diag_desc = 'Znaczny rozrzut ocen (tzw. forma w kratkę). Warto zadbać o równiejsze przygotowanie do wszystkich form sprawdzania wiedzy.'

    desc = (
        f"Wskaźnik stabilności formy ({score}% – {status_name}):\n"
        f"Mierzy systematyczność i przewidywalność wyników ucznia na podstawie matematycznego odchylenia standardowego (stdev: {stdev:.2f}).\n\n"
        f"• Skala 0–100%: Im wyższy wskaźnik, tym równiejsze oceny bez niespodziewanych potknięć.\n"
        f"• Wyniki powyżej 80% oznaczają stabilną formę i stały poziom wiedzy, natomiast poniżej 60% wskazują na duży rozrzut między sukcesami a wpadkami (formę w kratkę).\n\n"
        f"Diagnoza: {diag_desc}"
    )

    return {
        'has_data': True,
        'stdev': stdev,
        'score': score,
        'status': status,
        'label': label,
        'desc': desc,
    }


def _compute_pacing_metrics(
    chronological_grades: list[dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Wylicza tempo zdobywania ocen i szacunek pozostałych prac do końca semestru."""
    ref_now = now or datetime.now()

    dated_grades: list[datetime] = []
    for g in chronological_grades:
        dt = parse_grade_date(g.get('date'), g.get('added_at'))
        if dt:
            dated_grades.append(dt)

    if len(dated_grades) < 2:
        return {
            'has_data': False,
            'days_per_grade': None,
            'label': 'Zbyt mało ocen z datami do określenia tempa',
            'estimated_remaining': None,
            'semester_end_desc': '',
        }

    dated_grades.sort()
    first_dt = dated_grades[0]
    last_dt = dated_grades[-1]
    span_days = max(1, (last_dt - first_dt).days)
    days_per_grade = round(span_days / max(1, len(dated_grades) - 1), 1)
    if days_per_grade < 1.0:
        days_per_grade = 1.0

    cur_year = ref_now.year
    if ref_now.month in (9, 10, 11, 12):
        sem_end = datetime(cur_year + 1, 1, 31)
        sem_name = "I semestru (styczeń)"
    elif ref_now.month == 1:
        sem_end = datetime(cur_year, 1, 31)
        sem_name = "I semestru (styczeń)"
    else:
        sem_end = datetime(cur_year, 6, 25)
        sem_name = "roku szkolnego (czerwiec)"

    days_to_end = max(0, (sem_end - ref_now).days)
    if days_to_end > 0 and days_per_grade > 0:
        est_remaining = max(1, int(round(days_to_end / max(4.0, days_per_grade))))
    else:
        est_remaining = 0

    return {
        'has_data': True,
        'days_per_grade': days_per_grade,
        'label': f"Średnio 1 ocena co {days_per_grade:g} dni",
        'estimated_remaining': est_remaining,
        'days_to_end': days_to_end,
        'semester_end_desc': f"Do końca {sem_name} pozostało ok. {days_to_end} dni",
    }


def get_subject_detailed_analytics(
    grades_history: list[dict[str, Any]],
    subject_name: str,
    excluded_subjects: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Wylicza pełną analitykę, statystyki, średnią kroczącą, cele i ryzyka dla wybranego przedmiotu."""
    norm_excluded = {s.strip().lower() for s in (excluded_subjects or [])}
    target_subj = subject_name.strip()
    target_lower = target_subj.lower()

    # Filtrowanie ocen dla danego przedmiotu
    matching_grades: list[dict[str, Any]] = []
    canonical_name = target_subj
    for g in grades_history:
        g_subj = str(g.get('subject') or '').strip()
        if g_subj.lower() == target_lower:
            matching_grades.append(g)
            if g_subj:
                canonical_name = g_subj

    is_excluded = canonical_name.lower() in norm_excluded

    # Chronologiczne sortowanie ocen (od najstarszej do najnowszej) dla osi czasu
    def grade_sort_key(item: dict[str, Any]):
        dt = parse_grade_date(item.get('date'), item.get('added_at'))
        if dt:
            return dt
        parsed = parse_datetime_safe(item.get('added_at')) or parse_date_safe(item.get('date'))
        if parsed:
            return datetime.combine(parsed, datetime.min.time()) if isinstance(parsed, date) and not isinstance(parsed, datetime) else parsed
        return datetime.min

    chronological_grades = sorted(matching_grades, key=grade_sort_key)

    # Obliczanie średniej kroczącej (running average)
    timeline_data: list[dict[str, Any]] = []
    running_sum_weighted = 0.0
    running_sum_weights = 0.0
    numeric_vals: list[float] = []

    for idx, g in enumerate(chronological_grades, start=1):
        num_val = parse_numeric_grade(g.get('grade'))
        raw_weight = parse_weight(g.get('weight'))
        eff_weight = raw_weight if (raw_weight is not None and raw_weight > 0) else (1.0 if num_val is not None else 0.0)

        running_avg = None
        if num_val is not None:
            numeric_vals.append(num_val)
            running_sum_weighted += num_val * eff_weight
            running_sum_weights += eff_weight
            if running_sum_weights > 0:
                running_avg = round(running_sum_weighted / running_sum_weights, 2)

        dt = parse_grade_date(g.get('date'), g.get('added_at'))
        clean_date = dt.strftime("%Y-%m-%d") if dt else str(g.get('date') or g.get('added_at') or '')

        timeline_data.append({
            'index': idx,
            'id': str(g.get('id', idx)),
            'subject': canonical_name,
            'date': clean_date,
            'date_raw': str(g.get('date', '')),
            'grade': str(g.get('grade', '')),
            'numeric_grade': num_val,
            'weight': eff_weight,
            'weight_raw': str(g.get('weight', '')),
            'category': str(g.get('category') or 'Brak kategorii'),
            'teacher': str(g.get('teacher') or '—'),
            'comment': str(g.get('comment') or '—'),
            'running_average': running_avg,
            'is_custom': bool(g.get('is_custom')),
            'original_grade': str(g.get('original_grade') or ''),
            'original_weight': str(g.get('original_weight') or ''),
        })

    # Podsumowanie statystyk
    numeric_count = len(numeric_vals)
    total_count = len(matching_grades)
    final_avg = round(running_sum_weighted / running_sum_weights, 2) if running_sum_weights > 0 else None
    arithmetic_avg = round(sum(numeric_vals) / numeric_count, 2) if numeric_count > 0 else None
    min_grade = min(numeric_vals) if numeric_vals else None
    max_grade = max(numeric_vals) if numeric_vals else None
    median_grade = round(statistics.median(numeric_vals), 2) if numeric_vals else None

    # Dominanta
    mode_grade = None
    if numeric_vals:
        try:
            mode_grade = statistics.mode(numeric_vals)
        except statistics.StatisticsError:
            mode_grade = round(numeric_vals[-1], 2)

    # Proponowana ocena
    prop_num, prop_label = get_predicted_grade_tuple(final_avg) if final_avg is not None else (None, "Brak ocen")
    prop_word = GRADE_WORDS.get(prop_num, "—") if prop_num else "—"

    # Histogram rozkładu ocen
    histogram_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    for nv in numeric_vals:
        round_int = max(1, min(6, round(nv)))
        histogram_counts[round_int] += 1

    histogram_data = [
        {
            'grade': g_int,
            'count': histogram_counts[g_int],
            'percentage': round((histogram_counts[g_int] / numeric_count) * 100, 1) if numeric_count > 0 else 0,
        }
        for g_int in range(1, 7)
    ]

    # Analiza trendu (ostatnie oceny vs wcześniejsze)
    trend = "stable"
    trend_icon = "➡"
    trend_desc = "Średnia ustabilizowana"
    num_timeline = [p for p in timeline_data if p['numeric_grade'] is not None]
    if len(num_timeline) >= 4:
        recent_avg = sum(p['numeric_grade'] for p in num_timeline[-2:]) / 2
        prior_avg = sum(p['numeric_grade'] for p in num_timeline[:-2]) / len(num_timeline[:-2])
        if recent_avg - prior_avg >= 0.35:
            trend = "improving"
            trend_icon = "↗"
            trend_desc = "Wyraźny trend wzrostowy w ostatnich ocenach"
        elif prior_avg - recent_avg >= 0.35:
            trend = "declining"
            trend_icon = "↘"
            trend_desc = "Ostatnie oceny poniżej dotychczasowej średniej"

    target_analysis = _compute_target_analysis(final_avg, running_sum_weighted, running_sum_weights, prop_num)
    risk_analysis = _compute_risk_analysis(final_avg, running_sum_weighted, running_sum_weights, prop_num)
    category_analytics = _compute_category_analytics(matching_grades, running_sum_weights)
    impact_analysis = _compute_impact_analysis(timeline_data, final_avg, running_sum_weighted, running_sum_weights)
    consistency_metrics = _compute_consistency_metrics(numeric_vals)
    pacing_metrics = _compute_pacing_metrics(chronological_grades)

    # Tabela ocen posortowana malejąco (najnowsze wpisy u góry)
    table_grades = sorted(timeline_data, key=lambda x: x['index'], reverse=True)

    return {
        'subject': canonical_name,
        'is_excluded': is_excluded,
        'total_count': total_count,
        'numeric_count': numeric_count,
        'sum_weights': round(running_sum_weights, 2),
        'average': final_avg,
        'arithmetic_average': arithmetic_avg,
        'min_grade': min_grade,
        'max_grade': max_grade,
        'median_grade': median_grade,
        'mode_grade': mode_grade,
        'predicted_grade_num': prop_num,
        'predicted_grade_label': prop_label,
        'predicted_grade_word': prop_word,
        'trend': trend,
        'trend_icon': trend_icon,
        'trend_desc': trend_desc,
        'timeline_data': timeline_data,
        'table_grades': table_grades,
        'histogram_data': histogram_data,
        'target_analysis': target_analysis,
        'risk_analysis': risk_analysis,
        'category_analytics': category_analytics,
        'impact_analysis': impact_analysis,
        'consistency_metrics': consistency_metrics,
        'pacing_metrics': pacing_metrics,
    }


def calculate_certificate_summary(
    subject_averages: dict[str, dict[str, Any]],
    excluded_subjects: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Wylicza zestawienie przedmiotów na świadectwo wraz ze średnią z proponowanych ocen końcowych."""
    norm_excluded = {s.strip().lower() for s in (excluded_subjects or [])}
    subjects_list = []
    rated_grades: list[int] = []
    unrated_count = 0

    for subj, sdata in subject_averages.items():
        is_excluded = bool(sdata.get('is_excluded')) or (subj.strip().lower() in norm_excluded)
        avg = sdata.get('average')
        num_count = sdata.get('numeric_count', 0)

        if avg is not None and num_count > 0:
            prop_num, prop_label = get_predicted_grade_tuple(avg)
            prop_word = GRADE_WORDS.get(prop_num, "—")
            if not is_excluded:
                rated_grades.append(prop_num)
        else:
            prop_num = None
            prop_label = "Brak ocen"
            prop_word = "brak ocen"
            if not is_excluded:
                unrated_count += 1

        subjects_list.append({
            'subject': subj,
            'count': sdata.get('count', 0),
            'numeric_count': num_count,
            'average': avg,
            'proposed_grade_num': prop_num,
            'proposed_grade_word': prop_word,
            'proposed_grade_label': prop_label,
            'is_excluded': is_excluded,
        })

    certificate_avg = round(sum(rated_grades) / len(rated_grades), 2) if rated_grades else None
    has_red_stripe = certificate_avg is not None and certificate_avg >= 4.75
    red_stripe_diff = round(4.75 - certificate_avg, 2) if (certificate_avg is not None and certificate_avg < 4.75) else 0.0

    return {
        'subjects': subjects_list,
        'rated_count': len(rated_grades),
        'unrated_count': unrated_count,
        'total_count': len(subjects_list),
        'certificate_average': certificate_avg,
        'has_red_stripe': has_red_stripe,
        'red_stripe_diff': red_stripe_diff,
    }


def simulate_new_grade(
    grades_history: list[dict[str, Any]],
    subject: str,
    new_grade: float,
    new_weight: float = 1.0,
) -> dict[str, Any]:
    # Guard i normalizacja parametrów symulacji
    eff_grade = max(1.0, min(6.0, float(new_grade)))
    eff_new_weight = max(0.1, min(100.0, float(new_weight)))

    clean_subj = subject.strip()
    subject_grades = [g for g in grades_history if g.get('subject', '').strip().lower() == clean_subj.lower()]

    sum_weighted = 0.0
    sum_weights = 0.0

    for g in subject_grades:
        n_grade = parse_numeric_grade(g.get('grade'))
        w = parse_weight(g.get('weight'))
        if n_grade is not None:
            effective_weight = w if w is not None and w > 0 else 1.0
            sum_weighted += n_grade * effective_weight
            sum_weights += effective_weight

    old_avg = round(sum_weighted / sum_weights, 2) if sum_weights > 0 else None

    # Dodanie nowej oceny
    new_sum_weighted = sum_weighted + (eff_grade * eff_new_weight)
    new_sum_weights = sum_weights + eff_new_weight
    new_avg = round(new_sum_weighted / new_sum_weights, 2)

    diff = round(new_avg - old_avg, 2) if old_avg is not None else 0.0

    return {
        'subject': clean_subj,
        'old_avg': old_avg,
        'new_avg': new_avg,
        'diff': diff,
        'new_grade': eff_grade,
        'new_weight': eff_new_weight,
    }


def build_schedule_day_context(
    all_lessons: list[dict[str, Any]],
    timetable_entries: list[dict[str, Any]] | None = None,
    ref_now: datetime | None = None,
    requested_date: str | None = None,
) -> dict[str, Any]:
    """Przygotowuje spójny kontekst wyboru i nawigacji dnia dla planu lekcji (pulpit oraz /plan):

    - Koreluje sprawdziany/kartkówki z lekcjami.
    - Określa, czy lekcje w bieżącym dniu trwają (na podstawie godziny zakończenia ostatniej aktywnej lekcji).
    - Domyślnie wybiera dzień bieżący (gdy trwają lekcje) lub najbliższy przyszły dzień nauki (gdy lekcje minęły / dzień wolny).
    - Wyznacza poprzedni i kolejny dzień w sekwencji dla przycisków nawigacji.
    """
    now = ref_now or datetime.now()
    tests_by_date: dict[str, list] = {}
    for t in timetable_entries or []:
        t_d = t.get('date')
        if t_d and t.get('type') == 'test':
            tests_by_date.setdefault(t_d, []).append(t)

    by_date: dict[str, list] = {}
    for entry in all_lessons or []:
        d = entry.get('date')
        if d:
            clean_d = d.split()[0] if ' ' in d else d
            if clean_d not in by_date:
                by_date[clean_d] = []
            e_copy = dict(entry)
            if not e_copy.get('test') and clean_d in tests_by_date:
                e_sub = str(e_copy.get('subject', '')).strip().lower()
                for test_item in tests_by_date[clean_d]:
                    test_sub = str(test_item.get('subject', '')).strip().lower()
                    if test_sub and (test_sub in e_sub or e_sub in test_sub):
                        e_copy['test'] = test_item
                        break
            by_date[clean_d].append(e_copy)

    for d, l_list in by_date.items():
        l_list.sort(key=lambda x: (int(x.get('lesson_no', 0)) if str(x.get('lesson_no', '')).isdigit() else 99, x.get('time_from', '')))

    today_str = now.strftime('%Y-%m-%d')
    current_time_str = now.strftime('%H:%M')

    today_lessons = by_date.get(today_str, [])
    active_today_lessons = [les for les in today_lessons if not les.get('is_cancelled')]
    lessons_ongoing = False
    if today_lessons:
        last_lesson = max(active_today_lessons or today_lessons, key=lambda x: x.get('time_to', ''))
        last_time_to = last_lesson.get('time_to', '')
        if last_time_to:
            lessons_ongoing = (current_time_str <= last_time_to)
        else:
            lessons_ongoing = (now.hour < 15)

    sorted_dates = sorted(by_date.keys())
    future_dates = [d for d in sorted_dates if d > today_str]

    if lessons_ongoing and today_str in by_date:
        default_target_date = today_str
        target_reason = 'today_ongoing'
    elif future_dates:
        default_target_date = future_dates[0]
        target_reason = 'next_school_day'
    elif today_str in by_date:
        default_target_date = today_str
        target_reason = 'today_finished'
    elif sorted_dates:
        default_target_date = sorted_dates[-1]
        target_reason = 'latest_available'
    else:
        default_target_date = today_str
        target_reason = 'empty'

    req_clean = (requested_date or '').strip()
    selected_date = req_clean if req_clean in by_date else default_target_date

    prev_date = None
    next_date = None
    if selected_date in sorted_dates:
        idx = sorted_dates.index(selected_date)
        if idx > 0:
            prev_date = sorted_dates[idx - 1]
        if idx < len(sorted_dates) - 1:
            next_date = sorted_dates[idx + 1]

    weekdays_pl = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
    weekdays_short_pl = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Ndz"]
    days_data = []
    selected_day_data = None

    tomorrow_str = (now.date() + timedelta(days=1)).strftime('%Y-%m-%d')

    for d_str in sorted_dates:
        d_obj = parse_date_safe(d_str)
        if d_obj:
            w_name = weekdays_pl[d_obj.weekday()]
            w_short = weekdays_short_pl[d_obj.weekday()]
            f_date = d_obj.strftime("%d.%m")
        else:
            w_name = ""
            w_short = ""
            f_date = d_str

        day_lessons = by_date[d_str]
        active_day_lessons = [les for les in day_lessons if not les.get('is_cancelled')]
        cancelled_count = sum(1 for x in day_lessons if x.get('is_cancelled'))
        substitution_count = sum(1 for x in day_lessons if x.get('is_substitution'))
        tests_count = sum(1 for x in day_lessons if x.get('test'))

        start_time = active_day_lessons[0].get('time_from') if active_day_lessons else (day_lessons[0].get('time_from') if day_lessons else '')
        end_time = active_day_lessons[-1].get('time_to') if active_day_lessons else (day_lessons[-1].get('time_to') if day_lessons else '')
        time_span = f"{start_time} – {end_time}" if start_time and end_time else ""

        if d_str == today_str:
            label = f"Dzisiaj ({w_name.lower()}, {f_date})"
        elif d_str == tomorrow_str:
            label = f"Jutro ({w_name.lower()}, {f_date})"
        else:
            label = f"Plan lekcji ({w_name.lower()}, {f_date})"

        day_dict = {
            'date': d_str,
            'label': label,
            'weekday_name': w_name,
            'weekday_short': w_short,
            'formatted_date': f_date,
            'is_today': (d_str == today_str),
            'is_selected': (d_str == selected_date),
            'is_past': (d_str < today_str),
            'is_future': (d_str > today_str),
            'lessons': day_lessons,
            'total_count': len(day_lessons),
            'active_count': len(active_day_lessons),
            'cancelled_count': cancelled_count,
            'substitution_count': substitution_count,
            'tests_count': tests_count,
            'time_span': time_span,
            'has_any': len(day_lessons) > 0,
        }
        days_data.append(day_dict)
        if d_str == selected_date:
            selected_day_data = day_dict

    empty_summary = {
        'has_any': False,
        'lessons': [],
        'label': 'Brak lekcji w planie',
        'total_count': 0,
        'active_count': 0,
        'cancelled_count': 0,
        'substitution_count': 0,
        'tests_count': 0,
        'time_span': '',
        'date': today_str,
        'is_today': True,
        'is_past': False,
        'is_future': False,
    }

    return {
        'by_date': by_date,
        'sorted_dates': sorted_dates,
        'today_str': today_str,
        'today_date': today_str,
        'lessons_ongoing': lessons_ongoing,
        'default_target_date': default_target_date,
        'target_reason': target_reason,
        'selected_date': selected_date,
        'prev_date': prev_date,
        'next_date': next_date,
        'selected_day': selected_day_data,
        'selected_summary': selected_day_data or empty_summary,
        'days_data': days_data,
    }


def _get_grade_badge_color(grade_val: str | None) -> str:
    """Zwraca klasy stylów Tailwind CSS dla odznaki oceny na podstawie jej wartości."""
    g = str(grade_val or '').strip()
    if g in {'5', '6', '5+', '6-', '5-', '6+'}:
        return 'bg-emerald-100 text-emerald-800 border border-emerald-200'
    if g in {'4', '4+', '4-'}:
        return 'bg-sky-100 text-sky-800 border border-sky-200'
    if g in {'3', '3+', '3-'}:
        return 'bg-amber-100 text-amber-800 border border-amber-200'
    if g in {'1', '2', '1+', '2+', '1-', '2-'}:
        return 'bg-rose-100 text-rose-800 border border-rose-200'
    return 'bg-slate-100 text-slate-700 border border-slate-200'


def build_recent_days_timeline(
    grades: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    notifications: list[dict[str, Any]],
    timetable: list[dict[str, Any]],
    now: datetime | None = None,
    days_count: int = 5,
    hide_weekends: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """
    Buduje chronologiczne kalendarium ostatnich N dni (domyślnie 5) z zebranymi zdarzeniami:
    ocenami, wiadomościami, ogłoszeniami szkolnymi oraz zapowiedzianymi sprawdzianami.
    Opcjonalnie ukrywa weekendy (sobota i niedziela), prezentując tylko dni szkolne.
    """
    ref_now = now or datetime.now()
    ref_date = ref_now.date()
    days_count = max(1, min(30, days_count))

    if hide_weekends:
        target_dates = []
        cur_date = ref_date
        while len(target_dates) < days_count:
            if cur_date.weekday() < 5:  # 0=Pn .. 4=Pt
                target_dates.append(cur_date)
            cur_date -= timedelta(days=1)
        target_dates.reverse()
    else:
        target_dates = [ref_date - timedelta(days=offset) for offset in range(days_count - 1, -1, -1)]

    date_to_day: dict[str, dict[str, Any]] = {}
    weekdays_pl = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
    weekdays_short_pl = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Ndz"]

    for d in target_dates:
        d_str = d.strftime('%Y-%m-%d')
        date_to_day[d_str] = {
            'date': d_str,
            'date_obj': d,
            'formatted_date': d.strftime('%d.%m'),
            'weekday_name': weekdays_pl[d.weekday()],
            'weekday_short': weekdays_short_pl[d.weekday()],
            'is_today': (d == ref_date),
            'is_weekend': (d.weekday() >= 5),
            'events': [],
            'grades_count': 0,
            'messages_count': 0,
            'notifications_count': 0,
            'tests_count': 0,
        }

    # 1. Oceny
    for g in grades:
        raw_date = g.get('date') or g.get('added_at')
        dt = parse_datetime_safe(raw_date)
        if dt:
            d_str = dt.strftime('%Y-%m-%d')
            if d_str in date_to_day:
                grade_val = str(g.get('grade') or '').strip()
                date_to_day[d_str]['events'].append({
                    'type': 'grade',
                    'icon': '📝',
                    'badge': grade_val,
                    'badge_color': _get_grade_badge_color(grade_val),
                    'title': g.get('subject') or 'Ocena',
                    'category': g.get('category') if g.get('category') != '-' else '',
                    'weight': g.get('weight') or '1',
                    'comment': g.get('comment') if g.get('comment') != '-' else '',
                    'teacher': g.get('teacher', ''),
                    'datetime': dt,
                    'time_str': dt.strftime('%H:%M') if dt.hour != 0 or dt.minute != 0 else '',
                    'raw': g,
                })
                date_to_day[d_str]['grades_count'] += 1

    # 2. Wiadomości
    for m in messages:
        raw_date = m.get('datetime') or m.get('date') or m.get('added_at')
        dt = parse_datetime_safe(raw_date)
        if dt:
            d_str = dt.strftime('%Y-%m-%d')
            if d_str in date_to_day:
                body = (m.get('body') or '').strip()
                snippet = (body[:120] + '...') if len(body) > 120 else body
                date_to_day[d_str]['events'].append({
                    'type': 'message',
                    'icon': '✉️',
                    'badge': 'Wiadomość',
                    'title': m.get('title') or 'Wiadomość',
                    'sender': m.get('sender', ''),
                    'snippet': snippet,
                    'datetime': dt,
                    'time_str': dt.strftime('%H:%M') if dt.hour != 0 or dt.minute != 0 else '',
                    'raw': m,
                })
                date_to_day[d_str]['messages_count'] += 1

    # 3. Ogłoszenia
    for n in notifications:
        raw_date = n.get('datetime') or n.get('date') or n.get('added_at')
        dt = parse_datetime_safe(raw_date)
        if dt:
            d_str = dt.strftime('%Y-%m-%d')
            if d_str in date_to_day:
                body = (n.get('body') or '').strip()
                snippet = (body[:120] + '...') if len(body) > 120 else body
                date_to_day[d_str]['events'].append({
                    'type': 'notification',
                    'icon': '📢',
                    'badge': 'Ogłoszenie',
                    'title': n.get('title') or 'Ogłoszenie',
                    'sender': n.get('sender', ''),
                    'snippet': snippet,
                    'datetime': dt,
                    'time_str': dt.strftime('%H:%M') if dt.hour != 0 or dt.minute != 0 else '',
                    'raw': n,
                })
                date_to_day[d_str]['notifications_count'] += 1

    # 4. Sprawdziany (odbywające się w danym dniu oraz zapowiedziane na przyszłość)
    seen_test_events: set[tuple[str, str, str, str]] = set()

    for t in timetable:
        # A. Sprawdzian odbywający się w danym dniu
        raw_test_date = t.get('date')
        test_dt = parse_datetime_safe(raw_test_date)
        if test_dt:
            t_str = test_dt.strftime('%Y-%m-%d')
            if t_str in date_to_day:
                cat = t.get('category') or 'Sprawdzian'
                subj = t.get('subject') or 'Przedmiot'
                desc = (t.get('description') or '').strip()
                dedup_key = ('test', subj, cat, t_str)
                if dedup_key not in seen_test_events:
                    seen_test_events.add(dedup_key)
                    date_to_day[t_str]['events'].append({
                        'type': 'test',
                        'icon': '🔔',
                        'badge': cat,
                        'title': f'{cat}: {subj}',
                        'subject': subj,
                        'description': desc,
                        'lesson_no': t.get('lesson_no', ''),
                        'teacher': t.get('teacher', ''),
                        'datetime': test_dt,
                        'time_str': f'Lekcja {t.get("lesson_no")}' if t.get('lesson_no') else '',
                        'is_announced_future': False,
                        'raw': t,
                    })
                    date_to_day[t_str]['tests_count'] += 1

        # B. Sprawdzian zapowiedziany w danym dniu na przyszłość
        raw_add_date = t.get('add_date')
        add_dt = parse_datetime_safe(raw_add_date)
        if add_dt and test_dt and test_dt.date() > add_dt.date():
            add_str = add_dt.strftime('%Y-%m-%d')
            if add_str in date_to_day:
                cat = t.get('category') or 'Sprawdzian'
                subj = t.get('subject') or 'Przedmiot'
                desc = (t.get('description') or '').strip()
                target_date_str = test_dt.strftime('%d.%m')
                dedup_key = ('test_announced', subj, cat, f'{add_str}->{target_date_str}')
                if dedup_key not in seen_test_events:
                    seen_test_events.add(dedup_key)
                    date_to_day[add_str]['events'].append({
                        'type': 'test_announced',
                        'icon': '🗓️',
                        'badge': f'Na {target_date_str}',
                        'title': f'Zapowiedziano: {cat} ({subj})',
                        'subject': subj,
                        'description': desc,
                        'target_date': target_date_str,
                        'teacher': t.get('teacher', ''),
                        'datetime': add_dt,
                        'time_str': add_dt.strftime('%H:%M') if add_dt.hour != 0 or add_dt.minute != 0 else '',
                        'is_announced_future': True,
                        'raw': t,
                    })
                    date_to_day[add_str]['tests_count'] += 1

    # Sortowanie zdarzeń wewnątrz każdego dnia i kalkulacja sum
    timeline_days = []
    total_events = 0
    type_priority = {'test': 1, 'test_announced': 2, 'grade': 3, 'message': 4, 'notification': 5}

    for d in target_dates:
        d_str = d.strftime('%Y-%m-%d')
        day_data = date_to_day[d_str]
        day_data['events'].sort(key=lambda ev: (type_priority.get(ev['type'], 99), str(ev.get('datetime') or '')))
        day_data['events_count'] = len(day_data['events'])
        day_data['has_events'] = bool(day_data['events'])
        total_events += day_data['events_count']
        timeline_days.append(day_data)

    return timeline_days, total_events


def get_student_dashboard_bundle(
    storage: BaseStorage,
    login: str,
    config: dict,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Przygotowuje komplet danych dla wybranego ucznia do wyświetlenia na dashboardzie."""
    ref_now = now or datetime.now()

    student_name = resolve_student_name(config, storage, login)
    grades = storage.get_grades_history(login) if hasattr(storage, 'get_grades_history') else []
    timetable = storage.get_timetable_history(login) if hasattr(storage, 'get_timetable_history') else []
    schedule = storage.get_schedule_history(login) if hasattr(storage, 'get_schedule_history') else []
    raw_messages = storage.get_stored_messages(login) if hasattr(storage, 'get_stored_messages') else []
    raw_notifications = storage.get_stored_notifications(login) if hasattr(storage, 'get_stored_notifications') else []
    messages = sort_items_descending(raw_messages)
    notifications = sort_items_descending(raw_notifications)
    last_sync = storage.get_last_collect_time(login) if hasattr(storage, 'get_last_collect_time') else None
    last_sync_human = format_human_timestamp(last_sync, now=ref_now)

    # Analityka ocen
    excluded_subjects = storage.get_excluded_certificate_subjects(login) if hasattr(storage, 'get_excluded_certificate_subjects') else []
    all_subjects = storage.get_subjects(login) if hasattr(storage, 'get_subjects') else []
    subj_averages = calculate_subject_averages(grades, excluded_subjects=excluded_subjects, all_subjects=all_subjects)
    overall_avg = calculate_overall_average(subj_averages)
    certificate_summary = calculate_certificate_summary(subj_averages, excluded_subjects=excluded_subjects)

    # Najnowsze oceny (ostatnie 8 wystawionych)
    recent_grades = sort_grades_descending(grades)[:8]

    # Terminarz i plan lekcji
    timetable_summary = prepare_timetable_summary(timetable, reference_date=ref_now.date())
    sched_ctx = build_schedule_day_context(schedule, timetable_entries=timetable, ref_now=ref_now)
    schedule_summary = sched_ctx['selected_summary']
    today_schedule_summary = prepare_schedule_summary(schedule, timetable_entries=timetable, now=ref_now, day_offset=0)

    # Kalendarium ostatnich dni (konfiguracja: włączenie, liczba dni, ukrywanie weekendów)
    web_cfg = config.get('web', {}) if isinstance(config.get('web'), (dict, Mapping)) else {}
    timeline_enabled = bool(web_cfg.get('timeline_enabled', config.get('timeline_enabled', True)))
    try:
        timeline_days_count = int(web_cfg.get('timeline_days', config.get('timeline_days', 5)))
    except (ValueError, TypeError):
        timeline_days_count = 5
    timeline_days_count = max(1, min(14, timeline_days_count))
    timeline_hide_weekends = bool(web_cfg.get('timeline_hide_weekends', config.get('timeline_hide_weekends', False)))

    if timeline_enabled:
        recent_timeline_days, recent_timeline_total_events = build_recent_days_timeline(
            grades=grades,
            messages=raw_messages,
            notifications=raw_notifications,
            timetable=timetable,
            now=ref_now,
            days_count=timeline_days_count,
            hide_weekends=timeline_hide_weekends,
        )
    else:
        recent_timeline_days = []
        recent_timeline_total_events = 0

    # Liczba nadchodzących sprawdzianów w horyzoncie
    upcoming_tests_count = len(timetable_summary.get('immediate_tests', [])) + sum(
        len(d.get('tests', [])) for d in timetable_summary.get('upcoming_days', [])
    )

    return {
        'login': login,
        'name': student_name,
        'grades_count': len(grades),
        'subject_averages': subj_averages,
        'overall_average': overall_avg,
        'certificate_summary': certificate_summary,
        'excluded_subjects': excluded_subjects,
        'recent_grades': recent_grades,
        'recent_timeline_enabled': timeline_enabled,
        'recent_timeline_days_count': timeline_days_count,
        'recent_timeline_hide_weekends': timeline_hide_weekends,
        'recent_timeline_days': recent_timeline_days,
        'recent_timeline_total_events': recent_timeline_total_events,
        'timetable_summary': timetable_summary,
        'schedule_summary': schedule_summary,
        'today_schedule_summary': today_schedule_summary,
        'upcoming_tests_count': upcoming_tests_count,
        'messages': messages,
        'notifications': notifications,
        'messages_count': len(messages),
        'notifications_count': len(notifications),
        'last_sync': last_sync,
        'last_sync_human': last_sync_human,
        'all_schedule': schedule,
        'all_timetable': timetable,
    }


def capture_action_execution(func, *args, **kwargs) -> tuple[bool, str, Any]:
    """Wspólny wrapper przechwytujący logi i status wykonania akcji CLI."""
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    success = False
    result = None
    output = ""

    try:
        result = func(*args, **kwargs)
        success = True
    except Exception as e:
        logger.error(f"Błąd podczas wykonywania akcji: {e}", exc_info=True)
        log_capture.write(f"\n❌ Błąd: {type(e).__name__}: {str(e)}\n")
        success = False
    finally:
        root_logger.removeHandler(handler)
        output = log_capture.getvalue()

    return success, output, result


def build_progress_report_html(
    storage: BaseStorage,
    login: str,
    config: dict,
    days: int | None = None,
    now: datetime | None = None,
) -> str:
    """Generuje gotowy HTML raportu postępów dla wybranego ucznia."""
    grades = storage.get_grades_history(login) if hasattr(storage, 'get_grades_history') else []
    if not grades:
        return (
            '<div class="py-16 text-center bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">'
            '<div class="text-4xl mb-3">📝</div>'
            '<h3 class="text-lg font-bold text-slate-800 mb-1">Brak zapisanych ocen w pamięci podręcznej</h3>'
            '<p class="text-sm text-slate-500 max-w-md mx-auto mb-6">'
            'Nie odnaleziono jeszcze historii ocen dla tego ucznia w lokalnej bazie. '
            'Uruchom synchronizację z Librusem, aby pobrać najnowsze oceny.'
            '</p>'
            '<a href="/akcje" class="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-xs font-bold rounded-xl hover:bg-indigo-700 transition shadow-sm">'
            '⚡ Przejdź do synchronizacji'
            '</a>'
            '</div>'
        )

    ref_now = now or datetime.now()
    if days is not None:
        period_start = ref_now - timedelta(days=days)
    else:
        last_report_iso = storage.get_last_progress_report_date(login) if hasattr(storage, 'get_last_progress_report_date') else None
        period_start = parse_datetime_safe(last_report_iso) if last_report_iso else None
        if period_start is None:
            days_back = config.get('progress_report', {}).get('days_back', 7)
            period_start = ref_now - timedelta(days=days_back)

    excluded_subjects = storage.get_excluded_certificate_subjects(login) if hasattr(storage, 'get_excluded_certificate_subjects') else []
    analysis = ProgressAnalyzer.analyze(
        grades=grades,
        period_start=period_start,
        period_end=ref_now,
        excluded_subjects=excluded_subjects,
    )

    timetable_summary = None
    if hasattr(storage, 'get_timetable_history'):
        raw_timetable = storage.get_timetable_history(login)
        timetable_summary = prepare_timetable_summary(raw_timetable, reference_date=ref_now.date())

    user_cfg = next((u for u in config.get('librus_users', []) if str(u.get('librus_login', '')) == str(login)), None)
    if user_cfg:
        user_cfg = dict(user_cfg)
    else:
        user_cfg = {'librus_login': str(login)}
    user_cfg['librus_login_name'] = resolve_student_name(config, storage, login)

    return MailSender.create_mail_content_for_progress_report(
        user_config=user_cfg,
        analysis=analysis,
        timetable=timetable_summary,
    )


def build_student_report_html(
    storage: BaseStorage,
    login: str,
    config: dict,
    variant: str = 'teens',
    days: int | None = None,
    now: datetime | None = None,
) -> str:
    """Generuje motywacyjny raport ucznia w wybranym stylu (kids, teens, youth)."""
    grades = storage.get_grades_history(login) if hasattr(storage, 'get_grades_history') else []
    if not grades:
        return (
            '<div class="py-16 text-center bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">'
            '<div class="text-4xl mb-3">🌟</div>'
            '<h3 class="text-lg font-bold text-slate-800 mb-1">Brak zapisanych ocen w pamięci podręcznej</h3>'
            '<p class="text-sm text-slate-500 max-w-md mx-auto mb-6">'
            'Nie odnaleziono jeszcze historii ocen dla tego ucznia w lokalnej bazie. '
            'Uruchom synchronizację z Librusem, aby wygenerować kartę motywacyjną ucznia.'
            '</p>'
            '<a href="/akcje" class="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-xs font-bold rounded-xl hover:bg-indigo-700 transition shadow-sm">'
            '⚡ Przejdź do synchronizacji'
            '</a>'
            '</div>'
        )

    clean_variant = variant if variant in ('kids', 'teens', 'youth') else 'teens'
    ref_now = now or datetime.now()
    student_name = resolve_student_name(config, storage, login)
    effective_days = days if days is not None else 7

    analyzer = StudentAnalyzer(
        grades=grades,
        student_name=student_name,
        actual_date=ref_now.strftime('%Y-%m-%d'),
        days=effective_days,
    )
    metrics = analyzer.calculate_metrics()

    timetable_summary = None
    if hasattr(storage, 'get_timetable_history'):
        raw_timetable = storage.get_timetable_history(login)
        timetable_summary = prepare_timetable_summary(raw_timetable, reference_date=ref_now.date())

    return MailSender.create_mail_content_for_student_report(
        metrics=metrics,
        template_type=clean_variant,
        timetable=timetable_summary,
    )


def build_daily_summary_html(
    storage: BaseStorage,
    login: str,
    config: dict,
    target_date: date | str | None = None,
    now: datetime | None = None,
) -> str:
    grades = storage.get_grades_history(login) if hasattr(storage, 'get_grades_history') else []
    raw_messages = storage.get_stored_messages(login) if hasattr(storage, 'get_stored_messages') else []
    raw_notifications = storage.get_stored_notifications(login) if hasattr(storage, 'get_stored_notifications') else []
    messages = sort_items_descending(raw_messages)
    notifications = sort_items_descending(raw_notifications)
    timetable = storage.get_timetable_history(login) if hasattr(storage, 'get_timetable_history') else []
    schedule = storage.get_schedule_history(login) if hasattr(storage, 'get_schedule_history') else []

    if isinstance(target_date, str):
        sel_date = parse_date_safe(target_date) or (now.date() if now else datetime.now().date())
    elif isinstance(target_date, date):
        sel_date = target_date
    elif now:
        sel_date = now.date()
    else:
        sel_date = datetime.now().date()

    ref_now = datetime.combine(sel_date, datetime.min.time().replace(hour=18, minute=0))

    timetable_summary = prepare_timetable_summary(timetable, reference_date=sel_date)
    day_offset = int(config.get('schedule_day_offset', 1))
    schedule_summary = prepare_schedule_summary(schedule, timetable_entries=timetable, now=ref_now, day_offset=day_offset)

    user_cfg = next((u for u in config.get('librus_users', []) if str(u.get('librus_login', '')) == str(login)), None)
    if user_cfg:
        user_cfg = dict(user_cfg)
    else:
        user_cfg = {'librus_login': str(login)}
    user_cfg['librus_login_name'] = resolve_student_name(config, storage, login)

    day_grades = [
        g for g in grades
        if (dt := parse_item_datetime(g)) and dt.date() == sel_date
    ]
    day_messages = [
        m for m in messages
        if (dt := parse_item_datetime(m)) and dt.date() == sel_date
    ]
    day_notifications = [
        n for n in notifications
        if (dt := parse_item_datetime(n)) and dt.date() == sel_date
    ]

    return MailSender.create_mail_content_for_summary(
        user_config=user_cfg,
        messages=day_messages,
        notifications=day_notifications,
        grades=day_grades,
        timetable=timetable_summary,
        schedule=schedule_summary,
    )


def test_librus_credentials(login: str, password: str) -> tuple[bool, str]:
    """Testuje autoryzację do systemu Librus dla podanego loginu i hasła bez pobierania pełnych danych."""
    clean_login = str(login or '').strip()
    clean_password = str(password or '').strip()
    if not clean_login or not clean_password:
        return False, "Login i hasło do konta Librus są wymagane."

    from librus2mail.librus import Librus, NotLogged

    dummy_cfg = {
        'librus_login': clean_login,
        'librus_password': clean_password,
        'read_messages': False,
        'read_grades': False,
        'read_timetable': False,
        'read_schedule': False,
    }

    try:
        client = Librus(dummy_cfg)
        client.login()
        if client.logged:
            return True, f"✅ Logowanie konta {clean_login} powiodło się pomyślnie!"
        return False, "Nie udało się potwierdzić logowania w portalu Librus."
    except NotLogged as e:
        return False, f"Błąd autoryzacji: {e.message}"
    except Exception as e:
        logger.warning(f"Błąd podczas testu logowania Librus dla {clean_login}: {e}")
        return False, f"Błąd połączenia z portalem Librus: {e}"


def save_config_yaml(config_dict: dict[str, Any], target_path: str = 'config.yaml') -> str:
    """Zapisuje słownik konfiguracyjny do pliku YAML z zachowaniem czytelnej struktury."""
    from pathlib import Path

    import yaml

    target = Path(target_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    # Tworzenie kopii zapasowej jeśli plik docelowy już istnieje
    if target.is_file():
        backup_path = target.with_suffix('.yaml.bak')
        try:
            backup_path.write_bytes(target.read_bytes())
            logger.info(f"Utworzono kopię zapasową konfiguracji: {backup_path}")
        except Exception as e:
            logger.warning(f"Nie udało się utworzyć kopii zapasowej {backup_path}: {e}")

    content = yaml.safe_dump(
        config_dict,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )

    # Zapis bezpośredni in-place, aby zachować numer inode pliku
    # (niezbędne w środowisku Docker z montowaniem pojedynczego pliku :ro)
    with open(target, 'w', encoding='utf-8') as f:
        f.write(content)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    logger.info(f"Zapisano nową konfigurację do pliku {target}")
    return str(target)


# ==============================================================================
# ANALITYKA MIĘDZYPRZEDMIOTOWA I OPTYMALIZACJA CELU
# ==============================================================================

EDUCATIONAL_CATEGORIES: dict[str, dict[str, Any]] = {
    "scisle": {
        "key": "scisle",
        "label": "Ścisłe i przyrodnicze",
        "short_label": "Ścisłe",
        "icon": "📐",
        "color": "#4f46e5",  # indigo-600
        "bg_color": "rgba(79, 70, 229, 0.2)",
        "keywords": [
            "matemat", "fizyk", "chem", "biolog", "geograf",
            "informat", "przyrod", "technolog", "algorytm", "programow"
        ],
    },
    "humanistyczne": {
        "key": "humanistyczne",
        "label": "Humanistyczne i społeczne",
        "short_label": "Humanistyczne",
        "icon": "📖",
        "color": "#0ea5e9",  # sky-500
        "bg_color": "rgba(14, 165, 233, 0.2)",
        "keywords": [
            "polsk", "histor", "wos", "społeczeńst", "filozof",
            "etyk", "hit", "wiedza o", "język ojczysty"
        ],
    },
    "jezyki": {
        "key": "jezyki",
        "label": "Języki obce",
        "short_label": "Języki obce",
        "icon": "🌍",
        "color": "#10b981",  # emerald-500
        "bg_color": "rgba(16, 185, 129, 0.2)",
        "keywords": [
            "angielsk", "niemieck", "hiszpańsk", "francusk",
            "rosyjsk", "włosk", "język obcy", "łacina", "english"
        ],
    },
    "ruch_i_sztuka": {
        "key": "ruch_i_sztuka",
        "label": "Sport, kultura i praktyka",
        "short_label": "Sport i Sztuka",
        "icon": "🎨",
        "color": "#f59e0b",  # amber-500
        "bg_color": "rgba(245, 158, 11, 0.2)",
        "keywords": [
            "fizyczn", "wf", "w-f", "plastyk", "muzyk",
            "technik", "edb", "bezpieczeństw", "artystyczn", "sport", "teatr"
        ],
    },
    "inne": {
        "key": "inne",
        "label": "Inne i dodatkowe",
        "short_label": "Inne",
        "icon": "📦",
        "color": "#8b5cf6",  # purple-500
        "bg_color": "rgba(139, 92, 246, 0.2)",
        "keywords": [
            "religi", "etyk", "doradztw", "wychowawcz", "zajęcia z wychowawcą"
        ],
    },
}


def classify_subject(subject_name: str, user_overrides: dict[str, str] | None = None) -> str:
    """Klasyfikuje przedmiot do jednego z filarów edukacyjnych z uwzględnieniem nadpisań użytkownika."""
    target = str(subject_name or '').strip()
    if not target:
        return "inne"

    # 1. Sprawdzenie nadpisań użytkownika (case-insensitive)
    if user_overrides and isinstance(user_overrides, dict):
        for k, v in user_overrides.items():
            if str(k).strip().lower() == target.lower():
                val = str(v).strip().lower()
                if val in EDUCATIONAL_CATEGORIES:
                    return val

    # 2. Normalizacja tekstu
    clean = re.sub(r'\(.*?\)', '', target.lower())
    clean = clean.replace('-', ' ').replace('.', ' ')
    clean = re.sub(r'\s+', ' ', clean).strip()

    # Specjalne traktowanie języków obcych (np. "język angielski" vs "język polski")
    for kw in EDUCATIONAL_CATEGORIES["jezyki"]["keywords"]:
        if kw in clean:
            return "jezyki"

    for kw in EDUCATIONAL_CATEGORIES["scisle"]["keywords"]:
        if kw in clean:
            return "scisle"

    for kw in EDUCATIONAL_CATEGORIES["humanistyczne"]["keywords"]:
        if kw in clean:
            return "humanistyczne"

    for kw in EDUCATIONAL_CATEGORIES["ruch_i_sztuka"]["keywords"]:
        if kw in clean:
            return "ruch_i_sztuka"

    for kw in EDUCATIONAL_CATEGORIES["inne"]["keywords"]:
        if kw in clean:
            return "inne"

    return "inne"


def compute_educational_profile(
    subject_averages: dict[str, dict[str, Any]] | list[dict[str, Any]],
    user_overrides: dict[str, str] | None = None,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Oblicza przekrojowy profil zbalansowania ucznia w 4 głównych filarach edukacyjnych."""
    if overrides is not None and user_overrides is None:
        user_overrides = overrides
    if isinstance(subject_averages, list):
        subject_averages = {
            (item.get('subject') or item.get('name') or f'Item_{idx}'): item
            for idx, item in enumerate(subject_averages)
        }

    categories_data: dict[str, dict[str, Any]] = {
        key: {
            "key": key,
            "label": info["label"],
            "icon": info["icon"],
            "color": info["color"],
            "bg_color": info["bg_color"],
            "subjects": [],
            "averages": [],
            "total_grades": 0,
            "average": None,
        }
        for key, info in EDUCATIONAL_CATEGORIES.items()
    }

    all_classified_subjects = []

    for sname, sdata in subject_averages.items():
        cat_key = classify_subject(sname, user_overrides=user_overrides)
        avg = sdata.get('average')
        cnt = sdata.get('numeric_count')
        if cnt is None:
            cnt = sdata.get('grades_count', sdata.get('count', 0))

        item = {
            "name": sname,
            "subject": sname,
            "average": avg,
            "count": cnt,
            "category": cat_key,
            "category_label": EDUCATIONAL_CATEGORIES[cat_key]["label"],
            "category_icon": EDUCATIONAL_CATEGORIES[cat_key]["icon"],
            "is_excluded": sdata.get('is_excluded', False),
            "is_custom": bool(user_overrides and sname in user_overrides),
        }
        all_classified_subjects.append(item)
        categories_data[cat_key]["subjects"].append(item)
        if avg is not None and not sdata.get('is_excluded', False):
            categories_data[cat_key]["averages"].append(avg)
        categories_data[cat_key]["total_grades"] += cnt

    # Obliczenie średnich dla kategorii
    radar_labels = []
    radar_values = []
    radar_colors = []

    for key, cdata in categories_data.items():
        avgs = cdata["averages"]
        if avgs:
            cdata["average"] = round(sum(avgs) / len(avgs), 2)
        else:
            cdata["average"] = None

        # Do radaru bierzemy 4 główne filary
        if key in ("scisle", "humanistyczne", "jezyki", "ruch_i_sztuka"):
            short_l = EDUCATIONAL_CATEGORIES.get(key, {}).get("short_label", cdata["label"])
            radar_labels.append(f"{cdata['icon']} {short_l}")
            radar_values.append(cdata["average"] or 0.0)
            radar_colors.append(cdata["color"])

    # Wskaźnik dominującego profilu
    active_cats = [c for c in categories_data.values() if c["key"] != "inne" and c["average"] is not None]
    if active_cats:
        top_cat = max(active_cats, key=lambda x: x["average"])
        min_cat = min(active_cats, key=lambda x: x["average"])
        spread = round(top_cat["average"] - min_cat["average"], 2)
        if spread <= 0.40:
            balance_status = "Wszechstronny (zrównoważony profil nauki)"
            balance_badge = "🌟 Wszechstronny"
        else:
            balance_status = f"Wyraźny profil: {top_cat['label']} (śr. {top_cat['average']})"
            balance_badge = f"🚀 Profil {top_cat['icon']}"
    else:
        top_cat = None
        min_cat = None
        spread = 0.0
        balance_status = "Brak wystarczającej liczby ocen"
        balance_badge = "Brak danych"

    return {
        "categories": categories_data,
        "profile_groups": list(categories_data.values()),
        "radar": {
            "labels": radar_labels,
            "values": radar_values,
        },
        "radar_chart": {
            "labels": radar_labels,
            "values": radar_values,
        },
        "all_subjects": all_classified_subjects,
        "available_categories": [
            {"key": k, "label": v["label"], "icon": v["icon"]}
            for k, v in EDUCATIONAL_CATEGORIES.items()
        ],
        "top_category": top_cat,
        "dominant_category": top_cat,
        "min_category": min_cat,
        "growth_category": min_cat,
        "spread": spread,
        "balance_status": balance_status,
        "balance_badge": balance_badge,
    }


def calculate_goal_optimizer(
    subject_averages: dict[str, dict[str, Any]] | list[dict[str, Any]],
    target_avg: float | None = None,
    target_grade: float | None = None,
) -> dict[str, Any]:
    """Wieloprzedmiotowy optymalizator celu: wyznacza najłatwiejszą i najbardziej opłacalną ścieżkę do osiągnięcia docelowej średniej."""
    if target_grade is not None and target_avg is None:
        target_avg = target_grade
    if isinstance(subject_averages, list):
        subject_averages = {
            (item.get('subject') or item.get('name') or f'Item_{idx}'): item
            for idx, item in enumerate(subject_averages)
        }

    included_subjs = {
        s: data for s, data in subject_averages.items()
        if not data.get('is_excluded') and data.get('average') is not None
    }
    if not included_subjs:
        eff_target = target_avg or 4.75
        return {
            "current_average": 0.0,
            "target_average": eff_target,
            "target_grade": eff_target,
            "diff": 0.0,
            "achieved": False,
            "action_plan": [],
            "candidates": [],
            "has_candidates": False,
            "ranked_subjects": [],
        }

    n_subjects = len(included_subjs)
    cur_sum = sum(d['average'] for d in included_subjs.values())
    cur_avg = round(cur_sum / n_subjects, 2)

    if target_avg is None:
        if cur_avg < 4.75:
            target_avg = 4.75
        elif cur_avg < 5.00:
            target_avg = 5.00
        else:
            target_avg = round(min(6.0, cur_avg + 0.25), 2)
    else:
        target_avg = round(float(target_avg), 2)

    diff = round(target_avg - cur_avg, 2)
    if diff <= 0:
        return {
            "current_average": cur_avg,
            "target_average": target_avg,
            "target_grade": target_avg,
            "diff": 0.0,
            "achieved": True,
            "action_plan": [],
            "candidates": [],
            "has_candidates": False,
            "ranked_subjects": [],
        }

    # Analiza wrażliwości i ROI dla każdego przedmiotu
    # Badamy zysk ze zdobycia oceny 5 i 6 o wagach 1, 2, 3
    analyzed_subjects = []
    for sname, sdata in included_subjs.items():
        s_avg = sdata['average']
        s_weights = max(1.0, float(sdata.get('sum_weights') or sdata.get('total_weight') or 1.0))
        s_weighted = float(sdata.get('sum_weighted') or (s_avg * s_weights))

        # Symulacja: nowa ocena 5 o wadze 2
        new_w = 2.0
        new_g = 5.0 if s_avg < 4.8 else 6.0
        sim_subj_avg = (s_weighted + new_g * new_w) / (s_weights + new_w)
        subj_gain = max(0.0, sim_subj_avg - s_avg)
        overall_gain = subj_gain / n_subjects

        # ROI (zysk dla średniej ogólnej przypadający na jednostkę wagi)
        roi = overall_gain / new_w

        # Ile potrzeba ocen 5 (waga 2), aby ten przedmiot sam podniósł średnią o 0.1?
        analyzed_subjects.append({
            "name": sname,
            "subject": sname,
            "current_average": s_avg,
            "sum_weights": s_weights,
            "count": sdata.get('numeric_count', sdata.get('grades_count', sdata.get('count', 0))),
            "sim_grade": new_g,
            "sim_weight": new_w,
            "subj_gain": round(subj_gain, 2),
            "overall_gain": round(overall_gain, 3),
            "roi": roi,
            "recommendation": (
                f"Zdobądź ocenę {int(new_g)} z wagą {int(new_w)} "
                f"(np. ze sprawdzianu), aby podnieść średnią przedmiotu o +{subj_gain:.2f} "
                f"(+{overall_gain:.3f} do średniej ogólnej)."
            ),
        })

    # Sortujemy przedmioty od najwyższego ROI (najłatwiejsze do podniesienia, mała suma wag)
    analyzed_subjects.sort(key=lambda x: x['roi'], reverse=True)

    # Budujemy konkretny "Action Plan" (krok po kroku pokrywający 'diff')
    action_plan = []
    accumulated_gain = 0.0

    for item in analyzed_subjects:
        if accumulated_gain >= diff:
            break
        gain_on_subj = round(item["subj_gain"], 2)
        action_plan.append({
            "step": len(action_plan) + 1,
            "subject": item["name"],
            "current_average": item["current_average"],
            "suggested_grade": item["sim_grade"],
            "suggested_weight": item["sim_weight"],
            "target_proposal": int(item["sim_grade"]),
            "min_grade_needed": int(item["sim_grade"]),
            "gap": gain_on_subj,
            "estimated_gain": item["overall_gain"],
            "text": item["recommendation"],
        })
        accumulated_gain += item["overall_gain"]

    return {
        "current_average": cur_avg,
        "target_average": target_avg,
        "target_grade": target_avg,
        "diff": diff,
        "achieved": False,
        "action_plan": action_plan,
        "candidates": action_plan,
        "has_candidates": bool(action_plan),
        "ranked_subjects": analyzed_subjects,
    }


def compute_opportunity_matrix(
    subject_averages: dict[str, dict[str, Any]] | list[dict[str, Any]],
) -> dict[str, Any]:
    """Kategoryzuje przedmioty pod kątem szans na wyższą ocenę (Quick Wins) oraz ryzyka spadku."""
    if isinstance(subject_averages, list):
        subject_averages = {
            (item.get('subject') or item.get('name') or f'Item_{idx}'): item
            for idx, item in enumerate(subject_averages)
        }

    quick_wins = []
    at_risk = []
    safe = []
    intervention = []

    # Progi ocen w polskim systemie szkolnym
    grade_thresholds = [
        (1.75, 2.0, "dopuszczający (2)"),
        (2.75, 3.0, "dostateczny (3)"),
        (3.75, 4.0, "dobry (4)"),
        (4.75, 5.0, "bardzo dobry (5)"),
        (5.50, 6.0, "celujący (6)"),
    ]

    for sname, sdata in subject_averages.items():
        if sdata.get('is_excluded') or sdata.get('average') is None:
            continue

        avg = sdata['average']
        cnt = sdata.get('numeric_count')
        if cnt is None:
            cnt = sdata.get('grades_count', sdata.get('count', 0))
        total_entries = sdata.get('count', cnt)
        weights = max(0.1, float(sdata.get('sum_weights') or sdata.get('total_weight') or 1.0))
        weighted = float(sdata.get('sum_weighted') or (avg * weights))

        # 1. Sprawdzenie czy wymaga interwencji (bardzo niska średnia)
        if avg < 2.50:
            target_goal = 2.75
            pts_needed = round(max(0.0, (target_goal * weights) - weighted), 2)
            intervention.append({
                "subject": sname,
                "average": avg,
                "count": cnt,
                "total_entries": total_entries,
                "deficit": round(target_goal - avg, 2),
                "points_needed": pts_needed,
                "reason": "Średnia poniżej 2.50 – bezpośrednie ryzyko oceny dopuszczającej lub niedostatecznej.",
                "urgent_action": "Konieczna poprawa najniższych ocen lub zaliczenie prac klasowych, aby osiągnąć bezpieczny poziom 2.75+ (dostateczny).",
            })

        # 2. Sprawdzenie szans na wyższą ocenę (Quick Wins)
        # Szukamy pierwszego progu powyżej średniej
        next_threshold = None
        for thresh, target_mark, label in grade_thresholds:
            if avg < thresh:
                next_threshold = (thresh, target_mark, label)
                break

        if next_threshold:
            gap = round(next_threshold[0] - avg, 2)
            if 0.0 < gap <= 0.20:
                needed_w = 2.0
                new_avg_with_5 = (weighted + 5.0 * needed_w) / (weights + needed_w)
                remedy = "Wystarczy jedna ocena 5 (np. ze sprawdzianu lub kartkówki)" if new_avg_with_5 >= next_threshold[0] else "Potrzebna ocena 5 lub 6 o wadze min. 2-3"

                quick_wins.append({
                    "subject": sname,
                    "average": avg,
                    "count": cnt,
                    "total_entries": total_entries,
                    "gap": gap,
                    "target_label": next_threshold[2],
                    "threshold": next_threshold[0],
                    "remedy": remedy,
                })

        # 3. Sprawdzenie zagrożenia spadkiem vs Bezpieczny bufor
        prev_threshold = None
        for thresh, _, label in reversed(grade_thresholds):
            if avg >= thresh:
                prev_threshold = (thresh, label)
                break

        if prev_threshold:
            buffer = round(avg - prev_threshold[0], 2)
            if buffer <= 0.12 and avg >= 2.50:
                at_risk.append({
                    "subject": sname,
                    "average": avg,
                    "count": cnt,
                    "total_entries": total_entries,
                    "buffer": buffer,
                    "risk_label": prev_threshold[1],
                    "threshold": prev_threshold[0],
                    "warning": f"Margines bezpieczeństwa wynosi tylko +{buffer:.2f}. Jedna gorsza ocena może obniżyć ocenę.",
                })
            elif buffer > 0.12 and avg >= 2.50:
                thresh_val = prev_threshold[0]
                pts_buffer = round(weighted - thresh_val * weights, 2)
                # Obliczamy maksymalną wagę jedynki (1), którą uczeń może otrzymać bez spadku poniżej progu
                denom_1 = max(0.1, thresh_val - 1.0)
                max_w1 = math.floor(pts_buffer / denom_1) if denom_1 > 0 else 0

                is_preliminary = cnt <= 2 or weights < 3.0
                if is_preliminary:
                    test_w = 2.0
                    avg_with_5 = round((weighted + 5.0 * test_w) / (weights + test_w), 2)
                    avg_with_4 = round((weighted + 4.0 * test_w) / (weights + test_w), 2)
                    prop_with_5, _ = get_predicted_grade_tuple(avg_with_5)
                    prop_with_4, _ = get_predicted_grade_tuple(avg_with_4)

                    cnt_label = f"{cnt} {'ocena cyfrowa' if cnt == 1 else 'oceny cyfrowe'}"
                    if avg_with_5 < thresh_val:
                        resilience_desc = f"Wstępna ocena (tylko {cnt_label}): brak stabilności! Ocena 5 ze sprawdzianu obniży stopień do {prop_with_5}"
                    elif avg_with_4 < thresh_val:
                        resilience_desc = f"Wstępna ocena (tylko {cnt_label}): wrażliwa – ocena 4 ze sprawdzianu obniży stopień do {prop_with_4}"
                    else:
                        resilience_desc = f"Wstępna ocena (tylko {cnt_label}) – każda nowa ocena mocno wpływa na średnią"
                    resilience_weight = max_w1
                    resilience_icon = "⏳"
                    is_stable = False
                elif max_w1 >= 3:
                    resilience_desc = "Bardzo silna baza: wytrzyma nawet sprawdzian na 1 bez utraty oceny"
                    resilience_weight = max_w1
                    resilience_icon = "🛡️"
                    is_stable = True
                elif max_w1 >= 2:
                    resilience_desc = "Stabilna ocena: wytrzyma ocenę 1 ze sprawdzianu/odpowiedzi bez spadku"
                    resilience_weight = max_w1
                    resilience_icon = "🛡️"
                    is_stable = True
                elif max_w1 >= 1:
                    resilience_desc = "Dobra stabilność: wytrzyma jedynkę z kartkówki (waga 1)"
                    resilience_weight = max_w1
                    resilience_icon = "🛡️"
                    is_stable = True
                else:
                    # Nie wytrzyma jedynki, sprawdzamy trójkę (3)
                    denom_3 = max(0.1, thresh_val - 3.0)
                    max_w3 = math.floor(pts_buffer / denom_3) if thresh_val > 3.0 and denom_3 > 0 else 0
                    if max_w3 >= 2:
                        resilience_desc = "Utrzyma ocenę przy trójce (3) ze sprawdzianu"
                    else:
                        resilience_desc = f"Solidny bufor (+{buffer:.2f} pkt), wymaga ocen na poziomie 4 lub wyższym"
                    resilience_weight = 0
                    resilience_icon = "🛡️"
                    is_stable = True

                safe.append({
                    "subject": sname,
                    "average": avg,
                    "count": cnt,
                    "total_entries": total_entries,
                    "buffer": buffer,
                    "current_label": prev_threshold[1],
                    "threshold": thresh_val,
                    "pts_buffer": pts_buffer,
                    "resilience_weight": resilience_weight,
                    "resilience_desc": resilience_desc,
                    "resilience_icon": resilience_icon,
                    "is_stable": is_stable,
                    "is_preliminary": is_preliminary,
                })
        elif avg >= 2.50:
            safe.append({
                "subject": sname,
                "average": avg,
                "count": cnt,
                "total_entries": total_entries,
                "buffer": 0.0,
                "current_label": "Ocena bazowa",
                "threshold": 1.75,
                "pts_buffer": 0.0,
                "resilience_weight": 1,
                "resilience_desc": "Ocena stabilna",
                "resilience_icon": "🛡️",
                "is_stable": True,
                "is_preliminary": False,
            })

    # Sortowania
    quick_wins.sort(key=lambda x: x['gap'])
    at_risk.sort(key=lambda x: x['buffer'])
    safe.sort(key=lambda x: x['average'], reverse=True)

    return {
        "quick_wins": quick_wins,
        "at_risk": at_risk,
        "drop_risks": at_risk,
        "safe": safe,
        "intervention": intervention,
        "matrix_items": quick_wins + at_risk + safe + intervention,
        "counts": {
            "quick_wins": len(quick_wins),
            "at_risk": len(at_risk),
            "safe": len(safe),
            "intervention": len(intervention),
        },
    }


def compute_subject_stability_benchmark(
    subject_averages: dict[str, dict[str, Any]] | list[dict[str, Any]],
    grades_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Oblicza wskaźniki stabilności, rozrzutu ocen oraz porównanie lokomotyw i kotwic średniej."""
    import math

    if grades_history is None:
        grades_history = []
    if isinstance(subject_averages, list):
        subject_averages = {
            (item.get('subject') or item.get('name') or f'Item_{idx}'): item
            for idx, item in enumerate(subject_averages)
        }

    # Grupowanie wartości ocen per przedmiot
    grades_by_subject: dict[str, list[float]] = {}
    for g in grades_history:
        subj = g.get('subject') or g.get('name')
        if not subj:
            continue
        raw_val = g.get('grade') or g.get('value')
        clean_num = None
        try:
            m = re.search(r'([1-6])(?:\.0)?', str(raw_val))
            if m:
                clean_num = float(m.group(1))
        except (ValueError, TypeError):
            pass

        if clean_num:
            grades_by_subject.setdefault(subj, []).append(clean_num)

    benchmark_list = []
    for sname, sdata in subject_averages.items():
        if sdata.get('is_excluded') or sdata.get('average') is None:
            continue

        avg = sdata['average']
        vals = grades_by_subject.get(sname, [])

        if len(vals) >= 2:
            mean = sum(vals) / len(vals)
            variance = sum((x - mean) ** 2 for x in vals) / len(vals)
            std_dev = math.sqrt(variance)
            min_g = min(vals)
            max_g = max(vals)
        elif vals:
            std_dev = 0.0
            min_g = vals[0]
            max_g = vals[0]
        else:
            std_dev = 0.0
            min_g = None
            max_g = None

        if std_dev < 0.60:
            stability_tag = "Wysoka stabilność"
            stability_status = "high"
            stability_badge = "bg-emerald-50 text-emerald-700 border-emerald-200"
            stability_desc = "Oceny bardzo wyrównane i przewidywalne."
        elif std_dev <= 1.10:
            stability_tag = "Umiarkowana"
            stability_status = "moderate"
            stability_badge = "bg-sky-50 text-sky-700 border-sky-200"
            stability_desc = "Standardowe wahania ocen."
        else:
            stability_tag = "Duża zmienność"
            stability_status = "low"
            stability_badge = "bg-amber-50 text-amber-700 border-amber-200"
            stability_desc = "Skrajny rozrzut ocen (huśtawka wyników)."

        benchmark_list.append({
            "subject": sname,
            "average": avg,
            "count": sdata.get('numeric_count', sdata.get('grades_count', sdata.get('count', 0))),
            "std_dev": round(std_dev, 2),
            "stdev": round(std_dev, 2),
            "min_grade": min_g,
            "max_grade": max_g,
            "stability_tag": stability_tag,
            "stability_status": stability_status,
            "stability_badge": stability_badge,
            "stability_desc": stability_desc,
        })

    # Sortowanie po średniej malejąco
    benchmark_list.sort(key=lambda x: x['average'], reverse=True)

    locomotives = benchmark_list[:3] if len(benchmark_list) >= 3 else benchmark_list
    anchors = benchmark_list[-3:] if len(benchmark_list) >= 3 else []
    anchors.reverse()

    # Dane do wykresu słupkowego horyzontalnego
    chart_labels = [b["subject"] for b in benchmark_list]
    chart_values = [b["average"] for b in benchmark_list]

    return {
        "items": benchmark_list,
        "benchmark_items": benchmark_list,
        "subject_items": benchmark_list,
        "locomotives": locomotives,
        "anchors": anchors,
        "chart": {
            "labels": chart_labels,
            "values": chart_values,
        },
        "bar_chart": {
            "labels": chart_labels,
            "values": chart_values,
        },
    }



