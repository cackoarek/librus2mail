import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import yaml

from librus2mail.librus import Librus, NotLogged
from librus2mail.librus_collector import LibrusCollector, run_collector
from librus2mail.updates_notifier import UpdatesNotifier


class TestLibrus(unittest.TestCase):

    def setUp(self):
        self.config = {
            'librus_login': '123456',
            'librus_password': 'secret_password',
            'read_messages': False,
            'read_grades': True,
        }
        self.librus = Librus(self.config)

    def test_generate_baner_header(self):
        headers = self.librus._Librus__generate_baner_header()
        self.assertIn('x-baner', headers)
        self.assertIn('_', headers['x-baner'])
        self.assertTrue(len(headers['x-baner']) > 5)

    def test_fetch_messages_with_valid_table(self):
        sample_html = """
        <html>
        <body>
            <table class="decorated stretch">
                <tbody>
                    <tr>
                        <td>1</td>
                        <td><img src="attachment.png"/></td>
                        <td><a href="/wiadomosci/1/5/123">Kowalski Jan (Nauczyciel)</a></td>
                        <td>Zadanie domowe</td>
                        <td>2026-09-16 10:00:00</td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        self.librus.logged = True
        with patch.object(self.librus, 'parse_page') as mock_parse:
            from bs4 import BeautifulSoup
            mock_parse.return_value = BeautifulSoup(sample_html, 'html.parser')
            self.librus.fetch_messages()

            self.assertEqual(len(self.librus.messages), 1)
            msg = self.librus.messages[0]
            self.assertEqual(msg['title'], 'Zadanie domowe')
            self.assertEqual(msg['sender'], 'Jan Kowalski')
            self.assertEqual(msg['datetime'], '2026-09-16 10:00:00')
            self.assertEqual(msg['link'], '/wiadomosci/1/5/123')
            self.assertTrue(msg['has_attachment'])
            self.assertEqual(self.librus.unread_count, 1)

    def test_fetch_messages_with_empty_or_missing_table_does_not_crash(self):
        empty_html = "<html><body><div>Brak wiadomości</div></body></html>"
        self.librus.logged = True
        with patch.object(self.librus, 'parse_page') as mock_parse:
            from bs4 import BeautifulSoup
            mock_parse.return_value = BeautifulSoup(empty_html, 'html.parser')
            # Should NOT raise AttributeError: 'NoneType' object has no attribute 'find'
            self.librus.fetch_messages()
            self.assertEqual(self.librus.messages, [])
            self.assertEqual(self.librus.unread_count, 0)

    def test_fetch_messages_redirected_to_login_raises_not_logged(self):
        login_html = """
        <html>
        <body>
            <div id="AuthorizationForm">
                <input id="Login" name="Login" />
            </div>
        </body>
        </html>
        """
        self.librus.logged = True
        with patch.object(self.librus, 'parse_page') as mock_parse:
            from bs4 import BeautifulSoup
            mock_parse.return_value = BeautifulSoup(login_html, 'html.parser')
            with self.assertRaises(NotLogged):
                self.librus.fetch_messages()

    def test_fetch_notifications_missing_container_does_not_crash(self):
        empty_html = "<html><body><div>Pusto</div></body></html>"
        self.librus.logged = True
        with patch.object(self.librus, 'parse_page') as mock_parse:
            from bs4 import BeautifulSoup
            mock_parse.return_value = BeautifulSoup(empty_html, 'html.parser')
            self.librus.fetch_notifications()
            self.assertEqual(self.librus.notifications, [])

    def test_parse_page_brak_dostepu_raises_not_logged(self):
        brak_dostepu_html = """
        <html>
        <body>
            <div class="container static">
                <h2 class="inside">Brak dostępu</h2>
                <div class="container-background">
                    <img src="/images/stop.png" />
                </div>
            </div>
        </body>
        </html>
        """
        self.librus.logged = True
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = brak_dostepu_html.encode('utf-8')
        mock_session.get.return_value = mock_resp
        self.librus._Librus__session = mock_session

        with self.assertRaises(NotLogged):
            self.librus.parse_page("https://synergia.librus.pl/wiadomosci")

    def test_fetch_grades_with_valid_table(self):
        sample_grades_html = """
        <html>
        <body>
            <table class="decorated stretch">
                <tbody>
                    <tr>
                        <td><img src="collapse.png" /></td>
                        <td>Matematyka</td>
                        <td>
                            <span class="grade-box">
                                <a class="ocena" href="/przegladaj_oceny/szczegoly/112233"
                                   title="Kategoria: Sprawdzian<br>Data: 2026-09-16<br>Nauczyciel: Jan Kowalski<br>Waga: 3">5+</a>
                            </span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </body>
        </html>
        """
        self.librus.logged = True
        with patch.object(self.librus, 'parse_page') as mock_parse:
            from bs4 import BeautifulSoup
            mock_parse.return_value = BeautifulSoup(sample_grades_html, 'html.parser')
            self.librus.fetch_grades()

            self.assertEqual(len(self.librus.grades), 1)
            grade = self.librus.grades[0]
            self.assertEqual(grade['id'], '112233')
            self.assertEqual(grade['subject'], 'Matematyka')
            self.assertEqual(grade['grade'], '5+')
            self.assertEqual(grade['category'], 'Sprawdzian')
            self.assertEqual(grade['date'], '2026-09-16')
            self.assertEqual(grade['teacher'], 'Jan Kowalski')
            self.assertEqual(grade['weight'], '3')

            # Test wykrywania nowej oceny
            new_grades = self.librus.get_not_known_grades_and_mark_as_known()
            self.assertEqual(len(new_grades), 1)
            self.assertEqual(new_grades[0]['id'], '112233')

            # Drugie sprawdzenie - ocena już znana
            new_grades_second = self.librus.get_not_known_grades_and_mark_as_known()
            self.assertEqual(len(new_grades_second), 0)

    def test_fetch_grades_with_honeypot_dummy_table(self):
        # Symulacja rzeczywistego DOM Librusa z ukrytą tabelą-pułapką przeciwko rozszerzeniom
        sample_html = """
        <html>
        <body>
            <div id="body">
                <table class="decorated stretch" style="display: none;">
                    <tr>
                        <td></td><td></td>
                        <td>
                            <span id="Ocena0" class="grade-box">
                                <a class="ocena" href="/przegladaj_oceny/szczegoly/000000">1</a>
                            </span>
                        </td>
                    </tr>
                </table>
                <table class="decorated stretch">
                    <tbody>
                        <tr class="line0">
                            <td><img src="icon.png" /></td>
                            <td>Historia</td>
                            <td>
                                <span class="grade-box">
                                    <a class="ocena" href="/przegladaj_oceny/szczegoly/278026"
                                       title="Kategoria: Kartkówka<br>Data: 2026-09-11 (pt.)<br>Nauczyciel: Makowiec Małgorzata<br>Waga: 1<br>Komentarz: świetna odpowiedź">6</a>
                                </span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </body>
        </html>
        """
        self.librus.logged = True
        with patch.object(self.librus, 'parse_page') as mock_parse:
            from bs4 import BeautifulSoup
            mock_parse.return_value = BeautifulSoup(sample_html, 'html.parser')
            self.librus.fetch_grades()

            self.assertEqual(len(self.librus.grades), 1)
            grade = self.librus.grades[0]
            self.assertEqual(grade['id'], '278026')
            self.assertEqual(grade['subject'], 'Historia')
            self.assertEqual(grade['grade'], '6')
            self.assertEqual(grade['category'], 'Kartkówka')
            self.assertEqual(grade['teacher'], 'Makowiec Małgorzata')
            self.assertEqual(grade['weight'], '1')
            self.assertEqual(grade['comment'], 'świetna odpowiedź')

    def test_fetch_grades_disabled_when_read_grades_false(self):
        librus = Librus({
            'librus_login': '123456',
            'librus_password': 'secret_password',
            'read_grades': False,
        })
        librus.logged = True
        librus.fetch_grades()
        self.assertEqual(librus.grades, [])

    def test_librus_defaults_read_messages_and_grades(self):
        librus = Librus({
            'librus_login': '123456',
            'librus_password': 'secret_password',
        })
        self.assertTrue(librus._Librus__do_read_messages)
        self.assertTrue(librus.do_read_grades)

    def test_mail_sender_create_mail_content_for_grades(self):
        from librus2mail.mail_sender import MailSender
        user_cfg = {'librus_login': '123', 'librus_login_name': 'Jaś'}
        grades = [{
            'id': '1',
            'subject': 'Biologia',
            'grade': '6',
            'category': 'Kartkówka',
            'date': '2026-09-16',
            'teacher': 'Anna Nowak',
            'weight': '2',
            'comment': 'Brawo!'
        }]
        html = MailSender.create_mail_content_for_grades(user_cfg, grades)
        self.assertIn('Biologia', html)
        self.assertIn('6', html)
        self.assertIn('Kartkówka', html)
    def test_mail_sender_create_mail_content_for_summary(self):
        from librus2mail.mail_sender import MailSender
        user_cfg = {'librus_login': '123', 'librus_login_name': 'Jaś'}
        messages = [{
            'id': 'm1',
            'title': 'Wycieczka',
            'sender': 'Wychowawca',
            'datetime': '2026-09-16 10:00',
            'is_unread': True,
            'body': 'Szczegóły wycieczki...'
        }]
        notifications = [{
            'id': 'n1',
            'title': 'Dzień sportu',
            'sender': 'Dyrektor',
            'datetime': '2026-09-16 08:00',
            'is_unread': True,
            'body': 'Zapraszamy na zawody.'
        }]
        grades = [{
            'id': 'g1',
            'subject': 'Historia',
            'grade': '6',
            'category': 'Kartkówka',
            'date': '2026-09-16',
            'teacher': 'Jan Nowak',
            'weight': '1',
            'comment': 'Brawo'
        }]

        html = MailSender.create_mail_content_for_summary(user_cfg, messages, notifications, grades)
        self.assertIn('Nowe wiadomości (1)', html)
        self.assertIn('Wycieczka', html)
        self.assertIn('Szczegóły wycieczki...', html)
        self.assertIn('Nowe ogłoszenia (1)', html)
        self.assertIn('Dzień sportu', html)
        self.assertIn('Nowe oceny (1)', html)
        self.assertIn('Historia', html)
        self.assertIn('6', html)

        title = MailSender._create_summary_title(user_cfg, messages, notifications, grades)
        self.assertIn('1 nowa wiadomość', title)
        self.assertIn('1 nowe ogłoszenie', title)
        self.assertIn('Historia: 6', title)

    def test_mail_senders_send_summary(self):
        from librus2mail.gmail_sender import GmailSender
        from librus2mail.smtp_sender import SmtpSender

        mail_cfg = {
            'login': 'test@example.com',
            'password': 'pass',
            'use_gmail': True,
            'non_gmail_settings': {'smtp_host': 'localhost', 'port': 587}
        }
        user_cfg = {
            'librus_login': '123',
            'librus_login_name': 'Jaś',
            'notification_receivers': ['parent@example.com']
        }

        with patch('yagmail.SMTP') as mock_yag:
            gmail_sender = GmailSender(mail_cfg)
            gmail_sender.send_mail_with_summary(user_cfg, [{'title': 'T', 'sender': 'S', 'datetime': 'D', 'is_unread': True}], [], [])
            mock_yag.return_value.send.assert_called_once()

        with patch('smtplib.SMTP') as mock_smtp:
            smtp_sender = SmtpSender(mail_cfg)
            smtp_sender.send_mail_with_summary(user_cfg, [], [{'title': 'O', 'sender': 'D', 'datetime': 'D', 'is_unread': True}], [])
            mock_smtp.return_value.sendmail.assert_called_once()

    def test_create_storage_defaults(self):
        from librus2mail.storage import FileStorage, create_storage
        st = create_storage()
        self.assertIsInstance(st, FileStorage)
        self.assertEqual(st.storage_dir, "storage")

    def test_file_storage_persistence(self):
        import tempfile

        from librus2mail.storage import FileStorage, create_storage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorage(storage_dir=tmpdir)
            self.assertFalse(storage.has_existing_data("user1"))

            storage.save_known_items("user1", {"m1", "m2"}, {"n1"}, {"g1"})
            self.assertTrue(storage.has_existing_data("user1"))

            # Now create a new FileStorage instance pointing to same directory
            storage2 = FileStorage(storage_dir=tmpdir)
            data = storage2.load_known_items("user1")
            self.assertEqual(data['messages'], {"m1", "m2"})
            self.assertEqual(data['notifications'], {"n1"})
            self.assertEqual(data['grades'], {"g1"})

            # Test factory function with storage_dir
            file_s = create_storage(storage_dir=tmpdir)
            self.assertEqual(file_s.__class__.__name__, "FileStorage")

    def test_librus_with_storage_integration(self):
        import tempfile

        from librus2mail.storage import FileStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorage(storage_dir=tmpdir)
            cfg = {
                'librus_login': '999',
                'librus_password': 'pass',
                'read_grades': True
            }

            # 1. Instance A discovers a grade
            librus_a = Librus(cfg, storage=storage)
            librus_a.grades = [{'id': 'grade_99', 'subject': 'Fizyka', 'grade': '5'}]
            new_grades = librus_a.get_not_known_grades_and_mark_as_known()
            self.assertEqual(len(new_grades), 1)

            # 2. Instance B (like after application restart) loads the same storage
            librus_b = Librus(cfg, storage=storage)
            librus_b.grades = [{'id': 'grade_99', 'subject': 'Fizyka', 'grade': '5'}]
            new_grades_b = librus_b.get_not_known_grades_and_mark_as_known()
            # Grade is already known from file!
            self.assertEqual(len(new_grades_b), 0)

    def test_work_in_loop_config_handling(self):
        # Domyślnie True
        cfg_default = {}
        self.assertTrue(cfg_default.get('work-in-loop', cfg_default.get('work_in_loop', True)))

        # Wyłączona pętla (work-in-loop: false)
        cfg_disabled_hyphen = {'work-in-loop': False}
        self.assertFalse(cfg_disabled_hyphen.get('work-in-loop', cfg_disabled_hyphen.get('work_in_loop', True)))

        # Wyłączona pętla (work_in_loop: false z podkreśleniem)
        cfg_disabled_underscore = {'work_in_loop': False}
        self.assertFalse(cfg_disabled_underscore.get('work-in-loop', cfg_disabled_underscore.get('work_in_loop', True)))

        # Weryfikacja wykonania w run_collector z work-in-loop: false
        import tempfile

        import yaml

        from librus2mail.librus_collector import run_collector

        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_file = os.path.join(tmp_dir, "config.yaml")
            with open(cfg_file, "w", encoding="utf-8") as f:
                yaml.dump({
                    'work-in-loop': False,
                    'storage_dir': tmp_dir,
                    'librus_users': [],
                    'mail': {'use_gmail': False, 'login': 'a', 'password': 'b'},
                }, f)
            # Powinno wykonać 1 przebieg i zakończyć działanie bez zawieszenia w pętli
            run_collector(config_path=cfg_file, storage_dir=tmp_dir, offline=True)

            # Test z flagą once=True nadpisującą work-in-loop: true
            with open(cfg_file, "w", encoding="utf-8") as f:
                yaml.dump({
                    'work-in-loop': True,
                    'storage_dir': tmp_dir,
                    'librus_users': [],
                    'mail': {'use_gmail': False, 'login': 'a', 'password': 'b'},
                }, f)
            run_collector(config_path=cfg_file, storage_dir=tmp_dir, offline=True, once=True)

    def test_storage_error_tracking(self):
        import tempfile

        from librus2mail.storage import FileStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            fs = FileStorage(storage_dir=tmpdir)
            self.assertIsNone(fs.get_last_error("user1"))
            fs.save_last_error("user1", "Error 1", step="logowanie")
            err = fs.get_last_error("user1")
            self.assertIsNotNone(err)
            self.assertEqual(err['error'], "Error 1")
            self.assertEqual(err['step'], "logowanie")
            self.assertIn('timestamp', err)

            # Verify that saving known items does not overwrite last_error
            fs.save_known_items("user1", {"m1"}, {"n1"}, {"g1"})
            err2 = fs.get_last_error("user1")
            self.assertIsNotNone(err2)
            self.assertEqual(err2['error'], "Error 1")

            # Verify clearing last_error
            fs.clear_last_error("user1")
            self.assertIsNone(fs.get_last_error("user1"))

    def test_mail_sender_error_diagnostics_and_content(self):
        import requests

        from librus2mail.mail_sender import MailSender

        user_cfg = {
            'librus_login': '12345',
            'librus_login_name': 'Kasia Kowalska',
            'notification_receivers': ['mama@example.com']
        }

        # 1. Test NotLogged diagnostics
        nl_err = NotLogged("Sesja w portalu Synergia wygasła")
        cat, diag, rec = MailSender._get_error_diagnostics(nl_err)
        self.assertIn("autoryzacji", cat.lower())
        self.assertIn("portal.librus.pl", rec)

        # 2. Test ConnectionError diagnostics
        conn_err = requests.exceptions.ConnectionError("Failed to establish a new connection")
        cat_c, diag_c, rec_c = MailSender._get_error_diagnostics(conn_err)
        self.assertIn("połączenia", cat_c.lower())
        self.assertIn("internetowe", rec_c.lower())

        # 3. Test Parsing / HTML error diagnostics
        parse_err = AttributeError("'NoneType' object has no attribute 'find'")
        cat_p, diag_p, rec_p = MailSender._get_error_diagnostics(parse_err)
        self.assertIn("parsowania", cat_p.lower())
        self.assertIn("HTML", cat_p)

        # 4. Title formatting
        title = MailSender._create_error_title(user_cfg, nl_err, step_name="logowanie")
        self.assertIn("[ALERT]", title)
        self.assertIn("Kasia Kowalska", title)
        self.assertIn("Logowanie", title)
        self.assertIn("12345", title)

        # 5. Content formatting
        content = MailSender.create_mail_content_for_error(
            user_cfg,
            nl_err,
            step_name="logowanie",
            details="Traceback line 1\nTraceback line 2",
            cooldown_s=1800
        )
        self.assertIn("Kasia Kowalska", content)
        self.assertIn("12345", content)
        self.assertIn("Logowanie do portalu Synergia", content)
        self.assertIn("Traceback line 1", content)
        self.assertIn("30 minut", content)

    def test_mail_sender_cooldown_logic(self):
        import json
        import tempfile
        import time

        from librus2mail.mail_sender import MailSender
        from librus2mail.storage import FileStorage

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorage(storage_dir=tmpdir)
            user_login = "12345"

            # Initially, no prior errors -> should send
            self.assertTrue(MailSender.should_send_error_notification(storage, user_login, "Error A", cooldown_s=3600))

            # Record error
            storage.save_last_error(user_login, "Error A", step="logowanie")

            # Immediate next check with same error -> should be throttled
            self.assertFalse(MailSender.should_send_error_notification(storage, user_login, "Error A", cooldown_s=3600))

            # Next check with a DIFFERENT error -> should send immediately!
            self.assertTrue(MailSender.should_send_error_notification(storage, user_login, "Error B", cooldown_s=3600))

            # Check after artificial timestamp aging past cooldown
            fpath = storage._get_file_path(user_login)
            with open(fpath, encoding='utf-8') as f:
                d = json.load(f)
            d['last_error']['timestamp'] = time.time() - 3601
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(d, f)

            self.assertTrue(MailSender.should_send_error_notification(storage, user_login, "Error A", cooldown_s=3600))

            # Check cooldown_s <= 0 disables throttling
            storage.save_last_error(user_login, "Error A", step="logowanie")
            self.assertTrue(MailSender.should_send_error_notification(storage, user_login, "Error A", cooldown_s=0))

    def test_send_error_notification_gmail_and_smtp(self):
        import tempfile

        from librus2mail.gmail_sender import GmailSender
        from librus2mail.smtp_sender import SmtpSender
        from librus2mail.storage import FileStorage

        mail_cfg = {
            'login': 'test@example.com',
            'password': 'pass',
            'use_gmail': True,
            'non_gmail_settings': {'smtp_host': 'localhost', 'port': 587}
        }
        user_cfg = {
            'librus_login': '12345',
            'librus_login_name': 'Kasia',
            'notification_receivers': ['parent@example.com']
        }
        test_err = NotLogged("Sesja wygasła")

        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorage(storage_dir=tmpdir)

            # 1. Test GmailSender
            with patch('yagmail.SMTP') as mock_yag:
                gmail = GmailSender(mail_cfg)
                sent = gmail.send_error_notification(user_cfg, test_err, step_name="logowanie", storage=storage, cooldown_s=3600)
                self.assertTrue(sent)
                mock_yag.return_value.send.assert_called_once()
                # Verify error was saved to storage
                self.assertIsNotNone(storage.get_last_error("12345"))

                # Second attempt immediately should be throttled
                sent_again = gmail.send_error_notification(user_cfg, test_err, step_name="logowanie", storage=storage, cooldown_s=3600)
                self.assertFalse(sent_again)

            # 2. Test SmtpSender
            storage.clear_last_error("12345")
            with patch('smtplib.SMTP') as mock_smtp:
                smtp = SmtpSender(mail_cfg)
                sent_smtp = smtp.send_error_notification(user_cfg, test_err, step_name="oceny", storage=storage, cooldown_s=3600)
                self.assertTrue(sent_smtp)
                mock_smtp.return_value.sendmail.assert_called_once()
                self.assertIsNotNone(storage.get_last_error("12345"))

    def test_login_when_grant_redirects_directly_without_2fa(self):
        mock_session = MagicMock()

        # Step 1: portalRodzina
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.url = 'https://api.librus.pl/OAuth/Authorization?client_id=46&state=123'
        mock_session.get.side_effect = [
            resp1,
            # Step 3: GET next_url directly redirects to synergia with code=
            MagicMock(status_code=200, url='https://synergia.librus.pl/loguj/portalRodzina?code=abc&state=123')
        ]

        # Step 2: POST login
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {'status': 'ok', 'goTo': '/OAuth/Authorization/2FA?client_id=46'}
        mock_session.post.return_value = resp2

        librus = Librus({
            'librus_login': '123',
            'librus_password': 'haslo!with!exclamation'
        })
        librus._Librus__session = mock_session

        with patch('requests.Session', return_value=mock_session):
            librus.login()
            self.assertTrue(librus.logged)
            # Verify no POST was made to 2FA because grant_res.url was already synergia with code=
            self.assertEqual(mock_session.post.call_count, 1)

    def test_login_when_grant_has_error_raises_not_logged(self):
        mock_session = MagicMock()
        resp1 = MagicMock(status_code=200, url='https://api.librus.pl/OAuth/Authorization?client_id=46')
        resp2 = MagicMock(status_code=200)
        resp2.json.return_value = {'status': 'ok', 'goTo': '/OAuth/Authorization/Grant?client_id=46'}
        resp3 = MagicMock(status_code=200, url='https://synergia.librus.pl/loguj/portalRodzina?error=invalid_request')

        mock_session.get.side_effect = [resp1, resp3]
        mock_session.post.return_value = resp2

        librus = Librus({'librus_login': '123', 'librus_password': 'p!'})
        with patch('requests.Session', return_value=mock_session):
            with self.assertRaises(NotLogged):
                librus.login()

    def test_read_config_missing_file_raises_filenotfounderror(self):
        from librus2mail.config import read_config
        with self.assertRaises(FileNotFoundError) as ctx:
            read_config('non_existent_config_file_12345.yaml')
        self.assertIn("config-example.yaml", str(ctx.exception))
        self.assertIn("config-minimal.yaml", str(ctx.exception))
        self.assertIn("README.md", str(ctx.exception))

    def test_read_config_valid_file_loads_successfully(self):
        import tempfile

        from librus2mail.config import read_config
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
            f.write("test_key: test_value\n")
            f_name = f.name
        try:
            cfg = read_config(f_name)
            self.assertEqual(cfg.get('test_key'), 'test_value')
        finally:
            import os
            if os.path.exists(f_name):
                os.remove(f_name)


    def test_progress_analyzer_helpers(self):
        from librus2mail.progress_analyzer import (
            get_predicted_grade,
            parse_grade_date,
            parse_numeric_grade,
            parse_weight,
        )

        # Grades parsing
        self.assertEqual(parse_numeric_grade('5'), 5.0)
        self.assertEqual(parse_numeric_grade('5+'), 5.5)
        self.assertEqual(parse_numeric_grade('4-'), 3.75)
        self.assertEqual(parse_numeric_grade('3='), 2.5)
        self.assertEqual(parse_numeric_grade('2-'), 1.75)
        self.assertEqual(parse_numeric_grade('+'), None)
        self.assertEqual(parse_numeric_grade('np'), None)
        self.assertEqual(parse_numeric_grade(None), None)

        # Weight parsing
        self.assertEqual(parse_weight('3'), 3.0)
        self.assertEqual(parse_weight('2.5'), 2.5)
        self.assertEqual(parse_weight('-'), 1.0)
        self.assertEqual(parse_weight(None), 1.0)

        # Date parsing
        d1 = parse_grade_date('2026-09-15')
        self.assertEqual(d1.year, 2026)
        self.assertEqual(d1.month, 9)
        self.assertEqual(d1.day, 15)

        d2 = parse_grade_date('18.09.2026')
        self.assertEqual(d2.year, 2026)
        self.assertEqual(d2.month, 9)
        self.assertEqual(d2.day, 18)

        d3 = parse_grade_date('-', added_at_iso='2026-09-10T12:00:00')
        self.assertEqual(d3.day, 10)

        # Predicted grade
        self.assertIn("6", get_predicted_grade(5.75))
        self.assertIn("5", get_predicted_grade(4.80))
        self.assertIn("4", get_predicted_grade(3.90))
        self.assertIn("3", get_predicted_grade(2.80))
        self.assertIn("2", get_predicted_grade(1.90))
        self.assertIn("1", get_predicted_grade(1.50))
        self.assertEqual(get_predicted_grade(None), "-")

    def test_progress_analyzer_full_analysis(self):
        from datetime import datetime

        from librus2mail.progress_analyzer import ProgressAnalyzer

        grades = [
            # Matematyka: historyczna 4 (waga 1), nowa 5 (waga 2) -> trend up
            {'id': '1', 'subject': 'Matematyka', 'grade': '4', 'weight': '1', 'date': '2026-09-01'},
            {'id': '2', 'subject': 'Matematyka', 'grade': '5', 'weight': '2', 'date': '2026-09-15', 'category': 'Sprawdzian'},
            # Język polski: historyczna 5 (waga 2), nowa 2 (waga 3) -> trend down, warning
            {'id': '3', 'subject': 'Język polski', 'grade': '5', 'weight': '2', 'date': '2026-09-02'},
            {'id': '4', 'subject': 'Język polski', 'grade': '2', 'weight': '3', 'date': '2026-09-16', 'category': 'Wypracowanie'},
            # Aktywność
            {'id': '5', 'subject': 'Historia', 'grade': '+', 'weight': '1', 'date': '2026-09-17'},
            {'id': '6', 'subject': 'Historia', 'grade': 'np', 'weight': '1', 'date': '2026-09-17'},
        ]

        period_start = datetime(2026, 9, 10)
        analysis = ProgressAnalyzer.analyze(grades, period_start=period_start)

        self.assertEqual(analysis['total_grades_count'], 6)
        self.assertEqual(analysis['period_grades_count'], 4)
        self.assertEqual(analysis['activity_pluses'], 1)
        self.assertEqual(analysis['unprepared_count'], 1)

        subjects_dict = {s['subject']: s for s in analysis['subjects']}
        self.assertIn('Matematyka', subjects_dict)
        mat = subjects_dict['Matematyka']
        self.assertEqual(mat['period_avg'], 5.0)
        self.assertEqual(mat['trend'], 'up')

        pol = subjects_dict['Język polski']
        self.assertEqual(pol['period_avg'], 2.0)
        self.assertEqual(pol['trend'], 'down')

        # Sprawdzenie wygenerowanych ostrzeżeń (niska ocena z dużą wagą w okresie)
        warnings_text = " ".join(analysis['insights_warnings'])
        self.assertIn('Język polski', warnings_text)
        self.assertIn('nieprzygotowań', warnings_text)

    def test_storage_grades_history_and_report_date(self):
        import shutil
        import tempfile

        from librus2mail.storage import FileStorage

        temp_dir = tempfile.mkdtemp()
        try:
            st = FileStorage(storage_dir=temp_dir)
            user = "uczen_testowy_123"
            test_grades = [
                {'id': 'g1', 'subject': 'Fizyka', 'grade': '5', 'weight': '2', 'date': '2026-09-15'},
                {'id': 'g2', 'subject': 'Informatyka', 'grade': '6', 'weight': '1', 'date': '2026-09-16'}
            ]
            st.save_grades_details(user, test_grades)
            history = st.get_grades_history(user)
            self.assertEqual(len(history), 2)
            hist_ids = {g['id'] for g in history}
            self.assertEqual(hist_ids, {'g1', 'g2'})

            # Test zapisu daty ostatniego raportu
            self.assertIsNone(st.get_last_progress_report_date(user))
            now_iso = "2026-09-18T17:00:00"
            st.save_last_progress_report_date(user, now_iso)
            self.assertEqual(st.get_last_progress_report_date(user), now_iso)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_mail_sender_progress_report_html_and_title(self):
        from librus2mail.mail_sender import MailSender
        user_cfg = {'librus_login': '888', 'librus_login_name': 'Zosia'}
        analysis = {
            'period_start_str': '11.09.2026',
            'period_end_str': '18.09.2026',
            'overall_avg': 4.85,
            'period_avg': 5.00,
            'total_grades_count': 12,
            'period_grades_count': 3,
            'activity_pluses': 2,
            'activity_minuses': 0,
            'unprepared_count': 0,
            'insights_strengths': ['Wysoka średnia ogólna.'],
            'insights_warnings': [],
            'subjects': [{
                'subject': 'Matematyka',
                'overall_avg': 5.0,
                'period_avg': 5.0,
                'trend': 'up',
                'trend_label': '↗ (+0.50)',
                'predicted_grade': '5 (bardzo dobry)',
                'period_grades': [{'grade': '5+'}],
                'all_grades': [{'grade': '5'}, {'grade': '5+'}]
            }],
            'period_grades': [{
                'subject': 'Matematyka',
                'grade': '5+',
                'weight': '2',
                'category': 'Klasówka',
                'date': '2026-09-15',
                'teacher': 'Nowak Jan',
                'comment': 'Bardzo dobra praca'
            }],
            'distribution_overall': {'6': 2, '5': 8, '4': 2, '3': 0, '2': 0, '1': 0},
            'distribution_period': {'6': 0, '5': 3, '4': 0, '3': 0, '2': 0, '1': 0},
        }

        title = MailSender._create_progress_report_title(user_cfg, analysis)
        self.assertIn("Zosia", title)
        self.assertIn("4.85", title)
        self.assertIn("11.09.2026", title)

        content = MailSender.create_mail_content_for_progress_report(user_cfg, analysis)
        self.assertIn("Zosia", content)
        self.assertIn("Matematyka", content)
        self.assertIn("Klasówka", content)
        self.assertIn("Świadectwo z wyróżnieniem", content)
        self.assertIn("Wysoka średnia ogólna.", content)

    def test_send_progress_report_gmail_and_smtp(self):
        from librus2mail.gmail_sender import GmailSender
        from librus2mail.smtp_sender import SmtpSender

        mail_cfg = {
            'login': 'sender@example.com',
            'password': 'secret_pass',
            'use_gmail': True,
            'non_gmail_settings': {'smtp_host': 'localhost', 'port': 587}
        }
        user_cfg = {
            'librus_login': '999',
            'librus_login_name': 'Bartek',
            'notification_receivers': ['parent@example.com']
        }
        analysis = {
            'period_start_str': '10.09.2026',
            'period_end_str': '17.09.2026',
            'overall_avg': 4.20,
            'period_avg': 4.50,
            'total_grades_count': 5,
            'period_grades_count': 2,
            'activity_pluses': 0,
            'activity_minuses': 0,
            'unprepared_count': 0,
            'insights_strengths': [],
            'insights_warnings': [],
            'subjects': [],
            'period_grades': [],
            'distribution_overall': {},
            'distribution_period': {},
        }

        # 1. GmailSender
        with patch('yagmail.SMTP') as mock_yag:
            gmail = GmailSender(mail_cfg)
            sent = gmail.send_progress_report(user_cfg, analysis)
            self.assertTrue(sent)
            mock_yag.return_value.send.assert_called_once()

        # 2. SmtpSender
        with patch('smtplib.SMTP') as mock_smtp:
            smtp = SmtpSender(mail_cfg)
            sent_smtp = smtp.send_progress_report(user_cfg, analysis)
            self.assertTrue(sent_smtp)
            mock_smtp.return_value.sendmail.assert_called_once()

    def test_progress_report_cli_dry_run(self):
        import os
        import sys
        import tempfile

        import yaml

        from librus2mail.progress_report import run_progress_reports
        from librus2mail.storage import FileStorage

        temp_dir = tempfile.mkdtemp()
        cfg_path = os.path.join(temp_dir, 'config.yaml')
        storage_dir = os.path.join(temp_dir, 'storage')
        os.makedirs(storage_dir, exist_ok=True)

        # Pre-seed storage with grades
        st = FileStorage(storage_dir=storage_dir)
        st.save_grades_details('111222', [
            {'id': 'g1', 'subject': 'Biologia', 'grade': '5', 'weight': '2', 'date': '2026-09-15', 'category': 'Sprawdzian'}
        ])

        cfg_data = {
            'storage_dir': storage_dir,
            'librus_users': [{
                'librus_login': '111222',
                'librus_login_name': 'Michał',
                'librus_password': 'test',
                'notification_receivers': ['test@example.com']
            }],
            'mail': {
                'login': 'sender@example.com',
                'password': 'pass',
                'use_gmail': True
            }
        }

        with open(cfg_path, 'w', encoding='utf-8') as f:
            yaml.dump(cfg_data, f)

        # Run with --dry-run (offline by default)
        test_args = ['librus_progress_report.py', '-c', cfg_path, '--dry-run']
        with patch.object(sys, 'argv', test_args):
            with patch('librus2mail.storage.FileStorage', return_value=st):
                # Should execute cleanly without errors or sending emails
                run_progress_reports()


    def test_progress_analyzer_new_features(self):
        from datetime import datetime, timedelta

        from librus2mail.progress_analyzer import ProgressAnalyzer

        now = datetime(2026, 9, 20)
        old_date = (now - timedelta(days=40)).strftime('%Y-%m-%d')

        grades = [
            # Matematyka: średnia 3.67 (blisko progu 3.75 dla oceny 4 - szansa)
            {'id': '10', 'subject': 'Matematyka', 'grade': '4', 'weight': '2', 'date': '2026-09-12'},
            {'id': '11', 'subject': 'Matematyka', 'grade': '3', 'weight': '1', 'date': '2026-09-14'},
            # Historia: średnia 1.80 (blisko progu 1.75 - ryzyko spadku do 1)
            {'id': '20', 'subject': 'Historia', 'grade': '2', 'weight': '4', 'date': '2026-09-15'},
            {'id': '21', 'subject': 'Historia', 'grade': '1', 'weight': '1', 'date': '2026-09-16'},
            # Cichy przedmiot: Informatyka (ocena sprzed 40 dni)
            {'id': '40', 'subject': 'Informatyka', 'grade': '5', 'weight': '1', 'date': old_date},
            # Stabilność: Biologia (same 5 -> stabilna) vs Fizyka (1, 5, 1, 5 -> sinusoida)
            {'id': '50', 'subject': 'Biologia', 'grade': '5', 'weight': '1', 'date': '2026-09-10'},
            {'id': '51', 'subject': 'Biologia', 'grade': '5', 'weight': '1', 'date': '2026-09-11'},
            {'id': '52', 'subject': 'Biologia', 'grade': '5', 'weight': '1', 'date': '2026-09-12'},
            {'id': '60', 'subject': 'Fizyka', 'grade': '1', 'weight': '1', 'date': '2026-09-10'},
            {'id': '61', 'subject': 'Fizyka', 'grade': '5', 'weight': '1', 'date': '2026-09-11'},
            {'id': '62', 'subject': 'Fizyka', 'grade': '1', 'weight': '1', 'date': '2026-09-12'},
            {'id': '63', 'subject': 'Fizyka', 'grade': '5', 'weight': '1', 'date': '2026-09-13'},
        ]

        analysis = ProgressAnalyzer.analyze(grades, period_start=now - timedelta(days=14), period_end=now)

        # 1. Analiza na krawędzi (Borderline)
        self.assertTrue(any(o['subject'] == 'Matematyka' for o in analysis['borderline_opportunities']))
        self.assertTrue(any(r['subject'] == 'Historia' for r in analysis['borderline_risks']))

        # 2. Ciche przedmioty
        self.assertTrue(any(d['subject'] == 'Informatyka' for d in analysis['dormant_subjects']))

        # 3. Stabilność
        self.assertTrue(any(s['subject'] == 'Biologia' for s in analysis['stable_subjects']))
        self.assertTrue(any(v['subject'] == 'Fizyka' for v in analysis['volatile_subjects']))

        # 4. Legenda i przewodnik
        self.assertIn('legend', analysis)
        self.assertIn('thresholds', analysis['legend'])
        self.assertIn('trends', analysis['legend'])

    def test_progress_analyzer_learning_style(self):
        from librus2mail.progress_analyzer import ProgressAnalyzer

        # Uczeń ma 5 ze sprawdzianów (waga 3) i 2 z kartkówek (waga 1)
        grades_daily_lower = [
            {'id': '1', 'subject': 'Fizyka', 'grade': '5', 'weight': '3', 'category': 'Sprawdzian'},
            {'id': '2', 'subject': 'Matematyka', 'grade': '5', 'weight': '3', 'category': 'Praca klasowa'},
            {'id': '3', 'subject': 'Fizyka', 'grade': '2', 'weight': '1', 'category': 'Kartkówka'},
            {'id': '4', 'subject': 'Matematyka', 'grade': '2', 'weight': '1', 'category': 'Zadanie domowe'},
        ]
        res1 = ProgressAnalyzer.analyze(grades_daily_lower)
        self.assertEqual(res1['learning_style']['diagnosis_type'], 'daily_lower')
        self.assertGreater(res1['learning_style']['diff'], 0.40)

        # Uczeń ma 2 ze sprawdzianów i 5 z kartkówek
        grades_exams_lower = [
            {'id': '1', 'subject': 'Fizyka', 'grade': '2', 'weight': '3', 'category': 'Sprawdzian'},
            {'id': '2', 'subject': 'Matematyka', 'grade': '2', 'weight': '3', 'category': 'Praca klasowa'},
            {'id': '3', 'subject': 'Fizyka', 'grade': '5', 'weight': '1', 'category': 'Kartkówka'},
            {'id': '4', 'subject': 'Matematyka', 'grade': '5', 'weight': '1', 'category': 'Zadanie domowe'},
        ]
        res2 = ProgressAnalyzer.analyze(grades_exams_lower)
        self.assertEqual(res2['learning_style']['diagnosis_type'], 'exams_lower')
        self.assertLess(res2['learning_style']['diff'], -0.40)

    def test_mail_sender_progress_report_html_new_features(self):
        from datetime import datetime, timedelta

        from librus2mail.mail_sender import MailSender
        from librus2mail.progress_analyzer import ProgressAnalyzer

        now = datetime(2026, 9, 20)
        grades = [
            {'id': '1', 'subject': 'Matematyka', 'grade': '4', 'weight': '2', 'date': '2026-09-15', 'category': 'Sprawdzian'},
            {'id': '2', 'subject': 'Matematyka', 'grade': '3', 'weight': '1', 'date': '2026-09-16', 'category': 'Kartkówka'},
            {'id': '3', 'subject': 'Fizyka', 'grade': '5', 'weight': '1', 'date': '2026-08-01'},
        ]
        analysis = ProgressAnalyzer.analyze(grades, period_start=now - timedelta(days=7), period_end=now)
        user_cfg = {'librus_login': 'test_user', 'librus_login_name': 'Kacper'}

        html = MailSender.create_mail_content_for_progress_report(user_cfg, analysis)

        # Weryfikacja obecności kluczowych sekcji w szablonie HTML
        self.assertIn('Przewodnik rodzica: Jak rozumieć wskaźniki w raporcie?', html)
        self.assertIn('Sprawdziany vs Bieżąca praca', html)
        self.assertIn('Kalkulator szans i zagrożeń', html)
        self.assertIn('Czerwony Pasek', html)
        self.assertIn('Ciche przedmioty', html)
        self.assertIn('Dynamika i forma ucznia', html)

    def test_progress_analyzer_period_comparison_metrics(self):
        from datetime import datetime, timedelta

        from librus2mail.mail_sender import MailSender
        from librus2mail.progress_analyzer import ProgressAnalyzer

        now = datetime(2026, 9, 20)
        # Okres bieżący (T0): 13.09 - 20.09 (ostatnie 7 dni)
        # Okres poprzedni (T-1): 06.09 - 13.09 (wcześniejsze 7 dni)
        # Historia przed T-1: < 06.09
        grades_progress = [
            # Przed T-1
            {'id': '1', 'subject': 'Matematyka', 'grade': '3', 'weight': '1', 'date': '2026-09-01'},
            # T-1 (Poprzedni okres): słabsze oceny (średnia 2.50)
            {'id': '2', 'subject': 'Matematyka', 'grade': '2', 'weight': '1', 'date': '2026-09-08'},
            {'id': '3', 'subject': 'Fizyka', 'grade': '3', 'weight': '1', 'date': '2026-09-09'},
            # T0 (Bieżący okres): znakomita poprawa (średnia 5.00)
            {'id': '4', 'subject': 'Matematyka', 'grade': '5', 'weight': '2', 'date': '2026-09-15'},
            {'id': '5', 'subject': 'Fizyka', 'grade': '5', 'weight': '1', 'date': '2026-09-16'},
        ]

        res = ProgressAnalyzer.analyze(grades_progress, period_start=now - timedelta(days=7), period_end=now)
        pc = res['period_comparison']

        self.assertTrue(pc['enabled'])
        self.assertTrue(pc['has_prev_data'])
        self.assertEqual(pc['current_count'], 2)
        self.assertEqual(pc['prev_count'], 2)
        self.assertGreater(pc['current_avg'], pc['prev_avg'])
        self.assertGreater(pc['avg_diff'], 1.50)
        self.assertEqual(pc['status'], 'significant_progress')
        self.assertIn('PROGRES', pc['badge_text'])
        self.assertTrue(any(s['subject'] == 'Matematyka' for s in pc['top_improved_subjects']))

        # Test wygenerowania HTML
        user_cfg = {'librus_login': '888', 'librus_login_name': 'Zosia'}
        html = MailSender.create_mail_content_for_progress_report(user_cfg, res)
        self.assertIn('PROGRES', html)
        self.assertIn('Dynamika i forma ucznia', html)

    def test_progress_analyzer_period_comparison_warning(self):
        from datetime import datetime, timedelta

        from librus2mail.progress_analyzer import ProgressAnalyzer

        now = datetime(2026, 9, 20)
        grades_drop = [
            # T-1: bdb oceny (5, 5)
            {'id': '1', 'subject': 'Matematyka', 'grade': '5', 'weight': '1', 'date': '2026-09-08'},
            {'id': '2', 'subject': 'Fizyka', 'grade': '5', 'weight': '1', 'date': '2026-09-09'},
            # T0: spadek ocen (2, 1)
            {'id': '3', 'subject': 'Matematyka', 'grade': '2', 'weight': '1', 'date': '2026-09-15'},
            {'id': '4', 'subject': 'Fizyka', 'grade': '1', 'weight': '1', 'date': '2026-09-16'},
        ]

        res = ProgressAnalyzer.analyze(grades_drop, period_start=now - timedelta(days=7), period_end=now)
        pc = res['period_comparison']

        self.assertTrue(pc['enabled'])
        self.assertTrue(pc['has_prev_data'])
        self.assertLess(pc['avg_diff'], -2.0)
        self.assertEqual(pc['status'], 'warning')
        self.assertIn('SPADEK', pc['badge_text'])
        self.assertTrue(any(s['subject'] == 'Matematyka' for s in pc['declining_subjects']))

    def test_progress_report_resolve_output_path_and_render_standalone(self):
        import tempfile

        from librus2mail.progress_report import render_standalone_html, resolve_output_path

        # 1. Test render_standalone_html
        rendered = render_standalone_html("Tytuł Raportu", "<div>Zawartość raportu</div>")
        self.assertIn("<!DOCTYPE html>", rendered)
        self.assertIn("<meta charset=\"UTF-8\">", rendered)
        self.assertIn("<title>Tytuł Raportu</title>", rendered)
        self.assertIn("<div>Zawartość raportu</div>", rendered)

        # 2. Test resolve_output_path
        # Single user, explicit path
        p1 = resolve_output_path("raport.html", "111222", total_users=1)
        self.assertEqual(p1, "raport.html")

        # Multiple users, static path -> adds suffix
        p2 = resolve_output_path("raport.html", "111222", total_users=2)
        self.assertEqual(p2, "raport_111222.html")

        # Custom format template with {login}
        p3 = resolve_output_path("podglad_{login}.html", "111222", total_users=1)
        self.assertEqual(p3, "podglad_111222.html")

        # Directory path
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = os.path.join(tmpdir, "raporty")
            p4 = resolve_output_path(out_dir + "/", "111222", total_users=1)
            self.assertEqual(p4, os.path.join(out_dir, "raport_111222.html"))
            self.assertTrue(os.path.isdir(out_dir))

    def test_progress_report_save_html_execution(self):
        import tempfile

        import yaml

        from librus2mail.progress_report import run_progress_reports
        from librus2mail.storage import FileStorage

        with tempfile.TemporaryDirectory() as temp_dir:
            cfg_path = os.path.join(temp_dir, 'config.yaml')
            storage_dir = os.path.join(temp_dir, 'storage')
            html_out = os.path.join(temp_dir, 'raport_podglad.html')
            os.makedirs(storage_dir, exist_ok=True)

            st = FileStorage(storage_dir=storage_dir)
            st.save_grades_details('888999', [
                {'id': 'g1', 'subject': 'Fizyka', 'grade': '5', 'weight': '2', 'date': '2026-09-15', 'category': 'Sprawdzian'}
            ])

            cfg_data = {
                'storage_dir': storage_dir,
                'librus_users': [{
                    'librus_login': '888999',
                    'librus_login_name': 'Krzysztof',
                    'notification_receivers': ['test@example.com']
                }],
                # Note: No 'mail' section needed when using --save-html!
            }

            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg_data, f)

            test_args = ['librus_progress_report.py', '-c', cfg_path, '--save-html', html_out]
            with patch.object(sys, 'argv', test_args):
                with patch('librus2mail.storage.FileStorage', return_value=st):
                    run_progress_reports()

            self.assertTrue(os.path.isfile(html_out))
            with open(html_out, encoding='utf-8') as f:
                content = f.read()

            self.assertIn("<!DOCTYPE html>", content)
            self.assertIn("Raport postępów ucznia", content)
            self.assertIn("Krzysztof", content)
            self.assertIn("Fizyka", content)
            self.assertIn("888999", content)

            # Verification that last_progress_report_date was NOT advanced in storage
            self.assertIsNone(st.get_last_progress_report_date('888999'))

    def test_storage_list_stored_logins_and_cli_storage_dir(self):
        import tempfile

        import yaml

        from librus2mail.progress_report import run_progress_reports
        from librus2mail.storage import FileStorage

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_storage = os.path.join(temp_dir, 'custom_storage')
            os.makedirs(custom_storage, exist_ok=True)
            html_out = os.path.join(temp_dir, 'out.html')

            st = FileStorage(storage_dir=custom_storage)
            st.save_grades_details('999111', [
                {'id': 'g9', 'subject': 'Historia', 'grade': '6', 'weight': '1', 'date': '2026-09-10', 'category': 'Aktywność'}
            ])
            # Set student name
            file_path = os.path.join(custom_storage, '999111.json')
            import json
            with open(file_path, encoding='utf-8') as f:
                d = json.load(f)
            d['librus_login_name'] = "Testowy Uczeń"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(d, f)

            self.assertIn('999111', st.list_stored_logins())

            cfg_path = os.path.join(temp_dir, 'config.yaml')
            cfg_data = {
                'storage_dir': 'storage',  # purposefully different from custom_storage
                'librus_users': [],
            }
            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg_data, f)

            # Test using -s flag pointing to custom_storage
            test_args = ['librus_progress_report.py', '-c', cfg_path, '-s', custom_storage, '-o', html_out, '--force']
            with patch.object(sys, 'argv', test_args):
                run_progress_reports()

            self.assertTrue(os.path.isfile(html_out))
            with open(html_out, encoding='utf-8') as f:
                content = f.read()
            self.assertIn("Testowy Uczeń", content)
            self.assertIn("Historia", content)

    def test_collector_parse_item_datetime(self):
        from librus2mail.librus_collector import parse_item_datetime

        # ISO format
        dt1 = parse_item_datetime("2026-09-15T14:30:00")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.day, 15)

        # Standard datetime string
        dt2 = parse_item_datetime("2026-09-10 12:00:00")
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2.hour, 12)

        # Polish day-of-week grade format
        dt3 = parse_item_datetime("2026-09-08 (wt.)")
        self.assertIsNotNone(dt3)
        self.assertEqual(dt3.day, 8)

        # Item dictionary
        dt4 = parse_item_datetime({'datetime': '2026-09-16 15:39:20'})
        self.assertIsNotNone(dt4)
        self.assertEqual(dt4.minute, 39)

        # Invalid/empty
        self.assertIsNone(parse_item_datetime(""))
        self.assertIsNone(parse_item_datetime(None))

    def test_collector_simulation_period_and_save_html(self):
        import json
        import tempfile

        import yaml

        from librus2mail.librus_collector import run_collector
        from librus2mail.storage import FileStorage

        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = os.path.join(temp_dir, 'storage')
            os.makedirs(storage_dir, exist_ok=True)
            cfg_path = os.path.join(temp_dir, 'config.yaml')
            html_out = os.path.join(temp_dir, 'powiadomienie.html')

            now = datetime.now()
            d_recent = (now - timedelta(days=2)).strftime('%Y-%m-%d %H:%M:%S')
            d_old = (now - timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')

            st = FileStorage(storage_dir=storage_dir)
            st.save_grades_details('777111', [
                {'id': 'g_rec', 'subject': 'Biologia', 'grade': '5', 'weight': '2', 'date': d_recent, 'category': 'Sprawdzian'},
                {'id': 'g_old', 'subject': 'Matematyka', 'grade': '3', 'weight': '1', 'date': d_old, 'category': 'Kartkówka'}
            ])
            # Add messages & notifications to student json
            st_path = os.path.join(storage_dir, '777111.json')
            with open(st_path, encoding='utf-8') as f:
                d = json.load(f)
            d['librus_login_name'] = "Alicja Nowak"
            d['known_messages'] = [
                f"Zajęcia taneczne{d_recent}Instruktor (Instruktor) [Nauczyciel]",
                f"Archiwalna wiadomość{d_old}Sekretariat (Sekretariat) [Pracownik]"
            ]
            d['known_notifications'] = [
                f"Wycieczka do teatruNauczyciel{(now - timedelta(days=2)).strftime('%Y-%m-%d')}",
                f"Dawne ogłoszenieNauczyciel{(now - timedelta(days=20)).strftime('%Y-%m-%d')}"
            ]
            with open(st_path, 'w', encoding='utf-8') as f:
                json.dump(d, f)

            cfg_data = {
                'storage_dir': storage_dir,
                'librus_users': [],
            }
            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg_data, f)

            # Run simulation with 5 days period (should capture only recent items, excluding old items)
            run_collector(
                config_path=cfg_path,
                storage_dir=storage_dir,
                days=5,
                output_html=html_out,
                dry_run=True,
                offline=True,
            )

            self.assertTrue(os.path.isfile(html_out))
            with open(html_out, encoding='utf-8') as f:
                content = f.read()

            self.assertIn("Alicja Nowak", content)
            self.assertIn("Biologia", content)
            self.assertIn("Zajęcia taneczne", content)
            self.assertIn("Wycieczka do teatru", content)
            # Old items must NOT be included in the period notification
            self.assertNotIn("Archiwalna wiadomość", content)
            self.assertNotIn("Dawne ogłoszenie", content)

    def test_updates_notifier_standalone_offline_run(self):
        import json
        import tempfile

        import yaml

        from librus2mail.updates_notifier import run_notifier

        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = os.path.join(temp_dir, 'storage')
            os.makedirs(storage_dir, exist_ok=True)
            cfg_path = os.path.join(temp_dir, 'config.yaml')
            html_out = os.path.join(temp_dir, 'notif_standalone.html')

            now = datetime.now()
            d_recent = (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')

            st_path = os.path.join(storage_dir, '555666.json')
            with open(st_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'librus_login': '555666',
                    'librus_login_name': 'Tomasz Zieliński',
                    'known_messages': [f"Ważny komunikat{d_recent}Wychowawca (Wychowawca) [Nauczyciel]"],
                    'known_notifications': [f"Zebranie z rodzicamiDyrekcja{(now - timedelta(days=1)).strftime('%Y-%m-%d')}"],
                    'grades_history': {
                        'g55': {
                            'id': 'g55',
                            'subject': 'Geografia',
                            'grade': '5',
                            'weight': '2',
                            'date': d_recent,
                            'category': 'Kartkówka',
                        }
                    }
                }, f)

            cfg_data = {
                'storage_dir': storage_dir,
                'librus_users': [],
            }
            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg_data, f)

            results = run_notifier(
                config_path=cfg_path,
                storage_dir=storage_dir,
                days=3,
                dry_run=True,
                output_html=html_out,
                offline=True,
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['login'], '555666')
            self.assertEqual(len(results[0]['messages']), 1)
            self.assertEqual(len(results[0]['notifications']), 1)
            self.assertEqual(len(results[0]['grades']), 1)

            self.assertTrue(os.path.isfile(html_out))
            with open(html_out, encoding='utf-8') as f:
                content = f.read()
            self.assertIn("Tomasz Zieliński", content)
            self.assertIn("Ważny komunikat", content)
            self.assertIn("Geografia", content)

    def test_pipeline_orchestrator_modes(self):
        import tempfile

        import yaml

        from librus2mail.collect_and_notify import run_pipeline

        with tempfile.TemporaryDirectory() as temp_dir:
            storage_dir = os.path.join(temp_dir, 'storage')
            os.makedirs(storage_dir, exist_ok=True)
            cfg_path = os.path.join(temp_dir, 'config.yaml')

            cfg_data = {
                'storage_dir': storage_dir,
                'librus_users': [],
                'mail': {'use_gmail': False, 'login': 'test@example.com', 'password': 'pwd'},
            }
            with open(cfg_path, 'w', encoding='utf-8') as f:
                yaml.dump(cfg_data, f)

            # Test 1: collect_only with offline=True (should finish without error)
            run_pipeline(
                config_path=cfg_path,
                storage_dir=storage_dir,
                collect_only=True,
                offline=True,
            )

            # Test 2: notify_only with dry_run (should finish without error)
            run_pipeline(
                config_path=cfg_path,
                storage_dir=storage_dir,
                notify_only=True,
                dry_run=True,
            )

            # Test 3: report with dry_run and force (should finish without error)
            run_pipeline(
                config_path=cfg_path,
                storage_dir=storage_dir,
                report=True,
                dry_run=True,
                force=True,
            )

    def test_storage_watermarks_persistence(self):
        import json
        import tempfile

        from librus2mail.storage import FileStorage

        with tempfile.TemporaryDirectory() as temp_dir:
            storage = FileStorage(temp_dir)
            login = "123456u"

            # Check initial state
            self.assertIsNone(storage.get_last_collect_time(login))
            self.assertIsNone(storage.get_last_notify_time(login))

            # Save and verify last_collect_time
            collect_iso = "2026-09-18T10:00:00"
            storage.save_last_collect_time(login, collect_iso)
            self.assertEqual(storage.get_last_collect_time(login), collect_iso)

            # Save and verify last_notify_time / last_update_create
            notify_iso = "2026-09-18T12:30:00"
            storage.save_last_notify_time(login, notify_iso)
            self.assertEqual(storage.get_last_notify_time(login), notify_iso)

            # Check backward/alias compatibility: last_update_create in raw JSON
            file_path = os.path.join(temp_dir, f"{login}.json")
            with open(file_path, encoding='utf-8') as f:
                data = json.load(f)
            self.assertEqual(data.get('last_collect_time'), collect_iso)
            self.assertEqual(data.get('last_notify_time'), notify_iso)
            self.assertEqual(data.get('last_update_create'), notify_iso)

    def test_updates_notifier_watermark_flow(self):
        import tempfile
        from unittest.mock import MagicMock

        from librus2mail.storage import FileStorage
        from librus2mail.updates_notifier import UpdatesNotifier

        with tempfile.TemporaryDirectory() as temp_dir:
            storage = FileStorage(temp_dir)
            login = "test_student"
            user_cfg = {
                'librus_login': login,
                'librus_login_name': "Jan Kowalski",
                'email': "parent@example.com",
                'read_grades': True,
            }
            config = {
                'storage_dir': temp_dir,
                'librus_users': [user_cfg],
                'mail': {'use_gmail': False, 'login': 'test@example.com', 'password': 'pwd'},
            }

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Populate storage with initial history
            storage.save_messages_details(login, [
                {'id': 'msg1', 'title': 'Wiadomość 1', 'sender': 'Nauczyciel', 'datetime': now_str}
            ])
            storage.save_grades_details(login, [
                {'id': 'grade1', 'subject': 'Matematyka', 'grade': '5', 'weight': '2', 'date': '2026-09-18'}
            ])

            mock_mail_sender = MagicMock()
            notifier = UpdatesNotifier(config, storage=storage, mail_sender=mock_mail_sender)

            # 1. Preview mode (dry_run=True): should not advance last_notify_time
            notifier.process_user_notifications(user_cfg, dry_run=True)
            self.assertIsNone(storage.get_last_notify_time(login))
            mock_mail_sender.send_mail_with_messages.assert_not_called()

            # 2. Production delivery: sends mail and saves last_notify_time
            notifier.process_user_notifications(user_cfg, dry_run=False)
            first_notify_time = storage.get_last_notify_time(login)
            self.assertIsNotNone(first_notify_time)
            self.assertEqual(mock_mail_sender.send_mail_with_messages.call_count, 1)

            # 3. Subsequent run without new items: should find 0 new items because cutoff is after the old items
            mock_mail_sender.reset_mock()
            res_next = notifier.process_user_notifications(user_cfg, dry_run=False)
            self.assertEqual(len(res_next['messages']), 0)
            self.assertEqual(len(res_next['grades']), 0)
            mock_mail_sender.send_mail_with_messages.assert_not_called()

    def test_no_new_items_logs_skip_notification(self):
        import tempfile
        from unittest.mock import MagicMock, patch

        from librus2mail.librus_collector import LibrusCollector
        from librus2mail.storage import FileStorage
        from librus2mail.updates_notifier import UpdatesNotifier

        with tempfile.TemporaryDirectory() as temp_dir:
            storage = FileStorage(temp_dir)
            login = "test_student_logs"
            user_cfg = {
                'librus_login': login,
                'librus_login_name': "Anna Nowak",
                'email': "parent@example.com",
                'read_grades': True,
            }
            config = {
                'storage_dir': temp_dir,
                'librus_users': [user_cfg],
                'mail': {'use_gmail': False, 'login': 'test@example.com', 'password': 'pwd'},
            }

            # Test UpdatesNotifier logging when no new items are found
            mock_mail_sender = MagicMock()
            notifier = UpdatesNotifier(config, storage=storage, mail_sender=mock_mail_sender)

            with self.assertLogs('librus2mail.updates_notifier', level='INFO') as cm:
                res = notifier.process_user_notifications(
                    user_cfg,
                    new_messages=[],
                    new_notifications=[],
                    new_grades=[],
                    dry_run=False,
                )
                self.assertEqual(len(res['messages']), 0)
                self.assertTrue(
                    any("Brak nowych informacji" in msg and "nie zostało wysłane" in msg for msg in cm.output),
                    f"Expected skip log not found in: {cm.output}"
                )

            # Test LibrusCollector logging when no new items are found
            collector = LibrusCollector(config, storage=storage)
            mock_librus = MagicMock()
            mock_librus.get_not_known_messages_and_mark_as_known.return_value = []
            mock_librus.get_not_known_notifications_and_mark_as_known.return_value = []
            mock_librus.get_not_known_grades_and_mark_as_known.return_value = []
            collector.parsers[login] = mock_librus

            with patch('librus2mail.librus_collector.sleep'):
                with self.assertLogs('librus2mail.librus_collector', level='INFO') as cm_collector:
                    collect_res = collector.collect_user(user_cfg)
                    self.assertTrue(collect_res['success'])
                    self.assertTrue(
                        any("Brak nowych wpisów w dzienniku" in msg for msg in cm_collector.output),
                        f"Expected collection log not found in: {cm_collector.output}"
                    )

    def test_collector_delay_between_users(self):
        config_default = {
            'storage_dir': 'storage',
        }
        users = [
            {'librus_login': '111', 'librus_login_name': 'Uczeń 1'},
            {'librus_login': '222', 'librus_login_name': 'Uczeń 2'},
            {'librus_login': '333', 'librus_login_name': 'Uczeń 3'},
        ]

        collector = LibrusCollector(config_default, storage=MagicMock())
        with patch.object(collector, 'collect_user', return_value={'success': True}) as mock_collect:
            with patch('librus2mail.librus_collector.sleep') as mock_sleep:
                collector.collect_all(users)
                self.assertEqual(mock_collect.call_count, 3)
                # Domyślny delay to 10 sekund, wywoływany dla 2. i 3. użytkownika (nie dla 1.)
                self.assertEqual(mock_sleep.call_count, 2)
                mock_sleep.assert_has_calls([unittest.mock.call(10.0), unittest.mock.call(10.0)])

        # Test z niestandardową wartością w konfiguracji
        config_custom = {
            'storage_dir': 'storage',
            'delay_between_users_s': 7,
        }
        collector_custom = LibrusCollector(config_custom, storage=MagicMock())
        with patch.object(collector_custom, 'collect_user', return_value={'success': True}):
            with patch('librus2mail.librus_collector.sleep') as mock_sleep_custom:
                collector_custom.collect_all(users)
                self.assertEqual(mock_sleep_custom.call_count, 2)
                mock_sleep_custom.assert_has_calls([unittest.mock.call(7.0), unittest.mock.call(7.0)])

    def test_collector_error_notification_dispatch(self):
        config = {
            'storage_dir': 'storage',
            'send_error_notifications': True,
            'error_cooldown_s': 1800,
            'login_retry_delay_s': 0,
        }
        user_cfg = {
            'librus_login': '12345',
            'librus_login_name': 'Janek',
            'notification_receivers': ['rodzic@example.com'],
            'send_error_notifications': True,
        }

        mock_mail_sender = MagicMock()
        mock_mail_sender.send_error_notification.return_value = True

        mock_storage = MagicMock()
        collector = LibrusCollector(config, storage=mock_storage, mail_sender=mock_mail_sender)

        # Symulacja błędu podczas logowania
        with patch('librus2mail.librus_collector.Librus') as mock_librus_cls:
            mock_inst = MagicMock()
            mock_inst.login.side_effect = Exception("Nie udało się pominąć kroku 2FA")
            mock_librus_cls.return_value = mock_inst

            res = collector.collect_user(user_cfg)
            self.assertFalse(res['success'])
            self.assertEqual(res['step'], 'logowanie')
            self.assertIn("2FA", res['error'])

            # Weryfikacja wysłania powiadomienia e-mail o błędzie
            mock_mail_sender.send_error_notification.assert_called_once()
            call_kwargs = mock_mail_sender.send_error_notification.call_args.kwargs
            self.assertEqual(call_kwargs['user_config'], user_cfg)
            self.assertEqual(call_kwargs['step_name'], 'logowanie')
            self.assertEqual(call_kwargs['cooldown_s'], 1800)
            self.assertEqual(call_kwargs['storage'], mock_storage)

    def test_run_collector_skips_notifier_when_collection_fails(self):
        config = {
            'librus_users': [{'librus_login': '111', 'librus_login_name': 'Uczeń 1'}],
            'storage_dir': 'storage',
            'work-in-loop': False,
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = os.path.join(tmpdir, 'config.yaml')
            with open(cfg_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f)

            with patch('librus2mail.librus_collector.LibrusCollector.collect_all') as mock_collect_all, \
                 patch('librus2mail.librus_collector.UpdatesNotifier.process_user_notifications') as mock_notifier:
                # Kolektor zwraca błąd pobierania
                mock_collect_all.return_value = {
                    '111': {'success': False, 'login': '111', 'error': 'Timeout'}
                }
                run_collector(config_path=cfg_file)
                # Powiadomienia o nowościach NIE powinny być wywołane, gdy pobieranie zawiodło
                mock_notifier.assert_not_called()

    def test_updates_notifier_summary_override_and_one_summary_message(self):
        """Testuje czy opcja one_summary_message i flaga --summary wysyłają 1 mail podsumowujący."""
        user_cfg = {
            'librus_login': '12345',
            'librus_login_name': 'Kasia',
            'notification_receivers': ['parent@example.com'],
            'one_summary_message': False,
        }
        mock_messages = [{'title': 'M', 'sender': 'S', 'datetime': '2026-09-18 10:00:00', 'body': 'Treść'}]
        mock_notifications = [{'title': 'O', 'sender': 'S', 'date': '2026-09-18', 'body': 'Treść'}]
        mock_grades = [{'id': '1', 'subject': 'Matematyka', 'grade': '5', 'date': '2026-09-18'}]

        mock_storage = MagicMock()
        mock_storage.get_student_name.return_value = 'Kasia'
        mock_storage.get_last_notify_time.return_value = None

        mock_sender = MagicMock()

        notifier = UpdatesNotifier({'mail': {'use_gmail': False}}, storage=mock_storage)
        notifier.get_or_create_mail_sender = MagicMock(return_value=mock_sender)

        # 1. Domyślnie one_summary_message=False -> 3 osobne maile
        notifier.process_user_notifications(
            user_config=dict(user_cfg),
            new_messages=mock_messages,
            new_notifications=mock_notifications,
            new_grades=mock_grades,
            dry_run=False,
        )
        mock_sender.send_mail_with_summary.assert_not_called()
        mock_sender.send_mail_with_messages.assert_called_once()
        mock_sender.send_mail_with_notifications.assert_called_once()
        mock_sender.send_mail_with_grades.assert_called_once()

        mock_sender.reset_mock()

        # 2. Flaga summary=True (np. z CLI --summary) nadpisuje one_summary_message=False -> 1 zbiorczy mail
        notifier.process_user_notifications(
            user_config=dict(user_cfg),
            new_messages=mock_messages,
            new_notifications=mock_notifications,
            new_grades=mock_grades,
            dry_run=False,
            summary=True,
        )
        mock_sender.send_mail_with_summary.assert_called_once()
        mock_sender.send_mail_with_messages.assert_not_called()
        mock_sender.send_mail_with_notifications.assert_not_called()
        mock_sender.send_mail_with_grades.assert_not_called()

        mock_sender.reset_mock()

        # 3. user_config z one_summary_message=True -> 1 zbiorczy mail
        cfg_with_summary = dict(user_cfg)
        cfg_with_summary['one_summary_message'] = True
        notifier.process_user_notifications(
            user_config=cfg_with_summary,
            new_messages=mock_messages,
            new_notifications=mock_notifications,
            new_grades=mock_grades,
            dry_run=False,
        )
        mock_sender.send_mail_with_summary.assert_called_once()
        mock_sender.send_mail_with_messages.assert_not_called()

    def test_login_when_2fa_encountered_parses_form_and_sends_baner_header(self):
        mock_session = MagicMock()

        # Step 1: portalRodzina
        resp1 = MagicMock(status_code=200, url='https://api.librus.pl/OAuth/Authorization?client_id=46')
        # Step 2: POST login returns 2FA goTo
        resp2 = MagicMock(status_code=200)
        resp2.json.return_value = {'status': 'ok', 'goTo': '/OAuth/Authorization/2FA?client_id=46'}

        # Step 3: GET 2FA page with HTML form containing hidden CSRF token
        html_2fa = """
        <html>
        <body>
            <form action="/OAuth/Authorization/2FA/Confirm" method="POST">
                <input type="hidden" name="csrf_token" value="secret_csrf_123" />
                <input type="hidden" name="state" value="state_abc" />
                <button type="submit">Pomiń</button>
            </form>
        </body>
        </html>
        """
        resp3_2fa = MagicMock(status_code=200, url='https://api.librus.pl/OAuth/Authorization/2FA?client_id=46')
        resp3_2fa.content = html_2fa.encode('utf-8')

        # Step 4: POST 2FA returns goTo final grant
        resp4_2fa_post = MagicMock(status_code=200)
        resp4_2fa_post.json.return_value = {'status': 'ok', 'goTo': '/OAuth/Authorization/Grant?client_id=46'}

        # Step 5: GET final grant lands on synergia
        resp5_final = MagicMock(status_code=200, url='https://synergia.librus.pl/loguj/portalRodzina?code=xyz')

        mock_session.get.side_effect = [resp1, resp3_2fa, resp5_final]
        mock_session.post.side_effect = [resp2, resp4_2fa_post]

        librus = Librus({'librus_login': '123', 'librus_password': 'p!'})
        with patch('requests.Session', return_value=mock_session):
            librus.login()
            self.assertTrue(librus.logged)
            # Weryfikacja drugiego wywołania POST (pominięcie 2FA)
            self.assertEqual(mock_session.post.call_count, 2)
            second_post_call = mock_session.post.call_args_list[1]
            target_url = second_post_call[0][0]
            post_data = second_post_call[1]['data']
            post_headers = second_post_call[1]['headers']

            # Target URL powinien być pobrany z formularza
            self.assertEqual(target_url, 'https://api.librus.pl/OAuth/Authorization/2FA/Confirm')
            # Payload powinien zawierać ukryte tokeny z formularza oraz skip=true
            self.assertEqual(post_data.get('csrf_token'), 'secret_csrf_123')
            self.assertEqual(post_data.get('state'), 'state_abc')
            self.assertEqual(post_data.get('skip'), 'true')
            # Nagłówki powinny zawierać x-baner
            self.assertIn('x-baner', post_headers)

    def test_collector_login_retry_recovers_on_second_attempt(self):
        config = {
            'storage_dir': 'storage',
            'login_retries': 2,
            'login_retry_delay_s': 0,
        }
        collector = LibrusCollector(config, storage=MagicMock())
        user_cfg = {
            'librus_login': '12345',
            'librus_login_name': 'Janek',
            'read_messages': False,
            'read_grades': False,
        }

        with patch('librus2mail.librus_collector.Librus') as mock_librus_cls:
            mock_inst = MagicMock()
            # Próba 1 zawodzi, próba 2 kończy się sukcesem
            mock_inst.login.side_effect = [Exception("Błąd 2FA"), None]
            mock_librus_cls.return_value = mock_inst

            res = collector.collect_user(user_cfg)
            self.assertTrue(res['success'])
            self.assertEqual(mock_inst.login.call_count, 2)


if __name__ == '__main__':
    unittest.main()




