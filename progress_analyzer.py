import math
import re
from datetime import datetime
from typing import Any
from base_logger import logger


GRADE_VALUE_MAP = {
    '6': 6.0,
    '6-': 5.75,
    '5+': 5.5,
    '5': 5.0,
    '5-': 4.75,
    '4+': 4.5,
    '4': 4.0,
    '4-': 3.75,
    '3+': 3.5,
    '3': 3.0,
    '3-': 2.75,
    '3=': 2.5,
    '2+': 2.5,
    '2': 2.0,
    '2-': 1.75,
    '1+': 1.5,
    '1': 1.0,
    '1-': 0.75,
}

GRADE_THRESHOLDS = [
    (5.51, 6, "6 (celujący)"),
    (4.75, 5, "5 (bardzo dobry)"),
    (3.75, 4, "4 (dobry)"),
    (2.75, 3, "3 (dostateczny)"),
    (1.75, 2, "2 (dopuszczający)"),
    (0.00, 1, "1 (niedostateczny)"),
]

EXAM_KEYWORDS = (
    'sprawdzian', 'praca klasowa', 'klasówk', 'test', 'diagnoz',
    'egzamin', 'semestral', 'projekt', 'wypracowanie'
)

DAILY_KEYWORDS = (
    'kartkówk', 'odpowiedź', 'odp', 'aktywność', 'zadanie',
    'praca domowa', 'domowa', 'lekcj', 'ćwiczen', 'wejściówk'
)


def parse_numeric_grade(val: Any) -> float | None:
    """
    Przekształca stopień Librusa (np. '5', '5+', '4-', '3=') na wartość liczbową float.
    Dla ocen nieliczbowych (+, -, np, bz, zal) zwraca None.
    """
    if val is None:
        return None
    s = str(val).strip()
    if s in GRADE_VALUE_MAP:
        return GRADE_VALUE_MAP[s]

    clean = s.replace(',', '.')
    try:
        f = float(clean)
        if 1.0 <= f <= 6.0:
            return f
    except ValueError:
        pass

    m = re.match(r'^([1-6])([\+\-\=])?$', s)
    if m:
        base = float(m.group(1))
        mod = m.group(2)
        if mod == '+':
            return base + 0.5
        elif mod == '-':
            return base - 0.25
        elif mod == '=':
            return base - 0.5
        return base

    return None


def parse_weight(weight: Any) -> float:
    """
    Zwraca wagę oceny jako float. Domyślnie 1.0, jeśli brak lub nieprawidłowa wartość.
    """
    if weight is None or weight == '-' or str(weight).strip() == '':
        return 1.0
    try:
        w = float(str(weight).strip().replace(',', '.'))
        return max(0.0, w)
    except ValueError:
        return 1.0


def parse_grade_date(date_str: str, added_at_iso: str = None) -> datetime | None:
    """
    Wyodrębnia datę z ciągu Librusa (np. '2026-09-16', '2026-09-11 (pt.)') lub z added_at.
    """
    if date_str and date_str != '-':
        m = re.search(r'(\d{4})-(\d{2})-(\d{2})', str(date_str))
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        m2 = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', str(date_str))
        if m2:
            try:
                return datetime(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
            except ValueError:
                pass

    if added_at_iso:
        try:
            return datetime.fromisoformat(str(added_at_iso))
        except (ValueError, TypeError):
            pass

    return None


def get_predicted_grade_tuple(avg: float | None) -> tuple[int, str]:
    """
    Zwraca krotkę (stopień_int, etykieta) na podstawie progów szkolnych.
    """
    if avg is None or avg <= 0:
        return 0, "-"
    for threshold, num, label in GRADE_THRESHOLDS:
        if avg >= threshold:
            return num, label
    return 1, "1 (niedostateczny)"


def get_predicted_grade(avg: float | None) -> str:
    """
    Wyznacza sugerowaną ocenę końcową na podstawie średniej ważonej wg progów szkolnych.
    """
    _, label = get_predicted_grade_tuple(avg)
    return label


def _calculate_needed_grade(current_sum: float, current_weight: float, target_threshold: float, new_weight: float) -> float:
    """
    Wyznacza minimalną ocenę z nowej pracy o wadze new_weight, aby osiągnąć target_threshold.
    Formula: (current_sum + x * new_weight) / (current_weight + new_weight) >= target_threshold
    """
    if new_weight <= 0:
        return 6.0
    val = (target_threshold * (current_weight + new_weight) - current_sum) / new_weight
    return val


def _format_needed_grade_advice(val: float) -> str:
    """
    Formatuje wyliczoną wymaganą ocenę jako czytelną etykietę (np. 'min. 4', '5 lub 6', 'niemożliwe z jednej pracy').
    """
    if val <= 1.0:
        return "wystarczy jakakolwiek ocena pozytywna"
    if val <= 2.0:
        return "min. 2 (dopuszczający)"
    if val <= 3.0:
        return "min. 3 (dostateczny)"
    if val <= 4.0:
        return "min. 4 (dobry)"
    if val <= 5.0:
        return "min. 5 (bardzo dobry)"
    if val <= 6.0:
        return "ocena 6 (celujący)"
    return "wymaga kilku wysokich ocen"


class ProgressAnalyzer:
    """
    Silnik analityczny oceny postępów ucznia.
    Przelicza średnie ważone, wskaźniki pedagogiczne, symulatory ocen i generuje rekomendacje rodzicielskie.
    """

    @classmethod
    def analyze(
        cls,
        grades: list[dict],
        period_start: datetime = None,
        period_end: datetime = None
    ) -> dict[str, Any]:
        period_end = period_end or datetime.now()

        # 1. Podział ocen na okres i całość
        all_grades_parsed: list[dict[str, Any]] = []
        period_grades: list[dict[str, Any]] = []
        prior_grades: list[dict[str, Any]] = []

        for g in grades:
            g_val = g.get('grade', '').strip()
            num_val = parse_numeric_grade(g_val)
            weight = parse_weight(g.get('weight'))
            g_date = parse_grade_date(g.get('date'), g.get('added_at'))

            enriched = {
                **g,
                'numeric_val': num_val,
                'parsed_weight': weight,
                'parsed_date': g_date,
            }
            all_grades_parsed.append(enriched)

            # Sprawdzenie czy wpada w okres
            if period_start is not None:
                if g_date and g_date >= period_start:
                    period_grades.append(enriched)
                elif not g_date:
                    dt_added = parse_grade_date(None, g.get('added_at'))
                    if dt_added and dt_added >= period_start:
                        period_grades.append(enriched)
                    else:
                        prior_grades.append(enriched)
                else:
                    prior_grades.append(enriched)
            else:
                period_grades.append(enriched)

        # 2. Pogrupowanie według przedmiotów
        subjects_map: dict[str, dict[str, list[dict]]] = {}
        for g in all_grades_parsed:
            subj = g.get('subject') or 'Inny przedmiot'
            if subj not in subjects_map:
                subjects_map[subj] = {'all': [], 'period': [], 'prior': []}
            subjects_map[subj]['all'].append(g)

        for g in period_grades:
            subj = g.get('subject') or 'Inny przedmiot'
            subjects_map[subj]['period'].append(g)

        for g in prior_grades:
            subj = g.get('subject') or 'Inny przedmiot'
            subjects_map[subj]['prior'].append(g)

        def calc_weighted_avg(g_list: list[dict]) -> float | None:
            total_sum = 0.0
            total_weight = 0.0
            for item in g_list:
                nv = item.get('numeric_val')
                w = item.get('parsed_weight', 1.0)
                if nv is not None and w > 0:
                    total_sum += nv * w
                    total_weight += w
            if total_weight > 0:
                return round(total_sum / total_weight, 2)
            return None

        # 3. Analiza każdego przedmiotu
        analyzed_subjects = []
        valid_subject_averages = []

        for subj_name, data in sorted(subjects_map.items()):
            subj_all = data['all']
            subj_period = data['period']
            subj_prior = data['prior']

            avg_all = calc_weighted_avg(subj_all)
            avg_period = calc_weighted_avg(subj_period)
            avg_prior = calc_weighted_avg(subj_prior)

            if avg_all is not None:
                valid_subject_averages.append(avg_all)

            trend = 'none'
            trend_label = '—'
            if avg_period is not None and avg_prior is not None:
                diff = round(avg_period - avg_prior, 2)
                if diff >= 0.2:
                    trend = 'up'
                    trend_label = f"↗ (+{diff:.2f})"
                elif diff <= -0.2:
                    trend = 'down'
                    trend_label = f"↘ ({diff:.2f})"
                else:
                    trend = 'stable'
                    trend_label = "➡ (stabilnie)"
            elif avg_period is not None and not subj_prior:
                trend = 'new'
                trend_label = "✨ (nowy wpis)"

            predicted = get_predicted_grade(avg_all)

            analyzed_subjects.append({
                'subject': subj_name,
                'overall_avg': avg_all,
                'period_avg': avg_period,
                'trend': trend,
                'trend_label': trend_label,
                'predicted_grade': predicted,
                'all_grades': subj_all,
                'period_grades': subj_period,
                'grades_count': len(subj_all),
                'period_grades_count': len(subj_period)
            })

        # Sortowanie przedmiotów: najpierw te z nowymi ocenami w okresie, potem alfabetycznie
        analyzed_subjects.sort(key=lambda s: (-s['period_grades_count'], s['subject']))

        # 4. Statystyki ogólne
        overall_student_avg = None
        if valid_subject_averages:
            overall_student_avg = round(sum(valid_subject_averages) / len(valid_subject_averages), 2)

        period_student_avg = calc_weighted_avg(period_grades)

        # 5. Histogram rozkładu ocen
        distribution_overall = {str(i): 0 for i in range(1, 7)}
        distribution_period = {str(i): 0 for i in range(1, 7)}
        activity_pluses = 0
        activity_minuses = 0
        unprepared_count = 0

        for g in all_grades_parsed:
            nv = g.get('numeric_val')
            raw = g.get('grade', '').strip()
            if nv is not None:
                int_base = str(min(6, max(1, int(round(nv)))))
                distribution_overall[int_base] = distribution_overall.get(int_base, 0) + 1
            if raw == '+':
                activity_pluses += 1
            elif raw == '-':
                activity_minuses += 1
            elif raw.lower() in ('np', 'niepr', 'bz'):
                unprepared_count += 1

        for g in period_grades:
            nv = g.get('numeric_val')
            if nv is not None:
                int_base = str(min(6, max(1, int(round(nv)))))
                distribution_period[int_base] = distribution_period.get(int_base, 0) + 1

        # 6. Analiza dodatkowa 1: "Na granicy oceny" (Borderline analysis)
        borderline_opportunities = []
        borderline_risks = []

        for subj_item in analyzed_subjects:
            subj_name = subj_item['subject']
            avg_all = subj_item['overall_avg']
            if avg_all is None:
                continue

            subj_grades = subjects_map[subj_name]['all']
            sum_wx = sum(g['numeric_val'] * g['parsed_weight'] for g in subj_grades if g.get('numeric_val') is not None)
            sum_w = sum(g['parsed_weight'] for g in subj_grades if g.get('numeric_val') is not None)

            curr_num, curr_label = get_predicted_grade_tuple(avg_all)

            # Szansa na wyższą ocenę (gdy brakuje <= 0.25)
            if curr_num < 6:
                next_thresh_tuple = [t for t in GRADE_THRESHOLDS if t[1] == curr_num + 1][0]
                target_threshold, target_num, target_label = next_thresh_tuple
                diff_to_target = round(target_threshold - avg_all, 2)

                if 0.0 < diff_to_target <= 0.25:
                    needed_w2 = _calculate_needed_grade(sum_wx, sum_w, target_threshold, 2.0)
                    needed_w1 = _calculate_needed_grade(sum_wx, sum_w, target_threshold, 1.0)
                    advice_w2 = _format_needed_grade_advice(needed_w2)
                    advice_w1 = _format_needed_grade_advice(needed_w1)

                    advice_str = f"Średnia {avg_all:.2f} (brakuje tylko {diff_to_target:.2f} do {target_label}). Na sprawdzianie (waga 2): {advice_w2}; na kartkówce (waga 1): {advice_w1}."
                    borderline_opportunities.append({
                        'subject': subj_name,
                        'current_avg': avg_all,
                        'current_grade': curr_label,
                        'target_grade': target_label,
                        'gap': diff_to_target,
                        'advice': advice_str
                    })

            # Ryzyko spadku oceny (gdy margines bezpieczeństwa <= 0.12)
            if curr_num > 1:
                curr_thresh_tuple = [t for t in GRADE_THRESHOLDS if t[1] == curr_num][0]
                curr_threshold = curr_thresh_tuple[0]
                safety_margin = round(avg_all - curr_threshold, 2)

                if 0.0 <= safety_margin <= 0.12:
                    lower_thresh_tuple = [t for t in GRADE_THRESHOLDS if t[1] == curr_num - 1][0]
                    lower_label = lower_thresh_tuple[2]
                    warning_str = f"Średnia {avg_all:.2f} (margines bezpieczeństwa tylko {safety_margin:.2f} nad progiem). Jedna słaba ocena ze sprawdzianu zepchnie prognozę do: {lower_label}."
                    borderline_risks.append({
                        'subject': subj_name,
                        'current_avg': avg_all,
                        'current_grade': curr_label,
                        'lower_grade': lower_label,
                        'margin': safety_margin,
                        'warning': warning_str
                    })

        # 7. Analiza dodatkowa 2: Styl nauki - Sprawdziany vs Bieżąca praca
        exam_grades = []
        daily_grades = []
        for g in all_grades_parsed:
            if g.get('numeric_val') is None:
                continue
            cat = str(g.get('category') or '').lower()
            w = g.get('parsed_weight', 1.0)

            if any(kw in cat for kw in EXAM_KEYWORDS) or w >= 2.5:
                exam_grades.append(g)
            elif any(kw in cat for kw in DAILY_KEYWORDS) or w <= 1.0:
                daily_grades.append(g)
            elif w >= 2.0:
                exam_grades.append(g)
            else:
                daily_grades.append(g)

        exams_avg = calc_weighted_avg(exam_grades)
        daily_avg = calc_weighted_avg(daily_grades)

        learning_style = {
            'exams_avg': exams_avg,
            'exams_count': len(exam_grades),
            'daily_avg': daily_avg,
            'daily_count': len(daily_grades),
            'diff': round(exams_avg - daily_avg, 2) if exams_avg is not None and daily_avg is not None else None,
            'diagnosis_type': 'balanced',
            'diagnosis': 'Zrównoważone wyniki lub zbyt mało ocen w poszczególnych kategoriach.'
        }

        if exams_avg is not None and daily_avg is not None and len(exam_grades) >= 1 and len(daily_grades) >= 1:
            diff = learning_style['diff']
            if diff <= -0.40:
                learning_style['diagnosis_type'] = 'exams_lower'
                learning_style['diagnosis'] = (
                    f"Średnia ze sprawdzianów ({exams_avg:.2f}) jest niższa niż z bieżącej pracy ({daily_avg:.2f}). "
                    "Uczeń dobrze radzi sobie z bieżącym materiałem z lekcji na lekcję, lecz warto pomóc mu w powtórkach "
                    "i syntezie większych partii wiedzy przed sprawdzianami."
                )
            elif diff >= 0.40:
                learning_style['diagnosis_type'] = 'daily_lower'
                learning_style['diagnosis'] = (
                    f"Średnia ze sprawdzianów ({exams_avg:.2f}) jest wyższa niż z bieżącej pracy ({daily_avg:.2f}). "
                    "Dziecko ma wysoki potencjał i doskonale rozumie trudniejsze zagadnienia, ale gubi punkty na "
                    "bieżącej dyscyplinie (kartkówki, zadania domowe, aktywność)."
                )
            else:
                learning_style['diagnosis_type'] = 'balanced'
                learning_style['diagnosis'] = (
                    f"Zrównoważony styl pracy – oceny ze sprawdzianów ({exams_avg:.2f}) i bieżącej pracy ({daily_avg:.2f}) "
                    "są na bardzo spójnym poziomie."
                )

        # 8. Analiza dodatkowa 3: Symulator "Czerwonego Paska" (Świadectwo z wyróżnieniem)
        subjects_with_avg = [s for s in analyzed_subjects if s['overall_avg'] is not None]
        honor_roll = {
            'qualified': False,
            'status': 'target',
            'current_avg': overall_student_avg,
            'target_avg': 4.75,
            'gap': 0.0,
            'message': '',
            'key_opportunities': []
        }

        if subjects_with_avg and overall_student_avg is not None:
            has_failing = any(s['overall_avg'] < 1.75 for s in subjects_with_avg)
            if overall_student_avg >= 4.75 and not has_failing:
                honor_roll['qualified'] = True
                honor_roll['status'] = 'achieved'
                honor_roll['message'] = (
                    f"Aktualna średnia ({overall_student_avg:.2f}) kwalifikuje ucznia do świadectwa z wyróżnieniem! "
                    "Brak ocen niedostatecznych. Gratulacje!"
                )
            else:
                gap = round(4.75 - overall_student_avg, 2)
                honor_roll['gap'] = max(0.0, gap)
                candidates = []
                for s in subjects_with_avg:
                    avg = s['overall_avg']
                    curr_n, _ = get_predicted_grade_tuple(avg)
                    if curr_n < 5:  # Można podciągnąć na 5 lub 6
                        next_thresh = [t[0] for t in GRADE_THRESHOLDS if t[1] == curr_n + 1][0]
                        dist = round(next_thresh - avg, 2)
                        candidates.append({
                            'subject': s['subject'],
                            'current_avg': avg,
                            'dist': dist,
                            'target_grade': curr_n + 1
                        })
                candidates.sort(key=lambda c: c['dist'])
                honor_roll['key_opportunities'] = candidates[:3]

                opp_text = ""
                if candidates:
                    items_str = ", ".join([f"{c['subject']} (śr. {c['current_avg']:.2f}, brakuje {c['dist']:.2f} do {c['target_grade']})" for c in candidates[:2]])
                    opp_text = f" Najszybsza droga do paska to podniesienie ocen z: {items_str}."

                honor_roll['message'] = (
                    f"Do czerwonego paska (średnia 4.75) brakuje {gap:.2f} pkt średniej.{opp_text}"
                )

        # 9. Analiza dodatkowa 4: "Ciche przedmioty" (brak ocen od >= 30 dni)
        dormant_subjects = []
        for subj_name, data in subjects_map.items():
            grades_with_date = [g for g in data['all'] if g.get('parsed_date')]
            if grades_with_date:
                latest_dt = max(g['parsed_date'] for g in grades_with_date)
                days_ago = (period_end.date() - latest_dt.date()).days
                if days_ago >= 30:
                    dormant_subjects.append({
                        'subject': subj_name,
                        'days_ago': days_ago,
                        'last_date_str': latest_dt.strftime('%d.%m.%Y')
                    })
            elif not data['all']:
                dormant_subjects.append({
                    'subject': subj_name,
                    'days_ago': None,
                    'last_date_str': 'brak ocen w historii'
                })

        dormant_subjects.sort(key=lambda x: (x['days_ago'] is None, -(x['days_ago'] or 0)))

        # 10. Analiza dodatkowa 5: Wskaźnik stabilności ocen (odchylenie standardowe)
        stable_subjects = []
        volatile_subjects = []

        for subj_name, data in subjects_map.items():
            num_vals = [g['numeric_val'] for g in data['all'] if g.get('numeric_val') is not None]
            if len(num_vals) >= 3:
                mean_v = sum(num_vals) / len(num_vals)
                variance = sum((x - mean_v) ** 2 for x in num_vals) / len(num_vals)
                std_dev = round(math.sqrt(variance), 2)
                min_v = min(num_vals)
                max_v = max(num_vals)

                if std_dev <= 0.55:
                    stable_subjects.append({
                        'subject': subj_name,
                        'std_dev': std_dev,
                        'min': min_v,
                        'max': max_v
                    })
                elif std_dev >= 1.15:
                    volatile_subjects.append({
                        'subject': subj_name,
                        'std_dev': std_dev,
                        'min': min_v,
                        'max': max_v
                    })

        stable_subjects.sort(key=lambda s: s['std_dev'])
        volatile_subjects.sort(key=lambda s: -s['std_dev'])

        # 11. Analiza dodatkowa 6: Wpływ wag ocen (Średnia arytmetyczna vs ważona)
        all_numeric = [g for g in all_grades_parsed if g.get('numeric_val') is not None]
        if all_numeric:
            arithmetic_avg = round(sum(g['numeric_val'] for g in all_numeric) / len(all_numeric), 2)
            weighted_all_avg = calc_weighted_avg(all_numeric)
            weight_diff = round((weighted_all_avg or 0.0) - arithmetic_avg, 2)

            if weight_diff <= -0.20:
                impact_type = 'negative'
                impact_desc = (
                    f"Ujemny ({weight_diff:+.2f}): oceny ze sprawdzianów o dużej wadze są niższe niż drobne oceny cząstkowe, "
                    "co obniża ogólny wynik ucznia względem prostej średniej arytmetycznej."
                )
            elif weight_diff >= 0.20:
                impact_type = 'positive'
                impact_desc = (
                    f"Dodatni ({weight_diff:+.2f}): uczeń osiąga wyższe stopnie z kluczowych sprawdzianów o dużej wadze, "
                    "co skutecznie podciąga średnią w górę."
                )
            else:
                impact_type = 'neutral'
                impact_desc = (
                    f"Neutralny ({weight_diff:+.2f}): wyniki ze sprawdzianów i drobniejszych prac są proporcjonalne."
                )

            weight_impact = {
                'arithmetic_avg': arithmetic_avg,
                'weighted_avg': weighted_all_avg,
                'diff': weight_diff,
                'impact_type': impact_type,
                'description': impact_desc
            }
        else:
            weight_impact = {
                'arithmetic_avg': None,
                'weighted_avg': None,
                'diff': 0.0,
                'impact_type': 'none',
                'description': 'Brak ocen liczbowych do analizy wag.'
            }

        # 12. Alerty i rekomendacje rodzicielskie (Sukcesy i Uwagi)
        strengths = []
        warnings = []

        # Sukcesy
        if honor_roll['qualified']:
            strengths.append(f"🏅 <strong>Świadectwo z wyróżnieniem</strong>: aktualna średnia ucznia wynosi {overall_student_avg:.2f} (próg: 4.75)!")
        else:
            top_subjects = [s for s in analyzed_subjects if s['overall_avg'] and s['overall_avg'] >= 4.75]
            if top_subjects:
                top_names = ", ".join([f"<strong>{s['subject']}</strong> ({s['overall_avg']:.2f})" for s in top_subjects[:4]])
                strengths.append(f"Wysoka średnia z przedmiotów: {top_names}.")

        high_period_grades = [g for g in period_grades if g.get('numeric_val') and g['numeric_val'] >= 5.0 and g.get('parsed_weight', 1.0) >= 2.0]
        if high_period_grades:
            high_desc = ", ".join([f"{g['subject']}: {g['grade']} (waga {g.get('weight', '-')})" for g in high_period_grades[:3]])
            strengths.append(f"Bardzo dobre oceny ze sprawdzianów w tym okresie: {high_desc}.")

        if borderline_opportunities:
            top_opp = borderline_opportunities[0]
            strengths.append(f"🎯 <strong>Szansa na wyższą ocenę</strong>: {top_opp['advice']}")

        if stable_subjects:
            st_names = ", ".join([s['subject'] for s in stable_subjects[:3]])
            strengths.append(f"Stabilne, pewne wyniki bez wahań z przedmiotów: {st_names}.")

        # Zagrożenia i Uwagi
        threat_subjects = [s for s in analyzed_subjects if s['overall_avg'] and s['overall_avg'] < 2.0]
        if threat_subjects:
            names = ", ".join([f"<strong>{s['subject']}</strong> (średnia: {s['overall_avg']:.2f})" for s in threat_subjects])
            warnings.append(f"⚠️ Zagrożenie oceną niedostateczną z: {names}! Warto pilnie skonsultować się z nauczycielem.")

        weak_subjects = [s for s in analyzed_subjects if s['overall_avg'] and 2.0 <= s['overall_avg'] < 3.0]
        if weak_subjects:
            names = ", ".join([f"<strong>{s['subject']}</strong> ({s['overall_avg']:.2f})" for s in weak_subjects[:3]])
            warnings.append(f"Niska średnia (< 3.0) z przedmiotów: {names}.")

        if borderline_risks:
            risk = borderline_risks[0]
            warnings.append(f"⚖️ <strong>Ryzyko spadku oceny</strong>: {risk['warning']}")

        low_period_heavy = [g for g in period_grades if g.get('numeric_val') and g['numeric_val'] <= 2.0 and g.get('parsed_weight', 1.0) >= 2.0]
        if low_period_heavy:
            low_desc = ", ".join([f"{g['subject']}: {g['grade']} (waga {g.get('weight', '-')}, kategoria: {g.get('category', '-')})" for g in low_period_heavy[:3]])
            warnings.append(f"Słabe oceny ze sprawdzianów o dużej wadze w minionym okresie: {low_desc}. Warto zapytać o możliwość poprawy.")

        if learning_style['diagnosis_type'] == 'exams_lower':
            warnings.append(f"🔍 <strong>Styl nauki</strong>: {learning_style['diagnosis']}")

        if volatile_subjects:
            vol_names = ", ".join([f"{v['subject']} (rozrzut: {v['min']}–{v['max']})" for v in volatile_subjects[:2]])
            warnings.append(f"🎢 <strong>Nierównomierne oceny (sinusoida)</strong> z przedmiotów: {vol_names}. Warto sprawdzić przyczyny pojedynczych potknięć.")

        if dormant_subjects:
            d_names = ", ".join([f"{d['subject']} ({d['days_ago']} dni temu)" for d in dormant_subjects[:3] if d['days_ago']])
            if d_names:
                warnings.append(f"⏱️ <strong>Brak ocen od ponad miesiąca</strong> z przedmiotów: {d_names}. Uwaga na możliwą kumulację testów pod koniec semestru.")

        if unprepared_count > 0:
            warnings.append(f"Odnotowano {unprepared_count} nieprzygotowań / braków zadania domowego (np/bz).")

        # 13. Przewodnik rodzica (Legenda interpretacji wskaźników)
        legend = {
            'thresholds': "Progi ocen: 6 (od 5.51), 5 (od 4.75), 4 (od 3.75), 3 (od 2.75), 2 (od 1.75), 1 (poniżej 1.75).",
            'trends': "Wskaźnik trendu: ↗ oznacza wzrost średniej z okresu o min. +0.20 względem historii; ↘ spadek o min. -0.20; ➡ stabilny poziom; ✨ pierwszy wpis z przedmiotu.",
            'borderline': "Analiza na krawędzi ocen wskazuje, gdzie uczeń ma minimalną stratę (np. <= 0.25) do wyższego stopnia i wylicza ocenę potrzebną z kolejnej pracy, by go zdobyć.",
            'learning_style': "Porównanie sprawdzianów (wagi 2-3) z bieżącą pracą (kartkówki, odpowiedzi, waga 1). Pokazuje, czy dziecko ma trudności z powtórkami dużego materiału, czy z systematycznością.",
            'honor_roll': "Świadectwo z wyróżnieniem (czerwony pasek) przysługuje przy średniej ocen końcowych min. 4.75 i braku ocen niedostatecznych.",
            'stability': "Wskaźnik stabilności: niska zmienność oznacza pewne, stałe oceny; wysoka (sinusoida) wskazuje na przeplatankę 1 i 5, czyli nierówne przygotowanie do lekcji.",
            'weight_impact': "Wpływ wag: średnia ważona kładzie nacisk na sprawdziany. Efekt ujemny oznacza, że testy wypadają gorzej niż drobne zadania, zaniżając ogólny wynik."
        }

        p_start_str = period_start.strftime("%d.%m.%Y") if period_start else "Początek roku"
        p_end_str = period_end.strftime("%d.%m.%Y")

        return {
            'period_start_str': p_start_str,
            'period_end_str': p_end_str,
            'period_start_iso': period_start.isoformat() if period_start else None,
            'period_end_iso': period_end.isoformat(),
            'overall_avg': overall_student_avg,
            'period_avg': period_student_avg,
            'total_grades_count': len(all_grades_parsed),
            'period_grades_count': len(period_grades),
            'subjects': analyzed_subjects,
            'period_grades': period_grades,
            'distribution_overall': distribution_overall,
            'distribution_period': distribution_period,
            'insights_strengths': strengths,
            'insights_warnings': warnings,
            'borderline_opportunities': borderline_opportunities,
            'borderline_risks': borderline_risks,
            'learning_style': learning_style,
            'honor_roll': honor_roll,
            'dormant_subjects': dormant_subjects,
            'stable_subjects': stable_subjects,
            'volatile_subjects': volatile_subjects,
            'weight_impact': weight_impact,
            'legend': legend,
            'activity_pluses': activity_pluses,
            'activity_minuses': activity_minuses,
            'unprepared_count': unprepared_count,
        }
