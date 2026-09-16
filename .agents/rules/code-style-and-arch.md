# Code Style & Architecture Guidelines

## Code Standards
1. **Python Version & Syntax**:
   - Target: Python 3.10+.
   - Use standard modern type annotations (e.g., `list[dict[str, Any]]`, `str | None`).
   - Walrus operator (`:=`) is welcome where it improves clarity.

2. **Logging**:
   - Always use `from base_logger import logger`.
   - Never use `print()` for production logging.
   - Maintain Polish language log messages to be consistent with existing project logs.

3. **Mail Architecture**:
   - `MailSender`: Abstract base class providing HTML formatting for tables:
     - `create_mail_content_for_messages(user_config, messages)`
     - `create_mail_content_for_notifications(user_config, notifications)`
   - Concrete implementations must inherit from `MailSender`:
     - `GmailSender`: uses `yagmail.SMTP`.
     - `SmtpSender`: uses `smtplib.SMTP`, STARTTLS, `MIMEMultipart`.
   - When adding new notification channels (e.g. Telegram, Discord, Pushbullet), create a dedicated notifier class and dispatch through a factory.

4. **Resource & Exception Safety**:
   - In `SmtpSender.py`, initialize `server = None` before `try` block, and verify `if server: server.quit()` in `finally`.
   - Handle network timeouts with explicit `timeout` arguments in `requests` and `smtplib`.

5. **Dependency Management**:
   - Top-level dependencies must be listed in `requirements.txt`.
   - Explicitly include `requests>=2.28.0` and `beautifulsoup4>=4.10.0` rather than relying on transitive installation.
