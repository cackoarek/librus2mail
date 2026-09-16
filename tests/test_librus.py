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


if __name__ == '__main__':
    unittest.main()

