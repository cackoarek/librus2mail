"""Testy jednostkowe obiektów domenowych (Grade, Message, Announcement, TimetableEntry, ScheduleLesson)."""

import tempfile
import unittest

from librus2mail.domain_models import (
    Announcement,
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


if __name__ == '__main__':
    unittest.main()
