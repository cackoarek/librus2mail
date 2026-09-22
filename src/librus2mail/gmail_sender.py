import logging

import yagmail

from .mail_sender import MailSender

logger = logging.getLogger(__name__)


class GmailSender(MailSender):

    def send_mail_with_messages(self, user_config, messages):
        mail_content = self.create_mail_content_for_messages(user_config, messages)
        title = f"{user_config['librus_login_name']} ma nową wiadomość w Librusie (konto {user_config['librus_login']})"
        self.__send_gmail(user_config, title, mail_content, self.sender_email, self.password)

    def send_mail_with_notifications(self, user_config, messages):
        mail_content = self.create_mail_content_for_notifications(user_config, messages)
        title = f"{user_config['librus_login_name']} ma nowe ogłoszenie w Librusie (konto {user_config['librus_login']})"
        self.__send_gmail(user_config, title, mail_content, self.sender_email, self.password)

    def send_mail_with_grades(self, user_config, grades):
        mail_content = self.create_mail_content_for_grades(user_config, grades)
        grades_summary = ", ".join([f"{g['subject']}: {g['grade']}" for g in grades[:3]])
        if len(grades) > 3:
            grades_summary += f" (+{len(grades) - 3})"
        title = f"{user_config['librus_login_name']} ma nowe oceny w Librusie ({grades_summary})"
        self.__send_gmail(user_config, title, mail_content, self.sender_email, self.password)

    def send_mail_with_summary(self, user_config, messages=None, notifications=None, grades=None, timetable=None, schedule=None):
        messages = messages or []
        notifications = notifications or []
        grades = grades or []
        mail_content = self.create_mail_content_for_summary(user_config, messages, notifications, grades, timetable=timetable, schedule=schedule)
        title = self._create_summary_title(user_config, messages, notifications, grades, timetable=timetable, schedule=schedule)
        self.__send_gmail(user_config, title, mail_content, self.sender_email, self.password)

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
            self.__send_gmail(user_config, title, mail_content, self.sender_email, self.password)
            if storage:
                storage.save_last_error(login, error_str, step=step_name)
            return True
        except Exception as e:
            logger.error(f"Nie udało się wysłać powiadomienia o błędzie przez Gmail: {e}")
            return False

    def send_progress_report(self, user_config: dict, analysis: dict, timetable: dict | None = None) -> bool:
        receivers = user_config.get('notification_receivers')
        if not receivers:
            logger.warning(f"Brak odbiorców powiadomień (notification_receivers) dla konta {user_config.get('librus_login')}")
            return False

        mail_content = self.create_mail_content_for_progress_report(user_config, analysis, timetable=timetable)
        title = self._create_progress_report_title(user_config, analysis)
        try:
            logger.info(f"Wysyłam raport postępów dla {user_config.get('librus_login')} do {receivers}")
            self.__send_gmail(user_config, title, mail_content, self.sender_email, self.password)
            return True
        except Exception as e:
            logger.error(f"Nie udało się wysłać raportu postępów przez Gmail: {e}")
            return False

    def send_student_report(
        self,
        receivers: list[str],
        title: str,
        mail_content: str,
    ) -> bool:
        if not receivers:
            logger.warning("Brak odbiorców (receivers) dla raportu ucznia")
            return False
        cfg = {'notification_receivers': receivers}
        try:
            logger.info(f"Wysyłam raport dla ucznia do {receivers}: {title}")
            self.__send_gmail(cfg, title, mail_content, self.sender_email, self.password)
            return True
        except Exception as e:
            logger.error(f"Nie udało się wysłać raportu dla ucznia przez Gmail: {e}")
            return False

    @staticmethod
    def __send_gmail(config, title, contents, mail_user, mail_password):
        logger.info("Wysyłam wiadomość e-mail")
        yag = yagmail.SMTP(mail_user, mail_password)
        contents = contents.replace("\n", "")
        yag.send(config['notification_receivers'],
                 title,
                 contents)
        logger.info("Wiadomość e-mail wysłana")
