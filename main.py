from time import sleep

from GmailSender import GmailSender
from MailSender import MailSender
from SmtpSender import SmtpSender
from base_logger import logger
from config import read_config
from librus import Librus


def configure_mail_provider(config: dict) -> MailSender:
    mail_config = config['mail']
    if mail_config['use_gmail']:
        return GmailSender(mail_config)
    else:
        return SmtpSender(mail_config)


if __name__ == '__main__':
    config = read_config('config.yaml')
    # config = read_config('arek_config.yaml')

    for idx, user in enumerate(config['librus_users']):
        user['id'] = idx
        user['dry-parse'] = user['do_not_send_first_parse']

    mail_sender = configure_mail_provider(config)

    librus_parsers: dict[int, Librus] = {}

    # nieskończona pętla sprawdzania ciągle i wciąż
    while True:
        # dla każdego użytkownika przygotowujemy jego mini-konfigurację
        for user_config in config['librus_users']:
            checked = False

            # próba pobrania danych z Librusa
            try:
                librus_parsers.setdefault(user_config['id'], Librus(user_config))
                librus = librus_parsers.get(user_config['id'])
                librus.login()
                sleep(1000)
                librus.fetch_messages()
                sleep(1000)
                librus.fetch_notifications()
                checked = True
            except Exception as e:
                logger.error(
                    f"Błąd w głównej pętli dla {user_config['librus_login']}: {e}")
                checked = False

            # czy udało się pobrać dane z Librusa?
            if checked:
                # aktualna lista wszystkich wiadomości
                new_messages = librus.get_not_known_messages_and_mark_as_known()
                # aktualna lista wszystkich ogłoszeń
                new_notifications = librus.get_not_known_notifications_and_mark_as_known()

                if not user_config['dry-parse']:
                    if len(new_messages):
                        logger.info("Pojawiły się nowe wiadomości")

                        # wysyłamy mailowe powiadomienie
                        mail_sender.send_mail_with_messages(user_config, new_messages)
                    else:
                        logger.info("Brak nowych wiadomości")

                    if len(new_notifications) and not user_config['dry-parse']:
                        logger.info("Pojawiły się nowe powiadomienia")

                        # wysyłamy mailowe powiadomienie
                        mail_sender.send_mail_with_notifications(user_config, new_notifications)
                    else:
                        logger.info("Brak nowych ogłoszeń")

                else:
                    logger.info("Zebrano dane jako podstawę. Kolejne wpisy na liburs będą wysyłane mailem.")
                    user_config['dry-parse'] = False

        logger.info(f"Czekam przez {config['wait_time_s']} sekund")
        sleep(config['wait_time_s'])
