import logging
import random
import time
import urllib.parse
from datetime import datetime, timedelta
from time import sleep
from typing import Any

import requests
from bs4 import BeautifulSoup

from .dom_parser import (
    parse_announcements_html,
    parse_attendance_html,
    parse_grades_html,
    parse_messages_html,
    parse_schedule_html,
    parse_subjects_from_html,
    parse_timetable_html,
)
from .exceptions import (
    LibrusAuthError,
    LibrusError,
    LibrusNetworkError,
    LibrusParsingError,
    NotLogged,
)

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
ATTENDANCE_URL = 'https://synergia.librus.pl/przegladaj_nb/uczen'

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
DEFAULT_TIMEOUT = 20


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
        self.__do_read_attendance = config.get('read_attendance', True)
        self.attendance: list[dict[str, Any]] = []
        self.attendance_summary: list[dict[str, Any]] = []
        self._attendance_fetched = False
        self.__known_attendance: set[str] = set()
        self.__librus_login = config.get('librus_login')
        raw_password = config.get('librus_password')
        self.__librus_password = (
            raw_password.get_secret_value()
            if hasattr(raw_password, 'get_secret_value')
            else raw_password
        )

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
            except OSError:
                pass
        self.__session = requests.Session()
        self.logged = False

        logger.info(f"Autoryzuję w Librusie konto {self.__librus_login}")

        # Krok 1: Inicjalizacja sesji przez portalRodzina (ustawia ciasteczka sesyjne DZIENNIKSID i pobiera adres OAuth ze state)
        init_headers = {
            **self.__headers,
            'Referer': 'https://portal.librus.pl/'
        }
        try:
            res = self.__session.get(PORTAL_RODZINA_URL, headers=init_headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as e:
            logger.error(f"Inicjalizacja autoryzacji konta {self.__librus_login} nie powiodła się: {e}")
            raise LibrusNetworkError(f"Błąd sieciowy przy inicjalizacji autoryzacji: {e}", request=getattr(e, 'request', None), response=getattr(e, 'response', None)) from e

        if res.status_code not in (200, 302):
            logger.error(f"Inicjalizacja autoryzacji konta {self.__librus_login}: {res.status_code} {res.reason}")
            raise LibrusNetworkError(f"HTTP {res.status_code}: {res.reason} przy inicjalizacji autoryzacji", response=res)

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
        try:
            post_res = self.__session.post(login_target_url, data=login_payload, headers=post_headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as e:
            logger.error(f"Wysyłanie formularza logowania dla {self.__librus_login} nie powiodło się: {e}")
            raise LibrusNetworkError(f"Błąd sieciowy przy logowaniu: {e}", request=getattr(e, 'request', None), response=getattr(e, 'response', None)) from e

        if post_res.status_code != 200:
            logger.error(f"Logowanie nie powiodło się: {post_res.status_code} {post_res.reason}")
            if post_res.status_code in (401, 403):
                raise LibrusAuthError(f"HTTP {post_res.status_code}: {post_res.reason} - brak dostępu do konta {self.__librus_login}")
            raise LibrusNetworkError(f"HTTP {post_res.status_code}: {post_res.reason}", response=post_res)

        # Analiza odpowiedzi JSON
        try:
            resp_json = post_res.json()
        except (ValueError, requests.JSONDecodeError):
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
        try:
            grant_res = self.__session.get(next_url, headers=grant_headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as e:
            logger.error(f"Błąd sieciowy podczas pobierania grantu dla {self.__librus_login}: {e}")
            raise LibrusNetworkError(f"Błąd sieciowy podczas pobierania grantu: {e}", request=getattr(e, 'request', None), response=getattr(e, 'response', None)) from e

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
            try:
                two_fa_res = self.__session.post(action_target, data=two_fa_payload, headers=two_fa_headers, timeout=DEFAULT_TIMEOUT)
            except requests.RequestException as e:
                logger.error(f"Błąd sieciowy podczas wysyłania 2FA dla {self.__librus_login}: {e}")
                raise LibrusNetworkError(f"Błąd sieciowy podczas pomijania 2FA: {e}", request=getattr(e, 'request', None), response=getattr(e, 'response', None)) from e
            try:
                two_fa_json = two_fa_res.json()
            except (ValueError, requests.JSONDecodeError):
                two_fa_json = None

            if two_fa_json and two_fa_json.get('status') == 'ok':
                final_grant = two_fa_json.get('goTo', '')
                if final_grant.startswith('/'):
                    final_grant = f"https://api.librus.pl{final_grant}"
                logger.info("Pobieram docelowy grant autoryzacji")
                try:
                    grant_res = self.__session.get(final_grant, headers=grant_headers, timeout=DEFAULT_TIMEOUT)
                except requests.RequestException as e:
                    logger.error(f"Błąd sieciowy podczas pobierania grantu po 2FA dla {self.__librus_login}: {e}")
                    raise LibrusNetworkError(f"Błąd sieciowy podczas pobierania grantu po 2FA: {e}", request=getattr(e, 'request', None), response=getattr(e, 'response', None)) from e
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
        try:
            res = self.__session.get(url, headers=self.__headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as e:
            logger.error(f"Błąd sieciowy przy pobieraniu wiadomości {link}: {e}")
            raise LibrusNetworkError(f"Błąd sieciowy przy pobieraniu wiadomości: {e}", request=getattr(e, 'request', None), response=getattr(e, 'response', None)) from e

        if res.status_code != 200:
            logger.error(f"Pobieranie treści wiadomości {link}: {res.status_code} {res.reason}")
            raise LibrusNetworkError(f"HTTP {res.status_code}: {res.reason} przy pobieraniu treści wiadomości", response=res)

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
            except (requests.RequestException, NotLogged) as e:
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

        fetch_body_cb = (lambda link: self.__get_message_body(link)) if self.__do_read_messages else None
        try:
            messages = parse_messages_html(
                soup,
                known_messages=self.__known_messages,
                fetch_body_fn=fetch_body_cb,
                do_read_messages=self.__do_read_messages,
            )
        except (LibrusError, requests.RequestException):
            raise
        except Exception as e:
            logger.error(f"Błąd parsowania wiadomości: {e}", exc_info=True)
            raise LibrusParsingError(f"Błąd parsowania wiadomości: {e}") from e
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
            if hasattr(self, 'subjects') and self.subjects and hasattr(self.__storage, 'save_subjects'):
                self.__storage.save_subjects(
                    str(self.__librus_login),
                    self.subjects
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
                )
            if hasattr(self, 'attendance') and (self.attendance or getattr(self, '_attendance_fetched', False) or getattr(self, 'attendance_summary', None)) and hasattr(self.__storage, 'save_attendance'):
                self.__storage.save_attendance(
                    str(self.__librus_login),
                    self.attendance,
                    summary=getattr(self, 'attendance_summary', None),
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

        try:
            self.notifications = parse_announcements_html(
                soup,
                known_notifications=self.__known_notifications,
            )
        except (LibrusError, requests.RequestException):
            raise
        except Exception as e:
            logger.error(f"Błąd parsowania ogłoszeń: {e}", exc_info=True)
            raise LibrusParsingError(f"Błąd parsowania ogłoszeń: {e}") from e

    @property
    def do_read_grades(self) -> bool:
        return self.__do_read_grades

    @property
    def do_read_timetable(self) -> bool:
        return self.__do_read_timetable

    @property
    def do_read_attendance(self) -> bool:
        return self.__do_read_attendance

    def fetch_grades(self, force: bool = False):
        if not self.__do_read_grades and not force:
            logger.info("Pobieranie ocen jest wyłączone w konfiguracji (read_grades: false)")
            self.grades = []
            return

        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram oceny ucznia")
        soup = self.parse_page(GRADES_URL)

        try:
            grades = parse_grades_html(soup)
            subjects = parse_subjects_from_html(soup)
        except (LibrusError, requests.RequestException):
            raise
        except Exception as e:
            logger.error(f"Błąd parsowania ocen: {e}", exc_info=True)
            raise LibrusParsingError(f"Błąd parsowania ocen: {e}") from e

        if not grades:
            logger.warning("Nie znaleziono tabeli ocen")
        logger.info(f"Pobrano {len(grades)} ocen oraz {len(subjects)} przedmiotów")
        self.grades = grades
        self.subjects = subjects
        self.save_state()

    def get_not_known_grades_and_mark_as_known(self) -> list[dict[str, bool | str | Any]]:
        resp = [grade for grade in self.grades if grade['id'] not in self.__known_grades]
        self.__known_grades.update(grade['id'] for grade in self.grades)
        self.save_state()
        return resp

    def _parse_timetable_soup(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        return parse_timetable_html(soup)

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
            try:
                res = self.__session.post(TIMETABLE_URL, data={'miesiac': str(month), 'rok': str(year)}, headers=headers, timeout=DEFAULT_TIMEOUT)
            except requests.RequestException as e:
                logger.error(f"Błąd sieciowy przy pobieraniu terminarza dla {month}/{year}: {e}")
                raise LibrusNetworkError(f"Błąd sieciowy przy pobieraniu terminarza: {e}", request=getattr(e, 'request', None), response=getattr(e, 'response', None)) from e

            if res.status_code != 200:
                logger.error(f"Pobieranie terminarza dla {month}/{year}: {res.status_code} {res.reason}")
                raise LibrusNetworkError(f"HTTP {res.status_code}: {res.reason} przy pobieraniu terminarza", response=res)
            soup = BeautifulSoup(res.content, 'html.parser')
            try:
                entries = self._parse_timetable_soup(soup)
            except Exception as e:
                logger.error(f"Błąd parsowania terminarza: {e}", exc_info=True)
                raise LibrusParsingError(f"Błąd parsowania terminarza: {e}") from e
        else:
            soup = self.parse_page(TIMETABLE_URL)
            try:
                entries = self._parse_timetable_soup(soup)
            except Exception as e:
                logger.error(f"Błąd parsowania terminarza: {e}", exc_info=True)
                raise LibrusParsingError(f"Błąd parsowania terminarza: {e}") from e

            # Jeśli jesteśmy pod koniec miesiąca (od 24. dnia), pobieramy również kolejny miesiąc
            if datetime.now().day >= 24:
                try:
                    now = datetime.now()
                    next_month = 1 if now.month == 12 else now.month + 1
                    next_year = now.year + 1 if now.month == 12 else now.year
                    sleep(2)
                    headers = {**self.__headers, 'Referer': TIMETABLE_URL}
                    res_next = self.__session.post(TIMETABLE_URL, data={'miesiac': str(next_month), 'rok': str(next_year)}, headers=headers, timeout=DEFAULT_TIMEOUT)
                    if res_next.status_code == 200:
                        soup_next = BeautifulSoup(res_next.content, 'html.parser')
                        next_entries = self._parse_timetable_soup(soup_next)
                        existing_ids = {e['id'] for e in entries}
                        for ne in next_entries:
                            if ne['id'] not in existing_ids:
                                entries.append(ne)
                                existing_ids.add(ne['id'])
                except (requests.RequestException, LibrusError) as e:
                    logger.warning(f"Nie udało się pobrać terminarza na kolejny miesiąc: {e}")

        entries.sort(key=lambda e: (e.get('date', ''), e.get('lesson_no', '')))
        logger.info(f"Pobrano {len(entries)} wpisów z terminarza")
        self.timetable = entries
        self.save_state()
        return entries

    def _parse_schedule_soup(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        return parse_schedule_html(soup)

    def fetch_schedule(self, force: bool = False, date: datetime | None = None) -> list[dict[str, Any]]:
        if not self.__do_read_schedule and not force:
            logger.info("Pobieranie planu lekcji jest wyłączone w konfiguracji (read_schedule: false)")
            self.schedule = []
            return []

        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram plan lekcji")
        target_dt = date or datetime.now()
        base_monday = (target_dt - timedelta(days=target_dt.weekday())).date()

        # Pobieramy bieżący tydzień oraz kolejny tydzień w przód (a od piątku również 2 tygodnie w przód)
        weeks_to_fetch = [base_monday, base_monday + timedelta(days=7)]
        if target_dt.weekday() in (4, 5, 6):
            weeks_to_fetch.append(base_monday + timedelta(days=14))

        headers = {**self.__headers, 'Referer': PLAN_LEKCJI_URL}
        entries_by_id: dict[str, dict[str, Any]] = {}

        for w_idx, monday in enumerate(weeks_to_fetch):
            sunday = monday + timedelta(days=6)
            week_str = f"{monday.strftime('%Y-%m-%d')}_{sunday.strftime('%Y-%m-%d')}"
            try:
                if w_idx > 0:
                    sleep(1)
                res = self.__session.post(PLAN_LEKCJI_URL, data={'tydzien': week_str}, headers=headers, timeout=DEFAULT_TIMEOUT)
                if res.status_code == 200:
                    soup = BeautifulSoup(res.content, 'html.parser')
                    try:
                        w_entries = self._parse_schedule_soup(soup)
                    except Exception as parse_err:
                        logger.error(f"Błąd parsowania wycinka planu lekcji ({week_str}): {parse_err}", exc_info=True)
                        raise LibrusParsingError(f"Błąd parsowania planu lekcji: {parse_err}") from parse_err

                    for item in w_entries:
                        eid = item.get('id') or f"{item.get('date')}_{item.get('lesson_no')}"
                        entries_by_id[eid] = item
            except (requests.RequestException, LibrusError) as e:
                if isinstance(e, LibrusParsingError):
                    raise
                logger.warning(f"POST do planu lekcji ({week_str}) nie powiódł się ({e})")

        if not entries_by_id:
            soup = self.parse_page(PLAN_LEKCJI_URL)
            try:
                w_entries = self._parse_schedule_soup(soup)
            except Exception as parse_err:
                logger.error(f"Błąd parsowania planu lekcji: {parse_err}", exc_info=True)
                raise LibrusParsingError(f"Błąd parsowania planu lekcji: {parse_err}") from parse_err

            for item in w_entries:
                eid = item.get('id') or f"{item.get('date')}_{item.get('lesson_no')}"
                entries_by_id[eid] = item

        entries = sorted(
            entries_by_id.values(),
            key=lambda x: (
                x.get('date', ''),
                int(x.get('lesson_no', 0)) if str(x.get('lesson_no', '')).isdigit() else 99,
            ),
        )

        logger.info(f"Pobrano {len(entries)} lekcji z planu lekcji (zakres: {len(weeks_to_fetch)} tyg.)")
        self.schedule = entries
        self.save_state()
        return entries

    def fetch_attendance(self, force: bool = False) -> list[dict[str, Any]]:
        if not self.__do_read_attendance and not force:
            logger.info("Pobieranie frekwencji jest wyłączone w konfiguracji (read_attendance: false)")
            self.attendance = []
            self.attendance_summary = []
            return []

        if not self.logged:
            raise NotLogged()

        logger.info("Pobieram frekwencję ucznia")
        soup = self.parse_page(ATTENDANCE_URL)

        try:
            parsed = parse_attendance_html(soup)
        except (LibrusError, requests.RequestException):
            raise
        except Exception as e:
            logger.error(f"Błąd parsowania frekwencji: {e}", exc_info=True)
            raise LibrusParsingError(f"Błąd parsowania frekwencji: {e}") from e

        entries = parsed.get('entries', [])
        summary = parsed.get('periods_summary', [])
        logger.info(f"Pobrano {len(entries)} wpisów frekwencji")
        self.attendance = entries
        self.attendance_summary = summary
        self._attendance_fetched = True
        self.save_state()
        return entries

    def get_not_known_attendance_and_mark_as_known(self) -> list[dict[str, Any]]:
        resp = [att for att in self.attendance if att.get('id') and att['id'] not in self.__known_attendance]
        self.__known_attendance.update(att['id'] for att in self.attendance if att.get('id'))
        self.save_state()
        return resp

    def parse_page(self, url: str) -> BeautifulSoup:
        headers = {
            **self.__headers,
            'Referer': 'https://synergia.librus.pl/'
        }
        try:
            res = self.__session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
        except requests.RequestException as e:
            logger.error(f"Błąd sieciowy podczas pobierania {url}: {e}")
            raise LibrusNetworkError(f"Błąd sieciowy podczas pobierania {url}: {e}", request=getattr(e, 'request', None), response=getattr(e, 'response', None)) from e

        if res.status_code != 200:
            logger.error(f"Pobieranie strony {url}: {res.status_code} {res.reason}")
            raise LibrusNetworkError(f"HTTP {res.status_code}: {res.reason} przy pobieraniu {url}", response=res)

        soup = BeautifulSoup(res.content, 'html.parser')

        # Weryfikacja czy odpowiedź to nie strona 'Brak dostępu' lub powrót do logowania
        inside_header = soup.find('h2', class_='inside')
        header_text = inside_header.get_text().strip() if inside_header else ""
        if "Brak dostępu" in header_text or soup.find('div', id='AuthorizationForm') or soup.find('input', id='Login'):
            self.logged = False
            logger.error(f"Odrzucono dostęp do strony {url} ('Brak dostępu' - sesja w Synergii nie jest autoryzowana)")
            raise NotLogged(f"Brak dostępu do strony {url} - sesja w Synergii nie jest autoryzowana")

        return soup
