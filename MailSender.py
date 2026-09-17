import html
from datetime import datetime


class MailSender:
    def __init__(self, mail_config):
        self.sender_email = mail_config['login']
        self.password = mail_config['password']

    @staticmethod
    def create_mail_content_for_messages(user_config: dict, messages: list) -> str:
        contents = f"""
            <p>W Librusie dla konta {user_config['librus_login']} <strong>({user_config['librus_login_name']})</strong> pojawiły się <strong>nowe wiadomości</strong>.</p>
            <p>&nbsp;</p>
            <p>Lista wszystkich wiadomości (nowe <strong>boldem</strong>):</p>
            <table border="1" cellspacing="0" cellpadding="10">
            <thead><tr><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
            <tbody>
            """

        for message in messages:
            if message['is_unread']:
                contents += f"""
                    <tr>
                    <td><strong>{message['title']}</strong></td>
                    <td><strong>{message['sender']}</strong></td>
                    <td><strong>{message['datetime']}</strong></td>"""
                if 'body' in message:
                    body = message['body'].replace("\n", "<br>")
                    contents += f"""</tr><tr><td colspan="3">{body}</td>"""
                contents += '</tr>'
            else:
                contents += f"""
                    <tr>
                    <td>{message['title']}</td>
                    <td>{message['sender']}</td>
                    <td>{message['datetime']}</td>
                    </tr>
                    """

        contents += "</tbody></table>"
        return contents

    @staticmethod
    def create_mail_content_for_notifications(user_config: dict, notifications: list) -> str:
        contents = f"""
                <p>W Librusie dla konta {user_config['librus_login']} <strong>({user_config['librus_login_name']})</strong> pojawiły się <strong>nowe ogłoszenia</strong>.</p>
                <p>&nbsp;</p>
                <p>Lista wszystkich ogłoszeń (nowe <strong>boldem</strong>):</p>
                <table border="1" cellspacing="0" cellpadding="10">
                <thead><tr><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
                <tbody>
                """

        for notification in notifications:
            if notification['is_unread']:
                contents += f"""
                        <tr>
                        <td><strong>{notification['title']}</strong></td>
                        <td><strong>{notification['sender']}</strong></td>
                        <td><strong>{notification['datetime']}</strong></td>"""
                if 'body' in notification:
                    body = notification['body'].replace("\n", "<br>")
                    contents += f"""</tr><tr><td colspan="3">{body}</td>"""
                contents += '</tr>'
            else:
                contents += f"""
                        <tr>
                        <td>{notification['title']}</td>
                        <td>{notification['sender']}</td>
                        <td>{notification['datetime']}</td>
                        </tr>
                        """

        contents += "</tbody></table>"
        return contents

    @staticmethod
    def create_mail_content_for_grades(user_config: dict, grades: list) -> str:
        contents = f"""
            <p>W Librusie dla konta {user_config['librus_login']} <strong>({user_config['librus_login_name']})</strong> pojawiły się <strong>nowe oceny</strong>.</p>
            <p>&nbsp;</p>
            <table border="1" cellspacing="0" cellpadding="8" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;">
            <thead>
                <tr style="background-color: #f2f2f2; text-align: left;">
                    <th>Przedmiot</th>
                    <th style="text-align: center;">Ocena</th>
                    <th>Kategoria</th>
                    <th style="text-align: center;">Waga</th>
                    <th>Data</th>
                    <th>Nauczyciel</th>
                    <th>Komentarz</th>
                </tr>
            </thead>
            <tbody>
            """

        for grade in grades:
            weight = grade.get('weight') or '-'
            date = grade.get('date') or '-'
            teacher = grade.get('teacher') or '-'
            category = grade.get('category') or '-'
            comment = grade.get('comment') or '-'
            contents += f"""
                <tr>
                    <td><strong>{grade['subject']}</strong></td>
                    <td style="text-align: center; font-size: 16px;"><strong>{grade['grade']}</strong></td>
                    <td>{category}</td>
                    <td style="text-align: center;">{weight}</td>
                    <td>{date}</td>
                    <td>{teacher}</td>
                    <td>{comment}</td>
                </tr>
                """

        contents += "</tbody></table>"
        return contents

    @staticmethod
    def _create_summary_title(user_config: dict, messages: list, notifications: list, grades: list) -> str:
        parts = []
        if messages:
            count = len(messages)
            if count == 1:
                parts.append("1 nowa wiadomość")
            elif 2 <= count <= 4 or (count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]):
                parts.append(f"{count} nowe wiadomości")
            else:
                parts.append(f"{count} nowych wiadomości")

        if notifications:
            count = len(notifications)
            if count == 1:
                parts.append("1 nowe ogłoszenie")
            elif 2 <= count <= 4 or (count % 10 in [2, 3, 4] and count % 100 not in [12, 13, 14]):
                parts.append(f"{count} nowe ogłoszenia")
            else:
                parts.append(f"{count} nowych ogłoszeń")

        if grades:
            grades_summary = ", ".join([f"{g['subject']}: {g['grade']}" for g in grades[:2]])
            if len(grades) > 2:
                grades_summary += f" (+{len(grades) - 2})"
            parts.append(f"nowe oceny ({grades_summary})")

        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        if not parts:
            return f"{name} - Librus: podsumowanie"
        return f"{name} - Librus: " + ", ".join(parts)

    @staticmethod
    def create_mail_content_for_summary(
        user_config: dict,
        messages: list = None,
        notifications: list = None,
        grades: list = None
    ) -> str:
        messages = messages or []
        notifications = notifications or []
        grades = grades or []

        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        login = user_config.get('librus_login', '')

        contents = f"""
        <p>Zbiorcze powiadomienie z Librusa dla konta {login} <strong>({name})</strong>.</p>
        <p>&nbsp;</p>
        """

        if messages:
            contents += f"""
            <h3 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 5px; margin-top: 20px;">Nowe wiadomości ({len(messages)})</h3>
            <table border="1" cellspacing="0" cellpadding="10" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px;">
            <thead><tr style="background-color: #f2f2f2; text-align: left;"><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
            <tbody>
            """
            for message in messages:
                contents += f"""
                    <tr>
                    <td><strong>{message['title']}</strong></td>
                    <td><strong>{message['sender']}</strong></td>
                    <td><strong>{message['datetime']}</strong></td></tr>"""
                if 'body' in message:
                    body = message['body'].replace("\n", "<br>")
                    contents += f"""<tr><td colspan="3" style="background-color: #fcfcfc;">{body}</td></tr>"""
            contents += "</tbody></table><p>&nbsp;</p>"

        if notifications:
            contents += f"""
            <h3 style="color: #2c3e50; border-bottom: 2px solid #e67e22; padding-bottom: 5px; margin-top: 20px;">Nowe ogłoszenia ({len(notifications)})</h3>
            <table border="1" cellspacing="0" cellpadding="10" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px;">
            <thead><tr style="background-color: #f2f2f2; text-align: left;"><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
            <tbody>
            """
            for notification in notifications:
                contents += f"""
                    <tr>
                    <td><strong>{notification['title']}</strong></td>
                    <td><strong>{notification['sender']}</strong></td>
                    <td><strong>{notification['datetime']}</strong></td></tr>"""
                if 'body' in notification:
                    body = notification['body'].replace("\n", "<br>")
                    contents += f"""<tr><td colspan="3" style="background-color: #fcfcfc;">{body}</td></tr>"""
            contents += "</tbody></table><p>&nbsp;</p>"

        if grades:
            contents += f"""
            <h3 style="color: #2c3e50; border-bottom: 2px solid #27ae60; padding-bottom: 5px; margin-top: 20px;">Nowe oceny ({len(grades)})</h3>
            <table border="1" cellspacing="0" cellpadding="8" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px;">
            <thead>
                <tr style="background-color: #f2f2f2; text-align: left;">
                    <th>Przedmiot</th>
                    <th style="text-align: center;">Ocena</th>
                    <th>Kategoria</th>
                    <th style="text-align: center;">Waga</th>
                    <th>Data</th>
                    <th>Nauczyciel</th>
                    <th>Komentarz</th>
                </tr>
            </thead>
            <tbody>
            """
            for grade in grades:
                weight = grade.get('weight') or '-'
                date = grade.get('date') or '-'
                teacher = grade.get('teacher') or '-'
                category = grade.get('category') or '-'
                comment = grade.get('comment') or '-'
                contents += f"""
                    <tr>
                        <td><strong>{grade['subject']}</strong></td>
                        <td style="text-align: center; font-size: 16px;"><strong>{grade['grade']}</strong></td>
                        <td>{category}</td>
                        <td style="text-align: center;">{weight}</td>
                        <td>{date}</td>
                        <td>{teacher}</td>
                        <td>{comment}</td>
                    </tr>
                    """
            contents += "</tbody></table><p>&nbsp;</p>"

        return contents

    def send_mail_with_messages(self, user_config, messages):
        pass

    def send_mail_with_notifications(self, user_config, notifications):
        pass

    def send_mail_with_grades(self, user_config, grades):
        pass

    def send_mail_with_summary(self, user_config, messages=None, notifications=None, grades=None):
        pass

    @classmethod
    def _get_error_diagnostics(cls, error: Exception) -> tuple[str, str, str]:
        err_name = type(error).__name__
        err_str = str(error)
        err_lower = err_str.lower()

        if err_name == 'NotLogged' or 'brak dostępu' in err_lower or 'sesja' in err_lower or 'nie zalogowany' in err_lower:
            category = "Błąd autoryzacji / sesji Librus"
            diagnosis = "Sesja w portalu Librus Synergia wygasła lub autoryzacja konta nie powiodła się."
            recommendation = (
                "1. Upewnij się, że login i hasło w pliku konfiguracyjnym są poprawne.<br>"
                "2. <strong>Zaloguj się ręcznie przez przeglądarkę na portal.librus.pl</strong> (lub synergia.librus.pl) – "
                "szkoła lub Librus może wymagać zaakceptowania nowego regulaminu, zgody na przetwarzanie danych, zmiany hasła "
                "lub odczytania obowiązkowej wiadomości dyrekcji/ankiety, co blokuje automatyczny dostęp do dziennika.<br>"
                "3. Upewnij się, że konto nie zostało tymczasowo zablokowane z powodu zbyt wielu nieudanych prób logowania."
            )
        elif (
            'connection' in err_name.lower()
            or 'timeout' in err_name.lower()
            or 'ssl' in err_name.lower()
            or 'http' in err_name.lower()
            or 'resolution' in err_lower
            or 'max retries' in err_lower
            or 'failed to establish a new connection' in err_lower
        ):
            category = "Błąd połączenia sieciowego"
            diagnosis = "Nie udało się nawiązać stabilnego połączenia z serwerami Librus (brak połączenia z siecią, timeout lub błąd SSL/DNS)."
            recommendation = (
                "1. Sprawdź połączenie internetowe na serwerze/komputerze uruchamiającym aplikację.<br>"
                "2. Sprawdź w przeglądarce, czy portal https://synergia.librus.pl działa prawidłowo (możliwa przerwa techniczna Librusa).<br>"
                "3. Jeśli problem występuje regularnie, upewnij się, że zapora sieciowa (firewall) nie blokuje zapytań HTTPS."
            )
        elif err_name in ('AttributeError', 'TypeError', 'KeyError', 'IndexError') or 'parse' in err_lower or 'soup' in err_lower:
            category = "Błąd parsowania danych (zmiana struktury HTML)"
            diagnosis = "Dane ze strony Librusa zostały pobrane, lecz skrypt nie był w stanie wyodrębnić z nich informacji. Prawdopodobnie Librus zaktualizował strukturę HTML dziennika."
            recommendation = (
                "1. Sprawdź szczegółowy log w pliku <code>librus.log</code>.<br>"
                "2. Zaloguj się przez przeglądarkę i sprawdź, czy w dzienniku nie pojawił się niestandardowy komunikat lub okno modalne zastępujące widok danych.<br>"
                "3. Jeśli struktura strony uległa trwałej zmianie, konieczna może być aktualizacja selektorów w kodzie."
            )
        else:
            category = f"Błąd wykonania ({err_name})"
            diagnosis = f"Wystąpił nieoczekiwany błąd podczas pracy aplikacji: {err_str}"
            recommendation = "Sprawdź plik <code>librus.log</code> oraz poniższe szczegóły techniczne w celu zdiagnozowania problemu."

        return category, diagnosis, recommendation

    @staticmethod
    def _create_error_title(user_config: dict, error: Exception, step_name: str = "") -> str:
        step_labels = {
            'inicjalizacja': 'Inicjalizacja',
            'logowanie': 'Logowanie',
            'wiadomości': 'Pobieranie wiadomości',
            'ogłoszenia': 'Pobieranie ogłoszeń',
            'oceny': 'Pobieranie ocen'
        }
        step_desc = step_labels.get(step_name, step_name or "Komunikacja")
        name = user_config.get('librus_login_name') or user_config.get('librus_login')
        login = user_config.get('librus_login', '')
        return f"[ALERT] {name} - Librus: Błąd ({step_desc}) [konto {login}]"

    @classmethod
    def create_mail_content_for_error(
        cls,
        user_config: dict,
        error: Exception,
        step_name: str = "",
        details: str = None,
        cooldown_s: int = 3600
    ) -> str:
        step_labels = {
            'inicjalizacja': 'Inicjalizacja parsera',
            'logowanie': 'Logowanie do portalu Synergia',
            'wiadomości': 'Pobieranie wiadomości',
            'ogłoszenia': 'Pobieranie ogłoszeń',
            'oceny': 'Pobieranie ocen'
        }
        step_label = step_labels.get(step_name, step_name or "Komunikacja z portalem")
        category, diagnosis, recommendation = cls._get_error_diagnostics(error)

        name = html.escape(str(user_config.get('librus_login_name') or user_config.get('librus_login', '')))
        login = html.escape(str(user_config.get('librus_login', '')))
        error_msg = html.escape(f"{type(error).__name__}: {str(error)}")
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cooldown_min = max(1, cooldown_s // 60)

        details_html = ""
        if details:
            escaped_details = html.escape(str(details))
            details_html = f"""
            <details style="margin: 15px 0;">
                <summary style="cursor: pointer; color: #7f8c8d; font-size: 13px; font-weight: bold;">Szczegóły techniczne (traceback)</summary>
                <pre style="background-color: #2c3e50; color: #ecf0f1; padding: 12px; border-radius: 4px; font-size: 12px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; margin-top: 8px;">{escaped_details}</pre>
            </details>
            """

        contents = f"""
        <div style="font-family: Arial, sans-serif; color: #333333; max-width: 700px; line-height: 1.5;">
            <div style="background-color: #e74c3c; color: #ffffff; padding: 15px 20px; border-radius: 6px 6px 0 0;">
                <h2 style="margin: 0; font-size: 18px;">⚠️ Librus2mail: Błąd pobierania danych</h2>
            </div>
            
            <div style="border: 1px solid #e0e0e0; border-top: none; padding: 20px; border-radius: 0 0 6px 6px; background-color: #ffffff;">
                <p style="font-size: 14px; margin-top: 0;">
                    Podczas cyklicznego sprawdzania dziennika Librus dla konta <strong>{name}</strong> 
                    (login: <code>{login}</code>) wystąpił błąd uniemożliwiający pobranie aktualnych danych.
                </p>

                <table style="width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 14px;">
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold; width: 28%;">Etap:</td>
                        <td style="padding: 10px; border: 1px solid #dee2e6;">{step_label}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Kategoria błędu:</td>
                        <td style="padding: 10px; border: 1px solid #dee2e6; color: #c0392b; font-weight: bold;">{category}</td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Komunikat:</td>
                        <td style="padding: 10px; border: 1px solid #dee2e6;"><code>{error_msg}</code></td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: bold;">Data wystąpienia:</td>
                        <td style="padding: 10px; border: 1px solid #dee2e6;">{current_time}</td>
                    </tr>
                </table>

                <div style="background-color: #e8f4f8; border-left: 4px solid #3498db; padding: 12px 16px; margin: 20px 0; border-radius: 4px;">
                    <h4 style="margin: 0 0 8px 0; color: #2980b9;">🔍 Diagnoza</h4>
                    <p style="margin: 0; font-size: 14px;">{diagnosis}</p>
                </div>

                <div style="background-color: #fef9e7; border-left: 4px solid #f39c12; padding: 12px 16px; margin: 20px 0; border-radius: 4px;">
                    <h4 style="margin: 0 0 8px 0; color: #d68910;">💡 Zalecane działanie</h4>
                    <div style="margin: 0; font-size: 14px;">{recommendation}</div>
                </div>

                {details_html}

                <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="font-size: 12px; color: #7f8c8d; margin-bottom: 0;">
                    ℹ️ <em>Powiadomienia o kolejnych wystąpieniach tego samego błędu są wyciszane na {cooldown_min} minut, aby nie zaśmiecać skrzynki. Gdy błąd ustąpi, stan zostanie automatycznie zresetowany.</em>
                </p>
            </div>
        </div>
        """
        return contents

    @staticmethod
    def should_send_error_notification(storage, user_login: str, error_str: str, cooldown_s: int = 3600) -> bool:
        if not storage:
            return True
        last_err = storage.get_last_error(str(user_login))
        if not last_err:
            return True
        if cooldown_s <= 0:
            return True
        last_timestamp = last_err.get('timestamp', 0)
        last_msg = last_err.get('error', '')
        if error_str != last_msg:
            return True
        now = datetime.now().timestamp()
        if now - last_timestamp >= cooldown_s:
            return True
        return False

    def send_error_notification(
        self,
        user_config: dict,
        error: Exception,
        step_name: str = "",
        details: str = None,
        storage=None,
        cooldown_s: int = 3600
    ) -> bool:
        pass


