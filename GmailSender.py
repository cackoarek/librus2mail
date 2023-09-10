import yagmail

from MailSender import MailSender
from base_logger import logger


class GmailSender(MailSender):

    def send_mail(self, user_config, messages):
        mail_content = self.create_mail_content(user_config, messages)
        # wyslanie maila
        logger.info("Wysyłam maila z podsumowaniem")

        self.__send_gmail(user_config, mail_content, self.sender_email, self.password)

        logger.info("Mail z podsumowaniem wysłany")

    @staticmethod
    def __send_gmail(config, contents, mail_user, mail_password):
        yag = yagmail.SMTP(mail_user, mail_password)
        contents = contents.replace("\n", "")
        yag.send(config['notification_receivers'],
                 f"{config['librus_login_name']} ma nową wiadomość w Librusie (konto {config['librus_login']})",
                 contents)
