import yagmail
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from base_logger import logger


def send_mail(user_config, mail_config, df):
    # na potrzeby wysyłania maili
    mail_user = mail_config['login']
    mail_password = mail_config['password']

    # treść maila
    contents = f"""
    <p>W Librusie dla konta {user_config['librus_login']} <strong>({user_config['librus_login_name']})</strong> pojawiły się <strong>nowe wiadomości</strong>.</p>
    <p>&nbsp;</p>
    <p>Lista wszystkich wiadomości (nowe <strong>boldem</strong>):</p>
    <table border="1" cellspacing="0" cellpadding="10">
    <thead><tr><th>Tytuł</th><th>Nadawca</th><th>Data</th></tr></thead>
    <tbody>
    """

    for r in df:
        if r['is_unread']:
            contents += f"""
            <tr>
            <td><strong>{r['title']}</strong></td>
            <td><strong>{r['sender']}</strong></td>
            <td><strong>{r['datetime']}</strong></td>
            </tr>
            """
        else:
            contents += f"""
            <tr>
            <td>{r['title']}</td>
            <td>{r['sender']}</td>
            <td>{r['datetime']}</td>
            </tr>
            """

    contents += "</tbody></table>"

    # wyslanie maila
    logger.info("Wysyłam maila z podsumowaniem")

    if mail_config['use_gmail']:
        send_gmail(user_config, contents, mail_password, mail_user)
    else:
        send_smtp(user_config, mail_config, contents)

    logger.info("Mail z podsumowaniem wysłany")


def send_gmail(config, contents, mail_password, mail_user):
    yag = yagmail.SMTP(mail_user, mail_password)
    contents = contents.replace("\n", "")
    yag.send(config['notification_receivers'],
             f"{config['librus_login_name']} ma nową wiadomość w Librusa (konto {config['librus_login']})",
             contents)

def send_smtp(user_config, mail_config, contents):
    config = mail_config['non_gmail_settings']
    smtp_server = config['smtp_host']
    sender_email = mail_config['login']
    receiver_emails = user_config['notification_receivers']
    port = config['port']
    password = mail_config['password']

    message = MIMEMultipart("alternative")
    message["Subject"] = f"{user_config['librus_login_name']} ma nową wiadomość w Librusa (konto {user_config['librus_login']})"
    message["From"] = sender_email
    message["To"] = ", ".join(receiver_emails)

    # Turn these into plain/html MIMEText objects
    part1 = MIMEText(contents.replace("\n", ""), "plain") # TODO: fix this
    part2 = MIMEText(contents.replace("\n", ""), "html")

    # Add HTML/plain-text parts to MIMEMultipart message
    # The email client will try to render the last part first
    message.attach(part1)
    message.attach(part2)

    # Create a secure SSL context
    context = ssl.create_default_context()

    # Try to log in to server and send email
    try:
        server = smtplib.SMTP(smtp_server, port)
        server.ehlo()  # Can be omitted
        server.starttls(context=context)  # Secure the connection
        server.ehlo()  # Can be omitted
        server.login(sender_email, password)
        server.sendmail(sender_email, receiver_emails, message.as_string())
    except Exception as e:
        # Print any error messages to stdout
        print(e)
    finally:
        server.quit()