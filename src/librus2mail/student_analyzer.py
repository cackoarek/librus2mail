"""
Silnik analityczny dedykowany dla raportu ucznia (StudentAnalyzer).
Przekształca surowe dane z bazy ocen w przyjazne, motywujące metryki:
- Supermoce / Mocne strony (strengths)
- Szybkie punkty / Szanse na awans (quick_wins)
- Misje ratunkowe / Obszary uwagi (focus_areas)
- Formę i passę (streak, trend)
- Osiągnięcia i odznaki grywalizacyjne (achievements)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from librus2mail.progress_analyzer import parse_grade_date, parse_numeric_grade, parse_weight

logger = logging.getLogger(__name__)


@dataclass
class StudentAchievement:
    """Odznaka grywalizacyjna zdobyta przez ucznia."""

    id: str
    title: str
    icon: str
    description: str


@dataclass
class QuickWin:
    """Przedmiot z łatwym do zdobycia awansem na wyższy stopień."""

    subject: str
    current_avg: float
    target_grade: int
    needed_grade: int
    needed_weight: int
    hint: str


@dataclass
class SubjectStrength:
    """Mocna strona ucznia."""

    subject: str
    avg: float
    top_grades_count: int
    highlight: str


@dataclass
class FocusArea:
    """Obszar wymagający powtórki lub uwagi."""

    subject: str
    avg: float
    last_low_grade: str | None
    hint: str


@dataclass
class PeriodComparison:
    """Porównanie wyników z obecnego i poprzedniego okresu o tej samej długości."""

    has_comparison: bool  # True jeśli parametr days został określony
    has_prev_data: bool  # True jeśli w poprzednim okresie wystąpiły jakiekolwiek oceny
    current_start_str: str = ""
    current_end_str: str = ""
    prev_start_str: str = ""
    prev_end_str: str = ""
    current_avg: float | None = None
    prev_avg: float | None = None
    avg_diff: float | None = None  # różnica: current_avg - prev_avg
    current_count: int = 0
    prev_count: int = 0
    current_top_count: int = 0  # oceny >= 4.75
    prev_top_count: int = 0
    direction: str = "none"  # "up", "stable", "down", "none"
    message_kids: str = ""
    message_teens: str = ""
    message_youth: str = ""


@dataclass
class HonorRollTarget:
    """Pojedynczy przedmiot będący szansą na podniesienie średniej do paska."""

    subject: str
    current_avg: float
    target_grade: int
    gap_to_target: float
    hint: str


@dataclass
class HonorRollProgress:
    """Informacje o drodze do świadectwa z wyróżnieniem (czerwonego paska)."""

    current_avg: float
    target_avg: float = 4.75
    gap: float = 0.0
    progress_pct: int = 0
    status: str = "target"  # "achieved", "near", "milestone"
    has_failing: bool = False
    next_milestone_name: str = ""
    next_milestone_gap: float = 0.0
    headline: str = ""
    description: str = ""
    opportunities: list[HonorRollTarget] = field(default_factory=list)


@dataclass
class StudentMetrics:
    """Kompletny zestaw metryk dla raportu ucznia."""

    student_name: str
    total_grades_count: int
    period_grades_count: int
    overall_avg: float
    trend: str  # "up", "stable", "down"
    trend_description: str
    streak_count: int
    strengths: list[SubjectStrength] = field(default_factory=list)
    quick_wins: list[QuickWin] = field(default_factory=list)
    focus_areas: list[FocusArea] = field(default_factory=list)
    achievements: list[StudentAchievement] = field(default_factory=list)
    recent_grades: list[dict[str, Any]] = field(default_factory=list)
    period_start_str: str = ""
    period_end_str: str = ""
    period_desc: str = ""
    period_days: int | None = None
    period_comparison: PeriodComparison | None = None
    honor_roll: HonorRollProgress | None = None


class StudentAnalyzer:
    """Kalkulator metryk motywacyjnych dla ucznia."""

    def __init__(
        self,
        grades: list[dict[str, Any]],
        student_name: str = "Uczeń",
        actual_date: date | str | None = None,
        days: int | None = None,
    ):
        self.raw_grades = grades or []
        self.student_name = student_name

        if isinstance(actual_date, str):
            try:
                self.reference_date = datetime.strptime(actual_date, "%Y-%m-%d").date()
            except ValueError:
                self.reference_date = datetime.now().date()
        elif isinstance(actual_date, date):
            self.reference_date = actual_date
        else:
            self.reference_date = datetime.now().date()

        self.days = days
        self._parsed_grades = self._parse_all_grades()

    def _parse_all_grades(self) -> list[dict[str, Any]]:
        """Parsuje oceny, dodając wartości numeryczne, wagi i daty."""
        parsed = []
        for g in self.raw_grades:
            raw_grade = str(g.get("grade", "")).strip()
            num_val = parse_numeric_grade(raw_grade)
            if num_val is None:
                continue

            w_val = parse_weight(g.get("weight", 1))
            dt = parse_grade_date(g.get("date", ""), g.get("added_at"))
            g_date = dt.date() if dt else None

            raw_comment = str(g.get("comment", "")).strip()
            clean_comment = "" if raw_comment in ("-", "None", "null", "") else raw_comment
            raw_teacher = str(g.get("teacher", "")).strip()
            clean_teacher = "" if raw_teacher in ("-", "None", "null", "") else raw_teacher

            parsed.append({
                "subject": str(g.get("subject", "Inne")).strip(),
                "raw_grade": raw_grade,
                "numeric_grade": num_val,
                "weight": w_val,
                "date": g_date,
                "category": str(g.get("category", "")).strip(),
                "comment": clean_comment,
                "teacher": clean_teacher,
            })

        # Sortowanie od najnowszych
        parsed.sort(key=lambda x: x["date"] or date.min, reverse=True)
        return parsed

    def _filter_grades_by_period(self) -> list[dict[str, Any]]:
        """Zwraca oceny z wybranego okresu (np. ostatnich N dni)."""
        if not self.days:
            return self._parsed_grades

        cutoff = self.reference_date - timedelta(days=self.days)
        return [g for g in self._parsed_grades if g["date"] and cutoff <= g["date"] <= self.reference_date]

    def _calculate_period_comparison(
        self,
        current_grades: list[dict[str, Any]],
    ) -> PeriodComparison:
        """Wylicza porównanie wyników z obecnego i poprzedniego okresu o tej samej długości."""
        if not self.days:
            return PeriodComparison(has_comparison=False, has_prev_data=False)

        period_end = self.reference_date
        period_start = self.reference_date - timedelta(days=self.days)
        prev_end = period_start
        prev_start = period_start - timedelta(days=self.days)

        prev_grades = [
            g for g in self._parsed_grades
            if g["date"] and prev_start <= g["date"] < prev_end
        ]

        def calc_w_avg(grades_list: list[dict[str, Any]]) -> float | None:
            w_sum = sum(g["numeric_grade"] * g["weight"] for g in grades_list)
            w_tot = sum(g["weight"] for g in grades_list)
            return round(w_sum / w_tot, 2) if w_tot > 0 else None

        curr_avg = calc_w_avg(current_grades)
        prev_avg = calc_w_avg(prev_grades)

        curr_count = len(current_grades)
        prev_count = len(prev_grades)

        curr_top = sum(1 for g in current_grades if g["numeric_grade"] >= 4.75)
        prev_top = sum(1 for g in prev_grades if g["numeric_grade"] >= 4.75)

        has_prev = bool(prev_grades) and prev_avg is not None

        if curr_avg is None:
            direction = "none"
            diff = None
            msg_kids = "W tym okresie nie pojawiły się nowe oceny – to świetny moment, aby zebrać siły na kolejny tydzień! 🌟"
            msg_teens = "Brak nowych ocen w analizowanym okresie. Status: pauza / regeneracja."
            msg_youth = "Brak zarejestrowanych ocen w bieżącym oknie czasowym."
        elif not has_prev:
            direction = "none"
            diff = None
            msg_kids = (
                f"Zbierasz pierwsze oceny w nowym okresie! Twoja średnia to {curr_avg:.2f}. "
                f"To Twój punkt startowy – trzymamy kciuki za kolejne sukcesy! 🌟"
            )
            msg_teens = (
                f"Pierwszy badany okres – brak wcześniejszych danych referencyjnych. "
                f"Średnia wyjściowa: {curr_avg:.2f}. Zbuduj na tym swoje momentum!"
            )
            msg_youth = (
                f"Brak danych referencyjnych z poprzedniego przedziału czasowego. "
                f"Średnia bazowa dla bieżącego cyklu: {curr_avg:.2f}."
            )
        else:
            diff = round(curr_avg - prev_avg, 2)
            if diff >= 0.20:
                direction = "up"
                msg_kids = (
                    f"Level Up! Twoja forma rośnie! W tym okresie Twoja średnia to {curr_avg:.2f} "
                    f"(o +{diff:.2f} wyższa niż poprzednio – {prev_avg:.2f})! Zdobyłeś aż {curr_top} bardzo dobrych ocen. Świetna robota! 🚀"
                )
                msg_teens = (
                    f"Pozytywne momentum! Średnia z okresu wzrosła o +{diff:.2f} pkt (z {prev_avg:.2f} do {curr_avg:.2f}). "
                    f"Liczba wysokich ocen: {curr_top}. Trzymaj to tempo! 📈"
                )
                msg_youth = (
                    f"Wzrost dynamiki formy: średnia ważona wzrosła o +{diff:.2f} pkt względem poprzedniego cyklu "
                    f"({curr_avg:.2f} vs {prev_avg:.2f}). W bilansie odnotowano {curr_top} ocen wyróżniających."
                )
            elif diff <= -0.20:
                direction = "down"
                abs_diff = abs(diff)
                msg_kids = (
                    f"Chwilowa zadyszka – przed Tobą nowy tydzień! W tym okresie średnia wyniosła {curr_avg:.2f} "
                    f"(poprzednio {prev_avg:.2f}). Nie przejmuj się trudniejszymi tematami, odpocznij i w nowym tygodniu zdobędziesz nowe punkty! 💪"
                )
                msg_teens = (
                    f"Korekta formy (spadek o -{abs_diff:.2f} pkt z {prev_avg:.2f} na {curr_avg:.2f}). "
                    f"Warto sprawdzić tematy z ostatnich ocen i zaplanować krótką powtórkę. Dasz radę! 🎯"
                )
                msg_youth = (
                    f"Ujemna delta okresowa: spadek średniej ważonej o -{abs_diff:.2f} pkt ({curr_avg:.2f} vs {prev_avg:.2f}). "
                    f"Wskazana analiza tematów z ostatnich sprawdzianów i ukierunkowana powtórka."
                )
            else:
                direction = "stable"
                diff_str = f"+{diff:.2f}" if diff > 0 else f"{diff:.2f}"
                msg_kids = (
                    f"Równy, super poziom! Trzymasz stabilną formę (średnia {curr_avg:.2f} vs {prev_avg:.2f} poprzednio). "
                    f"Równy rytm nauki to najlepsza droga do sukcesu! 🎯"
                )
                msg_teens = (
                    f"Stabilne tempo. Średnia na zbliżonym poziomie ({curr_avg:.2f} vs {prev_avg:.2f}, zmiana {diff_str} pkt). "
                    f"Solidna i przewidywalna dyspozycja w dzienniku."
                )
                msg_youth = (
                    f"Stabilna dyspozycja: różnica średnich wynosi {diff_str} pkt ({curr_avg:.2f} vs {prev_avg:.2f}). "
                    f"Wskaźnik powtarzalności wyników na stałym poziomie."
                )

        return PeriodComparison(
            has_comparison=True,
            has_prev_data=has_prev,
            current_start_str=period_start.strftime("%d.%m.%Y"),
            current_end_str=period_end.strftime("%d.%m.%Y"),
            prev_start_str=prev_start.strftime("%d.%m.%Y"),
            prev_end_str=prev_end.strftime("%d.%m.%Y"),
            current_avg=curr_avg,
            prev_avg=prev_avg,
            avg_diff=diff,
            current_count=curr_count,
            prev_count=prev_count,
            current_top_count=curr_top,
            prev_top_count=prev_top,
            direction=direction,
            message_kids=msg_kids,
            message_teens=msg_teens,
            message_youth=msg_youth,
        )

    def calculate_metrics(self) -> StudentMetrics:
        """Główna metoda wyliczająca wskaźniki dla szablonów ucznia."""
        all_grades = self._parsed_grades
        period_grades = self._filter_grades_by_period()

        total_count = len(all_grades)
        period_count = len(period_grades)

        # Średnia ważona ogólna
        total_w_sum = sum(g["numeric_grade"] * g["weight"] for g in all_grades)
        total_w = sum(g["weight"] for g in all_grades)
        overall_avg = round(total_w_sum / total_w, 2) if total_w > 0 else 0.0

        # Grupowanie po przedmiotach
        by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for g in all_grades:
            by_subject[g["subject"]].append(g)

        subject_avgs = {}
        for subj, s_grades in by_subject.items():
            w_sum = sum(g["numeric_grade"] * g["weight"] for g in s_grades)
            w = sum(g["weight"] for g in s_grades)
            if w > 0:
                subject_avgs[subj] = round(w_sum / w, 2)

        # 1. Supermoce (strengths)
        strengths = self._calculate_strengths(by_subject, subject_avgs)

        # 2. Szybkie punkty (quick_wins)
        quick_wins = self._calculate_quick_wins(by_subject, subject_avgs)

        # 3. Obszary uwagi (focus_areas)
        focus_areas = self._calculate_focus_areas(by_subject, subject_avgs)

        # 4. Passa (streak) i trend
        streak_count = self._calculate_streak(all_grades)
        trend, trend_desc = self._calculate_trend(all_grades)

        # 5. Osiągnięcia (achievements)
        achievements = self._calculate_achievements(all_grades, streak_count, subject_avgs)

        # 6. Przyjazna lista ocen
        grades_to_show = period_grades if self.days else all_grades
        recent_grades = self._format_recent_grades(grades_to_show)

        # 7. Zakres analizowanego okresu
        period_end = self.reference_date
        period_end_str = period_end.strftime("%d.%m.%Y")
        if self.days:
            period_start = self.reference_date - timedelta(days=self.days)
            period_start_str = period_start.strftime("%d.%m.%Y")
            period_days = self.days
            period_desc = f"ostatnie {self.days} dni ({period_start_str} – {period_end_str})"
        else:
            dates = [g["date"] for g in all_grades if g["date"]]
            min_date = min(dates) if dates else None
            period_start_str = min_date.strftime("%d.%m.%Y") if min_date else "Początek roku"
            period_days = None
            period_desc = f"cały okres ({period_start_str} – {period_end_str})" if min_date else f"stan na {period_end_str}"

        # 8. Porównanie z poprzednim okresem (okres do okresu)
        period_comparison = self._calculate_period_comparison(period_grades)

        # 9. Droga do Czerwonego Paska (Świadectwo z Wyróżnieniem, próg 4.75)
        honor_roll = self._calculate_honor_roll(overall_avg, subject_avgs)

        return StudentMetrics(
            student_name=self.student_name,
            total_grades_count=total_count,
            period_grades_count=period_count,
            overall_avg=overall_avg,
            trend=trend,
            trend_description=trend_desc,
            streak_count=streak_count,
            strengths=strengths,
            quick_wins=quick_wins,
            focus_areas=focus_areas,
            achievements=achievements,
            recent_grades=recent_grades,
            period_start_str=period_start_str,
            period_end_str=period_end_str,
            period_desc=period_desc,
            period_days=period_days,
            period_comparison=period_comparison,
            honor_roll=honor_roll,
        )

    def _calculate_honor_roll(
        self,
        overall_avg: float,
        subject_avgs: dict[str, float],
    ) -> HonorRollProgress:
        """Kalkulator drogi do świadectwa z wyróżnieniem (Czerwony Pasek, próg 4.75)."""
        if not subject_avgs or overall_avg <= 0.0:
            return HonorRollProgress(
                current_avg=overall_avg,
                progress_pct=0,
                status="target",
                headline="🎯 Droga do Czerwonego Paska",
                description="Zbieraj pierwsze oceny w tym semestrze, aby uruchomić kalkulator paska!",
            )

        grade_thresholds = [
            (2, 1.75),
            (3, 2.75),
            (4, 3.75),
            (5, 4.75),
            (6, 5.75),
        ]

        has_failing = any(avg < 1.75 for avg in subject_avgs.values())

        # Znajdź szanse (najmniejszy dystans do kolejnej wyższej oceny)
        opportunities: list[HonorRollTarget] = []
        for subj, avg in subject_avgs.items():
            curr_grade = 1
            for g_val, thresh in grade_thresholds:
                if avg >= thresh:
                    curr_grade = g_val

            if curr_grade < 6:
                next_grade = curr_grade + 1
                next_thresh = [thresh for g_val, thresh in grade_thresholds if g_val == next_grade][0]
                dist = round(next_thresh - avg, 2)
                if 0.0 < dist <= 0.60:
                    hint = f"Jedna dobra ocena (5 lub 6) podniesie średnią z {subj} na ocenę {next_grade}."
                    opportunities.append(HonorRollTarget(
                        subject=subj,
                        current_avg=avg,
                        target_grade=next_grade,
                        gap_to_target=dist,
                        hint=hint,
                    ))

        opportunities.sort(key=lambda o: o.gap_to_target)
        top_opps = opportunities[:3]

        if overall_avg >= 4.75 and not has_failing:
            return HonorRollProgress(
                current_avg=overall_avg,
                target_avg=4.75,
                gap=0.0,
                progress_pct=100,
                status="achieved",
                has_failing=False,
                next_milestone_name="Czerwony Pasek (4.75)",
                next_milestone_gap=0.0,
                headline="🏆 Średnia na Czerwony Pasek!",
                description=(
                    f"Twoja aktualna średnia to {overall_avg:.2f} (wymagane min. 4.75). "
                    "Znakomita forma! Utrzymuj tę dyspozycję i pilnuj stabilności do końca semestru."
                ),
                opportunities=top_opps,
            )

        gap = round(max(0.0, 4.75 - overall_avg), 2)
        progress_pct = min(99, max(1, int(((overall_avg - 1.0) / (4.75 - 1.0)) * 100)))

        if overall_avg >= 4.30:
            status = "near"
            next_name = "Czerwony Pasek (4.75)"
            next_gap = gap
            headline = f"🎯 Pasek na wyciągnięcie ręki! Brakuje tylko {gap:.2f} pkt"
            description = (
                f"Twoja średnia wynosi {overall_avg:.2f}. Jesteś bardzo blisko paska! "
                "Skup się na 1–2 przedmiotach z listy poniżej, by wskoczyć na poziom 4.75."
            )
        else:
            status = "milestone"
            if overall_avg < 3.50:
                milestone_target = 3.75
                next_name = "Mocna Czwórka (3.75)"
            elif overall_avg < 4.00:
                milestone_target = 4.00
                next_name = "Średnia 4.00"
            else:
                milestone_target = 4.30
                next_name = "Średnia 4.30 (baza pod pasek)"

            next_gap = round(max(0.0, milestone_target - overall_avg), 2)
            headline = f"🚀 Droga do Czerwonego Paska ({progress_pct}% celu)"
            description = (
                f"Twoja obecna średnia to {overall_avg:.2f}. Do paska brakuje {gap:.2f} pkt, "
                f"a Twój najbliższy osiągalny cel to {next_name} (brakuje tylko {next_gap:.2f} pkt). "
                "Krok po kroku do przodu!"
            )

        return HonorRollProgress(
            current_avg=overall_avg,
            target_avg=4.75,
            gap=gap,
            progress_pct=progress_pct,
            status=status,
            has_failing=has_failing,
            next_milestone_name=next_name,
            next_milestone_gap=next_gap,
            headline=headline,
            description=description,
            opportunities=top_opps,
        )

    def _calculate_strengths(
        self,
        by_subject: dict[str, list[dict[str, Any]]],
        subject_avgs: dict[str, float],
    ) -> list[SubjectStrength]:
        strengths = []
        sorted_subjs = sorted(subject_avgs.items(), key=lambda item: item[1], reverse=True)

        for subj, avg in sorted_subjs:
            if avg < 4.0:
                continue
            s_grades = by_subject[subj]
            top_count = sum(1 for g in s_grades if g["numeric_grade"] >= 5.0)

            if avg >= 4.75:
                highlight = "Rewelacyjna forma! Ocena celująca lub bardzo dobra w zasięgu ręki."
            elif avg >= 4.5:
                highlight = "Mocna piątka! Trzymasz świetny poziom."
            else:
                highlight = "Bardzo stabilny, solidny wynik."

            strengths.append(SubjectStrength(
                subject=subj,
                avg=avg,
                top_grades_count=top_count,
                highlight=highlight,
            ))
            if len(strengths) >= 3:
                break
        return strengths

    def _calculate_quick_wins(
        self,
        by_subject: dict[str, list[dict[str, Any]]],
        subject_avgs: dict[str, float],
    ) -> list[QuickWin]:
        """Znajduje przedmioty, gdzie minimalny wysiłek podnosi ocenę o stopień wyżej."""
        wins = []
        # Progi ocen: 2 -> 1.75, 3 -> 2.75, 4 -> 3.75, 5 -> 4.75
        thresholds = [
            (5, 4.75, 4.40),  # cel 5, próg 4.75, badamy zakres 4.40-4.74
            (4, 3.75, 3.40),  # cel 4, próg 3.75, badamy zakres 3.40-3.74
            (3, 2.75, 2.40),  # cel 3, próg 2.75, badamy zakres 2.40-2.74
        ]

        for subj, avg in subject_avgs.items():
            s_grades = by_subject[subj]
            w_sum = sum(g["numeric_grade"] * g["weight"] for g in s_grades)
            w_total = sum(g["weight"] for g in s_grades)
            if w_total == 0:
                continue

            for target_grade, threshold, min_range in thresholds:
                if min_range <= avg < threshold:
                    # Sprawdźmy czy jedna ocena (np. 5 waga 2 lub 5 waga 1) przeskakuje próg
                    for possible_grade in [5, 4]:
                        for test_weight in [1, 2]:
                            new_avg = (w_sum + possible_grade * test_weight) / (w_total + test_weight)
                            if new_avg >= threshold:
                                w_label = "kartkówki" if test_weight == 1 else "odpowiedzi / sprawdzianu"
                                hint = (
                                    f"Brakuje Ci tylko odrobiny do oceny {target_grade}! "
                                    f"Jedna {possible_grade} z {w_label} (waga {test_weight}) "
                                    f"podniesie Twoją średnią na {new_avg:.2f}."
                                )
                                wins.append(QuickWin(
                                    subject=subj,
                                    current_avg=avg,
                                    target_grade=target_grade,
                                    needed_grade=possible_grade,
                                    needed_weight=test_weight,
                                    hint=hint,
                                ))
                                break
                        if any(w.subject == subj for w in wins):
                            break
                if any(w.subject == subj for w in wins):
                    break

        # Sortuj po najmniejszej różnicy do progu
        wins.sort(key=lambda w: w.target_grade, reverse=True)
        return wins[:3]

    def _calculate_focus_areas(
        self,
        by_subject: dict[str, list[dict[str, Any]]],
        subject_avgs: dict[str, float],
    ) -> list[FocusArea]:
        """Identyfikuje 1-2 przedmioty, w których warto powtórzyć materiał."""
        areas = []
        sorted_low = sorted(subject_avgs.items(), key=lambda item: item[1])

        for subj, avg in sorted_low:
            if avg >= 3.75:
                # Jeśli uczeń ze wszystkiego ma powyżej 3.75, nie ma palących zagrożeń
                continue

            s_grades = by_subject[subj]
            # Ostatnia niska ocena
            low_grades = [g for g in s_grades if g["numeric_grade"] <= 2.5]
            last_low = f"{low_grades[0]['raw_grade']} ({low_grades[0]['category']})" if low_grades else None

            if avg < 2.5:
                hint = "Warto zapytać nauczyciela o możliwość poprawy lub dodatkowej pracy. Każdy mały krok pomoże!"
            elif avg < 3.0:
                hint = "Przyda się spokojna powtórka przed kolejną kartkówką, aby zabezpieczyć stabilną trójkę."
            else:
                hint = "Niewiele brakuje do pewnej czwórki. Skup się na najbliższym temacie!"

            areas.append(FocusArea(
                subject=subj,
                avg=avg,
                last_low_grade=last_low,
                hint=hint,
            ))
            if len(areas) >= 2:
                break
        return areas

    def _calculate_streak(self, all_grades: list[dict[str, Any]]) -> int:
        """Liczy ile ostatnich ocen z rzędu to oceny pozytywne (>= 4.0)."""
        streak = 0
        for g in all_grades:
            if g["numeric_grade"] >= 4.0:
                streak += 1
            else:
                break
        return streak

    def _calculate_trend(self, all_grades: list[dict[str, Any]]) -> tuple[str, str]:
        """Porównuje średnią ostatnich 5 ocen ze średnią wcześniejszych ocen."""
        if len(all_grades) < 4:
            return "stable", "Zbierasz pierwsze oceny – dobra robota na start!"

        recent = all_grades[:5]
        older = all_grades[5:15] if len(all_grades) >= 10 else all_grades[5:]

        recent_avg = sum(g["numeric_grade"] for g in recent) / len(recent)
        older_avg = sum(g["numeric_grade"] for g in older) / len(older) if older else recent_avg

        diff = round(recent_avg - older_avg, 2)
        if diff >= 0.35:
            return "up", f"Świetna forma! Twoje ostatnie oceny są wyższe o {diff:.2f} niż wcześniej. Tak trzymaj! 🚀"
        elif diff <= -0.35:
            return "down", f"Mała zadyszka (spadek o {abs(diff):.2f}). Warto chwilę odpocząć i powtórzyć materiał. Dasz radę! 💪"
        else:
            return "stable", "Równa, stabilna forma. Trzymasz solidne tempo! 🎯"

    def _calculate_achievements(
        self,
        all_grades: list[dict[str, Any]],
        streak_count: int,
        subject_avgs: dict[str, float],
    ) -> list[StudentAchievement]:
        """Przyznaje motywacyjne odznaki za postępy i dobre wyniki."""
        badges = []

        # 1. Odznaka: Dobra Passa
        if streak_count >= 3:
            badges.append(StudentAchievement(
                id="streak",
                title="Dobra Passa!",
                icon="🔥",
                description=f"{streak_count} oceny z rzędu z notą 4 lub wyższą.",
            ))

        # 2. Odznaka: Snajper (ocena 5 lub 6 ze sprawdzianu waga >= 2)
        top_exams = [g for g in all_grades if g["numeric_grade"] >= 5.0 and g["weight"] >= 2]
        if top_exams:
            badges.append(StudentAchievement(
                id="sniper",
                title="Snajper Sprawdzianów",
                icon="🎯",
                description=f"Świetny wynik ({top_exams[0]['raw_grade']}) z ważnego sprawdzianu z przedmiotu {top_exams[0]['subject']}.",
            ))

        # 3. Odznaka: Lider Przedmiotu (średnia >= 4.8)
        top_subj = [s for s, a in subject_avgs.items() if a >= 4.8]
        if top_subj:
            badges.append(StudentAchievement(
                id="master",
                title="Mistrzowski Poziom",
                icon="👑",
                description=f"Średnia {subject_avgs[top_subj[0]]:.2f} z przedmiotu {top_subj[0]}.",
            ))

        # 4. Odznaka: Aktywny Uczeń (zdobyte minimum 5 ocen)
        if len(all_grades) >= 5:
            badges.append(StudentAchievement(
                id="active",
                title="W Rytmie Nauki",
                icon="⚡",
                description="Regularna nauka i zbieranie kolejnych punktów w e-dzienniku.",
            ))

        return badges

    def _format_recent_grades(self, grades: list[dict[str, Any]]) -> list[dict[str, Any]]:
        formatted = []
        for g in grades:
            w = g["weight"]
            if w >= 3:
                w_label = "Waga bardzo duża (sprawdzian)"
                w_badge = "important"
            elif w == 2:
                w_label = "Waga średnia (kartkówka/odpowiedź)"
                w_badge = "medium"
            else:
                w_label = "Waga standardowa"
                w_badge = "normal"

            dt_str = g["date"].strftime("%d.%m.%Y") if g["date"] else "Brak daty"
            formatted.append({
                "subject": g["subject"],
                "grade": g["raw_grade"],
                "numeric": g["numeric_grade"],
                "date_str": dt_str,
                "date": g["date"],
                "category": g["category"] or "Ocena bieżąca",
                "comment": g.get("comment", ""),
                "teacher": g.get("teacher", ""),
                "weight": w,
                "weight_label": w_label,
                "weight_badge": w_badge,
            })
        return formatted
