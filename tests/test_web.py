"""Testy jednostkowe i integracyjne dla panelu webowego Librus2mail (Flask)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from librus2mail.web import create_app, export_web_views
from librus2mail.web import main as web_main
from librus2mail.web.auth import LoginRateLimiter, get_client_ip
from librus2mail.web.services import (
    calculate_overall_average,
    calculate_subject_averages,
    capture_action_execution,
    get_storage,
    resolve_student_name,
    simulate_new_grade,
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
        self.assertIn(b'Symulator Nowej Oceny', res_oceny.data)
        self.assertIn(b'Matematyka', res_oceny.data)

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

        # Test ustalania pełnej nazwy ucznia (resolve_student_name)
        storage = get_storage(self.mock_config, self.storage_dir)
        resolved = resolve_student_name(self.mock_config, storage, '123456')
        self.assertEqual(resolved, 'Jan Kowalski (123456)')

        # Zapis i ponowny odczyt przez set_student_name
        storage.set_student_name('123456', 'Jan Kowalski Zaktualizowany')
        self.assertEqual(storage.get_student_name('123456'), 'Jan Kowalski Zaktualizowany')

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
            'web_terminarz.html',
            'web_wiadomosci.html',
            'web_akcje.html',
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

    def test_capture_action_execution_error_handling(self):
        """Testuje bezpieczne przechwytywanie wyjątków w capture_action_execution."""
        def faulty_action():
            raise RuntimeError("Testowy błąd operacji")

        success, output, result = capture_action_execution(faulty_action)
        self.assertFalse(success)
        self.assertIn("Testowy błąd operacji", output)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
