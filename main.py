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

    # lista wiadomości jakie przeszły przez sprawdzanie
    # żeby nie słać co chwilę tego samego powiadomienia jeśli są ciągle nie przeczytanie wiadomości
    known_msgs = {}
    for u in config['librus_users']:
        known_msgs[u['librus_login']] = []

    mail_sender = configure_mail_provider(config)

    # nieskończona pętla sprawdzania ciągle i wciąż
    while True:
        # dla każdego użytkownika przygotowujemy jego mini-konfigurację
        for user_config in config['librus_users']:
            checked = False

            # próba pobrania danych z Librusa
            try:
                librus = Librus(user_config)
                librus.fetch_messages()
                checked = True
            except Exception as e:
                logger.error(
                    f"Błąd w głównej pętli dla {user_config['librus_login']}: {e}")
                checked = False

            # czy udało się pobrać dane z Librusa?
            if checked:
                # aktualna lista wszystkich wiadomości
                new_messages = [m['link'] for m in librus.messages]
                if set(known_msgs[user_config['librus_login']]) != set(new_messages):
                    logger.info("Pojawiły się nowe wiadomości")

                    # nadpisujemy listę znanych wiadomości
                    known_msgs[user_config['librus_login']] = new_messages

                    # wysyłamy mailowe powiadomienie
                    mail_sender.send_mail(user_config, librus.messages)
                else:
                    logger.info("Brak nowych wiadomości")

                del(librus)

        logger.info(f"Czekam przez {config['wait_time_s']} sekund")
        sleep(config['wait_time_s'])
