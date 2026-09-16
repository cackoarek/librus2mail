# AGENTS.md - Developer & Agent Instructions for Librus2mail

Welcome to **Librus2mail**. This document provides essential context, architecture details, conventions, and safety guidelines for AI agents working in this repository.

---

## 1. Project Overview

**Librus2mail** is a Python daemon/service that logs into the **Librus Synergia** electronic school register (as a parent account), monitors messages and school announcements, and sends automated email summaries to configured recipients when new entries appear.

### Key Capabilities:
- Multi-account support (e.g. parents with multiple children in Librus).
- Scraping messages (`/wiadomosci`) with optional body reading.
- Scraping announcements (`/ogloszenia`).
- Email delivery via Gmail (`yagmail`) or custom SMTP server (`smtplib` + STARTTLS).
- Initial "dry-parse" run (`do_not_send_first_parse`) to establish a baseline without sending notifications for historical messages.
- Periodic polling in an infinite loop with configurable interval (`wait_time_s`).

---

## 2. Tech Stack & Environment

- **Language**: Python 3.10+ (requires union types `X | Y`, walrus operator `:=`).
- **Dependencies**:
  - `requests`: HTTP requests and OAuth session simulation.
  - `beautifulsoup4` (`bs4`): HTML parsing of Librus web pages.
  - `fake_useragent`: User-Agent rotation to mitigate basic anti-bot heuristics.
  - `pyYAML`: Reading YAML configuration files.
  - `yagmail`: Gmail sending client.
  - Built-in `smtplib`, `ssl`, `email.mime`: Standard SMTP email transport.
  - Built-in `logging`: Configured via `base_logger.py` with file and console handlers.

### Setup & Activation
```bash
# Virtual environment setup
virtualenv venv -p python3.10
source venv/bin/activate
python -m pip install -r requirements.txt
```

### Execution
```bash
source venv/bin/activate
python main.py
```

---

## 3. Project File Structure

```text
librus2mail/
├── .agents/
│   └── rules/                  # Antigravity modular agent rules
│       ├── security.md         # Secret protection & safe testing
│       ├── scraping-and-librus.md # Scraping quirks, rate limiting, DOM tips
│       └── code-style-and-arch.md # Python conventions, logging, typing
├── base_logger.py              # Central logger config ('librus' logger, writes to librus.log & stdout)
├── config.py                   # YAML configuration loader (read_config)
├── config.example.yaml         # Clean configuration template for users and tests
├── GmailSender.py              # MailSender subclass using yagmail for Gmail
├── librus.py                   # Librus scraping & OAuth client class
├── MailSender.py               # Base class with HTML table formatting for emails
├── main.py                     # Entrypoint & main polling loop
├── README.md                   # Human documentation
├── requirements.txt            # Python dependencies
├── SmtpSender.py               # MailSender subclass using standard smtplib + STARTTLS
├── AGENTS.md                   # Universal AI agent instructions (this file)
├── CLAUDE.md                   # Claude Code instructions
├── GEMINI.md                   # Google Antigravity / Gemini CLI instructions
└── .cursorrules                # Cursor IDE configuration
```

---

## 4. Architecture & Data Flow

1. **Startup (`main.py`)**:
   - Reads configuration (`config.yaml` or designated YAML).
   - Instantiates appropriate mail sender via `configure_mail_provider(config)`: `GmailSender` or `SmtpSender`.
   - Initializes a mapping of `Librus` parser instances per user account (`librus_parsers`).
   - Sets up initial state flags (`dry-parse` set from `do_not_send_first_parse`).

2. **Polling Loop (`main.py`)**:
   - For each user in `config['librus_users']`:
     1. Authenticates against Librus via `librus.login()`.
     2. Waits 5 seconds (`sleep(5)`).
     3. Calls `librus.fetch_messages()`.
     4. Waits 5 seconds (`sleep(5)`).
     5. Calls `librus.fetch_notifications()`.
     6. Retrieves newly discovered items (`get_not_known_messages_and_mark_as_known()`, `get_not_known_notifications_and_mark_as_known()`).
     7. If not in `dry-parse` mode and new items exist, triggers `mail_sender.send_mail_with_messages` or `mail_sender.send_mail_with_notifications`.
     8. If in `dry-parse` mode, marks baseline as initialized and sets `dry-parse = False`.
   - Sleeps for `config['wait_time_s']` seconds before next round.

3. **Librus Scraping (`librus.py`)**:
   - Simulates 3-step OAuth flow:
     - Step 1: GET `OAUTH_URL`
     - Step 2: POST `AUTH_URL` with user credentials (`login`, `pass`)
     - Step 3: GET `GRANT_URL`
   - Keeps authentication cookies in `requests.Session`.
   - Parses HTML using BeautifulSoup.
   - Generates composite string IDs for messages and notifications to detect unread/unseen entries across iterations.

---

## 5. Critical Guidelines & Traps for AI Agents

### 🔒 1. Secrets & Credentials Protection
- **NEVER stage or commit**: `config.yaml`, `arek_config.yaml`, `*_config.yaml`, `.env`, or `*.log`.
- **NEVER expose plaintext credentials**: Do not log passwords or logins.
- **Reference only `config.example.yaml`** when writing docs, examples, or tests.
- **DO NOT run `python main.py` in autonomous background loops**: It connects to real Librus accounts and may send actual emails to configured parent mailboxes.

### 🌐 2. Scraping Fragility & Anti-Ban
- **Preserve Delays**: Do not eliminate `sleep(5)` between requests in `main.py` or `librus.py`. Scraping too quickly risks IP bans, CAPTCHAs, or temporary account locks.
- **Message Read Side-Effect**: In Librus Synergia, visiting `/wiadomosci/szczegoly/...` marks the message as read in the official portal. Advise users to keep `read_messages: false` unless they explicitly want content extraction.
- **HTML Layout Volatility**: Librus Synergia frequently tweaks table layouts, CSS classes, or forms. Always defensively check if elements exist before indexing (`soup.find(...)`).

### 🐛 3. Known Bugs & Gotchas to Fix or Avoid
- **`res.error` does NOT exist in `requests.Response`**:
  - In `librus.py`, error logging currently uses `res.error` (e.g. `logger.error(f"... {res.status_code} {res.error}")`). This will raise an `AttributeError` when an error actually happens. Always use `res.reason`, `res.text`, or `res.raise_for_status()`.
- **`SmtpSender.py` unhandled variable in `finally`**:
  - `server.quit()` in `finally:` can raise `UnboundLocalError` if `smtplib.SMTP(...)` failed on instantiation. Ensure `server = None` is set before `try`, and check `if server: server.quit()`.
- **Missing explicit dependencies in `requirements.txt`**:
  - `requests` is directly imported in `librus.py`, but missing in `requirements.txt`.
  - `beautifulsoup4` should be specified directly rather than just `bs4`.
- **Incomplete `fetch_grades()`**:
  - `fetch_grades()` in `librus.py` is an unfinished stub copying notification code and assigning to `self.notifications`. Do not rely on it without a complete rewrite.

### 📝 4. Coding Conventions
- Logging: Always use `from base_logger import logger`. Do NOT use bare `print()` statements.
- Language: Keep existing Polish log messages and comments consistent.
- Typing: Add type hints (`list[dict[str, Any]]`, `Optional[str]`, etc.) to new functions.
- Class hierarchy: Keep `MailSender` as base, specialize subclasses.
