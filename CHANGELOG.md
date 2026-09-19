# Changelog

Wszystkie istotne zmiany w projekcie są dokumentowane w tym pliku.

Format bazuje na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/).
Projekt stosuje [Semantic Versioning](https://semver.org/lang/pl/).

---

## [Unreleased]

### Dodane
- Parametr `--actual-date YYYY-MM-DD` w `librus_updates_notifier.py` i `librus_progress_report.py` – umożliwia generowanie reprodukowalnych raportów z przykładowego storage
- Parametr `--summary` wymuszający wysłanie jednego zbiorczego e-maila zamiast osobnych wiadomości, ogłoszeń i ocen
- Kolumna "Komentarz" w tabelach ocen (szablony `grades.html` i `summary.html`)
- Parametr `delay_between_users_s` w `config.yaml` – konfigurowalny czas oczekiwania między pobieraniem danych dla kolejnych dzieci
- Pełna architektura 3-modułowa: `librus_collector`, `librus_updates_notifier`, `librus_progress_report`
- Analiza porównawcza z poprzednim okresem (PoP) w raportach postępów
- Kalkulator szans i zagrożeń na granicy ocen (symulator czerwonego paska)
- Obsługa wielu kont uczniów w jednej instancji
- Przykładowe dane testowe w `examples/storage/`

### Zmienione
- Ujednolicenie nazw skryptów uruchomieniowych w katalogu głównym pod prefiksem `librus_` (`librus_collect_and_notify.py`, `librus_collector.py`, `librus_progress_report.py`, `librus_updates_notifier.py`)
- Usunięcie zduplikowanego katalogu szablonów `templates/` w root (szablony żyją wyłącznie wewnątrz pakietu `src/librus2mail/templates/emails/`)
- Ulepszony wygląd powiadomień e-mail (Jinja2 HTML templates)
- Domyślny czas oczekiwania pętli monitorowania (`wait_time_s`)
- Refaktoryzacja struktury projektu (layout `src/`)

---

## [1.0.0] – 2026-09-16

### Pierwsze oficjalne wydanie 🎉

- Monitoring wiadomości (`/wiadomosci`) i ogłoszeń (`/ogloszenia`) z Librus Synergia
- Obsługa OAuth Librus (3-krokowy flow z pominięciem 2FA)
- Wysyłka e-mail przez Gmail (`yagmail`) lub dowolny SMTP (`smtplib` + STARTTLS)
- Raport postępów ucznia ze średnimi ważonymi, trendami i prognozami
- Docker image publikowany do GitHub Container Registry (GHCR)
- CI/CD z GitHub Actions: testy, linter, Docker build
- Konfiguracja przez `config.yaml`

---

[Unreleased]: https://github.com/cackoarek/librus2mail/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/cackoarek/librus2mail/releases/tag/v1.0.0
