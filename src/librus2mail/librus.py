import logging
import random
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from time import sleep
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# URLe
PORTAL_RODZINA_URL = 'https://synergia.librus.pl/loguj/portalRodzina'
OAUTH_DEFAULT_URL = 'https://api.librus.pl/OAuth/Authorization?client_id=46'
MESSAGES_URL = 'https://synergia.librus.pl/wiadomosci'
MESSAGE_BODY_URL = 'https://synergia.librus.pl'
NOTIFICATIONS_URL = 'https://synergia.librus.pl/ogloszenia'
GRADES_URL = 'https://synergia.librus.pl/przegladaj_oceny/uczen'
TIMETABLE_URL = 'https://synergia.librus.pl/terminarz'
PLAN_LEKCJI_URL = 'https://synergia.librus.pl/przegladaj_plan_lekcji'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'


class NotLogged(Exception):
    def __init__(self, message="Not logged into Librus"):
        logger.error(f"Nie zalogowany: {message}")
        self.message = message
        super().__init__(self.message)


DEFAULT_LESSON_TIMES: dict[int, tuple[str, str]] = {
    1: ("08:00", "08:45"),
    2: ("08:55", "09:40"),
    3: ("09:50", "10:35"),
    4: ("10:45", "11:30"),
    5: ("11:50", "12:35"),
    6: ("12:50", "13:35"),
    7: ("13:45", "14:30"),
    8: ("14:35", "15:20"),
    9: ("15:25", "16:10"),
    10: ("16:15", "17:00"),
}


class Librus:
    """
    Klasa obsługująca autoryzację i scraping danych z systemu Librus Synergia.
    Zaktualizowany przepływ logowania bazuje na mechanizmie portalu rodzina (synergia.librus.pl/loguj/portalRodzina).
    """
    logged = False
    unread_count = None

    def __init__(self, config: dict, storage=None):
        self.__storage = storage
        self.__do_read_messages = config.get('read_messages', True)
        self.__do_read_grades = config.get('read_grades', True)
        self.__do_read_timetable = config.get('read_timetable', True)
        self.__do_read_schedule = config.get('read_schedule', True)
        raw_ret = config.get('schedule_retention_days', 30)
        try:
            self.__schedule_retention_days = int(raw_ret) if raw_ret is not None else 30
        except (ValueError, TypeError):
            self.__schedule_retention_days = 30
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
        self.timetable = []
        self.schedule = []
        # Używamy spójnego, nowoczesnego User-Agenta desktopowego.
        # Losowanie random za każdym razem sprawia, że Librus traktuje każde zapytanie
        # jako logowanie z nowego urządzenia i wymusza procedurę 2FA.
        user_agent = config.get('user_agent') or USER_AGENT
        self.__headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        }
        self.__session = requests.Session()

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
        if hasattr(self, '_Librus__session') and self.__session:
            try:
                self.__session.close()
            except Exception:
                pass
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
            soup_2fa = BeautifulSoup(grant_res.content, 'html.parser')
            form_2fa = soup_2fa.find('form')

            two_fa_payload: dict[str, str] = {}
            action_target = grant_res.url
            if form_2fa:
                action_attr = form_2fa.get('action')
                if action_attr:
                    action_target = urllib.parse.urljoin(grant_res.url, action_attr)
                for hidden_input in form_2fa.find_all('input', type='hidden'):
                    h_name = hidden_input.get('name')
                    h_val = hidden_input.get('value', '')
                    if h_name:
                        two_fa_payload[h_name] = h_val

            two_fa_payload['action'] = 'requiredActions'
            two_fa_payload['skip'] = 'true'

            two_fa_headers = {
                **self.__headers,
                'Referer': grant_res.url,
                'X-Requested-With': 'XMLHttpRequest',
                **self.__generate_baner_header(),
            }
            two_fa_res = self.__session.post(action_target, data=two_fa_payload, headers=two_fa_headers)
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
            elif 'code=' in two_fa_res.url and 'synergia.librus.pl' in two_fa_res.url:
                logger.info("Pominięcie 2FA przekierowało bezpośrednio do Synergii")
                grant_res = two_fa_res
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
            if hasattr(self, 'messages') and self.messages and hasattr(self.__storage, 'save_messages_details'):
                self.__storage.save_messages_details(
                    str(self.__librus_login),
                    self.messages
                )
            if hasattr(self, 'notifications') and self.notifications and hasattr(self.__storage, 'save_notifications_details'):
                self.__storage.save_notifications_details(
                    str(self.__librus_login),
                    self.notifications
                )
            if hasattr(self, 'timetable') and self.timetable and hasattr(self.__storage, 'save_timetable_entries'):
                self.__storage.save_timetable_entries(
                    str(self.__librus_login),
                    self.timetable
                )
            if hasattr(self, 'schedule') and self.schedule and hasattr(self.__storage, 'save_schedule_entries'):
                self.__storage.save_schedule_entries(
                    str(self.__librus_login),
                    self.schedule,
                    retention_days=self.__schedule_retention_days,
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

    @property
    def do_read_timetable(self) -> bool:
        return self.__do_read_timetable

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

    def _parse_timetable_soup(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        m_sel = soup.find('select', {'name': 'miesiac'})
        r_sel = soup.find('select', {'name': 'rok'})
        cal_month = None
        cal_year = None
        if m_sel:
            selected_m = [opt.get('value') for opt in m_sel.find_all('option') if opt.get('selected') is not None]
            if selected_m and str(selected_m[0]).isdigit():
                cal_month = int(selected_m[0])
        if r_sel:
            selected_r = [opt.get('value') for opt in r_sel.find_all('option') if opt.get('selected') is not None]
            if selected_r and str(selected_r[0]).isdigit():
                cal_year = int(selected_r[0])

        if not cal_month or not cal_year:
            now = datetime.now()
            cal_month = cal_month or now.month
            cal_year = cal_year or now.year

        entries: list[dict[str, Any]] = []
        for num_div in soup.find_all('div', class_='kalendarz-numer-dnia'):
            day_str = num_div.get_text(strip=True)
            if not day_str.isdigit():
                continue
            day = int(day_str)
            date_str = f"{cal_year:04d}-{cal_month:02d}-{day:02d}"

            parent_day = num_div.find_parent('div', class_='kalendarz-dzien')
            if not parent_day:
                continue

            for td in parent_day.find_all('td'):
                onclick = td.get('onclick', '')
                title_attr = td.get('title', '')

                if 'szczegoly_wolne' in onclick:
                    # Nieobecność nauczyciela
                    m_id = re.search(r'/(\d+)', onclick)
                    raw_id = m_id.group(1) if m_id else f"absence_{date_str}"
                    entry_id = f"{raw_id}_{date_str}"

                    text = td.get_text(separator=' ', strip=True)
                    teacher = ""
                    hours = "Cały dzień"
                    if 'Nauczyciel:' in text:
                        t_part = text.split('Nauczyciel:')[1]
                        if 'Godziny:' in t_part:
                            teacher = t_part.split('Godziny:')[0].strip()
                            hours = t_part.split('Godziny:')[1].strip()
                        else:
                            teacher = t_part.strip()

                    entries.append({
                        'id': entry_id,
                        'date': date_str,
                        'type': 'absence',
                        'category': 'Nieobecność nauczyciela',
                        'teacher': teacher,
                        'time': hours,
                        'raw_text': text,
                    })

                elif 'szczegoly' in onclick:
                    m_id = re.search(r'/(\d+)', onclick)
                    entry_id = m_id.group(1) if m_id else None
                    if not entry_id:
                        continue

                    subject_span = td.find('span', class_='przedmiot')
                    subject = subject_span.get_text(strip=True) if subject_span else ''

                    teacher = ''
                    description = ''
                    add_date = ''
                    if title_attr:
                        clean_title = re.sub(r'<br\s*/?>', '\n', title_attr)
                        for line in clean_title.split('\n'):
                            line = line.strip()
                            if line.startswith('Nauczyciel:'):
                                teacher = line.replace('Nauczyciel:', '').strip()
                            elif line.startswith('Opis:'):
                                description = line.replace('Opis:', '').strip()
                            elif line.startswith('Data dodania:'):
                                add_date = line.replace('Data dodania:', '').strip()

                    td_lines = [line_text.strip() for line_text in td.get_text(separator='\n').split('\n') if line_text.strip()]
                    lesson_no = ''
                    category = 'Inne'

                    for line in td_lines:
                        clean_line = line.strip(',').strip()
                        if 'Nr lekcji:' in clean_line:
                            lesson_no = clean_line.replace('Nr lekcji:', '').strip()
                        for cat in ['Sprawdzian', 'Kartkówka', 'Praca klasowa', 'Zadanie domowe', 'Projekt', 'Wycieczka']:
                            if cat.lower() in clean_line.lower():
                                category = cat
                                break

                    entry_type = 'test' if any(cat in category for cat in ['Sprawdzian', 'Kartkówka', 'Praca klasowa']) else 'event'

                    entries.append({
                        'id': entry_id,
                        'date': date_str,
                        'type': entry_type,
                        'category': category,
                        'subject': subject,
                        'lesson_no': lesson_no,
                        'teacher': teacher,
                        'description': description,
                        'add_date': add_date,
                    })

        return entries

    def fetch_timetable(self, force: bool = False, month: int | None = None, year: int | None = None) -> list[dict[str, Any]]:
        if not self.__do_read_timetable and not force:
            logger.info("Pobieranie terminarza jest wyłączone w konfiguracji (read_timetable: false)")
            self.timetable = []
            return []

        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram terminarz (sprawdziany i nieobecności)")
        if month and year:
            headers = {**self.__headers, 'Referer': TIMETABLE_URL}
            res = self.__session.post(TIMETABLE_URL, data={'miesiac': str(month), 'rok': str(year)}, headers=headers)
            if res.status_code != 200:
                logger.error(f"Pobieranie terminarza dla {month}/{year}: {res.status_code} {res.reason}")
                raise requests.HTTPError(f"HTTP {res.status_code}: {res.reason}", response=res)
            soup = BeautifulSoup(res.content, 'html.parser')
            entries = self._parse_timetable_soup(soup)
        else:
            soup = self.parse_page(TIMETABLE_URL)
            entries = self._parse_timetable_soup(soup)

            # Jeśli jesteśmy pod koniec miesiąca (od 24. dnia), pobieramy również kolejny miesiąc
            if datetime.now().day >= 24:
                try:
                    now = datetime.now()
                    next_month = 1 if now.month == 12 else now.month + 1
                    next_year = now.year + 1 if now.month == 12 else now.year
                    sleep(2)
                    headers = {**self.__headers, 'Referer': TIMETABLE_URL}
                    res_next = self.__session.post(TIMETABLE_URL, data={'miesiac': str(next_month), 'rok': str(next_year)}, headers=headers)
                    if res_next.status_code == 200:
                        soup_next = BeautifulSoup(res_next.content, 'html.parser')
                        next_entries = self._parse_timetable_soup(soup_next)
                        existing_ids = {e['id'] for e in entries}
                        for ne in next_entries:
                            if ne['id'] not in existing_ids:
                                entries.append(ne)
                                existing_ids.add(ne['id'])
                except Exception as e:
                    logger.warning(f"Nie udało się pobrać terminarza na kolejny miesiąc: {e}")

        entries.sort(key=lambda e: (e.get('date', ''), e.get('lesson_no', '')))
        logger.info(f"Pobrano {len(entries)} wpisów z terminarza")
        self.timetable = entries
        self.save_state()
        return entries

    def _parse_schedule_soup(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        table = soup.find('table', class_=lambda c: c and 'plan-lekcji' in c)
        if not table:
            table = soup.find('table', class_=lambda c: c and 'decorated' in c and soup.find('td', id='timetableEntryBox'))
        if not table:
            return []

        # Wykrycie dat w nagłówkach kolumn
        header_dates: dict[int, str] = {}
        header_row = table.find('tr')
        if header_row:
            ths = header_row.find_all(['th', 'td'])
            for idx, th in enumerate(ths):
                th_text = th.get_text(separator=' ', strip=True)
                m_iso = re.search(r'(\d{4}-\d{2}-\d{2})', th_text)
                if m_iso:
                    header_dates[idx] = m_iso.group(1)
                else:
                    m_pl = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', th_text)
                    if m_pl:
                        header_dates[idx] = f"{m_pl.group(3)}-{m_pl.group(2)}-{m_pl.group(1)}"

        entries: list[dict[str, Any]] = []

        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue

            first_text = cells[0].get_text(strip=True)
            if not first_text.isdigit():
                continue
            lesson_no = int(first_text)

            row_time_from = ""
            row_time_to = ""
            for c in cells[:3]:
                c_text = c.get_text(separator=' ', strip=True).replace('\xa0', ' ')
                m_times = re.findall(r'\b\d{1,2}[:.]\d{2}\b', c_text)
                if len(m_times) >= 2:
                    row_time_from = m_times[0].replace('.', ':').zfill(5)
                    row_time_to = m_times[1].replace('.', ':').zfill(5)
                    break
            if not row_time_from and lesson_no in DEFAULT_LESSON_TIMES:
                row_time_from, row_time_to = DEFAULT_LESSON_TIMES[lesson_no]

            for col_idx, cell in enumerate(cells):
                is_entry_box = cell.get('id') == 'timetableEntryBox' or 'timetableEntryBox' in cell.get('class', [])
                if not is_entry_box and col_idx not in header_dates:
                    continue

                date_str = cell.get('data-date') or cell.get('date') or header_dates.get(col_idx)
                if not date_str:
                    continue

                time_from = (
                    cell.get('data-time_from')
                    or cell.get('data-time-from')
                    or cell.get('data-date-from')
                    or cell.get('date_from')
                    or row_time_from
                )
                time_to = (
                    cell.get('data-time_to')
                    or cell.get('data-time-to')
                    or cell.get('data-date-to')
                    or cell.get('date_to')
                    or row_time_to
                )
                if time_from and len(time_from) < 5 and ':' in time_from:
                    time_from = time_from.zfill(5)
                if time_to and len(time_to) < 5 and ':' in time_to:
                    time_to = time_to.zfill(5)

                cell_text = cell.get_text(separator=' ', strip=True).replace('\xa0', ' ')
                if not cell_text or cell_text in ('-', '') or cell_text.isdigit():
                    continue

                text_divs = cell.find_all('div', class_='text')
                blocks = text_divs if text_divs else [cell]

                info_div = cell.find('div', class_=lambda c: c and 'plan-lekcji-info' in c)
                info_text = info_div.get_text(separator=' ', strip=True).replace('\xa0', ' ') if info_div else ""

                tooltip_attrs: dict[str, str] = {}
                a_tag = cell.find('a')
                if a_tag and a_tag.get('title'):
                    raw_title = a_tag.get('title', '')
                    clean_title = re.sub(r'<br\s*/?>', '\n', raw_title)
                    clean_title = re.sub(r'<[^>]+>', '', clean_title)
                    for line in clean_title.split('\n'):
                        if ':' in line:
                            k, v = line.split(':', 1)
                            tooltip_attrs[k.strip().lower()] = v.strip()

                for b_idx, block in enumerate(blocks):
                    block_text = re.sub(r'\s+', ' ', block.get_text(separator=' ', strip=True).replace('\xa0', ' ')).strip()
                    if not block_text:
                        continue

                    sub_tag = block.find('b')
                    subject = ""
                    rest = ""
                    if sub_tag:
                        subject = re.sub(r'\s+', ' ', sub_tag.get_text(strip=True).replace('\xa0', ' ')).strip()
                        rest = block_text.replace(subject, '', 1).strip(' -')
                    elif '-' in block_text:
                        parts = block_text.split('-', 1)
                        subject = parts[0].strip()
                        rest = parts[1].strip()
                    else:
                        m_split = re.search(r'^(.*?)(?:\s+(?:s\.|sala|\()\s*.*)$', block_text, re.IGNORECASE)
                        if m_split and m_split.group(1).strip():
                            subject = m_split.group(1).strip()
                            rest = block_text[len(subject):].strip(' -')
                        else:
                            subject = block_text

                    subject = re.sub(r'\s+', ' ', subject).strip(' -')
                    teacher = ""
                    classroom = ""
                    if rest:
                        m_room = re.search(r'(?:s\.|sala)\s*([0-9a-zA-Z_.-]+)', rest, re.IGNORECASE)
                        if m_room:
                            classroom = m_room.group(1).strip('. ')
                            teacher = re.sub(r'(?:s\.|sala)\s*([0-9a-zA-Z_.-]+)', '', rest, flags=re.IGNORECASE).strip(' ,.-')
                        else:
                            teacher = rest.strip(' ,()')

                    teacher = re.sub(r'\s+', ' ', teacher).strip(' ,.-')
                    if 'nauczyciel' in tooltip_attrs and not teacher:
                        teacher = re.sub(r'\s+', ' ', tooltip_attrs['nauczyciel'].replace('\xa0', ' ')).strip()
                    if 'sala' in tooltip_attrs and not classroom:
                        classroom = re.sub(r'\s+', ' ', tooltip_attrs['sala'].replace('\xa0', ' ')).strip('. ')

                    has_strike = bool(
                        block.find(['s', 'strike', 'del'])
                        or 'line-through' in block.get('style', '')
                        or 'line-through' in cell.get('style', '')
                        or 'odwolana' in block.get('class', [])
                        or 'odwolana' in cell.get('class', [])
                    )

                    all_context = f"{info_text} {cell_text} {' '.join(tooltip_attrs.values())}".lower()
                    is_cancelled = False
                    is_substitution = False
                    is_moved = False
                    substitution_info = ""

                    if 'odwołan' in all_context or 'odwolana' in all_context or (has_strike and 'zastęp' not in all_context):
                        is_cancelled = True
                    elif 'zastęp' in all_context or 'zastep' in all_context:
                        is_substitution = True
                        if tooltip_attrs:
                            sub_parts = []
                            if 'przedmiot' in tooltip_attrs:
                                sub_parts.append(tooltip_attrs['przedmiot'])
                            if 'nauczyciel' in tooltip_attrs:
                                sub_parts.append(f"p. {tooltip_attrs['nauczyciel']}")
                            if 'sala' in tooltip_attrs:
                                sub_parts.append(f"s. {tooltip_attrs['sala']}")
                            substitution_info = ", ".join(sub_parts)
                        elif info_text:
                            substitution_info = info_text
                    elif 'przesunię' in all_context or 'przesunie' in all_context:
                        is_moved = True

                    entry_id = f"sched_{date_str}_{lesson_no}_{subject}_{b_idx}"
                    entries.append({
                        'id': entry_id,
                        'date': date_str,
                        'lesson_no': lesson_no,
                        'time_from': time_from,
                        'time_to': time_to,
                        'time_range': f"{time_from} - {time_to}" if time_from and time_to else "",
                        'subject': subject,
                        'teacher': teacher,
                        'classroom': classroom,
                        'is_cancelled': is_cancelled,
                        'is_substitution': is_substitution,
                        'is_moved': is_moved,
                        'substitution_info': substitution_info,
                        'info': info_text,
                        'raw_text': block_text,
                    })

        entries.sort(key=lambda x: (x.get('date', ''), x.get('lesson_no', 0)))
        return entries

    def fetch_schedule(self, force: bool = False, date: datetime | None = None) -> list[dict[str, Any]]:
        if not self.__do_read_schedule and not force:
            logger.info("Pobieranie planu lekcji jest wyłączone w konfiguracji (read_schedule: false)")
            self.schedule = []
            return []

        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram plan lekcji")
        target_dt = date or datetime.now()
        if target_dt.weekday() == 4 and target_dt.hour >= 15:
            target_dt = target_dt + timedelta(days=3)
        elif target_dt.weekday() == 5:
            target_dt = target_dt + timedelta(days=2)
        elif target_dt.weekday() == 6:
            target_dt = target_dt + timedelta(days=1)

        monday = target_dt - timedelta(days=target_dt.weekday())
        sunday = monday + timedelta(days=6)
        week_str = f"{monday.strftime('%Y-%m-%d')}_{sunday.strftime('%Y-%m-%d')}"

        headers = {**self.__headers, 'Referer': PLAN_LEKCJI_URL}
        entries = []
        try:
            res = self.__session.post(PLAN_LEKCJI_URL, data={'tydzien': week_str}, headers=headers)
            if res.status_code == 200:
                soup = BeautifulSoup(res.content, 'html.parser')
                entries = self._parse_schedule_soup(soup)
        except Exception as e:
            logger.warning(f"POST do planu lekcji ({week_str}) nie powiódł się ({e}), próbuję GET...")

        if not entries:
            soup = self.parse_page(PLAN_LEKCJI_URL)
            entries = self._parse_schedule_soup(soup)

        logger.info(f"Pobrano {len(entries)} lekcji z planu lekcji")
        self.schedule = entries
        self.save_state()
        return entries

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
