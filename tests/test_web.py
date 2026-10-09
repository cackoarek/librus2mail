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
from librus2mail.web.app import get_app_version
from librus2mail.web.auth import LoginRateLimiter, get_client_ip
from librus2mail.web.services import (
    build_daily_summary_html,
    build_progress_report_html,
    build_student_report_html,
    calculate_overall_average,
    calculate_subject_averages,
    capture_action_execution,
    format_human_timestamp,
    get_storage,
    resolve_student_name,
    simulate_new_grade,
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
            'web_raporty_postepy.html',
            'web_raporty_uczen_kids.html',
            'web_raporty_uczen_teens.html',
            'web_raporty_uczen_youth.html',
            'web_raporty_podsumowanie.html',
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
        app = create_app(config_path=new_config_path, storage_dir=self.storage_dir, no_auth=True)
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
        self.assertTrue(saved_cfg['work-in-loop'])
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
        # Kompatybilność wsteczna z formatem słownika
        legacy_reps = get_reports_schedules({'schedule': {'reports': {'weekday': 'friday', 'interval_days': 7}}})
        self.assertEqual(len(legacy_reps), 1)
        self.assertEqual(legacy_reps[0]['interval_days'], 7)
        self.assertEqual(legacy_reps[0]['frequency'], 'weekly')

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
        app = create_app(config_path=new_config_path, storage_dir=self.storage_dir, no_auth=True)
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
        self.assertIn('Dzisiaj (lekcje w toku)', res_ongoing.data.decode('utf-8'))

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


if __name__ == '__main__':
    unittest.main()
