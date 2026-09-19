# Security & Credentials Rules

## Critical Guardrails
1. **Never commit secrets**:
   - Files such as `config.yaml`, `arek_config.yaml`, `*_config.yaml`, `.env`, and `*.log` contain real credentials (Librus parent credentials, Gmail/SMTP passwords, recipient emails).
   - Never remove them from `.gitignore` or stage them in git commits (`git add`).
   - Always reference `config.example.yaml` when writing examples or test configurations.

2. **Never log sensitive data**:
   - Do not print or log plaintext passwords, authorization tokens, or session cookie values.
   - When handling exceptions in `base_logger`, ensure credential strings are not interpolated into error messages.

3. **No unattended live testing**:
   - Running `librus_collect_and_notify.py` or `librus_collector.py` directly executes live scraping against Librus Synergia and may dispatch actual emails to real recipient addresses configured in local YAML files.
   - Never invoke `python librus_collect_and_notify.py` or `python librus_collector.py` in background tasks or during autonomous verification without explicit user instructions.
   - For unit testing, use mocks or offline HTML fixtures.
