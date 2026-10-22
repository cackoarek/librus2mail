"""Testy jednostkowe i integracyjne dla panelu webowego Librus2mail (Flask)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import yaml

from librus2mail.web import create_app, export_web_views
from librus2mail.web import main as web_main
from librus2mail.web.app import get_app_version
from librus2mail.web.auth import LoginRateLimiter, get_client_ip
from librus2mail.web.services import (
    build_daily_summary_html,
    build_progress_report_html,
    build_recent_days_timeline,
    build_student_report_html,
    calculate_certificate_summary,
    calculate_goal_optimizer,
    calculate_overall_average,
    calculate_subject_averages,
    capture_action_execution,
    classify_subject,
    compute_educational_profile,
    compute_opportunity_matrix,
    compute_subject_stability_benchmark,
    format_human_timestamp,
    get_storage,
    resolve_student_name,
    simulate_new_grade,
    sort_grades_descending,
)
from librus2mail.web.services import (
    test_librus_credentials as check_librus_credentials,
)


class TestWebDashboard(unittest.TestCase):
    """Zestaw testów weryfikujących działanie aplikacji Flask i szablonów webowych."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, 'config.yaml')
        self.storage_dir = os.path.join(self.temp_dir, 'storage')
        os.makedirs(self.storage_dir, exist_ok=True)

        self.mock_config = {
            'librus_users': [
                {
                    'librus_login': '123456',
                    'librus_login_name': 'Jan Kowalski',
                    'librus_password': 'secret_pass',
                },
                {
                    'librus_login': '654321',
                    'librus_login_name': 'Anna Kowalska',
                    'librus_password': 'secret_pass_2',
                },
            ],
            'web': {
                'password': 'SuperParentPassword',
                'secret_key': 'test-secret-key-1234',
                'enable_csrf': False,
            },
            'storage_dir': self.storage_dir,
        }

        import yaml
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(self.mock_config, f)

        # Zapisanie przykładowych danych ucznia w storage/123456.json
        student_data = {
            'student_name': 'Jan Kowalski (klasa 5A)',
            'last_collect_time': '2026-09-22 20:00:00',
            'grades_history': [
                {
                    'id': 'g1',
                    'subject': 'Matematyka',
                    'grade': '5',
                    'weight': '2',
                    'category': 'Sprawdzian',
                    'date': '2026-09-20',
                    'teacher': 'A. Nowak',
                },
                {
                    'id': 'g2',
                    'subject': 'Matematyka',
                    'grade': '4',
                    'weight': '1',
                    'category': 'Kartkówka',
                    'date': '2026-09-21',
                    'teacher': 'A. Nowak',
                },
                {
                    'id': 'g3',
                    'subject': 'Język polski',
                    'grade': '3+',
                    'weight': '1',
                    'category': 'Odpowiedź',
                    'date': '2026-09-21',
                    'teacher': 'B. Wiśniewska',
                },
            ],
            'schedule_history': [
                {
                    'id': 'sch_1',
                    'date': '2026-09-23',
                    'lesson_no': 1,
                    'time_from': '08:00',
                    'time_to': '08:45',
                    'subject': 'Matematyka',
                    'teacher': 'A. Nowak',
                    'classroom': '12',
                    'is_substitution': False,
                    'is_cancelled': False,
                },
                {
                    'id': 'sch_2',
                    'date': '2026-09-23',
                    'lesson_no': 2,
                    'time_from': '08:55',
                    'time_to': '09:40',
                    'subject': 'Historia',
                    'teacher': 'C. Wójcik',
                    'classroom': '15',
                    'is_substitution': True,
                    'is_cancelled': False,
                    'substitution_info': 'Zastępstwo za J. Kowal',
                },
                {
                    'id': 'sch_3',
                    'date': '2026-09-23',
                    'lesson_no': 3,
                    'time_from': '09:50',
                    'time_to': '10:35',
                    'subject': 'Geografia',
                    'teacher': 'D. Krawczyk',
                    'classroom': '20',
                    'is_substitution': False,
                    'is_cancelled': True,
                },
            ],
            'timetable_history': [
                {
                    'date': '2026-09-23',
                    'type': 'test',
                    'category': 'Sprawdzian',
                    'subject': 'Matematyka',
                    'lesson_no': 1,
                    'description': 'Ułamki zwykłe i dziesiętne',
                    'teacher': 'A. Nowak',
                },
                {
                    'date': '2026-09-25',
                    'type': 'absence',
                    'category': 'Nieobecność',
                    'teacher': 'C. Wójcik',
                    'description': 'Wyjazd służbowy',
                },
            ],
            'known_messages': [
                'Zebranie z rodzicami 2026-09-18 17:00:00 Dyrekcja Szkoły',
            ],
            'known_notifications': [
                'Rozpoczęcie roku szkolnego 2026-09-01',
            ],
        }

        with open(os.path.join(self.storage_dir, '123456.json'), 'w', encoding='utf-8') as f:
            json.dump(student_data, f, ensure_ascii=False)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_auth_protection_when_password_set(self):
        """Testuje wymuszenie logowania rodzica, gdy skonfigurowano hasło."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            web_password='SecretPassword123',
            no_auth=False,
            secret_key='test-secret',
        )
        client = app.test_client()

        # Dostęp do pulpitu bez logowania powinien przekierować do /login
        res = client.get('/', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

        # Strona logowania powinna zwracać status 200 i NIE powinna ujawniać danych ucznia ani nawigacji
        login_res = client.get('/login')
        self.assertEqual(login_res.status_code, 200)
        self.assertIn('Odblokuj dostęp'.encode(), login_res.data)
        self.assertNotIn(b'Jan Kowalski', login_res.data)
        self.assertNotIn(b'123456', login_res.data)
        self.assertNotIn(b'Plan lekcji', login_res.data)

        # Logowanie ze złym hasłem powinno zakończyć się niepowodzeniem
        bad_post = client.post('/login', data={'password': 'WrongPassword'}, follow_redirects=True)
        self.assertEqual(bad_post.status_code, 200)
        self.assertIn('Nieprawidłowe hasło rodzica'.encode(), bad_post.data)

        # Logowanie z poprawnym hasłem powinno zalogować i przekierować
        good_post = client.post('/login', data={'password': 'SecretPassword123'}, follow_redirects=False)
        self.assertEqual(good_post.status_code, 302)

        # Po zalogowaniu pulpit powinien być dostępny i zawierać pełną nazwę ucznia z numerem konta
        dash_res = client.get('/', follow_redirects=True)
        self.assertEqual(dash_res.status_code, 200)
        self.assertIn(b'Jan Kowalski (123456)', dash_res.data)
        self.assertIn(b'Plan lekcji', dash_res.data)

        # Wylogowanie powinno przekierować do /login
        logout_res = client.get('/logout', follow_redirects=False)
        self.assertEqual(logout_res.status_code, 302)
        self.assertIn('/login', logout_res.headers.get('Location', ''))

    def test_open_mode_when_no_auth(self):
        """Testuje bezpośredni dostęp do widoków w trybie otwartym (--no-auth)."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            secret_key='test-secret',
        )
        client = app.test_client()

        # 1. Pulpit główny
        res_dash = client.get('/')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'Jan Kowalski', res_dash.data)
        self.assertIn('Średnia ocen'.encode(), res_dash.data)
        self.assertIn(b'href="/oceny"', res_dash.data)
        self.assertIn(b'href="/plan', res_dash.data)
        self.assertIn(b'href="/terminarz"', res_dash.data)

        # 2. Widok planu lekcji
        res_plan = client.get('/plan')
        self.assertEqual(res_plan.status_code, 200)
        self.assertIn(b'Plan lekcji', res_plan.data)
        self.assertIn(b'Matematyka', res_plan.data)
        self.assertIn('Zastępstwo'.encode(), res_plan.data)
        self.assertIn('Odwołana'.encode(), res_plan.data)

        # 3. Widok ocen
        res_oceny = client.get('/oceny')
        self.assertEqual(res_oceny.status_code, 200)
        self.assertIn('Oceny i Średnie'.encode(), res_oceny.data)
        self.assertIn(b'Aktualne oceny', res_oceny.data)
        self.assertIn('Świadectwo'.encode(), res_oceny.data)
        self.assertIn('Pasek z wyróżnieniem'.encode(), res_oceny.data)
        self.assertIn(b"switchGradesTab('swiadectwo')", res_oceny.data)
        self.assertIn(b'Optymalizator Celu', res_oceny.data)
        self.assertIn(b"switchGradesTab('optymalizator')", res_oceny.data)
        self.assertIn(b'Matematyka', res_oceny.data)

        res_oceny_swiad = client.get('/oceny?tab=swiadectwo')
        self.assertEqual(res_oceny_swiad.status_code, 200)
        self.assertIn(b'grades-pane-swiadectwo', res_oceny_swiad.data)
        self.assertIn('Średnia za całe świadectwo'.encode(), res_oceny_swiad.data)
        self.assertIn(b'Proponowana', res_oceny_swiad.data)
        self.assertIn(b'Ocena', res_oceny_swiad.data)
        self.assertIn('Słownie'.encode(), res_oceny_swiad.data)

        res_oceny_opt = client.get('/oceny?tab=optymalizator')
        self.assertEqual(res_oceny_opt.status_code, 200)
        self.assertIn(b'grades-pane-optymalizator', res_oceny_opt.data)

        # 4. Widok terminarza
        res_term = client.get('/terminarz')
        self.assertEqual(res_term.status_code, 200)
        self.assertIn(b'Terminarz', res_term.data)
        self.assertIn('Ułamki zwykłe i dziesiętne'.encode(), res_term.data)

        # 5. Widok wiadomości
        res_msg = client.get('/wiadomosci')
        self.assertEqual(res_msg.status_code, 200)
        self.assertIn('Wiadomości i Ogłoszenia'.encode(), res_msg.data)
        self.assertIn(b'Zebranie z rodzicami', res_msg.data)

        # 5b. Widok frekwencji
        res_att = client.get('/frekwencja')
        self.assertEqual(res_att.status_code, 200)
        self.assertIn('Frekwencja & Obecność'.encode(), res_att.data)
        self.assertIn(b'href="/frekwencja"', res_dash.data)

        res_att_alias = client.get('/attendance')
        self.assertEqual(res_att_alias.status_code, 200)

        # 6. Widok centrum akcji
        res_act = client.get('/akcje')
        self.assertEqual(res_act.status_code, 200)
        self.assertIn(b'Centrum Operacyjne CLI', res_act.data)
        self.assertIn(b'Pobierz dane z Librusa', res_act.data)

    def test_switch_student(self):
        """Testuje przełączanie aktywnego ucznia w sesji."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            secret_key='test-secret',
        )
        client = app.test_client()

        # Przełączenie na innego ucznia
        res = client.get('/student/654321', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        with client.session_transaction() as sess:
            self.assertEqual(sess.get('active_student_login'), '654321')

    def test_whatif_calculator_api(self):
        """Testuje endpoint symulacji nowej oceny /api/whatif."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            secret_key='test-secret',
        )
        client = app.test_client()

        # Poprawne zapytanie symulacyjne
        res = client.post('/api/whatif', data={
            'subject': 'Matematyka',
            'grade': '5',
            'weight': '3',
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn('Nowa średnia:'.encode(), res.data)
        self.assertIn(b'Matematyka', res.data)

        # Błędne parametry (np. nieliczbowa ocena)
        bad_res = client.post('/api/whatif', data={
            'subject': 'Matematyka',
            'grade': 'nie-liczba',
            'weight': '3',
        })
        self.assertEqual(bad_res.status_code, 400)

        # Ocena spoza zakresu 1–6
        out_res = client.post('/api/whatif', data={
            'subject': 'Matematyka',
            'grade': '7.5',
            'weight': '1',
        })
        self.assertEqual(out_res.status_code, 400)
        self.assertIn('Ocena musi być w przedziale 1–6'.encode(), out_res.data)

        # Waga ujemna lub 0
        neg_weight_res = client.post('/api/whatif', data={
            'subject': 'Matematyka',
            'grade': '5',
            'weight': '0',
        })
        self.assertEqual(neg_weight_res.status_code, 400)

    @patch('librus2mail.web.app.run_collector')
    def test_action_sync_endpoint(self, mock_collector):
        """Testuje wyzwolenie synchronizacji przez endpoint API /api/action/sync."""
        mock_collector.return_value = None
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            secret_key='test-secret',
        )
        client = app.test_client()

        res = client.post('/api/action/sync', data={'login': '123456'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('Synchronizacja konta 123456 zakończona'.encode(), res.data)
        self.assertTrue(mock_collector.called)

    @patch('librus2mail.web.app.run_notifier')
    def test_action_notify_endpoint(self, mock_notifier):
        """Testuje wyzwolenie wysyłki powiadomienia przez /api/action/notify."""
        mock_notifier.return_value = None
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            secret_key='test-secret',
        )
        client = app.test_client()

        res = client.post('/api/action/notify', data={
            'login': '123456',
            'days': '1',
            'dry_run': '1',
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Generowanie powiadomienia (tryb symulacji dry-run) dla 123456', res.data)
        self.assertTrue(mock_notifier.called)

    def test_services_analytics(self):
        """Testuje kalkulacje statystyczne w module services."""
        grades = [
            {'subject': 'Matematyka', 'grade': '5', 'weight': '2'},
            {'subject': 'Matematyka', 'grade': '3', 'weight': '1'},
            {'subject': 'Fizyka', 'grade': '4', 'weight': '1'},
        ]
        averages = calculate_subject_averages(grades)
        self.assertIn('Matematyka', averages)
        self.assertIn('Fizyka', averages)

        # Matematyka: (5*2 + 3*1) / (2+1) = 13 / 3 = 4.33
        self.assertEqual(averages['Matematyka']['average'], 4.33)
        self.assertEqual(averages['Fizyka']['average'], 4.0)

        overall = calculate_overall_average(averages)
        # (4.33 + 4.0) / 2 = 4.165 -> 4.17
        self.assertEqual(overall, 4.17)

        # Symulacja nowej oceny
        sim = simulate_new_grade(grades, 'Matematyka', new_grade=6.0, new_weight=3.0)
        # Stara suma wag: 3, stara suma ważona: 13.
        # Nowa: 13 + (6*3) = 31. Nowa suma wag: 3 + 3 = 6. Nowa średnia: 31/6 = 5.17
        self.assertEqual(sim['old_avg'], 4.33)
        self.assertEqual(sim['new_avg'], 5.17)
        self.assertEqual(sim['diff'], 0.84)

        # Test zestawienia na świadectwo (calculate_certificate_summary)
        averages_with_empty = dict(averages)
        averages_with_empty['Plastyka'] = {
            'subject': 'Plastyka',
            'grades': [],
            'count': 0,
            'numeric_count': 0,
            'average': None,
            'sum_weights': 0.0,
        }
        cert = calculate_certificate_summary(averages_with_empty)
        # Matematyka (śr 4.33 -> 4) + Fizyka (śr 4.0 -> 4)
        # Plastyka ma 0 ocen, więc nie wchodzi do średniej ze świadectwa
        self.assertEqual(cert['rated_count'], 2)
        self.assertEqual(cert['unrated_count'], 1)
        self.assertEqual(cert['total_count'], 3)
        self.assertEqual(cert['certificate_average'], 4.00)
        self.assertFalse(cert['has_red_stripe'])
        self.assertEqual(cert['red_stripe_diff'], 0.75)
        self.assertEqual(cert['subjects'][0]['proposed_grade_word'], 'dobry')
        self.assertEqual(cert['subjects'][2]['proposed_grade_word'], 'brak ocen')

        # Test wykluczenia przedmiotu ze średniej ze świadectwa (sekcja dolna)
        cert_ex = calculate_certificate_summary(averages_with_empty, excluded_subjects=['Fizyka'])
        self.assertEqual(len(cert_ex['included_subjects']), 2)
        self.assertEqual(len(cert_ex['excluded_subjects']), 1)
        self.assertEqual(cert_ex['excluded_subjects'][0]['subject'], 'Fizyka')
        self.assertTrue(cert_ex['excluded_subjects'][0]['is_excluded'])
        # Przedmioty wykluczone znajdują się na dole listy subjects
        self.assertEqual(cert_ex['rated_count'], 1)  # tylko Matematyka
        self.assertEqual(cert_ex['certificate_average'], 4.00)

        # Test kalkulacji z calculate_subject_averages dla przedmiotu bez ocen (np. Sztuka)
        full_subj_avgs = calculate_subject_averages(
            grades,
            all_subjects=['Matematyka', 'Fizyka', 'Sztuka'],
        )
        self.assertIn('Sztuka', full_subj_avgs)
        self.assertIsNone(full_subj_avgs['Sztuka']['average'])
        self.assertIsNone(full_subj_avgs['Sztuka']['proposed_grade_num'])
        self.assertEqual(full_subj_avgs['Sztuka']['proposed_grade_label'], 'Brak ocen')
        cert_full = calculate_certificate_summary(full_subj_avgs)
        self.assertEqual(cert_full['rated_count'], 2)
        self.assertEqual(cert_full['unrated_count'], 1)
        self.assertEqual(cert_full['certificate_average'], 4.00)

        # Test ustalania pełnej nazwy ucznia (resolve_student_name)
        storage = get_storage(self.mock_config, self.storage_dir)
        resolved = resolve_student_name(self.mock_config, storage, '123456')
        self.assertEqual(resolved, 'Jan Kowalski (123456)')

        # Zapis i ponowny odczyt przez set_student_name
        storage.set_student_name('123456', 'Jan Kowalski Zaktualizowany')
        self.assertEqual(storage.get_student_name('123456'), 'Jan Kowalski Zaktualizowany')

        # Test sortowania ocen malejąco po rzeczywistej dacie wystawienia
        unsorted_grades = [
            {'subject': 'Historia', 'grade': '6', 'date': '2026-09-11 (pt.)', 'added_at': '2026-10-15T20:00:00', 'id': '1005'},
            {'subject': 'Biologia', 'grade': 'np', 'date': '2026-09-15 (wt.)', 'added_at': '2026-10-15T20:00:00', 'id': '1010'},
            {'subject': 'Język angielski', 'grade': '4', 'date': '2026-10-16 (pt.)', 'added_at': '2026-10-16T15:00:00', 'id': '1055'},
            {'subject': 'Geografia', 'grade': '5-', 'date': '2026-10-12 (pon.)', 'added_at': '2026-10-15T20:00:00', 'id': '1040'},
            {'subject': 'Biologia', 'grade': '5', 'date': '2026-10-06 (wt.)', 'added_at': '2026-10-15T20:00:00', 'id': '1035'},
            {'subject': 'Biologia', 'grade': 'np', 'date': '2026-09-29 (wt.)', 'added_at': '2026-10-15T20:00:00', 'id': '1025'},
            {'subject': 'Język polski', 'grade': '3', 'date': '2026-10-16 (pt.)', 'added_at': '2026-10-16T15:00:00', 'id': '1054'},
        ]
        sorted_res = sort_grades_descending(unsorted_grades)
        dates_order = [g['date'] for g in sorted_res]
        self.assertEqual(dates_order, [
            '2026-10-16 (pt.)',
            '2026-10-16 (pt.)',
            '2026-10-12 (pon.)',
            '2026-10-06 (wt.)',
            '2026-09-29 (wt.)',
            '2026-09-15 (wt.)',
            '2026-09-11 (pt.)',
        ])
        # Tie-breaker po wyższym ID dla tej samej daty 16.10
        self.assertEqual(sorted_res[0]['subject'], 'Język angielski')
        self.assertEqual(sorted_res[1]['subject'], 'Język polski')

    def test_semester_split_and_annual_grade_algorithms(self):
        """Weryfikuje podział ocen na semestry, detekcję przedmiotów zakończonych oraz algorytmy ocen rocznych."""
        split_date = "2027-02-01"
        ref_in_sem2 = datetime(2027, 3, 15, 10, 0, 0)

        grades = [
            # Technika: oceny tylko w I semestrze (zakończony)
            {'subject': 'Technika', 'grade': '5', 'weight': '2', 'date': '2026-11-10', 'id': '101'},
            {'subject': 'Technika', 'grade': '5', 'weight': '1', 'date': '2026-12-05', 'id': '102'},

            # Matematyka: oceny w I i II semestrze (w toku), w II semestrze progres (I sem: 4, II sem: 5)
            {'subject': 'Matematyka', 'grade': '4', 'weight': '2', 'date': '2026-10-15', 'id': '103'},
            {'subject': 'Matematyka', 'grade': '4', 'weight': '2', 'date': '2027-01-20', 'id': '104'},
            {'subject': 'Matematyka', 'grade': '5', 'weight': '2', 'date': '2027-02-25', 'id': '105'},
            {'subject': 'Matematyka', 'grade': '5', 'weight': '3', 'date': '2027-03-05', 'id': '106'},

            # Fizyka: z oficjalną propozycją belfra
            {'subject': 'Fizyka', 'grade': '3', 'weight': '1', 'date': '2026-11-20', 'id': '107'},
            {'subject': 'Fizyka', 'grade': '4', 'weight': '1', 'date': '2027-02-15', 'id': '108'},
            {'subject': 'Fizyka', 'grade': '5', 'weight': '0', 'date': '2027-03-10', 'category': 'Proponowana ocena roczna', 'teacher': 'Nauczyciel Fizyki', 'id': '109'},
        ]

        # 1. Cały rok szkolny (semester='all')
        avgs_all = calculate_subject_averages(
            grades,
            semester='all',
            semester_split_date=split_date,
            ref_date=ref_in_sem2,
        )
        self.assertTrue(avgs_all['Technika']['is_completed'])
        self.assertEqual(avgs_all['Technika']['status_label'], 'Zakończony w I semestrze')
        self.assertEqual(avgs_all['Technika']['average'], 5.0)

        self.assertFalse(avgs_all['Matematyka']['is_completed'])
        self.assertEqual(avgs_all['Matematyka']['status_label'], 'W toku (Semestr II)')
        # Średnia roczna matematyki: (4*4 + 5*5) / 9 = 41 / 9 = 4.56
        self.assertEqual(avgs_all['Matematyka']['average'], 4.56)

        # 2. Filtr Semestr I (semester='sem1')
        avgs_sem1 = calculate_subject_averages(
            grades,
            semester='sem1',
            semester_split_date=split_date,
            ref_date=ref_in_sem2,
        )
        self.assertEqual(avgs_sem1['Matematyka']['average'], 4.0)
        self.assertEqual(len(avgs_sem1['Matematyka']['grades']), 2)

        # 3. Filtr Semestr II (semester='sem2')
        avgs_sem2 = calculate_subject_averages(
            grades,
            semester='sem2',
            semester_split_date=split_date,
            ref_date=ref_in_sem2,
        )
        # Matematyka w II semestrze ma same 5: średnia 5.0
        self.assertEqual(avgs_sem2['Matematyka']['average'], 5.0)
        self.assertEqual(len(avgs_sem2['Matematyka']['grades']), 2)
        # Technika zakończona w I semestrze zachowuje swoją ocenę z I semestru
        self.assertEqual(avgs_sem2['Technika']['average'], 5.0)

        # 4. Algorytmy predykcji ocen rocznych
        # A) all_year_weighted: Matematyka ma średnią 4.56 -> predykcja 4 (dobry, bo próg na 5 to 4.75)
        avgs_algo1 = calculate_subject_averages(
            grades,
            semester='all',
            semester_split_date=split_date,
            ref_date=ref_in_sem2,
            annual_grade_algorithm='all_year_weighted',
        )
        self.assertEqual(avgs_algo1['Matematyka']['proposed_grade_num'], 4)

        # B) semesters_average: I sem = 4, II sem = 5 -> średnia 4.5 -> 4
        avgs_algo2 = calculate_subject_averages(
            grades,
            semester='all',
            semester_split_date=split_date,
            ref_date=ref_in_sem2,
            annual_grade_algorithm='semesters_average',
        )
        self.assertEqual(avgs_algo2['Matematyka']['proposed_grade_num'], 4)

        # C) progress_favored: I sem = 4, II sem = 5 -> progres -> 5 (bardzo dobry)!
        avgs_algo3 = calculate_subject_averages(
            grades,
            semester='all',
            semester_split_date=split_date,
            ref_date=ref_in_sem2,
            annual_grade_algorithm='progress_favored',
        )
        self.assertEqual(avgs_algo3['Matematyka']['proposed_grade_num'], 5)

        # 5. Oficjalna propozycja nauczyciela na Fizyce ma pierwszeństwo (zaproponował 5)
        self.assertTrue(avgs_all['Fizyka']['is_official_proposal'])
        self.assertEqual(avgs_all['Fizyka']['proposed_grade_num'], 5)
        self.assertIsNotNone(avgs_all['Fizyka']['official_proposed_grade'])
        self.assertEqual(avgs_all['Fizyka']['official_proposed_grade']['teacher'], 'Nauczyciel Fizyki')

        # 6. Zestawienie na świadectwo uwzględnia ocenę proponowaną i algorytmy
        cert = calculate_certificate_summary(avgs_algo3)
        subj_map = {s['subject']: s for s in cert['subjects']}
        self.assertEqual(subj_map['Technika']['proposed_grade_num'], 5)
        self.assertTrue(subj_map['Technika']['is_completed'])
        self.assertEqual(subj_map['Matematyka']['proposed_grade_num'], 5)
        self.assertEqual(subj_map['Fizyka']['proposed_grade_num'], 5)
        self.assertTrue(subj_map['Fizyka']['is_official_proposal'])

    def test_login_rate_limiter_unit(self):
        """Testuje jednostkowo działanie klasy LoginRateLimiter (licznik prób i blokada)."""
        limiter = LoginRateLimiter(max_attempts=3, lockout_duration_s=600, window_s=120)
        ip = "192.168.1.100"
        t0 = datetime(2026, 10, 5, 12, 0, 0)

        # Początkowo IP nie jest zablokowane
        locked, sec = limiter.is_locked(ip, now=t0)
        self.assertFalse(locked)
        self.assertEqual(sec, 0)

        # Próba 1: nieudana, pozostały 2 próby
        locked, sec, rem = limiter.record_failure(ip, now=t0)
        self.assertFalse(locked)
        self.assertEqual(rem, 2)

        # Próba 2: nieudana, pozostała 1 próba
        locked, sec, rem = limiter.record_failure(ip, now=t0 + timedelta(seconds=10))
        self.assertFalse(locked)
        self.assertEqual(rem, 1)

        # Próba 3: limit przekroczony -> blokada na 600s
        locked, sec, rem = limiter.record_failure(ip, now=t0 + timedelta(seconds=20))
        self.assertTrue(locked)
        self.assertEqual(sec, 600)
        self.assertEqual(rem, 0)

        # Sprawdzenie w trakcie trwania blokady (t0 + 20s + 600s = t0 + 620s; przy t0 + 100s zostaje 520s)
        locked, sec = limiter.is_locked(ip, now=t0 + timedelta(seconds=100))
        self.assertTrue(locked)
        self.assertEqual(sec, 520)

        # Po upływie 600s blokada wygasa
        locked, sec = limiter.is_locked(ip, now=t0 + timedelta(seconds=621))
        self.assertFalse(locked)
        self.assertEqual(sec, 0)

        # Reset po udanym logowaniu
        limiter.record_failure(ip, now=t0)
        self.assertEqual(len(limiter._failed_attempts[ip]), 1)
        limiter.record_success(ip)
        self.assertEqual(len(limiter._failed_attempts[ip]), 0)

    def test_login_brute_force_lockout_integration(self):
        """Testuje integracyjnie blokadę IP i kod 429 po przekroczeniu limitu nieudanych logowań."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            web_password='SuperSecretPassword',
            max_login_attempts=3,
            lockout_duration_s=900,
            no_auth=False,
            secret_key='test-secret',
        )
        client = app.test_client()

        # 1. Pierwsza nieudana próba
        res1 = client.post('/login', data={'password': 'BadPassword'}, follow_redirects=True)
        self.assertEqual(res1.status_code, 200)
        self.assertIn('Nieprawidłowe hasło rodzica. Pozostało prób: 2.'.encode(), res1.data)

        # 2. Druga nieudana próba
        res2 = client.post('/login', data={'password': 'BadPassword2'}, follow_redirects=True)
        self.assertEqual(res2.status_code, 200)
        self.assertIn('Nieprawidłowe hasło rodzica. Pozostało prób: 1.'.encode(), res2.data)

        # 3. Trzecia nieudana próba -> Zablokowanie IP i kod 429
        res3 = client.post('/login', data={'password': 'BadPassword3'}, follow_redirects=True)
        self.assertEqual(res3.status_code, 429)
        self.assertIn(b'Adres IP tymczasowo zablokowany', res3.data)
        self.assertIn(b'15 min', res3.data)

        # 4. Kolejne żądanie GET /login również zwraca 429 i informację o blokadzie
        res4 = client.get('/login')
        self.assertEqual(res4.status_code, 429)
        self.assertIn(b'Adres IP tymczasowo zablokowany', res4.data)
        self.assertIn(b'disabled', res4.data)

        # 5. Nawet próba wysłania poprawnego hasła z zablokowanego IP jest odrzucana z kodem 429
        res5 = client.post('/login', data={'password': 'SuperSecretPassword'})
        self.assertEqual(res5.status_code, 429)

        # 6. Inny adres IP (np. przez proxy X-Forwarded-For) NIE jest zablokowany i może się zalogować
        res6 = client.post(
            '/login',
            data={'password': 'SuperSecretPassword'},
            headers={'X-Forwarded-For': '10.0.0.99'},
            follow_redirects=False,
        )
        self.assertEqual(res6.status_code, 302)

    def test_get_client_ip(self):
        """Testuje ekstrakcję adresu IP klienta z nagłówków proxy i gniazda HTTP."""
        class DummyRequest:
            def __init__(self, headers=None, remote_addr='127.0.0.1'):
                self.headers = headers or {}
                self.remote_addr = remote_addr

        # 1. Zwykłe zapytanie bez proxy
        req1 = DummyRequest(remote_addr='192.168.1.5')
        self.assertEqual(get_client_ip(req1), '192.168.1.5')

        # 2. Nagłówek X-Forwarded-For z łańcuchem proxy (bierze pierwszy / oryginalny IP)
        req2 = DummyRequest(headers={'X-Forwarded-For': '203.0.113.195, 70.41.3.18, 150.172.238.178'})
        self.assertEqual(get_client_ip(req2), '203.0.113.195')

        # 3. Nagłówek X-Real-IP
        req3 = DummyRequest(headers={'X-Real-IP': '198.51.100.42'})
        self.assertEqual(get_client_ip(req3), '198.51.100.42')

    def test_export_web_views_function(self):
        """Testuje programowe generowanie statycznych plików HTML panelu webowego."""
        export_dir = os.path.join(self.temp_dir, 'html_export')
        files = export_web_views(
            output_dir=export_dir,
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            user_login='123456',
            actual_date='2026-09-18',
            make_links_relative=True,
        )

        expected_files = {
            'web_login.html',
            'web_dashboard.html',
            'web_plan.html',
            'web_oceny.html',
            'web_oceny_swiadectwo.html',
            'web_oceny_optymalizator.html',
            'web_przedmiot_matematyka.html',
            'web_terminarz.html',
            'web_frekwencja.html',
            'web_wiadomosci.html',
            'web_raporty_podsumowanie.html',
            'web_raporty_postepy.html',
            'web_raporty_uczen_kids.html',
            'web_raporty_uczen_teens.html',
            'web_raporty_uczen_youth.html',
            'web_raporty_szanse.html',
            'web_raporty_profil.html',
            'web_raporty_stabilnosc.html',
            'web_akcje.html',
            'web_setup.html',
            'web_ustawienia.html',
        }
        self.assertEqual(set(files.keys()), expected_files)

        # Weryfikacja fizycznego istnienia plików na dysku
        for fname in expected_files:
            fpath = os.path.join(export_dir, fname)
            self.assertTrue(os.path.isfile(fpath), f"Brak pliku {fpath}")
            self.assertGreater(os.path.getsize(fpath), 0)

        # Weryfikacja zawartości ekranu logowania (brak wycieku danych ucznia, formularz kieruje na pulpit)
        with open(os.path.join(export_dir, 'web_login.html'), encoding='utf-8') as f:
            login_content = f.read()
            self.assertIn('Logowanie Rodzica', login_content)
            self.assertNotIn('Jan Kowalski', login_content)
            self.assertIn('action="web_dashboard.html"', login_content)

        # Weryfikacja zawartości pulpitu po zalogowaniu (obecność ucznia i relatywne linki zakładek)
        with open(os.path.join(export_dir, 'web_dashboard.html'), encoding='utf-8') as f:
            dash_content = f.read()
            self.assertIn('Jan Kowalski (123456)', dash_content)
            self.assertIn('href="web_plan.html"', dash_content)
            self.assertIn('href="web_oceny.html"', dash_content)

        # Weryfikacja podlinkowania analizy przedmiotu z poziomu zestawienia ocen
        with open(os.path.join(export_dir, 'web_oceny.html'), encoding='utf-8') as f:
            oceny_content = f.read()
            self.assertIn('href="web_przedmiot_matematyka.html"', oceny_content)

        # Weryfikacja zawartości analizy przedmiotu
        with open(os.path.join(export_dir, 'web_przedmiot_matematyka.html'), encoding='utf-8') as f:
            mat_content = f.read()
            self.assertIn('Matematyka', mat_content)
            self.assertIn('href="web_oceny.html"', mat_content)

    def test_web_cli_export_html_flag(self):
        """Testuje wywołanie eksportu widoków HTML przez flagę CLI --export-html."""
        export_dir = os.path.join(self.temp_dir, 'cli_export')
        test_args = [
            'librus_web.py',
            '-c', self.config_path,
            '-s', self.storage_dir,
            '-u', '123456',
            '--actual-date', '2026-09-18',
            '--export-html', export_dir,
        ]

        with patch.object(sys, 'argv', test_args):
            web_main()

        self.assertTrue(os.path.isfile(os.path.join(export_dir, 'web_dashboard.html')))
        self.assertTrue(os.path.isfile(os.path.join(export_dir, 'web_login.html')))

    def test_reports_views_endpoints(self):
        """Testuje podstronę /raporty oraz jej podzakładki i przełącznik wariantów stylu."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            actual_date='2026-09-22',
        )
        client = app.test_client()

        # 1. Domyślny widok /raporty (kieruje na podsumowanie dzienne)
        res_default = client.get('/raporty')
        self.assertEqual(res_default.status_code, 200)
        self.assertIn(b'Podsumowanie dzienne', res_default.data)
        self.assertIn(b'type="date"', res_default.data)
        self.assertIn(b'value="2026-09-22"', res_default.data)

        # 2. Zakładka /raporty/postepy z różnymi okresami (3, 14, 30 dni)
        for d in (3, 14, 30):
            res_p = client.get(f'/raporty/postepy?days={d}')
            self.assertEqual(res_p.status_code, 200)
            self.assertIn(f'{d} dni'.encode(), res_p.data)

        # 3. Zakładka /raporty/uczen z wariantami (kids, teens, youth) i okresami
        res_kids = client.get('/raporty/uczen?variant=kids&days=3')
        self.assertEqual(res_kids.status_code, 200)
        self.assertIn(b'Kids', res_kids.data)
        self.assertIn(b'3 dni', res_kids.data)

        res_teens = client.get('/raporty/uczen?variant=teens&days=14')
        self.assertEqual(res_teens.status_code, 200)
        self.assertIn(b'Teens', res_teens.data)
        self.assertIn(b'14 dni', res_teens.data)

        res_youth = client.get('/raporty/uczen?variant=youth&days=30')
        self.assertEqual(res_youth.status_code, 200)
        self.assertIn(b'Youth', res_youth.data)
        self.assertIn(b'30 dni', res_youth.data)

        # 4. Zakładka /raporty/podsumowanie z date pickerem
        res_summary = client.get('/raporty/podsumowanie')
        self.assertEqual(res_summary.status_code, 200)
        self.assertIn(b'Podsumowanie dzienne', res_summary.data)
        self.assertIn(b'type="date"', res_summary.data)
        self.assertIn(b'value="2026-09-22"', res_summary.data)

        # 5. Zakładka /raporty/podsumowanie z wybraną datą z date pickera
        res_summary_date = client.get('/raporty/podsumowanie?date=2026-09-20')
        self.assertEqual(res_summary_date.status_code, 200)
        self.assertIn(b'value="2026-09-20"', res_summary_date.data)

        # 6. Nowe zaawansowane moduły analityczne
        res_szanse = client.get('/raporty/szanse')
        self.assertEqual(res_szanse.status_code, 200)
        self.assertIn(b'Matryca Szans i Ryzyk', res_szanse.data)
        self.assertIn(b'Quick Wins', res_szanse.data)
        self.assertIn(b'Bezpieczny bufor', res_szanse.data)

        res_profil = client.get('/raporty/profil')
        self.assertEqual(res_profil.status_code, 200)
        self.assertIn(b'Profil i Balans', res_profil.data)
        self.assertIn('Radar Równowagi Edukacyjnej'.encode(), res_profil.data)
        self.assertIn('Jak wyliczane są średnie'.encode(), res_profil.data)

        res_stab = client.get('/raporty/stabilnosc')
        self.assertEqual(res_stab.status_code, 200)
        self.assertIn('Porównanie i Stabilność'.encode(), res_stab.data)
        self.assertIn(b'Lokomotywy', res_stab.data)
        self.assertIn(b'Kotwice', res_stab.data)

    def test_reports_builders_unit(self):
        """Testuje bezpośrednie funkcje generujące treść raportów (services)."""
        storage = get_storage(self.mock_config, self.storage_dir)

        # Raport postępów
        html_progress = build_progress_report_html(
            storage=storage,
            login='123456',
            config=self.mock_config,
            days=7,
            now=datetime(2026, 9, 22),
        )
        self.assertIn('Raport postępów', html_progress)
        self.assertIn('Jan Kowalski', html_progress)

        # Raport ucznia
        html_student = build_student_report_html(
            storage=storage,
            login='123456',
            config=self.mock_config,
            variant='teens',
            days=7,
            now=datetime(2026, 9, 22),
        )
        self.assertIn('Jan Kowalski', html_student)

        # Podsumowanie powiadomień dla konkretnego dnia (2026-09-20 Jan Kowalski ma ocenę z Matematyki)
        html_summary = build_daily_summary_html(
            storage=storage,
            login='123456',
            config=self.mock_config,
            target_date='2026-09-20',
            now=datetime(2026, 9, 22),
        )
        self.assertIn('Jan Kowalski', html_summary)
        self.assertIn('Matematyka', html_summary)

        # Obsługa nieznanego ucznia bez ocen w bazie
        html_empty = build_progress_report_html(
            storage=storage,
            login='999999',
            config=self.mock_config,
        )
        self.assertIn('Brak zapisanych ocen', html_empty)

    def test_capture_action_execution_error_handling(self):
        """Testuje bezpieczne przechwytywanie wyjątków w capture_action_execution."""
        def faulty_action():
            raise RuntimeError("Testowy błąd operacji")

        success, output, result = capture_action_execution(faulty_action)
        self.assertFalse(success)
        self.assertIn("Testowy błąd operacji", output)
        self.assertIsNone(result)

    def test_get_app_version_and_footer(self):
        """Weryfikuje dynamiczne pobieranie wersji aplikacji i wyświetlanie jej w stopce."""
        version = get_app_version()
        self.assertTrue(isinstance(version, str))
        self.assertTrue(len(version) > 0)
        self.assertFalse(version.startswith("v"))

        # Sprawdź czy wersja pojawia się w renderowanym szablonie panelu
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
        expected_footer = f"Librus2mail v{version}".encode()
        self.assertIn(expected_footer, response.data)

    def test_format_human_timestamp_and_dashboard_display(self):
        """Testuje konwersję daty na ludzki format w języku polskim oraz wyświetlanie na pulpicie."""
        now = datetime(2026, 10, 7, 13, 11, 30)

        # 1. Pusty / brak danych
        self.assertEqual(format_human_timestamp(None, now=now), "Brak danych")
        self.assertEqual(format_human_timestamp("", now=now), "Brak danych")

        # 2. Dzisiaj przed chwilą (< 1 min)
        self.assertEqual(
            format_human_timestamp("2026-10-07T13:11:10", now=now),
            "dzisiaj o 13:11 (przed chwilą)",
        )

        # 3. Dzisiaj kilkanaście/kilkadziesiąt minut temu (np. przypadek zgłoszony przez użytkownika)
        self.assertEqual(
            format_human_timestamp("2026-10-07T12:25:30.463551", now=now),
            "dzisiaj o 12:25 (45 min temu)",
        )

        # 4. Dzisiaj kilka godzin temu
        self.assertEqual(
            format_human_timestamp("2026-10-07T10:00:00", now=now),
            "dzisiaj o 10:00 (3 godz. temu)",
        )

        # 5. Wczoraj
        self.assertEqual(
            format_human_timestamp("2026-10-06T18:45:00", now=now),
            "wczoraj o 18:45",
        )

        # 6. Przedwczoraj
        self.assertEqual(
            format_human_timestamp("2026-10-05T20:10:00", now=now),
            "przedwczoraj o 20:10",
        )

        # 7. Kilka dni temu w bieżącym roku
        self.assertEqual(
            format_human_timestamp("2026-09-30T09:15:00", now=now),
            "30.09 o 09:15 (7 dni temu)",
        )

        # 8. Inny rok
        self.assertEqual(
            format_human_timestamp("2025-10-07T12:00:00", now=now),
            "07.10.2025 o 12:00",
        )

        # 9. Test integracyjny z widokiem dashboardu Flask
        storage = get_storage(self.mock_config, self.storage_dir)
        iso_sync = "2026-10-07T12:25:30.463551"
        storage.save_last_collect_time('123456', iso_sync)

        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            actual_date=now,
            no_auth=True,
        )
        client = app.test_client()
        res = client.get('/')
        self.assertEqual(res.status_code, 200)

        # W tekście powinien być ludzki opis, a w atrybucie title pełny znacznik ISO
        self.assertIn(b"dzisiaj o 12:25 (45 min temu)", res.data)
        self.assertIn(f'title="{iso_sync}"'.encode(), res.data)

    def test_favicon_endpoints_and_html_link(self):
        """Weryfikuje serwowanie wektorowego favikona oraz obecność tagu link w HTML."""
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()

        # 1. Endpoint /favicon.ico zwraca 200 oraz mime image/svg+xml
        res_ico = client.get('/favicon.ico')
        self.assertEqual(res_ico.status_code, 200)
        self.assertIn('image/svg+xml', res_ico.content_type)
        self.assertIn(b'<svg', res_ico.data)
        self.assertIn(b'#4f46e5', res_ico.data)

        # 2. Endpoint /favicon.svg zwraca to samo
        res_svg = client.get('/favicon.svg')
        self.assertEqual(res_svg.status_code, 200)
        self.assertIn('image/svg+xml', res_svg.content_type)

        # 3. Widok HTML zawiera <link rel="icon" type="image/svg+xml"
        res_home = client.get('/')
        self.assertEqual(res_home.status_code, 200)
        self.assertIn(b'<link rel="icon" type="image/svg+xml"', res_home.data)

    def test_has_valid_config_and_onboarding_redirect(self):
        """Weryfikuje, że brak kont Librusa w konfiguracji przekierowuje do kreatora /setup."""
        empty_config_path = os.path.join(self.temp_dir, 'empty_config.yaml')
        with open(empty_config_path, 'w', encoding='utf-8') as f:
            f.write("storage_dir: storage\n")

        app = create_app(
            config_path=empty_config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
        )
        client = app.test_client()

        # 1. Wejście na stronę główną / przekierowuje do /setup
        res_root = client.get('/', follow_redirects=False)
        self.assertEqual(res_root.status_code, 302)
        self.assertIn('/setup', res_root.headers.get('Location', ''))

        # 2. Wejście na podstronę /plan również przekierowuje do /setup
        res_plan = client.get('/plan', follow_redirects=False)
        self.assertEqual(res_plan.status_code, 302)
        self.assertIn('/setup', res_plan.headers.get('Location', ''))

        # 3. Wejście na /setup jest dozwolone i zwraca formularz kreatora
        res_setup = client.get('/setup')
        self.assertEqual(res_setup.status_code, 200)
        self.assertIn(b'Witaj w Librus2mail!', res_setup.data)
        self.assertIn(b'Testuj logowanie Librus', res_setup.data)
        self.assertIn(b'id="gmail-tip-box"', res_setup.data)

    def test_librus_credentials_service_and_api(self):
        """Testuje sprawdzanie poprawności danych logowania Librusa (funkcję i endpoint API)."""
        from librus2mail.librus import NotLogged

        # 1. Puste dane
        ok, msg = check_librus_credentials("", "")
        self.assertFalse(ok)
        self.assertIn("są wymagane", msg)

        # 2. Poprawne logowanie z zamockowaną klasą Librus
        with patch('librus2mail.librus.Librus') as mock_librus_cls:
            mock_inst = mock_librus_cls.return_value
            mock_inst.logged = True
            ok, msg = check_librus_credentials("student1", "secret")
            self.assertTrue(ok)
            self.assertIn("powiodło się pomyślnie", msg)

        # 3. Błąd autoryzacji (NotLogged)
        with patch('librus2mail.librus.Librus') as mock_librus_cls:
            mock_inst = mock_librus_cls.return_value
            mock_inst.login.side_effect = NotLogged("Niepoprawne hasło")
            ok, msg = check_librus_credentials("student1", "wrong_pass")
            self.assertFalse(ok)
            self.assertIn("Błąd autoryzacji: Niepoprawne hasło", msg)

        # 4. Inny wyjątek
        with patch('librus2mail.librus.Librus') as mock_librus_cls:
            mock_inst = mock_librus_cls.return_value
            mock_inst.login.side_effect = ConnectionError("Serwer nie odpowiada")
            ok, msg = check_librus_credentials("student1", "pass")
            self.assertFalse(ok)
            self.assertIn("Błąd połączenia z portalem Librus", msg)

        # 5. Test endpointu API /api/test-librus
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()

        with patch('librus2mail.web.app.test_librus_credentials', return_value=(True, "OK!")):
            res_api = client.post(
                '/api/test-librus',
                data={'login': 'test_user', 'password': 'test_password'},
            )
            self.assertEqual(res_api.status_code, 200)
            data = res_api.get_json()
            self.assertTrue(data.get('success'))
            self.assertEqual(data.get('message'), "OK!")

    def test_setup_wizard_submit_flow(self):
        """Weryfikuje wypełnienie kreatora /setup, zapisanie pliku config.yaml i odblokowanie aplikacji."""
        new_config_path = os.path.join(self.temp_dir, 'fresh_config.yaml')
        # Plik początkowo nie istnieje
        app = create_app(config_path=new_config_path, storage_dir=self.storage_dir, no_auth=True, enable_csrf=False)
        client = app.test_client()

        # Użytkownik przesyła formularz kreatora
        form_data = {
            'student_login_0': '987654',
            'student_name_0': 'Zosia Nowak',
            'student_password_0': 'haslo_zosia',
            'student_receivers_0': 'mama@example.com',
            'student_grades_0': 'on',
            'student_timetable_0': 'on',
            'student_schedule_0': 'on',
            'student_messages_0': 'on',
            'student_report_enabled_0': 'on',
            'student_report_email_0': 'zosia.nowak@szkola.edu.pl',
            'student_report_template_0': 'teens',
            'mail_provider': 'gmail',
            'mail_login': 'rodzic@gmail.com',
            'mail_password': 'tajne_haslo_app',
            'collection_mode': 'daily',
            'collection_time': '16:00',
            'collection_days': 'all',
            'report_name_0': 'Raport tygodniowy',
            'report_enabled_0': 'on',
            'report_frequency_0': 'weekly',
            'report_weekday_0': 'friday',
            'report_time_0': '17:00',
            'report_interval_days_0': '7',
            'report_name_1': 'Raport miesięczny',
            'report_enabled_1': 'on',
            'report_frequency_1': 'monthly',
            'report_day_of_month_1': '1',
            'report_time_1': '18:00',
            'report_interval_days_1': '30',
            'web_password': 'PanelPassword123',
        }
        res_post = client.post('/setup', data=form_data, follow_redirects=False)
        self.assertEqual(res_post.status_code, 302)
        self.assertEqual(res_post.headers.get('Location'), '/')

        # Sprawdzenie utworzenia pliku konfiguracyjnego
        self.assertTrue(os.path.isfile(new_config_path))
        import yaml
        with open(new_config_path, encoding='utf-8') as f:
            saved_cfg = yaml.safe_load(f)

        self.assertEqual(len(saved_cfg['librus_users']), 1)
        self.assertEqual(saved_cfg['librus_users'][0]['librus_login'], '987654')
        self.assertEqual(saved_cfg['librus_users'][0]['librus_login_name'], 'Zosia Nowak')
        self.assertEqual(saved_cfg['librus_users'][0]['librus_password'], 'haslo_zosia')
        self.assertIn('student_report', saved_cfg['librus_users'][0])
        self.assertTrue(saved_cfg['librus_users'][0]['student_report']['enabled'])
        self.assertEqual(saved_cfg['librus_users'][0]['student_report']['email'], 'zosia.nowak@szkola.edu.pl')
        self.assertEqual(saved_cfg['librus_users'][0]['student_report']['template'], 'teens')
        self.assertEqual(saved_cfg['mail']['login'], 'rodzic@gmail.com')
        self.assertTrue(saved_cfg['mail']['use_gmail'])
        self.assertEqual(saved_cfg['web']['password'], 'PanelPassword123')
        self.assertEqual(saved_cfg['schedule']['collection']['mode'], 'daily')
        self.assertEqual(saved_cfg['schedule']['collection']['time'], '16:00')
        self.assertEqual(len(saved_cfg['schedule']['reports']), 2)
        self.assertEqual(saved_cfg['schedule']['reports'][0]['name'], 'Raport tygodniowy')
        self.assertEqual(saved_cfg['schedule']['reports'][0]['weekday'], 'friday')
        self.assertEqual(saved_cfg['schedule']['reports'][0]['interval_days'], 7)
        self.assertEqual(saved_cfg['schedule']['reports'][1]['name'], 'Raport miesięczny')
        self.assertEqual(saved_cfg['schedule']['reports'][1]['frequency'], 'monthly')
        self.assertEqual(saved_cfg['schedule']['reports'][1]['interval_days'], 30)
        self.assertTrue(saved_cfg['work_in_loop'])
        self.assertTrue(saved_cfg.get('one_summary_message'))
        self.assertTrue(saved_cfg['librus_users'][0].get('one_summary_message'))

        # Kolejne zapytanie do / nie jest już przekierowywane do /setup
        res_after = client.get('/', follow_redirects=False)
        self.assertEqual(res_after.status_code, 200)
        self.assertIn(b'Zosia Nowak', res_after.data)

    def test_settings_view_and_save(self):
        """Weryfikuje widok /ustawienia, zapis zmian oraz zachowanie dotychczasowych haseł."""
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()

        # 1. GET /ustawienia
        res_get = client.get('/ustawienia')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b'Ustawienia Systemu', res_get.data)
        self.assertIn(b'Jan Kowalski', res_get.data)
        self.assertIn(b'/akcje', res_get.data)
        self.assertIn('Zaawansowane akcje i narzędzia CLI'.encode(), res_get.data)
        self.assertNotIn('⚡ Akcje CLI'.encode(), res_get.data)  # Wyczyszczone z navbaru

        # 2. POST /ustawienia z pustym hasłem (powinno zachować stare) i nową nazwą
        post_data = {
            'student_login_0': '123456',
            'student_name_0': 'Janek Kowalski (zaktualizowany)',
            'student_password_0': '',  # puste hasło -> zachowanie 'secret_pass'
            'student_receivers_0': 'rodzic@example.com',
            'mail_provider': 'gmail',
            'mail_login': 'janek.rodzic@gmail.com',
            'mail_password': '',  # puste -> brak zmiany
            'student_report_enabled_0': 'on',
            'student_report_email_0': 'janek.mlody@szkola.edu.pl',
            'student_report_template_0': 'youth',
            'collection_mode': 'interval',
            'collection_interval_hours': '2',
            'report_name_0': 'Raport tygodniowy',
            'report_enabled_0': 'on',
            'report_frequency_0': 'weekly',
            'report_weekday_0': 'friday',
            'report_time_0': '17:00',
            'report_interval_days_0': '7',
            'semester_split_date': '2027-02-15',
            'annual_grade_algorithm': 'progress_favored',
            'web_password': '',  # puste -> zachowanie starego
        }
        res_save = client.post('/ustawienia', data=post_data, follow_redirects=True)
        self.assertEqual(res_save.status_code, 200)
        self.assertIn('Ustawienia zostały pomyślnie zaktualizowane'.encode(), res_save.data)

        # Sprawdzenie utworzenia kopii zapasowej .bak
        bak_path = self.config_path + '.bak'
        self.assertTrue(os.path.isfile(bak_path))

        # Sprawdzenie zawartości pliku config.yaml
        import yaml
        with open(self.config_path, encoding='utf-8') as f:
            updated_cfg = yaml.safe_load(f)

        self.assertEqual(updated_cfg['librus_users'][0]['librus_login_name'], 'Janek Kowalski (zaktualizowany)')
        self.assertEqual(updated_cfg['librus_users'][0]['librus_password'], 'secret_pass')
        self.assertIn('student_report', updated_cfg['librus_users'][0])
        self.assertTrue(updated_cfg['librus_users'][0]['student_report']['enabled'])
        self.assertEqual(updated_cfg['librus_users'][0]['student_report']['email'], 'janek.mlody@szkola.edu.pl')
        self.assertEqual(updated_cfg['librus_users'][0]['student_report']['template'], 'youth')
        self.assertEqual(updated_cfg['schedule']['collection']['mode'], 'interval')
        self.assertEqual(updated_cfg['schedule']['collection']['interval_hours'], 2)
        self.assertEqual(updated_cfg['schedule']['reports'][0]['interval_days'], 7)
        self.assertEqual(updated_cfg['wait_time_s'], 7200)
        self.assertEqual(updated_cfg['web']['password'], 'SuperParentPassword')
        self.assertTrue(updated_cfg.get('one_summary_message'))
        self.assertTrue(updated_cfg['librus_users'][0].get('one_summary_message'))
        self.assertEqual(updated_cfg.get('semester_split_date'), '2027-02-15')
        self.assertEqual(updated_cfg.get('annual_grade_algorithm'), 'progress_favored')

        # 3. Zmiana dostawcy na SMTP ukrywa wskazówkę Gmaila (klasa hidden)
        post_data_smtp = dict(post_data)
        post_data_smtp['mail_provider'] = 'smtp'
        post_data_smtp['smtp_host'] = 'smtp.test.pl'
        res_smtp = client.post('/ustawienia', data=post_data_smtp, follow_redirects=True)
        self.assertEqual(res_smtp.status_code, 200)
        self.assertIn(b'id="gmail-settings-tip-box" class="hidden', res_smtp.data)

        # 4. Wyłączenie zbiorczego podsumowania (przełączenie na osobne maile)
        post_data_sep = dict(post_data)
        post_data_sep['one_summary_message'] = '0'
        res_sep = client.post('/ustawienia', data=post_data_sep, follow_redirects=True)
        self.assertEqual(res_sep.status_code, 200)
        with open(self.config_path, encoding='utf-8') as f:
            sep_cfg = yaml.safe_load(f)
        self.assertFalse(sep_cfg.get('one_summary_message'))
        self.assertFalse(sep_cfg['librus_users'][0].get('one_summary_message'))

    def test_multiple_reports_schedule_configuration_and_storage(self):
        """Testuje konfigurację wielu zaplanowanych raportów (tygodniowy i miesięczny) oraz izolację w storage."""
        from librus2mail.config import get_reports_schedules
        from librus2mail.web.app import parse_schedule_from_form

        # 1. Parsowanie formularza z dwoma raportami (weekly i monthly)
        form_payload = {
            'collection_mode': 'daily',
            'collection_time': '16:00',
            'collection_days': 'workdays',
            'report_name_0': 'Podsumowanie tygodnia',
            'report_enabled_0': 'on',
            'report_frequency_0': 'weekly',
            'report_weekday_0': 'friday',
            'report_time_0': '17:00',
            'report_interval_days_0': '7',
            'report_name_1': 'Raport miesięczny',
            'report_enabled_1': 'on',
            'report_frequency_1': 'monthly',
            'report_day_of_month_1': '1',
            'report_time_1': '18:00',
            'report_interval_days_1': '30',
        }
        sched_cfg, wait_s = parse_schedule_from_form(form_payload)
        self.assertEqual(sched_cfg['collection']['mode'], 'daily')
        self.assertEqual(len(sched_cfg['reports']), 2)
        self.assertEqual(sched_cfg['reports'][0]['name'], 'Podsumowanie tygodnia')
        self.assertEqual(sched_cfg['reports'][0]['frequency'], 'weekly')
        self.assertEqual(sched_cfg['reports'][0]['interval_days'], 7)
        self.assertEqual(sched_cfg['reports'][1]['name'], 'Raport miesięczny')
        self.assertEqual(sched_cfg['reports'][1]['frequency'], 'monthly')
        self.assertEqual(sched_cfg['reports'][1]['day_of_month'], 1)
        self.assertEqual(sched_cfg['reports'][1]['interval_days'], 30)

        # 2. Test get_reports_schedules z różnymi formatami
        reps = get_reports_schedules({'schedule': sched_cfg})
        self.assertEqual(len(reps), 2)
        single_rep_list = get_reports_schedules({'schedule': {'reports': [{'name': 'Raport piątkowy', 'weekday': 'friday', 'interval_days': 7}]}})
        self.assertEqual(len(single_rep_list), 1)
        self.assertEqual(single_rep_list[0]['interval_days'], 7)

        # 3. Test izolacji znaczników czasu w storage per report_key
        storage = get_storage(self.mock_config, self.storage_dir)
        user = '123456'
        t_weekly = "2026-10-02T17:00:00"
        t_monthly = "2026-10-01T18:00:00"

        storage.save_last_progress_report_date(user, t_weekly, report_key='rep_weekly_7_17:00')
        storage.save_last_progress_report_date(user, t_monthly, report_key='rep_monthly_30_18:00')

        self.assertEqual(storage.get_last_progress_report_date(user, report_key='rep_weekly_7_17:00'), t_weekly)
        self.assertEqual(storage.get_last_progress_report_date(user, report_key='rep_monthly_30_18:00'), t_monthly)
        self.assertEqual(storage.get_last_progress_report_date(user), t_monthly)

    def test_setup_and_settings_with_gmail_oauth2(self):
        """Weryfikuje konfigurację wysyłki Gmail przez OAuth2 w /setup oraz /ustawienia."""
        import yaml
        new_config_path = os.path.join(self.temp_dir, 'oauth_config.yaml')
        app = create_app(config_path=new_config_path, storage_dir=self.storage_dir, no_auth=True, enable_csrf=False)
        client = app.test_client()

        # 1. Przesłanie formularza kreatora /setup z Gmail OAuth2
        form_data = {
            'student_login_0': '111222',
            'student_name_0': 'Kacper',
            'student_password_0': 'haslo_kacper',
            'student_receivers_0': 'rodzic@gmail.com',
            'mail_provider': 'gmail',
            'gmail_auth_mode': 'oauth2',
            'gmail_oauth2_file': 'custom_yagmail_creds.json',
            'mail_login': 'rodzic@gmail.com',
            'web_password': 'Haslo',
        }
        res = client.post('/setup', data=form_data, follow_redirects=False)
        self.assertEqual(res.status_code, 302)

        with open(new_config_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f)

        self.assertTrue(cfg['mail']['use_gmail'])
        self.assertEqual(cfg['mail']['login'], 'rodzic@gmail.com')
        self.assertEqual(cfg['mail']['oauth2_file'], 'custom_yagmail_creds.json')
        self.assertNotIn('password', cfg['mail'])

        # 2. Aktualizacja w /ustawienia z powrotem na hasło aplikacji
        res_settings = client.post('/ustawienia', data={
            'student_login_0': '111222',
            'student_name_0': 'Kacper',
            'student_receivers_0': 'rodzic@gmail.com',
            'mail_provider': 'gmail',
            'gmail_auth_mode': 'app_password',
            'mail_login': 'rodzic@gmail.com',
            'mail_password': 'nowe_haslo_app_123',
        }, follow_redirects=False)
        self.assertEqual(res_settings.status_code, 302)

        with open(new_config_path, encoding='utf-8') as f:
            updated_cfg = yaml.safe_load(f)

        self.assertTrue(updated_cfg['mail']['use_gmail'])
        self.assertEqual(updated_cfg['mail']['password'], 'nowe_haslo_app_123')
        self.assertNotIn('oauth2_file', updated_cfg['mail'])

    def test_schedule_view_day_selection(self):
        """Weryfikuje inteligentny wybór dnia w /plan (trwające lekcje vs nadchodzący dzień nauki)."""
        storage = get_storage(self.mock_config, self.storage_dir)
        # Dodaj lekcje na 2026-09-24
        storage.save_schedule_entries('123456', [
            {
                'id': 'l_next_1',
                'date': '2026-09-24',
                'lesson_no': 1,
                'time_from': '08:00',
                'time_to': '08:45',
                'subject': 'Biologia',
                'teacher': 'E. Nowak',
                'classroom': '5',
                'is_substitution': False,
                'is_cancelled': False,
            }
        ])

        # 1. Podczas trwania lekcji w bieżącym dniu (2026-09-23 09:15) -> domyślnie dzień bieżący
        app_ongoing = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            actual_date=datetime(2026, 9, 23, 9, 15, 0),
        )
        client_ongoing = app_ongoing.test_client()
        res_ongoing = client_ongoing.get('/plan')
        self.assertEqual(res_ongoing.status_code, 200)
        self.assertIn(b'2026-09-23', res_ongoing.data)
        ongoing_html = res_ongoing.data.decode('utf-8')
        self.assertIn('Dzisiaj (lekcje w toku)', ongoing_html)
        self.assertIn('TRWA TERAZ', ongoing_html)
        self.assertIn('Odbyła się', ongoing_html)
        self.assertIn('Lekcja w toku', ongoing_html)

        # 1b. Podczas przerwy między lekcjami (2026-09-23 08:50) -> informacja o przerwie
        app_break = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            actual_date=datetime(2026, 9, 23, 8, 50, 0),
        )
        res_break = app_break.test_client().get('/plan')
        self.assertEqual(res_break.status_code, 200)
        break_html = res_break.data.decode('utf-8')
        self.assertIn('Trwa przerwa między lekcjami', break_html)
        self.assertIn('Dzwonek za 5 min', break_html)

        # 1c. Przed rozpoczęciem lekcji w bieżącym dniu (2026-09-23 00:28 - w nocy / rano przed 08:00)
        app_before = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            actual_date=datetime(2026, 9, 23, 0, 28, 0),
        )
        res_before = app_before.test_client().get('/plan')
        self.assertEqual(res_before.status_code, 200)
        before_html = res_before.data.decode('utf-8')
        self.assertIn('Dzisiaj (przed lekcjami', before_html)
        self.assertNotIn('Dzisiaj (lekcje w toku)', before_html)
        self.assertNotIn('TRWA TERAZ', before_html)
        self.assertNotIn('Odbyła się', before_html)

        # 2. Po zakończeniu lekcji w bieżącym dniu (2026-09-23 12:00) -> domyślnie kolejny dzień nauki (2026-09-24)
        app_finished = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            actual_date=datetime(2026, 9, 23, 12, 0, 0),
        )
        client_finished = app_finished.test_client()
        res_finished = client_finished.get('/plan')
        self.assertEqual(res_finished.status_code, 200)
        self.assertIn(b'2026-09-24', res_finished.data)
        self.assertIn('Nadchodzący dzień nauki', res_finished.data.decode('utf-8'))

        # 3. Jawne podanie daty w query param ?date=2026-09-23
        res_param = client_finished.get('/plan?date=2026-09-23')
        self.assertEqual(res_param.status_code, 200)
        self.assertIn(b'Matematyka', res_param.data)
        self.assertIn(b'Geografia', res_param.data)
        self.assertIn(b'id="schedule-calendar-date"', res_param.data)
        self.assertIn(b'type="date"', res_param.data)
        self.assertIn(b'value="2026-09-23"', res_param.data)

        # 3b. Wybór historycznego dnia z kalendarza bez wpisów (?date=2026-08-15)
        res_empty_day = client_finished.get('/plan?date=2026-08-15')
        self.assertEqual(res_empty_day.status_code, 200)
        self.assertIn(b'value="2026-08-15"', res_empty_day.data)
        self.assertIn('Brak lekcji w planie dla tego dnia', res_empty_day.data.decode('utf-8'))

        # 4. Widok wszystkich dni (?view=all)
        res_all = client_finished.get('/plan?view=all')
        self.assertEqual(res_all.status_code, 200)
        self.assertIn(b'Biologia', res_all.data)
        self.assertIn(b'Matematyka', res_all.data)

        # 5. Weryfikacja spójności dla pulpitu głównego (/) - trwające lekcje
        res_dash_ongoing = client_ongoing.get('/')
        self.assertEqual(res_dash_ongoing.status_code, 200)
        self.assertIn('Dzisiaj (lekcje w toku)', res_dash_ongoing.data.decode('utf-8'))
        self.assertIn('Matematyka', res_dash_ongoing.data.decode('utf-8'))

        # 6. Weryfikacja dla pulpitu głównego (/) - po zakończeniu lekcji
        res_dash_finished = client_finished.get('/')
        self.assertEqual(res_dash_finished.status_code, 200)
        self.assertIn('Nadchodzący dzień nauki', res_dash_finished.data.decode('utf-8'))
        self.assertIn('Biologia', res_dash_finished.data.decode('utf-8'))
        self.assertIn('Poprzedni dzień', res_dash_finished.data.decode('utf-8'))

        # 7. Nawigacja parametrem ?date= na pulpicie
        res_dash_param = client_finished.get('/?date=2026-09-23')
        self.assertEqual(res_dash_param.status_code, 200)
        self.assertIn('Matematyka', res_dash_param.data.decode('utf-8'))

    def test_background_collector_lifecycle(self):
        """Testuje uruchamianie wątku harmonogramu w tle w module webowym."""
        import threading
        from unittest.mock import patch

        from librus2mail.web.app import create_app, start_background_collector

        with patch('librus2mail.web.app.run_collector') as mock_run:
            mock_run.side_effect = Exception("Stop loop for test")
            with patch('threading.Thread.start') as mock_start, patch.object(threading.Thread, 'is_alive', return_value=True):
                thread = start_background_collector(
                    config_path=self.config_path,
                    storage_dir=self.storage_dir,
                )
                self.assertIsNotNone(thread)
                self.assertEqual(thread.name, "LibrusCollectorThread")
                self.assertTrue(thread.daemon)
                mock_start.assert_called_once()

                # Ponowne wywołanie powinno zwrócić ten sam wątek (singleton)
                thread2 = start_background_collector(
                    config_path=self.config_path,
                    storage_dir=self.storage_dir,
                )
                self.assertEqual(thread, thread2)

        # Test wywołania create_app z flagą run_collector_thread
        with patch('librus2mail.web.app.start_background_collector') as mock_start_bg:
            app = create_app(
                config_path=self.config_path,
                storage_dir=self.storage_dir,
                no_auth=True,
                run_collector_thread=True,
            )
            self.assertIsNotNone(app)
            mock_start_bg.assert_called_once_with(
                config_path=self.config_path,
                storage_dir=self.storage_dir,
            )

    def test_messages_and_announcements_sorted_by_date_descending(self):
        """Weryfikuje, że w dziale Wiadomości zarówno wiadomości, jak i ogłoszenia są sortowane od najnowszych."""
        storage = get_storage(self.mock_config, self.storage_dir)

        # Zapisujemy wiadomości w kolejności niechronologicznej (stara, najnowsza, średnia)
        raw_msgs = [
            {'id': 'msg_old', 'title': 'Wiadomość Wrzesień', 'sender': 'Nauczyciel A', 'datetime': '2026-09-05 10:00:00'},
            {'id': 'msg_newest', 'title': 'Wiadomość Dzisiaj', 'sender': 'Nauczyciel B', 'datetime': '2026-10-09 18:30:00'},
            {'id': 'msg_mid', 'title': 'Wiadomość Koniec Września', 'sender': 'Nauczyciel C', 'datetime': '2026-09-28 12:15:00'},
        ]
        storage.save_messages_details('123456', raw_msgs)

        # Zapisujemy ogłoszenia w kolejności niechronologicznej
        raw_notifs = [
            {'id': 'notif_old', 'title': 'Ogłoszenie Rozpoczęcie', 'sender': 'Dyrekcja', 'datetime': '2026-09-01'},
            {'id': 'notif_newest', 'title': 'Ogłoszenie Październikowe', 'sender': 'Dyrekcja', 'datetime': '2026-10-08'},
            {'id': 'notif_mid', 'title': 'Ogłoszenie Wycieczka', 'sender': 'Wychowawca', 'datetime': '2026-09-20'},
        ]
        storage.save_notifications_details('123456', raw_notifs)

        # 1. Test na poziomie storage
        sorted_msgs = storage.get_stored_messages('123456')
        self.assertEqual(len(sorted_msgs), 3)
        self.assertEqual(sorted_msgs[0]['id'], 'msg_newest')
        self.assertEqual(sorted_msgs[1]['id'], 'msg_mid')
        self.assertEqual(sorted_msgs[2]['id'], 'msg_old')

        sorted_notifs = storage.get_stored_notifications('123456')
        self.assertEqual(len(sorted_notifs), 3)
        self.assertEqual(sorted_notifs[0]['id'], 'notif_newest')
        self.assertEqual(sorted_notifs[1]['id'], 'notif_mid')
        self.assertEqual(sorted_notifs[2]['id'], 'notif_old')

        # 2. Test integracyjny widoku /wiadomosci (kolejność w HTML)
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()
        res = client.get('/wiadomosci')
        self.assertEqual(res.status_code, 200)

        html = res.data.decode('utf-8')
        pos_msg_new = html.find('Wiadomość Dzisiaj')
        pos_msg_mid = html.find('Wiadomość Koniec Września')
        pos_msg_old = html.find('Wiadomość Wrzesień')
        self.assertTrue(pos_msg_new != -1 and pos_msg_mid != -1 and pos_msg_old != -1)
        self.assertLess(pos_msg_new, pos_msg_mid, "Najnowsza wiadomość powinna pojawić się przed średnią")
        self.assertLess(pos_msg_mid, pos_msg_old, "Średnia wiadomość powinna pojawić się przed najstarszą")

        pos_notif_new = html.find('Ogłoszenie Październikowe')
        pos_notif_mid = html.find('Ogłoszenie Wycieczka')
        pos_notif_old = html.find('Ogłoszenie Rozpoczęcie')
        self.assertTrue(pos_notif_new != -1 and pos_notif_mid != -1 and pos_notif_old != -1)
        self.assertLess(pos_notif_new, pos_notif_mid, "Najnowsze ogłoszenie powinno pojawić się przed średnim")
        self.assertLess(pos_notif_mid, pos_notif_old, "Średnie ogłoszenie powinno pojawić się przed najstarszym")

    def test_api_grade_update_and_reset(self):
        """Testuje endpointy edycji oceny/wagi oraz przywracania oryginalnych wartości."""
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()

        # 1. Walidacja błędnych danych
        res_bad = client.post('/api/grade/update', data={'grade_id': 'g1', 'grade': '5', 'weight': 'invalid'})
        self.assertEqual(res_bad.status_code, 400)

        res_neg = client.post('/api/grade/update', data={'grade_id': 'g1', 'grade': '5', 'weight': '-2'})
        self.assertEqual(res_neg.status_code, 400)

        # 2. Udana edycja oceny (np. zmiana wagi sprawdzianu z 1 na 3)
        res_ok = client.post('/api/grade/update', data={'grade_id': 'g1', 'grade': '4+', 'weight': '3'})
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.get_json()
        self.assertTrue(data['success'])

        # Sprawdzenie w widoku /oceny
        res_view = client.get('/oceny')
        self.assertEqual(res_view.status_code, 200)
        self.assertIn(b'zmieniona', res_view.data)

        # Sprawdzenie w widoku szczegółowym /oceny/Matematyka
        res_detail = client.get('/oceny/Matematyka')
        self.assertEqual(res_detail.status_code, 200)
        self.assertIn(b'zmieniona', res_detail.data)
        self.assertIn(b'edit-grade-modal', res_detail.data)
        self.assertIn(b'openEditGradeModal', res_detail.data)

        # 3. Przywrócenie ze szkoły (reset)
        res_reset = client.post('/api/grade/reset', data={'grade_id': 'g1'})
        self.assertEqual(res_reset.status_code, 200)
        data_reset = res_reset.get_json()
        self.assertTrue(data_reset['success'])

    def test_api_subject_toggle_certificate(self):
        """Testuje wykluczanie i włączanie przedmiotu do średniej ze świadectwa."""
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()

        # 1. Walidacja braku nazwy przedmiotu
        res_empty = client.post('/api/subject/toggle-certificate', data={'subject': ''})
        self.assertEqual(res_empty.status_code, 400)

        # 2. Wykluczenie przedmiotu ze średniej (np. Godzina wychowawcza lub Język polski)
        res_ex = client.post('/api/subject/toggle-certificate', data={'subject': 'Język polski', 'included': 'false'})
        self.assertEqual(res_ex.status_code, 200)
        data_ex = res_ex.get_json()
        self.assertTrue(data_ex['success'])
        self.assertFalse(data_ex['included'])
        self.assertIn('Język polski', data_ex['excluded_subjects'])

        # 3. Sprawdzenie widoku /oceny - etykieta "Nie zaliczany do średniej" musi się pojawić
        res_view = client.get('/oceny')
        self.assertEqual(res_view.status_code, 200)
        self.assertIn('Nie zaliczany do średniej'.encode(), res_view.data)

        # Sprawdzenie w zakładce świadectwo (powinna być widoczna sekcja na dole tabeli)
        res_swiad = client.get('/oceny?tab=swiadectwo')
        self.assertEqual(res_swiad.status_code, 200)
        self.assertIn('Nie zaliczane do średniej'.encode(), res_swiad.data)
        self.assertIn('poza średnią'.encode(), res_swiad.data)

        # 4. Ponowne włączenie przedmiotu
        res_inc = client.post('/api/subject/toggle-certificate', data={'subject': 'Język polski', 'included': 'true'})
        self.assertEqual(res_inc.status_code, 200)
        data_inc = res_inc.get_json()
        self.assertTrue(data_inc['success'])
        self.assertTrue(data_inc['included'])
        self.assertNotIn('Język polski', data_inc['excluded_subjects'])

    def test_subject_detail_view_success(self):
        """Testuje szczegółowy widok przedmiotu z wykresem, statystykami i analizą celów."""
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()

        res = client.get('/oceny/Matematyka')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Matematyka', res.data)
        html_text = res.data.decode('utf-8')
        self.assertIn('Dział raportów: Trajektoria ocen w czasie ze średnią kroczącą', html_text)
        self.assertIn('Dział raportów', html_text)
        self.assertIn('Śr. ważona', html_text)
        self.assertIn('Szansa na podwyższenie oceny', html_text)
        self.assertIn('Margines bezpieczeństwa & ryzyko', html_text)
        self.assertIn('Interaktywny symulator nowej oceny z przedmiotu', html_text)
        self.assertIn('Rozkład ocen (Histogram)', html_text)
        self.assertIn('Wszystkie oceny cząstkowe z przedmiotu', html_text)

        # Weryfikacja nowych modułów analitycznych
        self.assertIn('Stabilność', html_text)
        self.assertIn('Tempo ocen', html_text)
        self.assertIn('Wpływ pojedynczych ocen na średnią ważoną', html_text)
        self.assertIn('Lokomotywy średniej', html_text)
        self.assertIn('Kotwice średniej', html_text)
        self.assertIn('Skuteczność wg formy sprawdzania wiedzy', html_text)
        self.assertIn('thresholdBandsPlugin', html_text)
        self.assertIn('initCategoryRadarChart', html_text)

    def test_subject_detail_przedmiot_alias(self):
        """Testuje działanie aliasu URL /przedmiot/<nazwa>."""
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()

        res = client.get('/przedmiot/Matematyka')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Matematyka', res.data)
        self.assertIn('Dział raportów', res.data.decode('utf-8'))

    def test_subject_detail_no_grades(self):
        """Testuje zachowanie widoku szczegółowego dla przedmiotu bez ocen."""
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()

        res = client.get('/oceny/Informatyka')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Brak zarejestrowanych ocen dla tego przedmiotu', res.data.decode('utf-8'))

    def test_get_subject_detailed_analytics_function(self):
        """Testuje bezpośrednio logikę get_subject_detailed_analytics w services.py."""
        from src.librus2mail.web.services import get_subject_detailed_analytics

        sample_grades = [
            {'id': '1', 'subject': 'Fizyka', 'grade': '3', 'weight': '2', 'date': '2026-09-10', 'category': 'Sprawdzian'},
            {'id': '2', 'subject': 'Fizyka', 'grade': '4', 'weight': '2', 'date': '2026-09-15', 'category': 'Kartkówka'},
            {'id': '3', 'subject': 'Fizyka', 'grade': '5', 'weight': '3', 'date': '2026-09-20', 'category': 'Odpowiedź ustna'},
            {'id': '4', 'subject': 'Chemia', 'grade': '6', 'weight': '1', 'date': '2026-09-22', 'category': 'Sprawdzian'},
        ]

        analytics = get_subject_detailed_analytics(sample_grades, 'Fizyka')
        self.assertEqual(analytics['subject'], 'Fizyka')
        self.assertEqual(analytics['total_count'], 3)
        self.assertEqual(analytics['numeric_count'], 3)
        self.assertIsNotNone(analytics['average'])
        self.assertAlmostEqual(analytics['average'], 4.14, places=2)
        self.assertEqual(analytics['min_grade'], 3.0)
        self.assertEqual(analytics['max_grade'], 5.0)
        self.assertEqual(analytics['median_grade'], 4.0)

        # Sprawdzenie osi czasu (timeline)
        timeline = analytics['timeline_data']
        self.assertEqual(len(timeline), 3)
        self.assertEqual(timeline[0]['running_average'], 3.0)
        self.assertEqual(timeline[1]['running_average'], 3.5)
        self.assertAlmostEqual(timeline[2]['running_average'], 4.14, places=2)

        # Sprawdzenie analizy celu podwyższenia
        target = analytics['target_analysis']
        self.assertTrue(target['has_target'])
        self.assertEqual(target['target_grade_num'], 5)
        self.assertGreater(len(target['scenarios']), 0)

        # Sprawdzenie analizy ryzyka
        risk = analytics['risk_analysis']
        self.assertTrue(risk['has_risk'])
        self.assertEqual(risk['lower_grade_num'], 3)
        self.assertIn('drop_simulations', risk)

        # Sprawdzenie analizy skuteczności wg kategorii (Category Analytics & Radar Chart)
        cat_analytics = analytics['category_analytics']
        self.assertTrue(cat_analytics['has_data'])
        self.assertEqual(len(cat_analytics['categories']), 3)
        self.assertEqual(len(cat_analytics['radar_labels']), 3)
        self.assertEqual(len(cat_analytics['radar_averages']), 3)
        self.assertIsNotNone(cat_analytics['best_category'])
        self.assertIsNotNone(cat_analytics['worst_category'])
        self.assertIn('insight', cat_analytics)

        # Sprawdzenie analizy wpływu (Impact Analysis: Boosters & Draggers)
        impact = analytics['impact_analysis']
        self.assertTrue(impact['has_data'])
        self.assertGreater(len(impact['boosters']), 0)
        self.assertGreater(len(impact['draggers']), 0)
        # Najwyższa ocena (5) powinna być boosterem
        self.assertEqual(impact['boosters'][0]['grade'], '5')
        self.assertGreater(impact['boosters'][0]['delta'], 0)
        # Najniższa ocena (3) powinna być draggerem
        self.assertEqual(impact['draggers'][0]['grade'], '3')
        self.assertLess(impact['draggers'][0]['delta'], 0)
        self.assertGreater(impact['draggers'][0]['gain_if_5'], 0)

        # Sprawdzenie stabilności formy (Consistency Metrics)
        consistency = analytics['consistency_metrics']
        self.assertTrue(consistency['has_data'])
        self.assertIsNotNone(consistency['score'])
        self.assertGreaterEqual(consistency['score'], 0)
        self.assertLessEqual(consistency['score'], 100)
        self.assertIn(consistency['status'], ['high', 'moderate', 'low'])
        self.assertGreater(consistency['stdev'], 0)
        self.assertIn('Wskaźnik stabilności formy', consistency['desc'])
        self.assertIn('odchylenia standardowego', consistency['desc'])
        self.assertIn('Diagnoza:', consistency['desc'])

        # Sprawdzenie tempa i estymacji (Pacing Metrics)
        pacing = analytics['pacing_metrics']
        self.assertTrue(pacing['has_data'])
        self.assertGreater(pacing['days_per_grade'], 0)
        self.assertGreaterEqual(pacing['estimated_remaining'], 0)

        # Test scenariusza z głębszym spadkiem (wyjściowa ocena 5 spadająca do 3 po 1 z wagą 3)
        sample_high = [
            {'id': '10', 'subject': 'Biologia', 'grade': '5', 'weight': '2', 'date': '2026-09-10'},
            {'id': '11', 'subject': 'Biologia', 'grade': '5', 'weight': '2', 'date': '2026-09-15'},
        ]
        analytics_high = get_subject_detailed_analytics(sample_high, 'Biologia')
        risk_high = analytics_high['risk_analysis']
        sim_3w = next(d for d in risk_high['drop_simulations'] if d['test_grade'] == 1 and d['test_weight'] == 3)
        self.assertEqual(sim_3w['sim_grade_num'], 3)
        self.assertIn('spadek do 3 (dostateczny)', sim_3w['desc'])

    def test_api_subject_set_category(self):
        """Testuje endpoint POST /api/subject/set-category do zmiany kategorii przedmiotu."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            actual_date='2026-09-22',
        )
        client = app.test_client()

        # 1. Błędne żądanie bez nazwy przedmiotu
        res_bad = client.post('/api/subject/set-category', json={'category': 'scisle'})
        self.assertEqual(res_bad.status_code, 400)
        self.assertFalse(res_bad.get_json()['success'])

        # 2. Poprawna zmiana kategorii przez JSON
        res_ok = client.post('/api/subject/set-category', json={'subject': 'Matematyka', 'category': 'humanistyczne'})
        self.assertEqual(res_ok.status_code, 200)
        data = res_ok.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['subject'], 'Matematyka')
        self.assertEqual(data['category'], 'humanistyczne')
        self.assertEqual(data['categories'].get('Matematyka'), 'humanistyczne')

        # 3. Sprawdzenie w storage
        storage = get_storage(self.mock_config, self.storage_dir)
        cats = storage.get_subject_categories('123456')
        self.assertEqual(cats.get('Matematyka'), 'humanistyczne')

        # 4. Przywrócenie domyślnej kategorii przez wysłanie 'default'
        res_reset = client.post('/api/subject/set-category', data={'subject': 'Matematyka', 'category': 'default'})
        self.assertEqual(res_reset.status_code, 200)
        self.assertNotIn('Matematyka', res_reset.get_json()['categories'])
        self.assertNotIn('Matematyka', storage.get_subject_categories('123456'))

    def test_storage_subject_categories(self):
        """Testuje bezpośrednio metody get_subject_categories i set_subject_category w FileStorage."""
        storage = get_storage(self.mock_config, self.storage_dir)
        self.assertEqual(storage.get_subject_categories('123456'), {})

        # Ustawienie kategorii
        updated = storage.set_subject_category('123456', 'Fizyka', 'scisle')
        self.assertEqual(updated, {'Fizyka': 'scisle'})
        self.assertEqual(storage.get_subject_categories('123456'), {'Fizyka': 'scisle'})

        # Usunięcie (None lub 'default')
        updated_none = storage.set_subject_category('123456', 'Fizyka', None)
        self.assertEqual(updated_none, {})
        self.assertEqual(storage.get_subject_categories('123456'), {})

    def test_classify_subject_and_educational_profile(self):
        """Testuje kategoryzację przedmiotów oraz profil i balans ucznia."""
        # 1. Automatyczna klasyfikacja po słowach kluczowych
        self.assertEqual(classify_subject('Matematyka'), 'scisle')
        self.assertEqual(classify_subject('Język polski'), 'humanistyczne')
        self.assertEqual(classify_subject('Język angielski'), 'jezyki')
        self.assertEqual(classify_subject('Wychowanie fizyczne'), 'ruch_i_sztuka')
        self.assertEqual(classify_subject('Informatyka'), 'scisle')
        self.assertEqual(classify_subject('Historia'), 'humanistyczne')
        self.assertEqual(classify_subject('Nietypowy przedmiot'), 'inne')

        # 2. Nadpisania użytkownika
        overrides = {'Nietypowy przedmiot': 'scisle', 'Matematyka': 'humanistyczne'}
        self.assertEqual(classify_subject('Nietypowy przedmiot', overrides), 'scisle')
        self.assertEqual(classify_subject('Matematyka', overrides), 'humanistyczne')

        # 3. compute_educational_profile
        subject_averages = [
            {'subject': 'Matematyka', 'average': 4.5, 'grades_count': 3},
            {'subject': 'Fizyka', 'average': 5.0, 'grades_count': 2},
            {'subject': 'Język polski', 'average': 3.5, 'grades_count': 4},
            {'subject': 'Język angielski', 'average': 4.0, 'grades_count': 2},
            {'subject': 'WF', 'average': 6.0, 'grades_count': 1},
        ]
        profile = compute_educational_profile(subject_averages, overrides={'WF': 'ruch_i_sztuka'})
        self.assertIn('profile_groups', profile)
        self.assertIn('radar_chart', profile)
        self.assertIn('dominant_category', profile)
        self.assertIn('growth_category', profile)
        self.assertEqual(len(profile['radar_chart']['labels']), 4)
        # Ścisłe średnia: (4.5 + 5.0) / 2 = 4.75
        stem_group = next(g for g in profile['profile_groups'] if g['key'] == 'scisle')
        self.assertAlmostEqual(stem_group['average'], 4.75, places=2)
        self.assertEqual(len(stem_group['subjects']), 2)

    def test_goal_optimizer(self):
        """Testuje Optymalizator Celu (ROI i plan działania)."""
        subject_averages = [
            {'subject': 'Matematyka', 'average': 4.60, 'total_weight': 10.0, 'grades_count': 5},
            {'subject': 'Fizyka', 'average': 3.70, 'total_weight': 4.0, 'grades_count': 2},
            {'subject': 'Historia', 'average': 3.10, 'total_weight': 2.0, 'grades_count': 1},
        ]
        res = calculate_goal_optimizer(subject_averages, target_grade=5.0)
        self.assertEqual(res['target_grade'], 5.0)
        self.assertTrue(res['has_candidates'])
        self.assertGreater(len(res['candidates']), 0)
        mat = next((c for c in res['candidates'] if c['subject'] == 'Matematyka'), None)
        self.assertIsNotNone(mat)
        self.assertEqual(mat['target_proposal'], 5)
        self.assertGreater(mat['gap'], 0)
        self.assertIsNotNone(mat['min_grade_needed'])

    def test_opportunity_matrix(self):
        """Testuje Matrycę Szans i Ryzyk (Quick Wins, Zagrożenia, Bezpieczny bufor, Interwencja)."""
        subject_averages = [
            {'subject': 'Biologia', 'average': 4.65, 'total_weight': 10.0, 'grades_count': 5},
            {'subject': 'Chemia', 'average': 3.76, 'total_weight': 8.0, 'grades_count': 4},
            {'subject': 'Fizyka', 'average': 2.10, 'total_weight': 4.0, 'grades_count': 2},
        ]
        matrix = compute_opportunity_matrix(subject_averages)
        self.assertIn('quick_wins', matrix)
        self.assertIn('drop_risks', matrix)
        self.assertIn('safe', matrix)
        self.assertIn('intervention', matrix)
        self.assertIn('matrix_items', matrix)

        qw_subjects = [q['subject'] for q in matrix['quick_wins']]
        self.assertIn('Biologia', qw_subjects)

        risk_subjects = [r['subject'] for r in matrix['drop_risks']]
        self.assertIn('Chemia', risk_subjects)

        safe_subjects = [s['subject'] for s in matrix['safe']]
        self.assertIn('Biologia', safe_subjects)
        bio_safe = next(s for s in matrix['safe'] if s['subject'] == 'Biologia')
        self.assertIn('resilience_desc', bio_safe)
        self.assertGreater(bio_safe['buffer'], 0.12)

        interv_subjects = [i['subject'] for i in matrix['intervention']]
        self.assertIn('Fizyka', interv_subjects)

        # Test małej próby i znaków nieliczbowych (np. Historia z 1 oceną 6 i 2 plusami)
        historia_case = [
            {
                'subject': 'Historia',
                'average': 6.0,
                'sum_weights': 1.0,
                'numeric_count': 1,
                'count': 3,  # 1 ocena + 2 plusy
            }
        ]
        hist_matrix = compute_opportunity_matrix(historia_case)
        hist_safe = next(s for s in hist_matrix['safe'] if s['subject'] == 'Historia')
        self.assertEqual(hist_safe['count'], 1)
        self.assertEqual(hist_safe['total_entries'], 3)
        self.assertTrue(hist_safe['is_preliminary'])
        self.assertEqual(hist_safe['resilience_icon'], '⏳')
        self.assertIn('brak stabilności', hist_safe['resilience_desc'])

    def test_subject_stability_benchmark(self):
        """Testuje Porównanie i Stabilność Przedmiotów (odchylenie standardowe, lokomotywy, kotwice)."""
        history = [
            {'id': '1', 'subject': 'Matematyka', 'grade': '5', 'weight': '2'},
            {'id': '2', 'subject': 'Matematyka', 'grade': '5', 'weight': '2'},
            {'id': '3', 'subject': 'Historia', 'grade': '2', 'weight': '1'},
            {'id': '4', 'subject': 'Historia', 'grade': '5', 'weight': '1'},
        ]
        averages = [
            {'subject': 'Matematyka', 'average': 5.0, 'grades_count': 2},
            {'subject': 'Historia', 'average': 3.5, 'grades_count': 2},
        ]
        benchmark = compute_subject_stability_benchmark(averages, history)
        self.assertIn('items', benchmark)
        self.assertIn('locomotives', benchmark)
        self.assertIn('anchors', benchmark)
        self.assertIn('bar_chart', benchmark)

        mat_item = next(i for i in benchmark['items'] if i['subject'] == 'Matematyka')
        self.assertEqual(mat_item['stdev'], 0.0)
        self.assertEqual(mat_item['stability_status'], 'high')

        hist_item = next(i for i in benchmark['items'] if i['subject'] == 'Historia')
        self.assertGreater(hist_item['stdev'], 0.0)

    def test_recent_days_timeline_unit_and_integration(self):
        """Weryfikuje moduł 5-dniowego kalendarium zdarzeń (jednostkowo oraz w widoku dashboardu)."""
        ref_now = datetime(2026, 9, 18, 12, 0, 0)
        grades = [
            {'id': '1', 'subject': 'Matematyka', 'grade': '5', 'weight': '2', 'date': '2026-09-18', 'comment': 'Bardzo dobrze'},
            {'id': '2', 'subject': 'Język polski', 'grade': '4', 'weight': '1', 'date': '2026-09-15', 'category': 'Kartkówka'},
        ]
        messages = [
            {'id': 'm1', 'title': 'Zajęcia SKS', 'sender': 'Nauczyciel WF', 'datetime': '2026-09-17 14:00:00', 'body': 'Przypominam o stroju.'},
        ]
        notifications = [
            {'id': 'n1', 'title': 'Apel szkolny', 'sender': 'Dyrekcja', 'datetime': '2026-09-16', 'body': 'Obowiązuje strój galowy.'},
        ]
        timetable = [
            {'id': 't1', 'date': '2026-09-18', 'category': 'Sprawdzian', 'subject': 'Historia', 'description': 'Wojny perskie', 'lesson_no': '3'},
            {'id': 't2', 'date': '2026-09-22', 'add_date': '2026-09-14 10:00:00', 'category': 'Kartkówka', 'subject': 'Biologia', 'description': 'Budowa komórki'},
        ]

        # 1. Test jednostkowy funkcji build_recent_days_timeline
        days, total = build_recent_days_timeline(grades, messages, notifications, timetable, now=ref_now, days_count=5)
        self.assertEqual(len(days), 5)
        self.assertEqual(total, 6)

        # Daty: 14.09, 15.09, 16.09, 17.09, 18.09
        dates = [d['date'] for d in days]
        self.assertEqual(dates, ['2026-09-14', '2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18'])
        self.assertFalse(days[0]['is_today'])
        self.assertTrue(days[4]['is_today'])

        # 14.09: zapowiedziana kartkówka z biologii
        day_14 = days[0]
        self.assertEqual(day_14['tests_count'], 1)
        self.assertEqual(day_14['events'][0]['type'], 'test_announced')
        self.assertIn('Biologia', day_14['events'][0]['title'])

        # 15.09: ocena z języka polskiego
        day_15 = days[1]
        self.assertEqual(day_15['grades_count'], 1)
        self.assertEqual(day_15['events'][0]['badge'], '4')

        # 16.09: ogłoszenie szkolne
        day_16 = days[2]
        self.assertEqual(day_16['notifications_count'], 1)
        self.assertEqual(day_16['events'][0]['type'], 'notification')

        # 17.09: wiadomość
        day_17 = days[3]
        self.assertEqual(day_17['messages_count'], 1)
        self.assertEqual(day_17['events'][0]['type'], 'message')

        # 18.09: sprawdzian z historii oraz ocena z matematyki
        day_18 = days[4]
        self.assertEqual(day_18['tests_count'], 1)
        self.assertEqual(day_18['grades_count'], 1)
        types_18 = [e['type'] for e in day_18['events']]
        self.assertIn('test', types_18)
        self.assertIn('grade', types_18)

        # 2. Test integracyjny z widokiem HTML dashboardu
        student_data = {
            'student_name': 'Jan Kowalski (klasa 5A)',
            'last_collect_time': '2026-09-18 20:00:00',
            'grades_history': grades,
            'messages_history': messages,
            'notifications_history': notifications,
            'timetable_history': timetable,
        }
        with open(os.path.join(self.storage_dir, '123456.json'), 'w', encoding='utf-8') as f:
            json.dump(student_data, f)

        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            actual_date=ref_now,
            no_auth=True,
        )
        client = app.test_client()
        res = client.get('/')
        self.assertEqual(res.status_code, 200)

        html = res.data.decode('utf-8')
        self.assertIn("Kalendarium ostatnich 5 dni", html)
        self.assertIn("Łącznie: 6 zdarzeń", html)
        self.assertIn("Wojny perskie", html)
        self.assertIn("Zajęcia SKS", html)
        self.assertIn("Apel szkolny", html)
        self.assertIn("Dziś", html)
        # Ikona zębatki powinna linkować bezpośrednio do sekcji #kalendarium w Ustawieniach
        self.assertIn('href="/ustawienia#kalendarium"', html)

        # Sprawdzenie obecności kotwicy #kalendarium w widoku /ustawienia
        res_settings = client.get('/ustawienia')
        self.assertEqual(res_settings.status_code, 200)
        self.assertIn('id="kalendarium"', res_settings.data.decode('utf-8'))

        # 3. Test opcji hide_weekends=True (ukrywanie weekendów)
        ref_monday = datetime(2026, 9, 21, 10, 0, 0)
        school_days, _ = build_recent_days_timeline(
            grades, messages, notifications, timetable, now=ref_monday, days_count=5, hide_weekends=True
        )
        school_dates = [d['date'] for d in school_days]
        # Powinny być tylko dni robocze: wtorek 15.09, środa 16.09, czwartek 17.09, piątek 18.09, poniedziałek 21.09
        self.assertEqual(school_dates, ['2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18', '2026-09-21'])
        self.assertFalse(any(d['is_weekend'] for d in school_days))

        # 4. Test opcji reverse_order=True (odwrotne sortowanie - dzisiaj na początku/u góry)
        rev_days, _ = build_recent_days_timeline(
            grades, messages, notifications, timetable, now=ref_now, days_count=5, reverse_order=True
        )
        self.assertEqual(rev_days[0]['date'], '2026-09-18')
        self.assertTrue(rev_days[0]['is_today'])
        self.assertEqual(rev_days[-1]['date'], '2026-09-14')

        # 5. Test filtrowania typów zdarzeń (enabled_types)
        filtered_days, filtered_total = build_recent_days_timeline(
            grades, messages, notifications, timetable, now=ref_now, days_count=5, enabled_types=['grades']
        )
        # Tylko 2 oceny, brak powiadomień, wiadomości i sprawdzianów
        self.assertEqual(filtered_total, 2)
        all_ev_types = [ev['type'] for d in filtered_days for ev in d['events']]
        self.assertTrue(all(t == 'grade' for t in all_ev_types))

        # 6. Test wyłączenia kalendarium w dedykowanej sekcji timeline (enabled: False)
        cfg_disabled = dict(self.mock_config)
        cfg_disabled['timeline'] = {'enabled': False}
        with open(self.config_path, 'w', encoding='utf-8') as f:
            import yaml
            yaml.dump(cfg_disabled, f)

        app_disabled = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        res_disabled = app_disabled.test_client().get('/')
        self.assertEqual(res_disabled.status_code, 200)
        self.assertNotIn("Kalendarium ostatnich", res_disabled.data.decode('utf-8'))

        # 7. Test niestandardowej liczby dni wstecz w dedykowanej sekcji timeline (days: 3)
        cfg_3days = dict(self.mock_config)
        cfg_3days['timeline'] = {'enabled': True, 'days': 3}
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(cfg_3days, f)

        app_3days = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True, actual_date=ref_now)
        res_3days = app_3days.test_client().get('/')
        self.assertEqual(res_3days.status_code, 200)
        html_3days = res_3days.data.decode('utf-8')
        self.assertIn("Kalendarium ostatnich 3 dni", html_3days)

        # 8. Test zapisu ustawień kalendarium przez formularz POST /ustawienia (dedykowana sekcja timeline)
        post_data = {
            'student_login_0': '123456',
            'student_name_0': 'Jan Kowalski',
            'mail_provider': 'gmail',
            'mail_login': 'parent@example.com',
            'timeline_settings_present': '1',
            'timeline_enabled': 'on',
            'timeline_days': '7',
            'timeline_hide_weekends': 'on',
            'timeline_reverse_order': 'on',
            'timeline_type_grades': 'on',
            'timeline_type_tests': 'on',
            'collection_mode': 'interval',
            'collection_interval_hours': '1',
        }
        res_post = client.post('/ustawienia', data=post_data, follow_redirects=True)
        self.assertEqual(res_post.status_code, 200)
        with open(self.config_path, encoding='utf-8') as f:
            saved_cfg = yaml.safe_load(f)
        self.assertIn('timeline', saved_cfg)
        self.assertTrue(saved_cfg['timeline']['enabled'])
        self.assertEqual(saved_cfg['timeline']['days'], 7)
        self.assertTrue(saved_cfg['timeline']['hide_weekends'])
        self.assertTrue(saved_cfg['timeline']['reverse_order'])
        self.assertEqual(saved_cfg['timeline']['event_types'], ['grades', 'tests'])

    def test_annual_archive_and_historical_browser(self):
        """Testuje moduł archiwizacji rocznej (storage.py) oraz przeglądarkę historyczną w panelu WWW."""
        app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        client = app.test_client()
        storage = app.config['STORAGE']
        login = '123456'

        # 1. Zapisujemy stan początkowy z ocenami, wiadomościami i konfiguracją ucznia
        storage.save_grades_details(login, [
            {'id': 'gr_hist_1', 'subject': 'Matematyka', 'grade': '5', 'weight': '2', 'date': '2024-11-10'},
            {'id': 'gr_hist_2', 'subject': 'Historia', 'grade': '4', 'weight': '1', 'date': '2024-12-05'},
        ])
        storage.save_messages_details(login, [
            {'id': 'msg_august', 'title': 'Rozpoczęcie roku', 'date': '2024-08-30'},
        ])
        storage.set_subject_certificate_inclusion(login, 'Religia', False)
        storage.set_subject_category(login, 'Matematyka', 'sciences')

        # 2. Wykonujemy archiwizację roku 2024/2025
        archive_path = storage.archive_school_year(login, '2024/2025')
        self.assertTrue(archive_path.is_file())
        self.assertIn('123456_2024_2025.json', archive_path.name)

        # Sprawdzamy stan pliku archiwalnego
        arch_data = json.loads(archive_path.read_text(encoding='utf-8'))
        self.assertEqual(arch_data.get('school_year_label'), '2024/2025')
        self.assertIn('archived_at', arch_data)
        self.assertEqual(len(arch_data.get('grades_history', {})), 5)

        # Sprawdzamy czysty stan bieżący:
        # - Wiadomości i konfiguracja są zachowane
        # - Oceny są wyczyszczone do zera
        curr_grades = storage.get_grades_history(login)
        self.assertEqual(len(curr_grades), 0)
        curr_messages = storage.get_stored_messages(login)
        self.assertTrue(any(m.get('id') == 'msg_august' for m in curr_messages))
        self.assertIn('religia', [s.lower() for s in storage.get_excluded_certificate_subjects(login)])
        self.assertEqual(storage.get_subject_categories(login).get('Matematyka'), 'sciences')

        # 3. Lista zarchiwizowanych lat
        arch_list = storage.list_archived_years(login)
        self.assertEqual(len(arch_list), 1)
        self.assertEqual(arch_list[0]['label'], '2024/2025')

        # 4. Widok archiwalny (ArchivedFileStorage)
        arch_view = storage.get_archived_view('2024/2025')
        arch_grades = arch_view.get_grades_history(login)
        self.assertEqual(len(arch_grades), 5)
        self.assertTrue(any(g['subject'] == 'Matematyka' for g in arch_grades))

        # Próba modyfikacji w widoku archiwalnym jest ignorowana
        res_mut = arch_view.update_grade_custom(login, 'gr_hist_1', '6', '3')
        self.assertIsNone(res_mut)
        self.assertEqual(arch_view.get_grades_history(login)[0]['grade'], '5')

        # 5. Integracja WWW: Przełączenie na rok archiwalny
        res_switch = client.get('/school-year/switch?year=2024/2025', follow_redirects=True)
        self.assertEqual(res_switch.status_code, 200)
        html_arch = res_switch.data.decode('utf-8')
        self.assertIn('Przeglądasz zarchiwizowany rok szkolny', html_arch)
        self.assertIn('2024/2025', html_arch)
        self.assertIn('Wróć do roku bieżącego', html_arch)

        # Sprawdzenie widoku ocen w trybie archiwalnym - widzi oceny z tamtego roku
        res_grades_view = client.get('/oceny')
        self.assertEqual(res_grades_view.status_code, 200)
        html_grades = res_grades_view.data.decode('utf-8')
        self.assertIn('Matematyka', html_grades)
        self.assertIn('Historia', html_grades)

        # 6. Blokada operacji POST/API w trybie archiwalnym
        def extract_csrf(html_str: str) -> str:
            import re
            match = re.search(r'name=["\']csrf_token["\']\s+value=["\']([^"\']+)["\']', html_str)
            return match.group(1) if match else 'test_token'

        csrf_tok = extract_csrf(res_switch.data.decode('utf-8'))
        res_blocked = client.post('/api/grade/update', json={
            'grade_id': 'gr_hist_1',
            'grade': '6',
            'weight': '3',
            'csrf_token': csrf_tok,
        })
        self.assertEqual(res_blocked.status_code, 403)
        self.assertIn('trybie archiwalnym', res_blocked.get_json().get('message', ''))

        # 7. Powrót do roku bieżącego
        res_return = client.get('/school-year/switch?year=current', follow_redirects=True)
        self.assertEqual(res_return.status_code, 200)
        html_current = res_return.data.decode('utf-8')
        self.assertNotIn('Przeglądasz zarchiwizowany rok szkolny', html_current)

        # 8. Test formularza akcji archiwizacji POST /actions/archive-year
        # Dodajemy ocenę do bieżącego roku i archiwizujemy przez endpoint
        storage.save_grades_details(login, [
            {'id': 'gr_2025_1', 'subject': 'Fizyka', 'grade': '6', 'weight': '3', 'date': '2025-10-01'},
        ])
        csrf_curr = extract_csrf(html_current)
        res_action_arch = client.post('/actions/archive-year', data={
            'school_year_label': '2025/2026',
            'csrf_token': csrf_curr,
        }, follow_redirects=True)
        self.assertEqual(res_action_arch.status_code, 200)
        html_after_arch = res_action_arch.data.decode('utf-8')
        self.assertIn('Pomyślnie zarchiwizowano rok szkolny 2025/2026', html_after_arch)

        # Sprawdzamy czy są teraz 2 archiwa
        updated_arch_list = storage.list_archived_years(login)
        self.assertEqual(len(updated_arch_list), 2)
        arch_labels = [a['label'] for a in updated_arch_list]
        self.assertIn('2025/2026', arch_labels)
        self.assertIn('2024/2025', arch_labels)

        # 9. Test wielodzietności: przypomnienie o drugim dziecku oraz checkbox 'archive_all_students'
        # Dopisujemy drugie dziecko do configu
        with open(self.config_path, encoding='utf-8') as f:
            multi_cfg = yaml.safe_load(f)
        multi_cfg['librus_users'].append({
            'librus_login': '654321',
            'librus_login_name': 'Kasia Kowalska',
            'librus_password': 'secret_pass_2',
            'receivers': ['mama@example.com'],
        })
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(multi_cfg, f)

        # Tworzymy aplikację z nowym configiem zawierającym dwoje dzieci
        multi_app = create_app(config_path=self.config_path, storage_dir=self.storage_dir, no_auth=True)
        multi_client = multi_app.test_client()

        # a) Archiwizacja pojedyncza (bez zaznaczonego checkboxa 'archive_all_students')
        res_single = multi_client.post('/actions/archive-year', data={
            'school_year_label': '2026/2027',
            'csrf_token': csrf_curr,
        }, follow_redirects=True)
        self.assertEqual(res_single.status_code, 200)
        html_single = res_single.data.decode('utf-8')
        self.assertIn('Pomyślnie zarchiwizowano rok szkolny 2026/2027', html_single)
        self.assertIn('Pamiętaj: operacja dotyczyła wyłącznie tego profilu', html_single)
        self.assertIn('Kasia Kowalska', html_single)

        # b) Archiwizacja masowa ze zaznaczonym checkboxem 'archive_all_students'
        res_all = multi_client.post('/actions/archive-year', data={
            'school_year_label': '2027/2028',
            'archive_all_students': '1',
            'csrf_token': csrf_curr,
        }, follow_redirects=True)
        self.assertEqual(res_all.status_code, 200)
        html_all = res_all.data.decode('utf-8')
        self.assertIn('Pomyślnie zarchiwizowano rok szkolny 2027/2028 jednocześnie dla wszystkich dzieci', html_all)
        self.assertIn('Kasia Kowalska', html_all)

        # Sprawdzamy, czy archiwum powstało zarówno dla pierwszego, jak i dla drugiego dziecka
        self.assertIn('2027/2028', [a['label'] for a in storage.list_archived_years('123456')])
        self.assertIn('2027/2028', [a['label'] for a in storage.list_archived_years('654321')])

    def test_theme_engine_integration(self):
        """Weryfikuje integrację silnika skórek: obecność tokenów CSS, skryptu pre-render, selektora w nagłówku i kafelków w ustawieniach."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            secret_key='test-secret',
        )
        client = app.test_client()
        res_dashboard = client.get('/')
        self.assertEqual(res_dashboard.status_code, 200)
        html_dashboard = res_dashboard.data.decode('utf-8')

        # Weryfikacja tokenów i skryptu pre-render w base.html
        self.assertIn('librus2mail_theme', html_dashboard)
        self.assertIn('data-theme', html_dashboard)
        self.assertIn('THEME_DATA', html_dashboard)
        self.assertIn('--theme-bg-body', html_dashboard)
        self.assertIn('--theme-bg-card', html_dashboard)

        # Weryfikacja selektora motywów w nagłówku
        self.assertIn('id="theme-menu-container"', html_dashboard)
        self.assertIn("setTheme('light')", html_dashboard)
        self.assertIn("setTheme('dark')", html_dashboard)
        self.assertIn("setTheme('midnight')", html_dashboard)
        self.assertIn("setTheme('forest')", html_dashboard)
        self.assertIn("setTheme('auto')", html_dashboard)

        # Weryfikacja sekcji wyboru motywu w Ustawieniach
        res_settings = client.get('/ustawienia')
        self.assertEqual(res_settings.status_code, 200)
        html_settings = res_settings.data.decode('utf-8')
        self.assertIn('id="wyglad-i-motyw"', html_settings)
        self.assertIn('data-theme-card="light"', html_settings)
        self.assertIn('data-theme-card="dark"', html_settings)
        self.assertIn('data-theme-card="midnight"', html_settings)
        self.assertIn('data-theme-card="forest"', html_settings)

    def test_attendance_view_with_data_and_empty_state(self):
        """Testuje podstronę /frekwencja w stanie pustym oraz z zapisanymi danymi absencji."""
        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            secret_key='test-secret',
        )
        client = app.test_client()

        # 1. Pusty stan dla studenta (brak absencji)
        res_empty = client.get('/frekwencja')
        self.assertEqual(res_empty.status_code, 200)
        html_empty = res_empty.data.decode('utf-8')
        self.assertIn('Brak zarejestrowanych nieobecności', html_empty)
        self.assertIn('wzorowa 100% frekwencja', html_empty)

        # 2. Zapisanie danych frekwencji do storage
        storage = get_storage(self.mock_config, self.storage_dir)
        entries = [
            {
                'id': '9001',
                'date': '2026-09-18',
                'lesson_no': 3,
                'subject': 'Geografia',
                'symbol': 'u',
                'type': 'nieobecność uspr.',
                'teacher': 'Dorota Opolska',
                'topic': 'Ukształtowanie terenu',
                'is_absence': True,
                'is_justified': True,
                'is_late': False,
                'is_exempt': False,
                'is_trip': False,
                'justification_info': 'e-Usprawiedliwienie',
            },
            {
                'id': '9002',
                'date': '2026-09-22',
                'lesson_no': 2,
                'subject': 'Matematyka',
                'symbol': 'nb',
                'type': 'nieobecność',
                'teacher': 'Jan Kowalski',
                'is_absence': True,
                'is_justified': False,
                'is_late': False,
                'is_exempt': False,
                'is_trip': False,
            },
            {
                'id': '9003',
                'date': '2026-09-22',
                'lesson_no': 1,
                'subject': 'Fizyka',
                'symbol': 'sp',
                'type': 'spóźnienie',
                'teacher': 'Piotr Wiśniewski',
                'is_absence': False,
                'is_justified': False,
                'is_late': True,
                'is_exempt': False,
                'is_trip': False,
            },
        ]
        summary = [
            {
                'period': 'Okres 1',
                'label': 'Suma za okres 1',
                'justified': 1,
                'unjustified': 1,
                'total_absences': 2,
                'lates': 1,
                'exemptions': 0,
            }
        ]
        storage.save_attendance('123456', entries, summary)

        # 3. Ponowne odpytanie /frekwencja z danymi
        res_with_data = client.get('/frekwencja')
        self.assertEqual(res_with_data.status_code, 200)
        html = res_with_data.data.decode('utf-8')

        # Weryfikacja kart KPI
        self.assertIn('Nieusprawiedliwione', html)
        self.assertIn('wymaga reakcji', html)
        self.assertIn('Usprawiedliwione', html)
        self.assertIn('Spóźnienia', html)

        # Weryfikacja osi czasu (Timeline)
        self.assertIn('Geografia', html)
        self.assertIn('Matematyka', html)
        self.assertIn('e-Usprawiedliwienie', html)
        self.assertIn('Fizyka', html)
        self.assertIn('Spóźnienie', html)

        # Weryfikacja semestralnego kalendarza
        self.assertIn('Przegląd obecności w roku szkolnym', html)
        self.assertIn('scrollToDay', html)

        # Weryfikacja zestawienia przedmiotowego
        self.assertIn('Absencje wg przedmiotów', html)

        # Weryfikacja podsumowania semestralnego
        self.assertIn('Podsumowania semestralne (Librus)', html)
        self.assertIn('Okres 1', html)

        # Weryfikacja alertu na głównym Pulpicie (Dashboard)
        res_dash = client.get('/')
        self.assertEqual(res_dash.status_code, 200)
        dash_html = res_dash.data.decode('utf-8')
        self.assertIn('nieusprawiedliwione godziny lekcyjne', dash_html)
        self.assertIn('href="/frekwencja"', dash_html)

    def test_attendance_integration_in_schedule_and_dashboard(self):
        """Weryfikuje oznaczanie zdarzeń frekwencji (nb, u, sp, zw) w planie lekcji na pulpicie oraz w widoku /plan."""
        storage = get_storage(self.mock_config, self.storage_dir)

        # 1. Zapisanie lekcji w schedule na 2026-09-18
        storage.save_schedule_entries('123456', [
            {
                'id': 'sch_18_1',
                'date': '2026-09-18',
                'lesson_no': 1,
                'time_from': '08:00',
                'time_to': '08:45',
                'subject': 'Język polski',
                'teacher': 'B. Wiśniewska',
                'classroom': '11',
                'is_substitution': False,
                'is_cancelled': False,
            },
            {
                'id': 'sch_18_2',
                'date': '2026-09-18',
                'lesson_no': 2,
                'time_from': '08:55',
                'time_to': '09:40',
                'subject': 'Matematyka',
                'teacher': 'A. Nowak',
                'classroom': '12',
                'is_substitution': False,
                'is_cancelled': False,
            },
            {
                'id': 'sch_18_3',
                'date': '2026-09-18',
                'lesson_no': 3,
                'time_from': '09:50',
                'time_to': '10:35',
                'subject': 'Geografia',
                'teacher': 'D. Opolska',
                'classroom': '22',
                'is_substitution': False,
                'is_cancelled': False,
            },
            {
                'id': 'sch_18_4',
                'date': '2026-09-18',
                'lesson_no': 4,
                'time_from': '10:45',
                'time_to': '11:30',
                'subject': 'Historia',
                'teacher': 'C. Wójcik',
                'classroom': '15',
                'is_substitution': False,
                'is_cancelled': False,
            },
        ])

        # 2. Zapisanie zdarzeń frekwencji na 2026-09-18 (lekcja 2 spóźnienie, lekcja 3 nieobecność uspr., lekcja 4 nieobecność nieuspr.)
        entries = [
            {
                'id': 'att_18_2',
                'date': '2026-09-18',
                'lesson_no': 2,
                'subject': 'Matematyka',
                'symbol': 'sp',
                'type': 'spóźnienie',
                'teacher': 'A. Nowak',
                'is_absence': False,
                'is_justified': False,
                'is_late': True,
                'is_exempt': False,
                'is_trip': False,
            },
            {
                'id': 'att_18_3',
                'date': '2026-09-18',
                'lesson_no': 3,
                'subject': 'Geografia',
                'symbol': 'u',
                'type': 'nieobecność uspr.',
                'teacher': 'D. Opolska',
                'topic': 'Ukształtowanie terenu',
                'is_absence': True,
                'is_justified': True,
                'is_late': False,
                'is_exempt': False,
                'is_trip': False,
                'justification_info': 'e-Usprawiedliwienie',
            },
            {
                'id': 'att_18_4',
                'date': '2026-09-18',
                'lesson_no': 4,
                'subject': 'Historia',
                'symbol': 'nb',
                'type': 'nieobecność',
                'teacher': 'C. Wójcik',
                'is_absence': True,
                'is_justified': False,
                'is_late': False,
                'is_exempt': False,
                'is_trip': False,
            },
        ]
        storage.save_attendance('123456', entries, [])

        app = create_app(
            config_path=self.config_path,
            storage_dir=self.storage_dir,
            no_auth=True,
            secret_key='test-secret',
        )
        client = app.test_client()

        # 3. Weryfikacja w widoku /plan?date=2026-09-18
        res_plan = client.get('/plan?date=2026-09-18')
        self.assertEqual(res_plan.status_code, 200)
        html_plan = res_plan.data.decode('utf-8')

        # Wskaźniki w nagłówku dnia
        self.assertIn('🔴 1 nieuspr.', html_plan)
        self.assertIn('🟢 1 uspr.', html_plan)
        self.assertIn('🟡 1 spóźnienie', html_plan)

        # Odznaki przy przedmiotach
        self.assertIn('🟡 Spóźnienie', html_plan)
        self.assertIn('🟢 Usprawiedliwiona (e-Usprawiedliwienie)', html_plan)
        self.assertIn('🔴 Nieobecność (nieuspr.)', html_plan)

        # Przyciski ze skrótem frekwencji po prawej stronie
        self.assertIn('⏱️ Frekwencja: sp', html_plan)
        self.assertIn('⏱️ Frekwencja: u', html_plan)
        self.assertIn('⏱️ Frekwencja: nb', html_plan)
        self.assertIn('/frekwencja#day-2026-09-18', html_plan)

        # 4. Weryfikacja na Pulpicie (Dashboard) przy wyborze tej daty /?date=2026-09-18
        res_dash = client.get('/?date=2026-09-18')
        self.assertEqual(res_dash.status_code, 200)
        html_dash = res_dash.data.decode('utf-8')

        # Alerty w sekcji planu na pulpicie
        self.assertIn('🔴 1 nieuspr.', html_dash)
        self.assertIn('🟢 1 uspr.', html_dash)
        self.assertIn('🟡 1 spóźnienie', html_dash)

        # Etykiety przy przedmiotach na pulpicie
        self.assertIn('🟡 Spóźnienie', html_dash)
        self.assertIn('🟢 Usprawiedliwiona (e-Usprawiedliwienie)', html_dash)
        self.assertIn('🔴 Nieobecność (nieuspr.)', html_dash)

        # Przyciski po prawej stronie na pulpicie
        self.assertIn('⏱️ sp', html_dash)
        self.assertIn('⏱️ u', html_dash)
        self.assertIn('⏱️ nb', html_dash)



if __name__ == '__main__':
    unittest.main()



