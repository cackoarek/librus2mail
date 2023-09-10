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

    def send_mail_with_messages(self, user_config, messages):
        pass

    def send_mail_with_notifications(self, user_config, messages):
        pass


