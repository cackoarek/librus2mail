from time import sleep
from typing import Any

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from base_logger import logger

# URLe
OAUTH_URL = 'https://api.librus.pl/OAuth/Authorization?client_id=46&response_type=code&scope=mydata'
AUTH_URL = 'https://api.librus.pl/OAuth/Authorization?client_id=46'
GRANT_URL = 'https://api.librus.pl/OAuth/Authorization/Grant?client_id=46'
MESSAGES_URL = 'https://synergia.librus.pl/wiadomosci'
MESSAGE_BODY_URL = 'https://synergia.librus.pl'
NOTIFICATIONS_URL = 'https://synergia.librus.pl/ogloszenia'
GRADES_URL = 'https://synergia.librus.pl/przegladaj_oceny/uczen'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36'


class NotLogged(Exception):
    def __init__(self, message="Not logged into Librus"):
        logger.error(f"Nie zalogowany: {message}")
        self.message = message
        super().__init__(self.message)


class Librus:
    """
    Klasa na podstawie kodu z https://github.com/Mati365/librus-api/blob/master/lib/api.js
    """
    logged = False
    unread_count = None
    __headers = {'User-Agent': UserAgent().random}

    def __init__(self, config):
        self.__do_read_messages = config.get('read_messages', False)
        self.__librus_login = config.get('librus_login')
        self.__librus_password = config.get('librus_password')
        self.__known_messages = {}
        self.__known_notifications = {}

    def login(self):
        self.__session = requests.Session()

        logger.info(f"Autoryzuję w Librusie konto {self.__librus_login}")
        res = self.__session.get(OAUTH_URL, headers=self.__headers)
        if res.status_code != 200:
            logger.error(
                f"Autoryzacja konta {self.__librus_login}: {res.status_code} {res.error}")
            raise requests.HTTPError(res.status_code, res.error)

        logger.info("Logowanie do Librusa")
        res = self.__session.post(AUTH_URL,
                                  data={'action': 'login',
                                        'login': self.__librus_login,
                                        'pass': self.__librus_password},
                                  headers=self.__headers)
        if res.status_code != 200:
            logger.error(
                f"Logowanie: {res.status_code} {res.error}")
            raise requests.HTTPError(res.status_code, res.error)

        logger.info("Grant uprawnień")
        res = self.__session.get(GRANT_URL, headers=self.__headers)
        if res.status_code != 200:
            logger.error(
                f"Grant uprawnień: {res.status_code} {res.error}")
            raise requests.HTTPError(res.status_code, res.error)

        self.__cookies = self.__session.cookies
        self.logged = True

    def __get_message_body(self, link):
        if not self.logged:
            raise NotLogged()

        url = f"{MESSAGE_BODY_URL}{link}"
        logger.info(f"Pobieram treść wiadomość {link}")
        res = self.__session.get(url,
                                 cookies=self.__cookies,
                                 headers=self.__headers)
        if res.status_code != 200:
            logger.error(
                f"Pobieranie treści wiadomości {link}: {res.status_code} {res.error}")
            raise requests.HTTPError(res.status_code, res.error)

        soup = BeautifulSoup(res.content, 'html.parser')

        message_body = soup.find('div',
                                 attrs={'class': 'container-message-content'})
        message_body = message_body.get_text()

        sleep(5)

        return message_body

    def fetch_messages(self):
        def correct_sender(s):
            # wyrzucenie powtórzonego nazwiska w nawiasie
            sender = s.strip()
            sender = sender.split('(')[0].strip()
            # odwrócenie kolejności - imię i nazwisko
            sender = ' '.join(sender.split()[::-1])
            return sender

        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram listę wiadomości")
        soup = self.parse_page(MESSAGES_URL)

        mess_tab = soup.find('table',
                             attrs={'class': 'decorated stretch'})
        mess_tab = mess_tab.find('tbody')

        messages = []
        for msg_row in mess_tab.find_all('tr'):
            tds = msg_row.find_all('td')
            message = {
                'title': tds[3].get_text().strip(),
                'sender': correct_sender(tds[2].get_text()),
                'is_unread': False,
                'datetime': tds[4].get_text().strip(),
                'link': tds[2].find('a').attrs.get('href').strip(),
                'has_attachment': True if tds[1].find('img') else False,
                'id': tds[3].get_text().strip() + tds[4].get_text().strip() + tds[2].get_text()
            }

            if message['id'] not in self.__known_messages:
                message['is_unread'] = True
                # pobranie treści wiadomości
                if self.__do_read_messages:
                    message['body'] = self.__get_message_body(message.get('link'))
                # czy wiadomość przeczytana?
                if style := tds[2].attrs.get('style'):
                    message['is_unread'] = style.find('bold') > 0

            messages.append(message)

        # sortowanie w kolejności od najnowszych
        messages = sorted(messages, key=lambda m: m['datetime'], reverse=True)
        self.messages = messages

        self.unread_count = sum([m['is_unread'] for m in messages])

    def get_not_known_messages_and_mark_as_known(self) -> list[dict[str, bool | str | Any]]:
        resp = [message for message in self.messages if message['id'] not in self.__known_messages]
        self.__known_messages = set([message['id'] for message in self.messages])
        return resp

    def get_not_known_notifications_and_mark_as_known(self) -> list[dict[str, bool | str | Any]]:
        resp = [notification for notification in self.notifications if
                notification['id'] not in self.__known_notifications]
        self.__known_notifications = set([notification['id'] for notification in self.notifications])
        return resp

    def fetch_notifications(self):
        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram listę ogłoszeń")
        soup = self.parse_page(NOTIFICATIONS_URL)

        notif_tab = soup.find('div',
                              attrs={'class': 'container-background'})

        notifications = []
        for notif_row in notif_tab.find_all('table'):
            tds = notif_row.find_all('td')
            notification = {
                'title': tds[0].get_text().strip(),
                'sender': tds[1].get_text().strip(),
                'datetime': tds[2].get_text().strip(),
                'is_unread': False,
                'body': tds[3].get_text().strip(),
                'id': tds[0].get_text().strip() + tds[1].get_text().strip() + tds[2].get_text().strip(),
                # 'has_attachment': True if tds[1].find('img') else False
            }

            if notification['id'] not in self.__known_notifications:
                notification['is_unread'] = True

            # # czy wiadomość przeczytana? nie widziałem jeszcze ogłoszenia jak wygląda
            # if style := tds[2].attrs.get('style'):
            #     notification['is_unread'] = style.find('bold') > 0

            notifications.append(notification)

        # sortowanie w kolejności od najnowszych
        notifications = sorted(notifications, key=lambda m: m['datetime'], reverse=True)
        self.notifications = notifications

    def fetch_grades(self):
        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram oceny ucznia")
        soup = self.parse_page(GRADES_URL)

        notif_tab = soup.find('div',
                              attrs={'class': 'container-background'})

        notifications = []
        for notif_row in notif_tab.find_all('table'):
            tds = notif_row.find_all('td')
            notification = {
                'title': tds[0].get_text().strip(),
                'sender': tds[1].get_text().strip(),
                'datetime': tds[2].get_text().strip(),
                'is_unread': False,
                'body': tds[3].get_text().strip(),
                'id': tds[0].get_text().strip() + tds[1].get_text().strip() + tds[2].get_text().strip(),
                # 'has_attachment': True if tds[1].find('img') else False
            }

            if notification['id'] not in self.__known_notifications:
                notification['is_unread'] = True

            # # czy wiadomość przeczytana? nie widziałem jeszcze ogłoszenia jak wygląda
            # if style := tds[2].attrs.get('style'):
            #     notification['is_unread'] = style.find('bold') > 0

            notifications.append(notification)

        # sortowanie w kolejności od najnowszych
        notifications = sorted(notifications, key=lambda m: m['datetime'], reverse=True)
        self.notifications = notifications

    def parse_page(self, url):
        res = self.__session.get(url,
                                 cookies=self.__cookies,
                                 headers=self.__headers)
        if res.status_code != 200:
            logger.error(
                f"Pobieranie listy wiadomości: {res.status_code} {res.error}")
            raise requests.HTTPError(res.status_code, res.error)
        soup = BeautifulSoup(res.content, 'html.parser')
        return soup
