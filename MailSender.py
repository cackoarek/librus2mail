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

    def send_mail_with_messages(self, user_config, messages):
        pass

    def send_mail_with_notifications(self, user_config, notifications):
        pass

    def send_mail_with_grades(self, user_config, grades):
        pass


