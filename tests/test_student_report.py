"""Tests for Student Motivational Report module (librus2mail.student_analyzer and student_report)."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from librus2mail.mail_sender import MailSender
from librus2mail.student_analyzer import (
    FocusArea,
    HonorRollProgress,
    HonorRollTarget,
    PeriodComparison,
    QuickWin,
    StudentAchievement,
    StudentAnalyzer,
    StudentMetrics,
    SubjectStrength,
)
from librus2mail.student_report import main as student_report_main
from librus2mail.student_report import run_student_reports


class TestStudentAnalyzer(unittest.TestCase):
    """Test the analytical calculations and metrics for student reports."""

    def setUp(self):
        self.mock_grades = [
            {
                "id": "1",
                "subject": "Matematyka",
                "grade": "5",
                "date": "2026-09-10",
                "category": "Sprawdzian",
                "weight": "3",
            },
            {
                "id": "2",
                "subject": "Matematyka",
                "grade": "5-",
                "date": "2026-09-12",
                "category": "Kartkówka",
                "weight": "1",
            },
            {
                "id": "3",
                "subject": "Język polski",
                "grade": "4+",
                "date": "2026-09-14",
                "category": "Wypracowanie",
                "weight": "2",
            },
            {
                "id": "4",
                "subject": "Język angielski",
                "grade": "6",
                "date": "2026-09-15",
                "category": "Odpowiedź",
                "weight": "1",
            },
            {
                "id": "5",
                "subject": "Historia",
                "grade": "2",
                "date": "2026-09-16",
                "category": "Sprawdzian",
                "weight": "3",
            },
            {
                "id": "6",
                "subject": "Historia",
                "grade": "3",
                "date": "2026-09-17",
                "category": "Kartkówka",
                "weight": "1",
            },
        ]

    def test_empty_grades(self):
        analyzer = StudentAnalyzer(grades=[], student_name="Kacper")
        metrics = analyzer.calculate_metrics()
        self.assertEqual(metrics.student_name, "Kacper")
        self.assertEqual(metrics.overall_avg, 0.0)
        self.assertEqual(metrics.total_grades_count, 0)
        self.assertEqual(len(metrics.strengths), 0)
        self.assertEqual(len(metrics.quick_wins), 0)
        self.assertEqual(len(metrics.achievements), 0)

    def test_metrics_calculation(self):
        analyzer = StudentAnalyzer(
            grades=self.mock_grades,
            student_name="Kacper",
            actual_date="2026-09-18",
        )
        metrics = analyzer.calculate_metrics()

        self.assertIsNotNone(metrics.overall_avg)
        self.assertGreater(metrics.overall_avg, 3.5)
        self.assertEqual(metrics.total_grades_count, 6)

        # Angielski has grade 6 (avg 6.0), Matematyka has 5 & 5- (avg ~4.94) -> should be strengths
        strength_subjects = [s.subject for s in metrics.strengths]
        self.assertIn("Język angielski", strength_subjects)

        # Historia has 2 & 3 (avg 2.25) -> should be a focus area
        focus_subjects = [f.subject for f in metrics.focus_areas]
        self.assertIn("Historia", focus_subjects)

        # Achievements should be granted
        self.assertGreater(len(metrics.achievements), 0)
        titles = [a.title for a in metrics.achievements]
        self.assertTrue(any("Orzeł" in t or "Mistrz" in t or "Start" in t or "Dobra passa" in t for t in titles))

    def test_quick_wins_detection(self):
        # Create a grade profile where average is just below a threshold (e.g. 4.60)
        borderline_grades = [
            {"id": "1", "subject": "Geografia", "grade": "5", "date": "2026-09-10", "weight": "2"},
            {"id": "2", "subject": "Geografia", "grade": "4", "date": "2026-09-12", "weight": "1"},
            # weighted avg: (5*2 + 4*1) / 3 = 14 / 3 = 4.67 (near 5)
        ]
        analyzer = StudentAnalyzer(grades=borderline_grades, student_name="Zosia")
        metrics = analyzer.calculate_metrics()
        self.assertTrue(any(qw.subject == "Geografia" for qw in metrics.quick_wins))

    def test_days_filtering(self):
        analyzer = StudentAnalyzer(
            grades=self.mock_grades,
            student_name="Kacper",
            actual_date="2026-09-18",
            days=3,  # Only grades from 2026-09-15 onwards
        )
        metrics = analyzer.calculate_metrics()
        # Only grades from 2026-09-15 to 2026-09-18 (grades 4, 5, 6) should be in recent_grades
        self.assertLessEqual(len(metrics.recent_grades), 3)
        self.assertEqual(metrics.period_start_str, "15.09.2026")
        self.assertEqual(metrics.period_end_str, "18.09.2026")
        self.assertEqual(metrics.period_days, 3)

    def test_period_comparison_up(self):
        grades = [
            # current period (11.09 - 18.09) -> high grades
            {"id": "1", "subject": "Matematyka", "grade": "5", "date": "2026-09-17", "weight": "2"},
            {"id": "2", "subject": "Fizyka", "grade": "5", "date": "2026-09-16", "weight": "2"},
            # previous period (04.09 - 11.09) -> lower grades
            {"id": "3", "subject": "Matematyka", "grade": "3", "date": "2026-09-08", "weight": "2"},
            {"id": "4", "subject": "Fizyka", "grade": "4", "date": "2026-09-07", "weight": "2"},
        ]
        analyzer = StudentAnalyzer(
            grades=grades,
            student_name="Tymon",
            actual_date="2026-09-18",
            days=7,
        )
        metrics = analyzer.calculate_metrics()
        pc = metrics.period_comparison
        self.assertIsNotNone(pc)
        self.assertTrue(pc.has_comparison)
        self.assertTrue(pc.has_prev_data)
        self.assertEqual(pc.current_avg, 5.0)
        self.assertEqual(pc.prev_avg, 3.5)
        self.assertEqual(pc.avg_diff, 1.5)
        self.assertEqual(pc.direction, "up")
        self.assertIn("Level Up", pc.message_kids)
        self.assertIn("Pozytywne momentum", pc.message_teens)

    def test_period_comparison_down(self):
        grades = [
            # current period (11.09 - 18.09) -> lower grades
            {"id": "1", "subject": "Matematyka", "grade": "3", "date": "2026-09-17", "weight": "2"},
            # previous period (04.09 - 11.09) -> high grades
            {"id": "2", "subject": "Matematyka", "grade": "5", "date": "2026-09-08", "weight": "2"},
        ]
        analyzer = StudentAnalyzer(
            grades=grades,
            student_name="Tymon",
            actual_date="2026-09-18",
            days=7,
        )
        metrics = analyzer.calculate_metrics()
        pc = metrics.period_comparison
        self.assertIsNotNone(pc)
        self.assertEqual(pc.direction, "down")
        self.assertEqual(pc.avg_diff, -2.0)
        self.assertIn("Chwilowa zadyszka", pc.message_kids)

    def test_period_comparison_no_prev_data(self):
        grades = [
            {"id": "1", "subject": "Matematyka", "grade": "5", "date": "2026-09-17", "weight": "2"},
        ]
        analyzer = StudentAnalyzer(
            grades=grades,
            student_name="Tymon",
            actual_date="2026-09-18",
            days=7,
        )
        metrics = analyzer.calculate_metrics()
        pc = metrics.period_comparison
        self.assertIsNotNone(pc)
        self.assertTrue(pc.has_comparison)
        self.assertFalse(pc.has_prev_data)
        self.assertEqual(pc.direction, "none")
        self.assertIn("punkt startowy", pc.message_kids)

    def test_period_comparison_disabled_without_days(self):
        analyzer = StudentAnalyzer(
            grades=self.mock_grades,
            student_name="Tymon",
            actual_date="2026-09-18",
            days=None,
        )
        metrics = analyzer.calculate_metrics()
        self.assertIsNotNone(metrics.period_comparison)
        self.assertFalse(metrics.period_comparison.has_comparison)

    def test_teacher_comments_cleaned(self):
        grades_with_comments = [
            {
                "id": "1",
                "subject": "Matematyka",
                "grade": "5",
                "date": "2026-09-10",
                "category": "Sprawdzian",
                "weight": "3",
                "comment": "Bardzo ładna praca",
                "teacher": "Jan Kowalski",
            },
            {
                "id": "2",
                "subject": "Fizyka",
                "grade": "4",
                "date": "2026-09-12",
                "category": "Kartkówka",
                "weight": "1",
                "comment": "-",
                "teacher": "-",
            },
        ]
        analyzer = StudentAnalyzer(grades=grades_with_comments, student_name="Kacper")
        metrics = analyzer.calculate_metrics()
        self.assertEqual(metrics.recent_grades[1]["comment"], "Bardzo ładna praca")
        self.assertEqual(metrics.recent_grades[1]["teacher"], "Jan Kowalski")
        self.assertEqual(metrics.recent_grades[0]["comment"], "")
        self.assertEqual(metrics.recent_grades[0]["teacher"], "")

    def test_honor_roll_achieved(self):
        high_grades = [
            {"id": "1", "subject": "Matematyka", "grade": "5", "date": "2026-09-10", "weight": "2"},
            {"id": "2", "subject": "Język polski", "grade": "5", "date": "2026-09-12", "weight": "2"},
            {"id": "3", "subject": "Historia", "grade": "5", "date": "2026-09-14", "weight": "2"},
        ]
        analyzer = StudentAnalyzer(grades=high_grades, student_name="Kacper")
        metrics = analyzer.calculate_metrics()
        hr = metrics.honor_roll
        self.assertIsNotNone(hr)
        self.assertEqual(hr.status, "achieved")
        self.assertEqual(hr.current_avg, 5.0)
        self.assertEqual(hr.gap, 0.0)
        self.assertEqual(hr.progress_pct, 100)
        self.assertFalse(hr.has_failing)
        self.assertIn("Średnia na Czerwony Pasek", hr.headline)

    def test_honor_roll_near(self):
        near_grades = [
            {"id": "1", "subject": "Matematyka", "grade": "4", "date": "2026-09-10", "weight": "1"},
            {"id": "2", "subject": "Język polski", "grade": "5", "date": "2026-09-12", "weight": "1"},
        ]
        # Avg = 4.50 -> near
        analyzer = StudentAnalyzer(grades=near_grades, student_name="Kacper")
        metrics = analyzer.calculate_metrics()
        hr = metrics.honor_roll
        self.assertIsNotNone(hr)
        self.assertEqual(hr.status, "near")
        self.assertEqual(hr.current_avg, 4.50)
        self.assertEqual(hr.gap, 0.25)
        self.assertGreater(hr.progress_pct, 90)
        self.assertIn("wyciągnięcie ręki", hr.headline)
        # Matematyka avg is 4.0, threshold to 5 is 4.75, dist = 0.75 > 0.60
        # If we had a grade 4+ (4.50), dist to 4.75 is 0.25 <= 0.60
        self.assertTrue(hr.target_avg == 4.75)

    def test_honor_roll_milestone(self):
        lower_grades = [
            {"id": "1", "subject": "Matematyka", "grade": "3", "date": "2026-09-10", "weight": "2"},
            {"id": "2", "subject": "Język polski", "grade": "3", "date": "2026-09-12", "weight": "2"},
        ]
        analyzer = StudentAnalyzer(grades=lower_grades, student_name="Kacper")
        metrics = analyzer.calculate_metrics()
        hr = metrics.honor_roll
        self.assertIsNotNone(hr)
        self.assertEqual(hr.status, "milestone")
        self.assertEqual(hr.current_avg, 3.0)
        self.assertEqual(hr.next_milestone_name, "Mocna Czwórka (3.75)")
        self.assertEqual(hr.next_milestone_gap, 0.75)
        self.assertIn("Krok po kroku", hr.description)

    def test_honor_roll_opportunities_detection(self):
        # Przedmiot blisko progu wyższej oceny (np. 4.60 -> do 5 (4.75) brakuje 0.15 <= 0.60)
        opp_grades = [
            {"id": "1", "subject": "Geografia", "grade": "5", "date": "2026-09-10", "weight": "2"},
            {"id": "2", "subject": "Geografia", "grade": "4", "date": "2026-09-12", "weight": "1"},
            # weighted avg: 14/3 = 4.67 -> next threshold is 5 (4.75), gap = 0.08
        ]
        analyzer = StudentAnalyzer(grades=opp_grades, student_name="Kacper")
        metrics = analyzer.calculate_metrics()
        hr = metrics.honor_roll
        self.assertIsNotNone(hr)
        self.assertTrue(any(opp.subject == "Geografia" and opp.target_grade == 5 for opp in hr.opportunities))


class TestStudentReportTemplates(unittest.TestCase):
    """Test rendering of all 3 student report templates."""

    def setUp(self):
        self.metrics = StudentMetrics(
            student_name="Tymon",
            overall_avg=4.75,
            total_grades_count=12,
            period_grades_count=4,
            trend="up",
            trend_description="Forma rośnie! Znakomity tydzień.",
            streak_count=3,
            strengths=[
                SubjectStrength(subject="Informatyka", avg=5.50, top_grades_count=2, highlight="Mistrzowski poziom!"),
                SubjectStrength(subject="Matematyka", avg=4.90, top_grades_count=3, highlight="Świetna seria ocen"),
            ],
            quick_wins=[
                QuickWin(
                    subject="Język polski",
                    current_avg=4.65,
                    target_grade=5,
                    needed_grade=5,
                    needed_weight=1,
                    hint="Brakuje zaledwie 0.10 do mocnej 5!",
                )
            ],
            focus_areas=[
                FocusArea(
                    subject="Historia",
                    avg=3.20,
                    last_low_grade="2",
                    hint="Warto przejrzeć ostatnie notatki z lekcji.",
                )
            ],
            achievements=[
                StudentAchievement(
                    id="ace",
                    title="As Przestworzy",
                    icon="🚀",
                    description="Zdobyłeś najwyższą ocenę (6)!",
                )
            ],
            recent_grades=[
                {
                    "subject": "Informatyka",
                    "grade": "6",
                    "date": "2026-09-18",
                    "date_str": "18.09.2026",
                    "category": "Projekt",
                    "comment": "Wzorowe wykonanie",
                    "teacher": "Jan Nauczyciel",
                    "weight": "3",
                    "weight_label": "Waga bardzo duża (sprawdzian)",
                    "weight_badge": "important",
                    "is_high": True,
                    "is_low": False,
                }
            ],
            period_start_str="11.09.2026",
            period_end_str="18.09.2026",
            period_desc="ostatnie 7 dni (11.09.2026 – 18.09.2026)",
            period_days=7,
            period_comparison=PeriodComparison(
                has_comparison=True,
                has_prev_data=True,
                current_start_str="11.09.2026",
                current_end_str="18.09.2026",
                prev_start_str="04.09.2026",
                prev_end_str="11.09.2026",
                current_avg=5.0,
                prev_avg=4.33,
                avg_diff=0.67,
                current_count=1,
                prev_count=3,
                current_top_count=1,
                prev_top_count=1,
                direction="up",
                message_kids="Level Up! Twoja forma rośnie!",
                message_teens="Pozytywne momentum! Średnia wzrosła o +0.67 pkt.",
                message_youth="Wzrost dynamiki formy: średnia ważona wzrosła o +0.67 pkt.",
            ),
            honor_roll=HonorRollProgress(
                current_avg=4.75,
                target_avg=4.75,
                gap=0.0,
                progress_pct=100,
                status="achieved",
                has_failing=False,
                next_milestone_name="Czerwony Pasek (4.75)",
                next_milestone_gap=0.0,
                headline="🏆 Średnia na Czerwony Pasek!",
                description="Twoja aktualna średnia to 4.75 (wymagane min. 4.75). Znakomita forma!",
                opportunities=[
                    HonorRollTarget(
                        subject="Matematyka",
                        current_avg=4.90,
                        target_grade=5,
                        gap_to_target=0.10,
                        hint="Jedna dobra ocena podniesie średnią.",
                    )
                ],
            ),
        )

    def test_render_kids_template(self):
        html = MailSender.create_mail_content_for_student_report(
            metrics=self.metrics,
            template_type="kids",
        )
        self.assertIn("KARTA MOCY", html)
        self.assertIn("Tymon", html)
        self.assertIn("Supermoce", html)
        self.assertIn("Informatyka", html)
        self.assertIn("As Przestworzy", html)
        self.assertIn("11.09.2026", html)
        self.assertIn("18.09.2026", html)
        self.assertIn("Wzorowe wykonanie", html)
        self.assertIn("Jan Nauczyciel", html)
        self.assertIn("Radar Formy", html)
        self.assertIn("Czerwony Pasek", html)
        self.assertIn("100% celu", html)

    def test_render_teens_template(self):
        html = MailSender.create_mail_content_for_student_report(
            metrics=self.metrics,
            template_type="teens",
        )
        self.assertIn("WEEKLY BRIEFING", html)
        self.assertIn("Tymon", html)
        self.assertIn("Mocne Filary", html)
        self.assertIn("Szybkie Punkty", html)
        self.assertIn("Informatyka", html)
        self.assertIn("11.09.2026", html)
        self.assertIn("18.09.2026", html)
        self.assertIn("Wzorowe wykonanie", html)
        self.assertIn("Jan Nauczyciel", html)
        self.assertIn("WEEKLY MOMENTUM", html)
        self.assertIn("CEL: ŚWIADECTWO Z WYRÓŻNIENIEM", html)
        self.assertIn("100% celu", html)

    def test_render_youth_template(self):
        html = MailSender.create_mail_content_for_student_report(
            metrics=self.metrics,
            template_type="youth",
        )
        self.assertIn("STUDENT PERFORMANCE DASHBOARD", html)
        self.assertIn("Tymon", html)
        self.assertIn("Stabilne Filary", html)
        self.assertIn("Rekomendacje Celowe", html)
        self.assertIn("Informatyka", html)
        self.assertIn("11.09.2026", html)
        self.assertIn("18.09.2026", html)
        self.assertIn("Wzorowe wykonanie", html)
        self.assertIn("Jan Nauczyciel", html)
        self.assertIn("Zestawienie Cyklu", html)
        self.assertIn("Target: Wyróżnienie Semestralne", html)
        self.assertIn("Realizacja: 100%", html)

    def test_render_templates_with_timetable(self):
        mock_timetable = {
            "has_any": True,
            "immediate_label": "Jutro (poniedziałek, 21.09)",
            "immediate_tests": [
                {
                    "category": "Sprawdzian",
                    "subject": "Historia",
                    "lesson_no": "2",
                    "description": "Starożytność",
                    "teacher": "A. Nowak",
                }
            ],
            "immediate_absences": [],
            "upcoming_days": [
                {
                    "date": "2026-09-23",
                    "date_str": "23.09.2026",
                    "weekday": "Środa",
                    "tests": [
                        {
                            "category": "Kartkówka",
                            "subject": "Język angielski",
                            "lesson_no": "5",
                            "description": "Słówka",
                            "teacher": "M. Kiljańczyk",
                        }
                    ],
                }
            ],
        }

        # 1. Kids
        html_kids = MailSender.create_mail_content_for_student_report(
            metrics=self.metrics,
            template_type="kids",
            timetable=mock_timetable,
        )
        self.assertIn("Nadchodzące Wyzwania", html_kids)
        self.assertIn("Historia", html_kids)
        self.assertIn("Starożytność", html_kids)
        self.assertIn("Język angielski", html_kids)
        self.assertIn("Słówka", html_kids)

        # 2. Teens
        html_teens = MailSender.create_mail_content_for_student_report(
            metrics=self.metrics,
            template_type="teens",
            timetable=mock_timetable,
        )
        self.assertIn("Nadchodzące Sprawdziany i Kartkówki", html_teens)
        self.assertIn("Historia", html_teens)
        self.assertIn("Starożytność", html_teens)
        self.assertIn("Język angielski", html_teens)
        self.assertIn("Słówka", html_teens)

        # 3. Youth
        html_youth = MailSender.create_mail_content_for_student_report(
            metrics=self.metrics,
            template_type="youth",
            timetable=mock_timetable,
        )
        self.assertIn("Harmonogram Sprawdzianów i Kartkówek", html_youth)
        self.assertIn("Historia", html_youth)
        self.assertIn("Starożytność", html_youth)
        self.assertIn("Język angielski", html_youth)
        self.assertIn("Słówka", html_youth)

    def test_unknown_template_fallback_to_kids(self):
        html = MailSender.create_mail_content_for_student_report(
            metrics=self.metrics,
            template_type="non_existent",
        )
        self.assertIn("KARTA MOCY", html)

    def test_create_student_report_title(self):
        title_kids = MailSender.create_student_report_title(self.metrics, "kids")
        self.assertIn("Tymon", title_kids)
        self.assertIn("Karta Mocy", title_kids)

        title_teens = MailSender.create_student_report_title(self.metrics, "teens")
        self.assertIn("Tymon", title_teens)
        self.assertIn("Weekly Briefing", title_teens)

        title_youth = MailSender.create_student_report_title(self.metrics, "youth")
        self.assertIn("Tymon", title_youth)
        self.assertIn("Student Performance Dashboard", title_youth)


class TestStudentReportRunner(unittest.TestCase):
    """Test run_student_reports orchestrator and CLI flow."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage_dir = os.path.join(self.temp_dir.name, "storage")
        os.makedirs(self.storage_dir, exist_ok=True)

        # Create mock state with grades
        user_state = {
            "librus_login": "123456",
            "student_name": "Kamil Nowak",
            "grades_history": {
                "g1": {
                    "id": "g1",
                    "subject": "Matematyka",
                    "grade": "5",
                    "date": "2026-09-15",
                    "category": "Sprawdzian",
                    "weight": "3",
                },
                "g2": {
                    "id": "g2",
                    "subject": "Język polski",
                    "grade": "4",
                    "date": "2026-09-16",
                    "category": "Odpowiedź",
                    "weight": "1",
                },
            },
            "timetable_history": [
                {
                    "id": "t1",
                    "date": "2026-09-21",
                    "type": "test",
                    "category": "Sprawdzian",
                    "subject": "Fizyka",
                    "lesson_no": "2",
                    "description": "Dynamika Newtona",
                    "teacher": "P. Nowak",
                }
            ],
        }
        with open(os.path.join(self.storage_dir, "123456.json"), "w", encoding="utf-8") as f:
            json.dump(user_state, f)

        # Create mock config
        self.config_path = os.path.join(self.temp_dir.name, "config.yaml")
        config_content = f"""
storage_dir: "{self.storage_dir}"
storage_type: "FILES"
mail:
  login: "test@example.com"
  password: "secretpassword"
  use_gmail: false
  non_gmail_settings:
    smtp_host: "smtp.example.com"
    port: 587
librus_users:
  - librus_login: "123456"
    librus_login_name: "Kamil Nowak"
    student_report:
      enabled: true
      email: "kamil@example.com"
      template: "teens"
"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(config_content)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_run_student_reports_dry_run(self):
        results = run_student_reports(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            dry_run=True,
            actual_date="2026-09-18",
        )
        self.assertIn("123456", results)
        res = results["123456"]
        self.assertEqual(res["name"], "Kamil Nowak")
        self.assertEqual(res["template"], "teens")
        self.assertFalse(res["email_sent"])
        self.assertIsNotNone(res["metrics"].overall_avg)

    def test_run_student_reports_output_html(self):
        out_html = os.path.join(self.temp_dir.name, "output.html")
        results = run_student_reports(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            output_html=out_html,
            template_type="youth",
            actual_date="2026-09-18",
        )
        self.assertIn("123456", results)
        self.assertTrue(os.path.exists(out_html))
        with open(out_html, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Kamil Nowak", content)
        self.assertIn("STUDENT PERFORMANCE DASHBOARD", content)
        self.assertIn("Dynamika Newtona", content)

    def test_run_student_reports_template_override(self):
        results = run_student_reports(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            template_type="kids",
            dry_run=True,
            actual_date="2026-09-18",
        )
        self.assertIn("123456", results)
        self.assertEqual(results["123456"]["template"], "kids")

    def test_run_student_reports_disabled_when_not_in_config(self):
        # Create config with student_report: enabled: false
        disabled_config_path = os.path.join(self.temp_dir.name, "disabled_config.yaml")
        with open(disabled_config_path, "w", encoding="utf-8") as f:
            f.write(f"""
storage_dir: "{self.storage_dir}"
librus_users:
  - librus_login: "123456"
    librus_login_name: "Kamil Nowak"
    student_report:
      enabled: false
      email: "kamil@example.com"
""")
        results = run_student_reports(
            config_path=disabled_config_path,
            storage_dir=self.storage_dir,
        )
        self.assertEqual(len(results), 0)

    def test_run_student_reports_email_sending(self):
        mock_sender = MagicMock()
        mock_sender.send_student_report.return_value = True

        with patch("librus2mail.student_report.configure_mail_provider", return_value=mock_sender):
            results = run_student_reports(
                config_path=self.config_path,
                storage_dir=self.storage_dir,
                actual_date="2026-09-18",
            )
            self.assertIn("123456", results)
            self.assertTrue(results["123456"]["email_sent"])
            mock_sender.send_student_report.assert_called_once()
            args, kwargs = mock_sender.send_student_report.call_args
            self.assertIn("kamil@example.com", kwargs["receivers"])

    def test_run_student_reports_custom_storage_with_different_user(self):
        # Create a separate storage directory with a different student (e.g. 999999)
        custom_storage_dir = os.path.join(self.temp_dir.name, "custom_storage")
        os.makedirs(custom_storage_dir, exist_ok=True)
        custom_user_state = {
            "librus_login": "999999",
            "student_name": "Alicja Gwiazda",
            "grades_history": {
                "g1": {
                    "id": "g1",
                    "subject": "Biologia",
                    "grade": "6",
                    "date": "2026-09-15",
                    "category": "Sprawdzian",
                    "weight": "3",
                }
            },
        }
        with open(os.path.join(custom_storage_dir, "999999.json"), "w", encoding="utf-8") as f:
            json.dump(custom_user_state, f)

        # 1. Without -u: should automatically detect 999999 from custom_storage
        results_no_u = run_student_reports(
            config_path=self.config_path,  # contains only 123456
            storage_dir=custom_storage_dir,
            dry_run=True,
            actual_date="2026-09-18",
        )
        self.assertIn("999999", results_no_u)
        self.assertEqual(results_no_u["999999"]["name"], "Alicja Gwiazda")

        # 2. With -u 999999: should match student from custom_storage
        results_with_u = run_student_reports(
            config_path=self.config_path,
            storage_dir=custom_storage_dir,
            user_filter="999999",
            dry_run=True,
            actual_date="2026-09-18",
        )
        self.assertIn("999999", results_with_u)
        self.assertEqual(results_with_u["999999"]["name"], "Alicja Gwiazda")

    def test_cli_main_entrypoint(self):
        test_args = [
            "librus_student_report.py",
            "-c", self.config_path,
            "-s", self.storage_dir,
            "--dry-run",
            "--actual-date", "2026-09-18",
        ]
        with patch.object(sys, "argv", test_args):
            student_report_main()


if __name__ == "__main__":
    import sys
    unittest.main()
