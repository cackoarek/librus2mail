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


