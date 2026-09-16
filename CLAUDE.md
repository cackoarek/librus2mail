# CLAUDE.md - Instructions for Claude Code

## Commands
- **Environment**: `source venv/bin/activate`
- **Dependencies**: `pip install -r requirements.txt`
- **Run**: `python main.py` (Caution: live scraper; do not run without user consent)
- **Tests**: Currently no automated test suite. Use offline mock tests.

## Architecture
- `main.py`: Entrypoint with main loop (`while True`) checking messages and announcements per account.
- `librus.py`: Web scraper for Librus Synergia. Handles OAuth login simulation, session cookies, HTML parsing with BeautifulSoup.
- `config.py`: Reads YAML configuration (`yaml.safe_load`).
- `base_logger.py`: Central logger named `librus`, outputs to console and `librus.log`.
- `MailSender.py`: Base email class generating HTML table templates.
- `GmailSender.py`: Subclass sending mail through `yagmail`.
- `SmtpSender.py`: Subclass sending mail through `smtplib` with STARTTLS.

## Critical Rules
1. **Secrets**: Never commit `config.yaml`, `arek_config.yaml`, or any `*_config.yaml`. Reference `config.example.yaml`.
2. **Rate Limits**: Do not remove `sleep(5)` calls between requests.
3. **HTTP Errors**: Do NOT use `res.error` on `requests.Response` (it does not exist). Use `res.status_code`, `res.reason`, or `res.raise_for_status()`.
4. **Side Effects**: `read_messages=True` marks messages as read in the user's Librus portal.
5. **Style**: Python 3.10+, PEP 8, typed annotations, Polish log messages via `base_logger.logger`.
