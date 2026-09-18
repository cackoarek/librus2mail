import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .mail_sender import MailSender

logger = logging.getLogger(__name__)


class SmtpSender(MailSender):

    def __init__(self, mail_config):
        MailSender.__init__(self, mail_config)
        config = mail_config['non_gmail_settings']
        self.smtp_server = config['smtp_host']
        self.port = config['port']

    def send_mail_with_messages(self, user_config, messages):
        mail_content = self.create_mail_content_for_messages(user_config, messages)
        title = f"{user_config['librus_login_name']} ma nową wiadomość w Librusie (konto {user_config['librus_login']})"

        self.__send_smtp(user_config, title, mail_content)

    def send_mail_with_notifications(self, user_config, messages):
        mail_content = self.create_mail_content_for_notifications(user_config, messages)
        title = f"{user_config['librus_login_name']} ma nowe ogłoszenie w Librusie (konto {user_config['librus_login']})"
        self.__send_smtp(user_config, title, mail_content)

    def send_mail_with_grades(self, user_config, grades):
        mail_content = self.create_mail_content_for_grades(user_config, grades)
        grades_summary = ", ".join([f"{g['subject']}: {g['grade']}" for g in grades[:3]])
        if len(grades) > 3:
            grades_summary += f" (+{len(grades) - 3})"
        title = f"{user_config['librus_login_name']} ma nowe oceny w Librusie ({grades_summary})"
        self.__send_smtp(user_config, title, mail_content)

    def send_mail_with_summary(self, user_config, messages=None, notifications=None, grades=None):
        messages = messages or []
        notifications = notifications or []
        grades = grades or []
        mail_content = self.create_mail_content_for_summary(user_config, messages, notifications, grades)
        title = self._create_summary_title(user_config, messages, notifications, grades)
        self.__send_smtp(user_config, title, mail_content)

    def send_error_notification(self, user_config, error, step_name="", details=None, storage=None, cooldown_s=3600):
        receivers = user_config.get('notification_receivers')
        if not receivers:
            logger.warning(f"Brak odbiorców powiadomień (notification_receivers) dla konta {user_config.get('librus_login')}")
            return False

        login = str(user_config.get('librus_login'))
        error_str = f"{type(error).__name__}: {str(error)}"
        if not self.should_send_error_notification(storage, login, error_str, cooldown_s=cooldown_s):
            logger.warning(
                f"Pominięto wysyłkę e-maila o błędzie dla konta {login} (aktywny cooldown {cooldown_s}s)"
            )
            return False

        mail_content = self.create_mail_content_for_error(user_config, error, step_name, details, cooldown_s)
        title = self._create_error_title(user_config, error, step_name)
        try:
            logger.info(f"Wysyłam powiadomienie o błędzie ({step_name}) dla {login} do {receivers}")
            sent = self.__send_smtp(user_config, title, mail_content)
            if sent and storage:
                storage.save_last_error(login, error_str, step=step_name)
            return sent
        except Exception as e:
            logger.error(f"Nie udało się wysłać powiadomienia o błędzie przez SMTP: {e}")
            return False

    def send_progress_report(self, user_config: dict, analysis: dict) -> bool:
        receivers = user_config.get('notification_receivers')
        if not receivers:
            logger.warning(f"Brak odbiorców powiadomień (notification_receivers) dla konta {user_config.get('librus_login')}")
            return False

        mail_content = self.create_mail_content_for_progress_report(user_config, analysis)
        title = self._create_progress_report_title(user_config, analysis)
        try:
            logger.info(f"Wysyłam raport postępów dla {user_config.get('librus_login')} do {receivers}")
            return self.__send_smtp(user_config, title, mail_content)
        except Exception as e:
            logger.error(f"Nie udało się wysłać raportu postępów przez SMTP: {e}")
            return False

    def __send_smtp(self, user_config, title, contents):
        logger.info("Wysyłam wiadomość e-mail")
        receiver_emails = user_config['notification_receivers']
        message = MIMEMultipart("alternative")
        message["Subject"] = title
        message["From"] = self.sender_email
        message["To"] = ", ".join(receiver_emails)

        # Turn these into plain/html MIMEText objects
        part1 = MIMEText(contents.replace("\n", ""), "plain")  # TODO: fix this
        part2 = MIMEText(contents.replace("\n", ""), "html")

        # Add HTML/plain-text parts to MIMEMultipart message
        # The email client will try to render the last part first
        message.attach(part1)
        message.attach(part2)

        # Create a secure SSL context
        context = ssl.create_default_context()

        # Try to log in to server and send email
        server = None
        try:
            server = smtplib.SMTP(self.smtp_server, self.port)
            server.ehlo()  # Can be omitted
            server.starttls(context=context)  # Secure the connection
            server.ehlo()  # Can be omitted
            server.login(self.sender_email, self.password)
            server.sendmail(self.sender_email, receiver_emails, message.as_string())
            logger.info("Wiadomość e-mail wysłana")
            return True
        except Exception as e:
            logger.error(f"Błąd wysyłania SMTP: {e}")
            return False
        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass
