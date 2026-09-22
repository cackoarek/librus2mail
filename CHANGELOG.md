# Changelog

Wszystkie istotne zmiany w projekcie są dokumentowane w tym pliku.

Format bazuje na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/).
Projekt stosuje [Semantic Versioning](https://semver.org/lang/pl/).

---

## [Unreleased]

### Dodane
- **Pobieranie i synchronizacja planu lekcji (`plan_lekcji`)**: moduł `Librus` pobiera tygodniowy rozkład zajęć ze szkolnego planu (`/przegladaj_plan_lekcji`), wykrywając sale lekcyjne, nauczycieli, odwołane lekcje oraz zastępstwa.
- **Trwała persystencja planu w `FileStorage`**: zapis i historia lekcji w plikach JSON (`schedule_history`, `schedule_last_sync`).
- **Sekcja planu lekcji w codziennym powiadomieniu (`summary.html`)**:
  - Wyświetlanie godzin pobytu dziecka w szkole (np. `⏰ 08:00 – 13:35`) i liczby zaplanowanych lekcji.
  - Wyraźne alerty o zmianach w planie (liczba zastępstw, odwołanych lekcji oraz notatka o zastępstwie).
  - Korelacja lekcji ze sprawdzianami i kartkówkami z terminarza szkolnego na dany dzień (oznaczenia `📕 Sprawdzian`, `📙 Kartkówka`).
  - W pełni responsywny layout mobilny dostosowany do czytania na smartfonach i komputerach.
- Opcja konfiguracyjna `read_schedule: true` (domyślnie włączona) w profilach uczniów.
- **Automatyczna retencja wpisów planu lekcji**: parametr `schedule_retention_days` (domyślnie `30` dni), usuwający historyczne lekcje sprzed podanej liczby dni z lokalnego storage przy zachowaniu lekcji bieżących i przyszłych.
- **Konfigurowalne przesunięcie dnia planu lekcji (`schedule_day_offset`)**:
  - Domyślnie `1` (+1 dzień roboczy, czyli jutro, a w piątek/weekend najbliższy poniedziałek).
  - Możliwość ustawienia `0` (bieżący dzień raportu) w `config.yaml` lub przełącznikiem CLI `--schedule-offset` / `--schedule-day-offset` we wszystkich modułach CLI (`librus_updates_notifier.py`, `librus_collector.py`, `librus_collect_and_notify.py`).

---

## [1.3.0] – 2026-09-21

### Dodane
- card-base layout for grades in notification
- add timetable events to parent and student raports
- add timetable events to notify email
- add timetable data parse to storage

### Naprawione
- remove waga after sprawdzian
- fix layout of daily notification

---
## [1.2.0] – 2026-09-20

### Dodane
- add new module - student report

---
## [1.1.1] – 2026-09-19

### Naprawione
- Naprawa błędu autoryzacji 2FA dla drugiego konta dziecka przy konfiguracji z wieloma uczniami
- Dynamiczne odczytywanie ukrytych pól formularza (CSRF, tokeny stanu) ze strony weryfikacji dwuetapowej
- Dołączenie wyliczanego nagłówka `x-baner` wymaganego przez `Authorization.js` w żądaniu pominięcia 2FA

### Zmienione
- Zastąpienie losowej rotacji User-Agent stałym identyfikatorem przeglądarki desktopowej z możliwością nadpisania parametrem `user_agent` (zapobiega traktowaniu każdego logowania jako nowego urządzenia przez Librus)
- Zwiększenie domyślnego odstępu między kontami (`delay_between_users_s`) z 3s do 10s
- Wprowadzenie automatycznego mechanizmu ponawiania prób logowania (`login_retries`: 2, `login_retry_delay_s`: 5s)

---

## [1.1.0] – 2026-09-19

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

## [1.0.1] – 2026-09-19

### Dodane
- Integracja GitHub Pages dla przykładowych raportów HTML z e-dziennika
- Szablony podglądu powiadomień i raportów postępów pod publicznymi adresami URL GitHub Pages

### Naprawione
- Poprawka ścieżek oraz artefaktów podczas wdrażania strony demonstracyjnej na gałąź `gh-pages`

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

[Unreleased]: https://github.com/cackoarek/librus2mail/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/cackoarek/librus2mail/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/cackoarek/librus2mail/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/cackoarek/librus2mail/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/cackoarek/librus2mail/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/cackoarek/librus2mail/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/cackoarek/librus2mail/releases/tag/v1.0.0
