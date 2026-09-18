import unittest
from unittest.mock import MagicMock, patch
from librus import Librus, NotLogged


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

    def test_mail_sender_create_mail_content_for_grades(self):
        from MailSender import MailSender
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
        from MailSender import MailSender
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
        from GmailSender import GmailSender
        from SmtpSender import SmtpSender

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
        from storage import FileStorage, create_storage
        st = create_storage()
        self.assertIsInstance(st, FileStorage)
        self.assertEqual(st.storage_dir, "storage")

    def test_file_storage_persistence(self):
        import tempfile
        from storage import FileStorage, create_storage

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
        from storage import FileStorage

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

    def test_storage_error_tracking(self):
        import tempfile
        from storage import FileStorage

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
        from MailSender import MailSender
        import requests

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
        import time
        import json
        import tempfile
        from MailSender import MailSender
        from storage import FileStorage

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
            with open(fpath, 'r', encoding='utf-8') as f:
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
        from GmailSender import GmailSender
        from SmtpSender import SmtpSender
        from storage import FileStorage

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
        from config import read_config
        with self.assertRaises(FileNotFoundError) as ctx:
            read_config('non_existent_config_file_12345.yaml')
        self.assertIn("config.example.yaml", str(ctx.exception))
        self.assertIn("README.md", str(ctx.exception))

    def test_read_config_valid_file_loads_successfully(self):
        import tempfile
        from config import read_config
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
        from progress_analyzer import parse_numeric_grade, parse_weight, parse_grade_date, get_predicted_grade

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
        from progress_analyzer import ProgressAnalyzer
        from datetime import datetime

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
        import tempfile
        import shutil
        from storage import FileStorage

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
        from MailSender import MailSender
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
        from GmailSender import GmailSender
        from SmtpSender import SmtpSender

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
        import sys
        import tempfile
        import os
        import yaml
        from progress_report import run_progress_reports
        from storage import FileStorage

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
        test_args = ['progress_report.py', '-c', cfg_path, '--dry-run']
        with patch.object(sys, 'argv', test_args):
            with patch('storage.FileStorage', return_value=st):
                # Should execute cleanly without errors or sending emails
                run_progress_reports()


    def test_progress_analyzer_new_features(self):
        from progress_analyzer import ProgressAnalyzer
        from datetime import datetime, timedelta

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
        from progress_analyzer import ProgressAnalyzer

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
        from MailSender import MailSender
        from progress_analyzer import ProgressAnalyzer
        from datetime import datetime, timedelta

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


if __name__ == '__main__':
    unittest.main()



