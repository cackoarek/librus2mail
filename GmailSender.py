import yagmail

from MailSender import MailSender
from base_logger import logger


class GmailSender(MailSender):

    def send_mail_with_messages(self, user_config, messages):
        mail_content = self.create_mail_content_for_messages(user_config, messages)
        title = f"{user_config['librus_login_name']} ma nową wiadomość w Librusie (konto {user_config['librus_login']})"
        self.__send_gmail(user_config, title, mail_content, self.sender_email, self.password)

    def send_mail_with_notifications(self, user_config, messages):
        mail_content = self.create_mail_content_for_notifications(user_config, messages)
        title = f"{user_config['librus_login_name']} ma nowe ogłoszenie w Librusie (konto {user_config['librus_login']})"
        self.__send_gmail(user_config, title, mail_content, self.sender_email, self.password)

    @staticmethod
    def __send_gmail(config, title, contents, mail_user, mail_password):
        logger.info("Wysyłam maila z podsumowaniem")
        yag = yagmail.SMTP(mail_user, mail_password)
        contents = contents.replace("\n", "")
        yag.send(config['notification_receivers'],
                 title,
                 contents)
        logger.info("Mail z podsumowaniem wysłany")
