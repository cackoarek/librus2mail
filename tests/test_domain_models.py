"""Testy jednostkowe obiektów domenowych (Grade, Message, Announcement, TimetableEntry, ScheduleLesson)."""

import tempfile
import unittest

from librus2mail.domain_models import (
    Announcement,
    AttendanceEntry,
    AttendancePeriodSummary,
    Grade,
    Message,
    Notification,
    ScheduleEntry,
    ScheduleLesson,
    TimetableEntry,
)
from librus2mail.progress_analyzer import ProgressAnalyzer
from librus2mail.storage import FileStorage
from librus2mail.student_analyzer import StudentAnalyzer


class TestDomainModels(unittest.TestCase):
    """Zestaw testów weryfikujących modele domenowe Librus2mail."""

    def test_grade_model_fields_and_properties(self):
        grade = Grade(
            id='12345',
            subject='Matematyka',
            grade='5+',
            category='Sprawdzian',
            date='2026-10-07',
            teacher='Jan Kowalski',
            weight='3',
            comment='Znakomita praca',
        )

        # Dostęp atrybutowy
        self.assertEqual(grade.id, '12345')
        self.assertEqual(grade.subject, 'Matematyka')
        self.assertEqual(grade.grade, '5+')
        self.assertEqual(grade.category, 'Sprawdzian')

        # Wyliczane właściwości pomocnicze
        self.assertEqual(grade.numeric_value, 5.5)
        self.assertEqual(grade.weight_value, 3.0)

        # Dostęp słownikowy (kompatybilność wsteczna)
        self.assertEqual(grade['subject'], 'Matematyka')
        self.assertEqual(grade.get('category'), 'Sprawdzian')
        self.assertEqual(grade.get('missing', 'default'), 'default')
        self.assertIn('grade', grade)

        # Rozpakowywanie i modyfikacja słownikowa
        grade['numeric_val'] = 5.5
        self.assertEqual(grade['numeric_val'], 5.5)
        unpacked = {**grade}
        self.assertEqual(unpacked['subject'], 'Matematyka')
        self.assertEqual(unpacked['numeric_val'], 5.5)

    def test_message_model_and_date_alias(self):
        # Tworzenie z 'datetime'
        msg1 = Message(
            id='m1',
            title='Zebranie z rodzicami',
            sender='Wychowawca Klasy',
            datetime='2026-10-07 16:30',
            has_attachment=True,
        )
        self.assertEqual(msg1.datetime, '2026-10-07 16:30')
        self.assertEqual(msg1.date, '2026-10-07 16:30')
        self.assertEqual(msg1['datetime'], '2026-10-07 16:30')
        self.assertEqual(msg1['date'], '2026-10-07 16:30')
        self.assertTrue(msg1.has_attachment)

        # Tworzenie z aliasem 'date'
        msg2 = Message.model_validate({
            'id': 'm2',
            'title': 'Wycieczka',
            'sender': 'Nauczyciel',
            'date': '2026-10-08 09:00',
        })
        self.assertEqual(msg2.datetime, '2026-10-08 09:00')
        self.assertEqual(msg2.date, '2026-10-08 09:00')

    def test_announcement_model_and_aliases(self):
        notif = Announcement.model_validate({
            'id': 'a1',
            'title': 'Dzień Nauczyciela',
            'author': 'Dyrekcja Szkoły',
            'date': '2026-10-14',
            'body': 'Uroczysty apel o 10:00',
        })
        self.assertEqual(notif.sender, 'Dyrekcja Szkoły')
        self.assertEqual(notif.author, 'Dyrekcja Szkoły')
        self.assertEqual(notif['author'], 'Dyrekcja Szkoły')
        self.assertEqual(notif['sender'], 'Dyrekcja Szkoły')
        self.assertEqual(notif.datetime, '2026-10-14')
        self.assertEqual(notif.date, '2026-10-14')
        self.assertIs(Notification, Announcement)

    def test_timetable_and_schedule_models(self):
        tt = TimetableEntry(
            id='tt1',
            date='2026-10-10',
            type='test',
            category='Kartkówka',
            subject='Fizyka',
            lesson_no='3',
        )
        self.assertEqual(tt.type, 'test')
        self.assertEqual(tt['category'], 'Kartkówka')

        lesson = ScheduleLesson(
            id='sched1',
            date='2026-10-10',
            lesson_no=1,
            time_from='08:00',
            time_to='08:45',
            subject='Język polski',
            is_substitution=True,
            substitution_info='s. 102',
        )
        self.assertEqual(lesson.lesson_no, 1)
        self.assertTrue(lesson.is_substitution)
        self.assertEqual(lesson['substitution_info'], 's. 102')
        self.assertIs(ScheduleEntry, ScheduleLesson)

    def test_storage_integration_with_domain_models(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = FileStorage(tmp_dir)
            user_login = '1234567'

            grades = [
                Grade(id='g1', subject='Historia', grade='5', weight='2', date='2026-10-01'),
                Grade(id='g2', subject='Geografia', grade='4', weight='1', date='2026-10-02'),
            ]
            storage.save_grades_details(user_login, grades)

            history = storage.get_grades_history(user_login)
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]['id'], 'g1')
            self.assertEqual(history[0]['subject'], 'Historia')

    def test_analyzers_with_grade_domain_models(self):
        grades = [
            Grade(id='g1', subject='Matematyka', grade='5', weight='2', date='2026-10-01'),
            Grade(id='g2', subject='Matematyka', grade='6', weight='3', date='2026-10-03'),
            Grade(id='g3', subject='Historia', grade='4', weight='1', date='2026-10-04'),
        ]

        # 1. ProgressAnalyzer
        progress = ProgressAnalyzer.analyze(grades)
        self.assertIn('distribution_overall', progress)
        self.assertIn('subjects', progress)

        # 2. StudentAnalyzer
        analyzer = StudentAnalyzer(grades=grades, student_name="Uczeń")
        student = analyzer.calculate_metrics()
        self.assertGreater(student.overall_avg, 4.0)
        self.assertTrue(len(student.achievements) > 0)

    def test_attendance_domain_models(self):
        entry = AttendanceEntry(
            id='5001',
            date='2026-10-21',
            lesson_no=1,
            subject='Język angielski',
            symbol='u',
            type='nieobecność uspr.',
            teacher='Jan Kowalski',
            topic='Unit 3 test',
            added_by='Jan Kowalski',
            is_trip=False,
            is_late=False,
            is_absence=True,
            is_justified=True,
            is_exempt=False,
            justification_info='e-Usprawiedliwienie',
            color='#2ECC71',
            period='Okres 1',
        )

        self.assertEqual(entry.id, '5001')
        self.assertEqual(entry.date, '2026-10-21')
        self.assertEqual(entry.lesson_no, 1)
        self.assertEqual(entry.subject, 'Język angielski')
        self.assertEqual(entry['symbol'], 'u')
        self.assertTrue(entry.is_justified)
        self.assertTrue(entry.is_absence)
        self.assertFalse(entry.is_late)
        self.assertEqual(entry.color, '#2ECC71')

        summary = AttendancePeriodSummary(
            label='Suma za okres 1',
            period='Okres 1',
            justified=5,
            unjustified=1,
            total_absences=6,
            lates=2,
            exemptions=0,
        )
        self.assertEqual(summary.period, 'Okres 1')
        self.assertEqual(summary.justified, 5)
        self.assertEqual(summary.total_absences, 6)
        self.assertEqual(summary['lates'], 2)

    def test_attendance_storage_integration(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage = FileStorage(tmp_dir)
            user_login = '1234567'

            entries = [
                AttendanceEntry(
                    id='5001',
                    date='2026-10-21',
                    lesson_no=1,
                    subject='Matematyka',
                    symbol='u',
                    type='nieobecność uspr.',
                    is_absence=True,
                    is_justified=True,
                ).to_dict(),
                AttendanceEntry(
                    id='5002',
                    date='2026-10-22',
                    lesson_no=2,
                    subject='Fizyka',
                    symbol='sp',
                    type='spóźnienie',
                    is_late=True,
                ).to_dict(),
            ]
            summary = [
                AttendancePeriodSummary(
                    label='Suma za okres 1',
                    period='Okres 1',
                    justified=1,
                    unjustified=0,
                    total_absences=1,
                    lates=1,
                    exemptions=0,
                ).to_dict()
            ]

            storage.save_attendance(user_login, entries, summary)

            history = storage.get_attendance_history(user_login)
            self.assertEqual(len(history), 2)
            # Powinno być posortowane malejąco po dacie: 2026-10-22 najpierw
            self.assertEqual(history[0]['id'], '5002')
            self.assertEqual(history[1]['id'], '5001')

            stored_summary = storage.get_attendance_summary(user_login)
            self.assertEqual(len(stored_summary), 1)
            self.assertEqual(stored_summary[0]['lates'], 1)

            last_sync = storage.get_last_attendance_sync(user_login)
            self.assertIsNotNone(last_sync)

            # Test archiwizacji czyści historię frekwencji
            storage.archive_school_year(user_login, "2025/2026")
            cleared_history = storage.get_attendance_history(user_login)
            self.assertEqual(cleared_history, [])
            self.assertIsNone(storage.get_last_attendance_sync(user_login))


if __name__ == '__main__':
    unittest.main()
