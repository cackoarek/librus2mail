import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from MailSender import MailSender
from base_logger import logger


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

    def __send_smtp(self, user_config, title, contents):
        logger.info("Wysyłam maila z podsumowaniem")
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
        try:
            server = smtplib.SMTP(self.smtp_server, self.port)
            server.ehlo()  # Can be omitted
            server.starttls(context=context)  # Secure the connection
            server.ehlo()  # Can be omitted
            server.login(self.sender_email, self.password)
            server.sendmail(self.sender_email, receiver_emails, message.as_string())
            logger.info("Mail z podsumowaniem wysłany")
        except Exception as e:
            # Print any error messages to stdout
            print(e)
        finally:
            server.quit()
