# Changelog

Wszystkie istotne zmiany w projekcie są dokumentowane w tym pliku.

Format bazuje na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/).
Projekt stosuje [Semantic Versioning](https://semver.org/lang/pl/).

---

## [Unreleased]

### Dodane
- **Nowy moduł Web: Interaktywny Dashboard Rodzica (`librus_web.py` / `librus-web`)**:
  - Lekki serwer WWW w Pythonie oparty na Flask 3.x z nowoczesnym, responsywnym frontendem w TailwindCSS i HTMX (bez konieczności instalowania Node.js / npm).
  - **Ochrona hasłem rodzica (Parent Gate) i blokada IP przed atakami brute-force**:
    - Zabezpieczenie dostępu hasłem/PINem zdefiniowanym w `config.yaml` (`web: password: ...`), zmiennej środowiskowej `LIBRUS_WEB_PASSWORD` lub przełączniku CLI `--password`, z opcjonalnym trybem otwartym `--no-auth`.
    - **Aktywna ochrona brute-force i rate limiting**: inteligentne monitorowanie błędnych prób logowania per adres IP klienta (`LoginRateLimiter`) z obsługą nagłówków proxy (`X-Forwarded-For`, `X-Real-IP`).
    - **Tymczasowa blokada IP (Lockout)**: po przekroczeniu limitu nieudanych prób (domyślnie 5) adres IP zostaje zablokowany na konfigurowalny czas (domyślnie 15 minut) z kodem HTTP 429 Too Many Requests, odliczaniem czasu w interfejsie logowania i wyłączeniem pól formularza.
    - Parametry konfiguracyjne w `config.yaml` (`max_login_attempts`, `lockout_duration_s`) oraz przełączniki CLI `--max-attempts` i `--lockout-duration`.
  - **Przełącznik uczniów (Multi-account Switcher)**: Wygodne przełączanie profilu dziecka na górnym pasku nawigacji.
  - **Główny Pulpit (Dashboard)**: Szybki przegląd kluczowych wskaźników KPI (średnia ogólna, liczba ocen, plan na najbliższy dzień, nadchodzące sprawdziany w terminarzu).
  - **Przeglądarka planu lekcji (`/plan`)**: Widok rozkładu lekcji w układzie dni tygodnia z wyróżnieniem zastępstw, odwołanych lekcji oraz powiązanych sprawdzianów.
  - **Przeglądarka ocen & Symulator "Co jeśli?" (`/oceny`, `/api/whatif`)**: Wyliczone średnie ważone per przedmiot oraz dynamiczny kalkulator symulujący wpływ potencjalnej nowej oceny z wagą na średnią ważoną przedmiotu (HTMX).
  - **Terminarz i zapowiedzi (`/terminarz`)**: Chronologiczny kalendarz nadchodzących sprawdzianów i nieobecności nauczycieli.
  - **Wiadomości i ogłoszenia (`/wiadomosci`)**: Przegląd korespondencji od nauczycieli i oficjalnych komunikatów dyrekcji szkoły.
  - **Centrum Operacyjne CLI (`/akcje`)**: Interaktywne przyciski wyzwalające kluczowe operacje systemowe (synchronizacja ze szkołą, wysyłka maila, generowanie raportu postępów, raport motywacyjny ucznia) z bezpośrednim podglądem logów konsoli w przeglądarce.
  - **Generator i eksporter widoków statycznych HTML (`--export-html <DIR>`)**:
    - Możliwość wygenerowania pełnego zestawu statycznych widoków HTML (strona logowania przed zalogowaniem `web_login.html`, pulpit `web_dashboard.html`, plan lekcji `web_plan.html`, oceny `web_oceny.html`, terminarz `web_terminarz.html`, wiadomości `web_wiadomosci.html`, akcje `web_akcje.html`) do przeglądania offline.
    - Automatyczne przepinanie odnośników na relatywne ścieżki (`make_offline_friendly`), umożliwiające klikanie pomiędzy zakładkami bezpośrednio z dysku w dowolnej przeglądarce bez uruchomionego serwera HTTP.
    - Włączenie generowania podglądów webowych do skryptu `examples/reports/regenerate_reports.sh`.
  - Punkt wejścia CLI `librus_web.py` oraz konsolowe polecenie `librus-web`.

---

## [1.4.0] – 2026-09-22

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

[Unreleased]: https://github.com/cackoarek/librus2mail/compare/v1.4.0...HEAD
[1.4.0]: https://github.com/cackoarek/librus2mail/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/cackoarek/librus2mail/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/cackoarek/librus2mail/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/cackoarek/librus2mail/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/cackoarek/librus2mail/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/cackoarek/librus2mail/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/cackoarek/librus2mail/releases/tag/v1.0.0
