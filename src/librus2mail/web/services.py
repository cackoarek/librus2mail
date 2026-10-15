"""Warstwa usług i logiki biznesowej dla panelu webowego Librus2mail."""

import io
import logging
import os
import statistics
from collections import defaultdict
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
from librus2mail.storage import BaseStorage, create_storage, sort_items_descending
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
        sorted_grades = sorted(g_list, key=lambda x: str(x.get('date', '')), reverse=True)
        is_excluded = subj.strip().lower() in norm_excluded

        result[subj] = {
            'subject': subj,
            'grades': sorted_grades,
            'count': len(g_list),
            'numeric_count': numeric_count,
            'average': avg,
            'sum_weights': sum_weights,
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

    # Najnowsze oceny (ostatnie 8)
    recent_grades = sorted(grades, key=lambda x: str(x.get('added_at', '') or x.get('date', '')), reverse=True)[:8]

    # Terminarz i plan lekcji
    timetable_summary = prepare_timetable_summary(timetable, reference_date=ref_now.date())
    sched_ctx = build_schedule_day_context(schedule, timetable_entries=timetable, ref_now=ref_now)
    schedule_summary = sched_ctx['selected_summary']
    today_schedule_summary = prepare_schedule_summary(schedule, timetable_entries=timetable, now=ref_now, day_offset=0)

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


