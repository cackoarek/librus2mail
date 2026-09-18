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

    def test_memory_storage(self):
        from storage import MemoryStorage
        storage = MemoryStorage()
        self.assertFalse(storage.has_existing_data("123"))

        storage.save_known_items("123", {"msg1"}, {"notif1"}, {"grade1"})
        self.assertTrue(storage.has_existing_data("123"))

        data = storage.load_known_items("123")
        self.assertEqual(data['messages'], {"msg1"})
        self.assertEqual(data['notifications'], {"notif1"})
        self.assertEqual(data['grades'], {"grade1"})

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

            # Test factory function
            ram_s = create_storage("RAM")
            self.assertEqual(ram_s.__class__.__name__, "MemoryStorage")
            file_s = create_storage("FILES", storage_dir=tmpdir)
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
        import time
        from storage import MemoryStorage, FileStorage

        # 1. MemoryStorage
        mem = MemoryStorage()
        self.assertIsNone(mem.get_last_error("user1"))
        mem.save_last_error("user1", "Error 1", step="logowanie")
        err = mem.get_last_error("user1")
        self.assertIsNotNone(err)
        self.assertEqual(err['error'], "Error 1")
        self.assertEqual(err['step'], "logowanie")
        self.assertIn('timestamp', err)
        mem.clear_last_error("user1")
        self.assertIsNone(mem.get_last_error("user1"))

        # 2. FileStorage
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = FileStorage(storage_dir=tmpdir)
            self.assertIsNone(fs.get_last_error("user2"))
            fs.save_last_error("user2", "Error 2", step="wiadomości")
            err_f = fs.get_last_error("user2")
            self.assertIsNotNone(err_f)
            self.assertEqual(err_f['error'], "Error 2")
            self.assertEqual(err_f['step'], "wiadomości")

            # Verify that saving known items does not overwrite last_error
            fs.save_known_items("user2", {"m1"}, {"n1"}, {"g1"})
            err_f2 = fs.get_last_error("user2")
            self.assertIsNotNone(err_f2)
            self.assertEqual(err_f2['error'], "Error 2")

            # Verify clearing last_error
            fs.clear_last_error("user2")
            self.assertIsNone(fs.get_last_error("user2"))

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
        from MailSender import MailSender
        from storage import MemoryStorage

        storage = MemoryStorage()
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
        storage._last_errors[user_login]['timestamp'] = time.time() - 3601
        self.assertTrue(MailSender.should_send_error_notification(storage, user_login, "Error A", cooldown_s=3600))

        # Check cooldown_s <= 0 disables throttling
        storage.save_last_error(user_login, "Error A", step="logowanie")
        self.assertTrue(MailSender.should_send_error_notification(storage, user_login, "Error A", cooldown_s=0))

    def test_send_error_notification_gmail_and_smtp(self):
        from GmailSender import GmailSender
        from SmtpSender import SmtpSender
        from storage import MemoryStorage

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
        storage = MemoryStorage()
        test_err = NotLogged("Sesja wygasła")

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


if __name__ == '__main__':
    unittest.main()

