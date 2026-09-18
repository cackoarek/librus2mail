import random
import time
from time import sleep
from typing import Any

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

from .base_logger import logger

# URLe
PORTAL_RODZINA_URL = 'https://synergia.librus.pl/loguj/portalRodzina'
OAUTH_DEFAULT_URL = 'https://api.librus.pl/OAuth/Authorization?client_id=46'
MESSAGES_URL = 'https://synergia.librus.pl/wiadomosci'
MESSAGE_BODY_URL = 'https://synergia.librus.pl'
NOTIFICATIONS_URL = 'https://synergia.librus.pl/ogloszenia'
GRADES_URL = 'https://synergia.librus.pl/przegladaj_oceny/uczen'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'


class NotLogged(Exception):
    def __init__(self, message="Not logged into Librus"):
        logger.error(f"Nie zalogowany: {message}")
        self.message = message
        super().__init__(self.message)


class Librus:
    """
    Klasa obsługująca autoryzację i scraping danych z systemu Librus Synergia.
    Zaktualizowany przepływ logowania bazuje na mechanizmie portalu rodzina (synergia.librus.pl/loguj/portalRodzina).
    """
    logged = False
    unread_count = None

    def __init__(self, config: dict, storage=None):
        self.__storage = storage
        self.__do_read_messages = config.get('read_messages', False)
        self.__do_read_grades = config.get('read_grades', False)
        self.__librus_login = config.get('librus_login')
        self.__librus_password = config.get('librus_password')

        if self.__storage:
            known = self.__storage.load_known_items(str(self.__librus_login))
            self.__known_messages = known.get('messages', set())
            self.__known_notifications = known.get('notifications', set())
            self.__known_grades = known.get('grades', set())
        else:
            self.__known_messages = set()
            self.__known_notifications = set()
            self.__known_grades = set()

        self.grades = []
        try:
            self.__headers = {'User-Agent': UserAgent().random}
        except Exception:
            self.__headers = {'User-Agent': USER_AGENT}

    @staticmethod
    def __generate_baner_header() -> dict[str, str]:
        """
        Generuje nagłówek 'x-baner' oczekiwany przez skrypt autoryzacji Librusa (Authorization.js).
        """
        now_ms = str(int(time.time() * 1000))
        turnips = "".join([chr(ord(c) + 20) for c in now_ms])
        rnd = str(random.random())
        pre_turnips = "".join([chr(ord(c) + 20) for c in rnd])
        return {'x-baner': f"{pre_turnips}_{turnips}"}

    def login(self):
        self.__session = requests.Session()
        self.logged = False

        logger.info(f"Autoryzuję w Librusie konto {self.__librus_login}")

        # Krok 1: Inicjalizacja sesji przez portalRodzina (ustawia ciasteczka sesyjne DZIENNIKSID i pobiera adres OAuth ze state)
        init_headers = {
            **self.__headers,
            'Referer': 'https://portal.librus.pl/'
        }
        res = self.__session.get(PORTAL_RODZINA_URL, headers=init_headers)
        if res.status_code not in (200, 302):
            logger.error(f"Inicjalizacja autoryzacji konta {self.__librus_login}: {res.status_code} {res.reason}")
            raise requests.HTTPError(f"HTTP {res.status_code}: {res.reason}", response=res)

        login_target_url = res.url or OAUTH_DEFAULT_URL

        # Krok 2: Wysłanie formularza logowania do docelowego punktu OAuth
        logger.info("Logowanie do Librusa")
        post_headers = {
            **self.__headers,
            'Referer': login_target_url,
            'X-Requested-With': 'XMLHttpRequest',
            **self.__generate_baner_header()
        }
        login_payload = {
            'action': 'login',
            'login': self.__librus_login,
            'pass': self.__librus_password
        }
        post_res = self.__session.post(login_target_url, data=login_payload, headers=post_headers)
        if post_res.status_code != 200:
            logger.error(f"Logowanie nie powiodło się: {post_res.status_code} {post_res.reason}")
            raise requests.HTTPError(f"HTTP {post_res.status_code}: {post_res.reason}", response=post_res)

        # Analiza odpowiedzi JSON
        try:
            resp_json = post_res.json()
        except Exception:
            resp_json = None

        next_url = None
        if resp_json:
            status = resp_json.get('status')
            if status == 'ok':
                go_to = resp_json.get('goTo', '')
                next_url = f"https://api.librus.pl{go_to}" if go_to.startswith('/') else go_to
            elif status == 'actionRequired':
                logger.error(f"Konto {self.__librus_login} wymaga akcji w portalu Librus (np. zmiana hasła, 2FA lub akceptacja regulaminu)")
                raise NotLogged(f"Konto {self.__librus_login} wymaga akcji w portalu (actionRequired). Zaloguj się przez przeglądarkę.")
            else:
                error_msg = resp_json.get('message') or resp_json.get('errors') or status or "Nieprawidłowe dane logowania"
                logger.error(f"Odrzucono logowanie dla {self.__librus_login}: {error_msg}")
                raise NotLogged(f"Błąd logowania dla {self.__librus_login}: {error_msg}")
        else:
            # Fallback dla starszych wersji lub bezpośrednich przekierowań
            if 'invalidUserType' in post_res.text or 'Nieprawidłowy login' in post_res.text:
                raise NotLogged(f"Nieprawidłowy login lub hasło dla konta {self.__librus_login}")
            next_url = post_res.headers.get('Location') or OAUTH_DEFAULT_URL

        # Krok 3: Grant uprawnień i obsługa 2FA / requiredActions
        logger.info("Grant uprawnień")
        grant_headers = {
            **self.__headers,
            'Referer': login_target_url
        }
        grant_res = self.__session.get(next_url, headers=grant_headers)

        # Sprawdzenie czy wylądowaliśmy na ekranie 2FA (wymaga potwierdzenia/pominięcia).
        # Uwaga: weryfikujemy wyłącznie grant_res.url (a nie next_url), ponieważ jeśli Librus nie wymaga 2FA,
        # zapytanie GET od razu przekierowuje do synergia.librus.pl z parametrami code i state.
        if '2FA' in grant_res.url:
            logger.info("Wykryto krok 2FA - wysyłam pominięcie (action: requiredActions, skip: true)")
            two_fa_headers = {
                **self.__headers,
                'Referer': grant_res.url,
                'X-Requested-With': 'XMLHttpRequest'
            }
            two_fa_payload = {
                'action': 'requiredActions',
                'skip': 'true'
            }
            two_fa_res = self.__session.post(grant_res.url, data=two_fa_payload, headers=two_fa_headers)
            try:
                two_fa_json = two_fa_res.json()
            except Exception:
                two_fa_json = None

            if two_fa_json and two_fa_json.get('status') == 'ok':
                final_grant = two_fa_json.get('goTo', '')
                if final_grant.startswith('/'):
                    final_grant = f"https://api.librus.pl{final_grant}"
                logger.info("Pobieram docelowy grant autoryzacji")
                grant_res = self.__session.get(final_grant, headers=grant_headers)
            else:
                err_info = two_fa_json or two_fa_res.text[:200]
                logger.error(f"Pominięcie 2FA nie powiodło się: {err_info}")
                raise NotLogged(f"Nie udało się pominąć kroku 2FA: {err_info}")

        if grant_res.status_code not in (200, 302) or 'error=' in grant_res.url:
            logger.error(f"Grant uprawnień nie powiódł się: {grant_res.status_code} {grant_res.url}")
            raise NotLogged(f"Autoryzacja w Librusie nie powiodła się: {grant_res.url}")

        logger.info(f"Autoryzacja zakończona pomyślnie. URL docelowy: {grant_res.url}")
        self.__session.cookies.set('TestCookie', '1', domain='synergia.librus.pl', path='/')
        self.__cookies = self.__session.cookies
        self.logged = True

    def __get_message_body(self, link: str) -> str:
        if not self.logged:
            raise NotLogged()

        url = f"{MESSAGE_BODY_URL}{link}"
        logger.info(f"Pobieram treść wiadomość {link}")
        res = self.__session.get(url, headers=self.__headers)
        if res.status_code != 200:
            logger.error(f"Pobieranie treści wiadomości {link}: {res.status_code} {res.reason}")
            raise requests.HTTPError(f"HTTP {res.status_code}: {res.reason}", response=res)

        soup = BeautifulSoup(res.content, 'html.parser')
        message_body_elem = soup.find('div', attrs={'class': 'container-message-content'})
        message_body = message_body_elem.get_text().strip() if message_body_elem else ""

        sleep(5)
        return message_body

    def fetch_messages(self):
        def correct_sender(s: str) -> str:
            sender = s.strip().split('(')[0].strip()
            return ' '.join(sender.split()[::-1])

        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram listę wiadomości")
        soup = self.parse_page(MESSAGES_URL)

        # Weryfikacja czy sesja nie została przekierowana na stronę logowania
        if soup.find('div', id='AuthorizationForm') or soup.find('input', id='Login'):
            self.logged = False
            raise NotLogged("Sesja w portalu Synergia wygasła lub nie powiodła się autoryzacja")

        mess_tab = (
            soup.select_one('table.decorated.stretch')
            or soup.select_one('table.decorated')
            or soup.select_one('table.container-message table')
        )

        # Jeśli nie znaleziono tabeli na /wiadomosci, sprawdź bezpośredni widok folderu odebrane (/wiadomosci/5)
        if not mess_tab:
            try:
                soup_inbox = self.parse_page(f"{MESSAGES_URL}/5")
                mess_tab = (
                    soup_inbox.select_one('table.decorated.stretch')
                    or soup_inbox.select_one('table.decorated')
                    or soup_inbox.select_one('table.container-message table')
                )
                if mess_tab:
                    soup = soup_inbox
            except Exception as e:
                logger.debug(f"Próba odpytania /wiadomosci/5 nie powiodła się: {e}")

        if not mess_tab:
            page_text = soup.get_text().lower()
            if 'brak wiadomości' in page_text or 'skrzynka jest pusta' in page_text:
                logger.info("Skrzynka odbiorcza jest pusta (brak wiadomości)")
            else:
                title = soup.find('title').get_text().strip() if soup.find('title') else 'Brak'
                tables = [f"{t.name}.{'.'.join(t.get('class', []))}" for t in soup.find_all('table')]
                logger.warning(f"Nie znaleziono tabeli wiadomości (Tytuł: '{title}', Tabele: {tables})")

            self.messages = []
            self.unread_count = 0
            return

        tbody = mess_tab.find('tbody') or mess_tab

        messages = []
        for msg_row in tbody.find_all('tr'):
            tds = msg_row.find_all('td')
            if len(tds) < 5:
                continue

            link_elem = tds[2].find('a')
            link = link_elem.attrs.get('href', '').strip() if link_elem else ""

            has_attachment = bool(tds[1].find('img')) if len(tds) > 1 else False

            title = tds[3].get_text().strip()
            sender = correct_sender(tds[2].get_text())
            dt = tds[4].get_text().strip()

            message = {
                'title': title,
                'sender': sender,
                'is_unread': False,
                'datetime': dt,
                'link': link,
                'has_attachment': has_attachment,
                'id': title + dt + tds[2].get_text().strip()
            }

            if message['id'] not in self.__known_messages:
                message['is_unread'] = True
                if self.__do_read_messages and link:
                    message['body'] = self.__get_message_body(link)
                if style := tds[2].attrs.get('style'):
                    message['is_unread'] = 'bold' in style

            messages.append(message)

        # sortowanie w kolejności od najnowszych
        messages = sorted(messages, key=lambda m: m['datetime'], reverse=True)
        self.messages = messages
        self.unread_count = sum(1 for m in messages if m.get('is_unread'))

    def save_state(self) -> None:
        if self.__storage:
            self.__storage.save_known_items(
                str(self.__librus_login),
                self.__known_messages,
                self.__known_notifications,
                self.__known_grades
            )
            if hasattr(self, 'grades') and self.grades:
                self.__storage.save_grades_details(
                    str(self.__librus_login),
                    self.grades
                )

    def get_not_known_messages_and_mark_as_known(self) -> list[dict[str, bool | str | Any]]:
        resp = [message for message in self.messages if message['id'] not in self.__known_messages]
        self.__known_messages.update(message['id'] for message in self.messages)
        self.save_state()
        return resp

    def get_not_known_notifications_and_mark_as_known(self) -> list[dict[str, bool | str | Any]]:
        resp = [notification for notification in self.notifications if notification['id'] not in self.__known_notifications]
        self.__known_notifications.update(notification['id'] for notification in self.notifications)
        self.save_state()
        return resp

    def fetch_notifications(self):
        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram listę ogłoszeń")
        soup = self.parse_page(NOTIFICATIONS_URL)

        # Weryfikacja czy sesja nie została przekierowana na stronę logowania
        if soup.find('div', id='AuthorizationForm') or soup.find('input', id='Login'):
            self.logged = False
            raise NotLogged("Sesja w portalu Synergia wygasła lub nie powiodła się autoryzacja")

        notif_tab = soup.find('div', attrs={'class': 'container-background'})
        if not notif_tab:
            logger.warning("Nie znaleziono kontenera ogłoszeń")
            self.notifications = []
            return

        notifications = []
        for notif_row in notif_tab.find_all('table'):
            tds = notif_row.find_all('td')
            if len(tds) < 4:
                continue

            title = tds[0].get_text().strip()
            sender = tds[1].get_text().strip()
            dt = tds[2].get_text().strip()
            body = tds[3].get_text().strip()

            notification = {
                'title': title,
                'sender': sender,
                'datetime': dt,
                'is_unread': False,
                'body': body,
                'id': title + sender + dt,
            }

            if notification['id'] not in self.__known_notifications:
                notification['is_unread'] = True

            notifications.append(notification)

        # sortowanie w kolejności od najnowszych
        notifications = sorted(notifications, key=lambda m: m['datetime'], reverse=True)
        self.notifications = notifications

    @property
    def do_read_grades(self) -> bool:
        return self.__do_read_grades

    def fetch_grades(self, force: bool = False):
        if not self.__do_read_grades and not force:
            logger.info("Pobieranie ocen jest wyłączone w konfiguracji (read_grades: false)")
            self.grades = []
            return

        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram oceny ucznia")
        soup = self.parse_page(GRADES_URL)

        # Pobieramy widoczne tabele ocen, ignorując ukryte tabele-pułapki (np. z display: none przeciwko rozszerzeniom)
        visible_tables = [
            table for table in soup.find_all('table', class_='decorated')
            if 'display:none' not in table.get('style', '').replace(' ', '').lower()
        ]
        if not visible_tables:
            body = soup.find('div', id='body') or soup
            visible_tables = [
                table for table in body.find_all('table')
                if 'display:none' not in table.get('style', '').replace(' ', '').lower()
            ]

        if not visible_tables:
            logger.warning("Nie znaleziono tabeli ocen")
            self.grades = []
            return

        raw_grades = []
        for table in visible_tables:
            for a in table.find_all('a', class_='ocena'):
                href = a.get('href', '').strip()
                if not href or '/przegladaj_oceny/szczegoly/' not in href:
                    continue

                grade_id = href.split('/')[-1].split('?')[0]
                if not grade_id or grade_id == '000000':
                    continue

                val = a.get_text().strip()
                title_attr = a.get('title', '')

                tr = a.find_parent('tr')
                subject = ''
                if tr:
                    tds = tr.find_all('td')
                    if len(tds) > 1:
                        subject = tds[1].get_text().strip()

                if not subject:
                    parent_table = a.find_parent('table')
                    if parent_table:
                        parent_tr = parent_table.find_parent('tr')
                        if parent_tr:
                            prev_tr = parent_tr.find_previous_sibling('tr')
                            if prev_tr:
                                prev_tds = prev_tr.find_all('td')
                                if len(prev_tds) > 1:
                                    subject = prev_tds[1].get_text().strip()

                category = ''
                date = ''
                teacher = ''
                weight = ''
                comment = ''
                for part in title_attr.replace('<br/>', '<br>').replace('<br />', '<br>').split('<br>'):
                    part = part.strip()
                    if part.startswith('Kategoria:'):
                        category = part.replace('Kategoria:', '').strip()
                    elif part.startswith('Data:'):
                        date = part.replace('Data:', '').strip()
                    elif part.startswith('Nauczyciel:'):
                        teacher = part.replace('Nauczyciel:', '').strip()
                    elif part.startswith('Waga:'):
                        weight = part.replace('Waga:', '').strip()
                    elif part.startswith('Komentarz:'):
                        comment = part.replace('Komentarz:', '').strip()

                raw_grades.append({
                    'id': grade_id,
                    'subject': subject or "Inny przedmiot",
                    'grade': val,
                    'category': category or "-",
                    'date': date or "-",
                    'teacher': teacher or "-",
                    'weight': weight or "-",
                    'comment': comment or "-",
                    'href': href
                })

        # Deduplikacja po ID
        unique_grades = {}
        for g in raw_grades:
            if g['id'] not in unique_grades:
                unique_grades[g['id']] = g

        grades = list(unique_grades.values())
        logger.info(f"Pobrano {len(grades)} ocen")
        self.grades = grades
        self.save_state()

    def get_not_known_grades_and_mark_as_known(self) -> list[dict[str, bool | str | Any]]:
        resp = [grade for grade in self.grades if grade['id'] not in self.__known_grades]
        self.__known_grades.update(grade['id'] for grade in self.grades)
        self.save_state()
        return resp

    def parse_page(self, url: str) -> BeautifulSoup:
        headers = {
            **self.__headers,
            'Referer': 'https://synergia.librus.pl/'
        }
        res = self.__session.get(url, headers=headers)
        if res.status_code != 200:
            logger.error(f"Pobieranie strony {url}: {res.status_code} {res.reason}")
            raise requests.HTTPError(f"HTTP {res.status_code}: {res.reason}", response=res)

        soup = BeautifulSoup(res.content, 'html.parser')

        # Weryfikacja czy odpowiedź to nie strona 'Brak dostępu' lub powrót do logowania
        inside_header = soup.find('h2', class_='inside')
        header_text = inside_header.get_text().strip() if inside_header else ""
        if "Brak dostępu" in header_text or soup.find('div', id='AuthorizationForm') or soup.find('input', id='Login'):
            self.logged = False
            logger.error(f"Odrzucono dostęp do strony {url} ('Brak dostępu' - sesja w Synergii nie jest autoryzowana)")
            raise NotLogged(f"Brak dostępu do strony {url} - sesja w Synergii nie jest autoryzowana")

        return soup
