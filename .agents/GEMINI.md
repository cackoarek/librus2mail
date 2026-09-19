# GEMINI.md - Antigravity Agent Guidelines for Librus2mail

## Quick Context
- **Project**: Librus2mail (Librus Synergia web scraper & email notifier).
- **Stack**: Python 3.10+, `requests`, `bs4`, `fake_useragent`, `yagmail`, `pyYAML`.
- **Entrypoint**: `librus_collect_and_notify.py` (infinite loop checking messages and announcements).

## Agent Directives

1. **Security & Secrets**:
   - Strictly avoid staging or committing `config.yaml`, `arek_config.yaml`, `*_config.yaml`, `.env`, or `*.log`.
   - Never run `python librus_collect_and_notify.py` or `python librus_collector.py` autonomously; it interacts with live school accounts and sends real emails.
   - For configuration documentation and tests, reference only `config-example.yaml` or `config-minimal.yaml`.

2. **Scraping Integrity**:
   - Do not remove or shorten the `sleep(5)` rate-limiting delays.
   - Librus Synergia has no official public API; HTML parsing is brittle. Check all `soup.find(...)` results defensively.
   - `read_messages` and `read_grades` default to `true`. Visiting `/szczegoly` marks messages as read on the web portal.

3. **Code Style**:
   - Standard: Python 3.10+ PEP 8 with type hints.
   - Logger: Use `logger = logging.getLogger(__name__)`. Configure handlers in CLI entrypoints (`setup_logging()`). Avoid `print()`.
   - Preserve existing Polish comments and log messages.

## Modular Rules Reference
Detailed rules are modularized under `.agents/rules/`:
- [.agents/rules/security.md](file:///.agents/rules/security.md): Handling credentials and safe verification.
- [.agents/rules/scraping-and-librus.md](file:///.agents/rules/scraping-and-librus.md): Librus Synergia OAuth and DOM parsing rules.
- [.agents/rules/code-style-and-arch.md](file:///.agents/rules/code-style-and-arch.md): Architecture and code quality guidelines.
