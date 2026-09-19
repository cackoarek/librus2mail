# CLAUDE.md - Instructions for Claude Code

## Commands
- **Environment**: `source venv/bin/activate`
- **Dependencies**: `pip install -e .` (or `pip install -r requirements.txt`)
- **Dev tools**: `pip install -e ".[dev]"`
- **Run**: `librus-collect-and-notify` or `python librus_collect_and_notify.py` (Caution: live scraper; do not run without user consent)
- **Report**: `librus-report --dry-run` or `python librus_progress_report.py --dry-run`
- **Tests**: `pytest`
- **Linter**: `ruff check`

## Architecture
- `src/librus2mail/`: Canonical package with `src/` layout.
- `librus_collect_and_notify.py` / `librus_collector.py` / `librus_updates_notifier.py`: CLI entrypoints.
- `librus_progress_report.py`: Offline progress report generator CLI.
- `src/librus2mail/mail_sender.py`: Base email class generating HTML emails with Jinja2 templates (`src/librus2mail/templates/emails/`).
- `src/librus2mail/gmail_sender.py`: Subclass sending mail through `yagmail`.
- `src/librus2mail/smtp_sender.py`: Subclass sending mail through `smtplib` with STARTTLS.
- `src/librus2mail/librus.py`: Web scraper for Librus Synergia. Handles OAuth login simulation, session cookies, HTML parsing with BeautifulSoup.
- `src/librus2mail/progress_analyzer.py`: Analytical engine for grades, averages, thresholds, and parent insights.
- `src/librus2mail/storage.py`: State and grade history persistence (`FileStorage`).

## Critical Rules
1. **Secrets**: Never commit `config.yaml`, `arek_config.yaml`, or any `*_config.yaml`. Reference `config.example.yaml`.
2. **Rate Limits**: Do not remove `sleep(5)` calls between requests.
3. **HTTP Errors**: Do NOT use `res.error` on `requests.Response` (it does not exist). Use `res.status_code`, `res.reason`, or `res.raise_for_status()`.
4. **Side Effects**: `read_messages=True` marks messages as read in the user's Librus portal.
5. **Style**: Python 3.10+, PEP 8, typed annotations, Polish log messages via `base_logger.logger`.
