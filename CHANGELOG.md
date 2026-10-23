# Changelog

Wszystkie istotne zmiany w projekcie są dokumentowane w tym pliku.

Format bazuje na [Keep a Changelog](https://keepachangelog.com/pl/1.0.0/).
Projekt stosuje [Semantic Versioning](https://semver.org/lang/pl/).

---

## [Unreleased]

### Dodane
- **Automatyczny audyt bezpieczeństwa i skanowanie podatności (CI & Dependabot)**:
  - Dodano dedykowany workflow GitHub Actions ([security.yml](file:///.github/workflows/security.yml)) uruchamiający cotygodniowy audyt podatności w zależnościach za pomocą [pip-audit](https://github.com/pypa/pip-audit) (baza PyPI/OSV CVE) oraz statyczną analizę bezpieczeństwa kodu (SAST) za pomocą [bandit](https://github.com/PyCQA/bandit).
  - Skonfigurowano [dependabot.yml](file:///.github/dependabot.yml) do automatycznego monitorowania zależności Pythona oraz akcji CI z automatycznym generowaniem Pull Requestów z łatkami CVE.
  - Podbito bezpieczne minimalne wersje bibliotek `requests>=2.32.0` oraz `jinja2>=3.1.4` w [requirements.txt](file:///requirements.txt) i [pyproject.toml](file:///pyproject.toml).
  - Oznaczono kontrolowane miejsca w kodzie (`mail_sender.py`, `app.py`), uzyskując 0 podatności i w 100% czysty wynik analizy SAST Bandit.
- **Pełna przeglądarka Kalendarium szkolnego (Kronika) w zakładce Terminarz**:
  - Rozszerzono zakładkę **Terminarz** ([timetable.html](file:///home/acacko/PycharmProjects/librus2mail/src/librus2mail/templates/web/timetable.html)) o przełącznik trybów: **Najbliższe dni** (perspektywa w przód) oraz **Kronika szkolna** (pełna historia wstecz).
  - Silnik agregacji [build_chronicle_timeline()](file:///home/acacko/PycharmProjects/librus2mail/src/librus2mail/web/services.py) łączący wszystkie zarejestrowane w bazie zdarzenia: oceny, frekwencję (nieobecności, spóźnienia, zwolnienia), zapowiedziane sprawdziany, wiadomości od nauczycieli oraz ogłoszenia szkolne.
  - Karty KPI podsumowujące całą historię (liczba ocen, frekwencja z wyróżnieniem nieobecności nieusprawiedliwionych, sprawdziany, komunikacja).
  - Pasek kontrolny z dynamicznym wyborem miesiąca (`Wszystkie`, `Wrzesień`, `Październik`...), filtrami typów zdarzeń (pigułki wielokrotnego wyboru) oraz natychmiastową wyszukiwarką na żywo (po przedmiotach, nauczycielach, opisach i tematach).
  - Nowy przycisk na Pulpicie w module kalendarium: **`Pełne kalendarium ➔`**, prowadzący bezpośrednio do kroniki szkolnej w Terminarzu.
  - Skrótowa trasa URL `/kalendarium` przekierowująca do `/terminarz?view=chronicle`.
  - Pełna interaktywność i wsparcie offline dla eksportowanych raportów HTML ([web_terminarz.html](file:///home/acacko/PycharmProjects/librus2mail/examples/reports/web_terminarz.html)).
- **Interaktywny dymek szczegółów (Popover / Tooltip) po najechaniu na komórkę Heatmapy frekwencji**:
  - Dodano dynamiczny dymek po najechaniu kursorem (`hover` / `focus`) na komórki heatmapy z odnotowanymi zdarzeniami frekwencyjnymi (nieobecności nieusprawiedliwione i usprawiedliwione, spóźnienia, zwolnienia).
  - Dymek prezentuje pełne podsumowanie dnia bez konieczności klikania i przewijania strony do osi czasu: sformatowaną datę w języku polskim, pigułki z podsumowaniem liczbowym (`🔴 1 nieobecność nieuspr.`, `🟢 2 usprawiedliwione`, `🟡 1 spóźnienie`, `🔵 1 zwolnienie`) oraz listę zajęć lekcyjnych ze szczegółami (przedmiot, godzina lekcyjna, symbol, nauczyciel, temat zajęć i status e-Usprawiedliwienia).
  - Inteligentne pozycjonowanie dymka (dokowanie nad/pod komórką, zabezpieczenie przed wykraczaniem poza krawędzie ekranu, płynne zamykanie przy przewijaniu).
  - Spójna obsługa dymka zarówno w rocznej Heatmapie w stylu GitHub, jak i w widoku kalendarza miesięcznego.

---

## [2.8.0] – 2026-10-22

### Dodane
- email notification and report with attendence data
- email notification and report with attendence data
- 2 graphs to choose in attendace view
- 1 new module: attendance
- improved Wiadomosci view navigation

### Naprawione
- **Spójność oznaczenia następnej lekcji na Pulpicie i w Planie lekcji**:
  - Ujednolicono treść odznaki nadchodzącej lekcji w widoku planu lekcji na Pulpicie (`dashboard.html`), zastępując skrótowy napis `Następna` pełną, spójną z zakładką Plan lekcji (`schedule.html`) frazą `Następna lekcja (za X min)` z dynamicznym odliczaniem czasu do rozpoczęcia zajęć.
- modify colors in some themes

### Dokumentacja
- refactor docs
- refactor docs

---
## [2.7.0] – 2026-10-21

### Dodane
- **Moduł frekwencji i obecności ucznia (Scraping, Storage & Panel WWW)**:
  - Automatyczne pobieranie danych o frekwencji z systemu Librus Synergia (`/przegladaj_nb/uczen`) w `librus.py` i `librus_collector.py` z możliwością wyłączenia opcją konfiguracyjną `read_attendance: false`.
  - Parsowanie wpisów frekwencji w `dom_parser.py`: ekstrakcja daty, godziny lekcyjnej, przedmiotu, symbolu (`nb`, `u`, `sp`, `zw`), typu absencji, nauczyciela, tematu lekcji, informacji o wycieczkach oraz adnotacji modułu e-Usprawiedliwień, wraz z oficjalnymi sumarycznymi tabelami semestralnymi.
  - Nowe modele domenowe `AttendanceEntry` oraz `AttendanceSummary` w `domain_models.py` i pełna persystencja w `storage.py` (`save_attendance`, `get_attendance_history`, `get_attendance_summary`).
  - **Nowa podstrona w panelu WWW (`/frekwencja` oraz `/attendance`)**:
    - Umieszczenie nowej pozycji w głównym pasku nawigacyjnym pomiędzy *Terminarz* a *Wiadomości*.
    - **Karty metryk KPI**: liczniki nieobecności nieusprawiedliwionych (z alertem o wymaganej reakcji), usprawiedliwionych, spóźnień oraz zwolnień.
    - **Dwa tryby wizualizacji kalendarza z rozwijanym menu wyboru (`attendance_view_mode`)**:
      - **Opcja 2 (domyślna)**: Roczna horyzontalna heatmapa obecności w stylu GitHub (kompaktowy pasek tygodni IX–VI z etykietami miesięcy, statystykami frekwencji i kolorowymi kafelkami statusu dni).
      - **Opcja 1**: Widok pojedynczego miesiąca z wygodnymi pigułkami wyboru miesięcy (sygnalizatory zdarzeń, wyszarzone miesiące przyszłe) i dedykowaną, czytelną siatką dni wybranego miesiąca.
      - Rozwijane menu wyboru umieszczone bezpośrednio na karcie Frekwencji z natychmiastowym przełączaniem widoków i trwałym zapisem wyboru w `config.yaml` (`POST /api/attendance/view-mode`).
    - **Interaktywna oś czasu (Timeline)**: pogrupowane chronologicznie zdarzenia z odznakami symboli, szczegółami lekcji i statusami e-Usprawiedliwień.
    - **Zestawienie przedmiotowe i podsumowanie okresów**: agregacja absencji według przedmiotów oraz oficjalne tabele semestralne Librus.
  - **Oznaczanie frekwencji w Planie lekcji (`/plan`) i na Pulpicie (`/`)**:
    - Inteligentna korelacja lekcji z frekwencją według klucza `(data, nr_lekcji)`.
    - Kolorystyczne oznaczenie krawędzi kart lekcji (🔴 czerwona dla nieuspr., 🟢 zielona dla uspr., 🟡 żółta dla spóźnień).
    - Odznaki przy nazwach przedmiotów (np. `🔴 Nieobecność (nieuspr.)`, `🟢 Usprawiedliwiona (e-Usprawiedliwienie)`, `🟡 Spóźnienie`).
    - Skrótowe przyciski `⏱️ Frekwencja: [symbol]` / `⏱️ [symbol]` z linkami kotwicowymi prowadzącymi do sekcji danego dnia w module frekwencji.
    - Kropki statusu obecności na pigułkach wyboru dni tygodnia w widoku `/plan`.
    - Liczniki obecności w podsumowaniu planu dnia (`🔴 X nieuspr.`, `🟢 Y uspr.`, `🟡 Z spóźnień`).
  - **Prezentacja i wyróżnianie frekwencji w Kalendarium zdarzeń na Pulpicie (`/`)**:
    - Włączenie zdarzeń frekwencji (nieobecności usprawiedliwione i nieusprawiedliwione, spóźnienia, zwolnienia) do chronologicznego kalendarium ostatnich dni na pulpicie głównym (`build_recent_days_timeline`).
    - Odznaczanie kart zdarzeń kolorowymi obramowaniami (`border-l-4`), wyrazistymi odznakami (`🔴 nb`, `🟢 u`, `🟡 sp`, `🔵 zw`), numerem lekcji, tematem, nauczycielem i adnotacją e-Usprawiedliwień oraz bezpośrednim łączem kotwicowym do danego dnia w module frekwencji.
    - Sygnalizowanie absencji bezpośrednio w nagłówkach dni w kalendarium (np. `🔴 1 nb`, `🟢 1 uspr.`, `🟡 1 sp.`) oraz alertowe oznaczenie obramowania całej karty dnia w przypadku nieobecności nieusprawiedliwionej.
    - Dodanie nowej opcji wyboru typu zdarzeń „⏱️ Frekwencja i obecność” w formularzu Ustawień w sekcji kalendarium (`timeline.event_types`).
  - **Prezentacja frekwencji w powiadomieniach e-mail i raportach okresowych**:
    - **Raport postępów ucznia (`librus_progress_report.py` / `progress_report.html`)**:
      - Dodanie kafelka KPI w podsumowaniu okresu prezentującego bilans frekwencji (nieobecności usprawiedliwione/nieusprawiedliwione, spóźnienia).
      - Dedykowana sekcja „⏱️ Zdarzenia frekwencji w analizowanym okresie” z odznakami symboli (`🟢 nieobecność uspr.`, `🔴 nieobecność`, `🟡 spóźnienie`), numerem lekcji, przedmiotem, statusem e-Usprawiedliwienia, nauczycielem i tematem lekcji.
      - Aktualizacja funkcji `print_cli_summary` w konsoli o zestawienie zdarzeń frekwencji.
    - **Bieżące powiadomienia e-mail (`librus_updates_notifier.py` / `summary.html`)**:
      - Uwzględnienie frekwencji w tytule e-maila (np. `frekwencja (1 nieob.)`).
      - Czwarty kafelek KPI „Frekwencja” w nagłówku podsumowania.
      - Wizualne odznaki statusu obecności bezpośrednio przy lekcjach w planie dnia powiadomienia (`🟢 Usprawiedliwiona`, `🔴 Nieobecność nieuspr.`, `🟡 Spóźnienie`).
      - Dedykowana karta podsumowująca nowe wpisy frekwencji w treści powiadomienia.
    - Przekazywanie i formatowanie frekwencji w `MailSender`, `GmailSender`, `SmtpSender`, `UpdatesNotifier` oraz `LibrusCollector`.
  - Wygenerowano statyczny widok demonstracyjny `examples/reports/web_frekwencja.html` i zaktualizowano zestaw raportów w `examples/reports/` (w tym `raport_8979296.html` oraz `powiadomienie_collector.html`).
- **Śledzenie lekcji w czasie rzeczywistym w Planie lekcji i na Pulpicie (Live Lesson Tracker)**:
  - Automatyczne wykrywanie lekcji trwającej w danej chwili (`🟢 TRWA TERAZ`) z pulsującym wskaźnikiem, licznikiem czasu do dzwonka (`⏱️ jeszcze X min`) oraz wyeksponowanym numerem sali i nazwiskiem nauczyciela.
  - Oznaczanie lekcji, które się już odbyły (`✓ Odbyła się`) ze stonowanym tłem i wyciszonym kontrastem, co ułatwia rodzicowi natychmiastowe zorientowanie się w bieżącym planie dnia.
  - Wykrywanie przerw międzylekcyjnych z automatycznym banerem informującym o czasie do kolejnego dzwonka (`☕ Trwa przerwa między lekcjami (do HH:MM) • Dzwonek za X min →`) oraz zapowiedzią najbliższego przedmiotu (`⏳ Następna lekcja`).
  - Spójna prezentacja statusów na żywo zarówno w pełnym widoku `/plan`, jak i w kafelku planu lekcji na pulpicie głównym (`/`).
- **Wysuwany panel boczny nawigacji (Mobile Drawer / Sheet)**:
  - Dedykowane menu boczne otwierane przyciskiem `☰` poniżej breakpointu `xl`, zawierające pełną nawigację po modułach, wygodny przełącznik profili dzieci, szybki wybór motywów oraz wylogowanie.
- **Dedykowany modal potwierdzenia archiwizacji roku szkolnego**: Zastąpienie przeglądarkowego okna `confirm()` własnym, ostylowanym modalem w zakładce Ustawienia z dynamicznym podsumowaniem zakresu operacji i obsługą klawiszy Enter oraz Escape.
- **Obsługa wielu dzieci przy archiwizacji roku**: Możliwość zarchiwizowania okresu jednocześnie dla wszystkich dzieci (checkbox w oknie modalnym) oraz systemowe przypomnienie `flash` o konieczności archiwizacji drugiego dziecka przy operacji pojedynczej.
- **Obsługa przedmiotów szkolnych bez ocen w bazie i na świadectwie**:
  - Wzbogacenie danych demonstracyjnych w `examples/storage/8979296.json` o przedmiot „Sztuka” (wliczany do średniej, bez ocen) oraz „Godzina wychowawcza” (oceny 4 i 5, wyłączona ze średniej na świadectwie).
- **Deterministyczny token CSRF w statycznym eksporcie widoków HTML**: Użycie stałego identyfikatora tokenu CSRF w trybie demonstracyjnym (`export_web_views`), eliminujące zbędne diffy w gicie w plikach `examples/reports/*.html` przy ponownym uruchamianiu `regenerate_reports.sh`.
- **Wielomotywowy silnik skórek panelu WWW (Theme Engine)**:
  - Obsługa 4 skórek out-of-the-box: Jasny (☀️ Domyślny), Ciemny Grafit (🌙 Slate Dark), Północ (🌌 OLED True Black), Szmaragdowy (🌲 Forest Green) oraz trybu Auto (💻 zgodnego z motywem systemu).
  - Skalowalna architektura Design Tokens (zmienne CSS `--theme-*` i selektory `[data-theme="..."]`), umożliwiająca łatwe dopisywanie kolejnych skórek bez konieczności modyfikowania szablonów podstron.
  - Szybki selektor motywu w prawym górnym rogu paska nawigacyjnego oraz sekcja wyboru z interaktywnymi kafelkami podglądu palet w zakładce Ustawienia.
  - Skrypt pre-renderujący w `<head>` eliminujący efekt migania jasnego tła (*Flash-of-White*) i trwała pamięć wyboru w `localStorage`.
  - Dynamiczna adaptacja kolorystyki osi, siatek i legend wykresów Chart.js w czasie rzeczywistym przy zmianie motywu (`themechange` event).
- **Animowany podgląd możliwości aplikacji (Showcase GIF / WebP) w nagłówku README**:
  - Zoptymalizowany animowany GIF (`docs/assets/librus2mail_showcase.gif`) oraz wersja WebP prezentujące pełny przekrój możliwości ekosystemu Librus2mail.
  - Zautomatyzowany skrypt `scripts/generate_showcase.py` (Headless Chrome + ffmpeg) generujący bezstratne klatki z widoków demonstracyjnych `examples/reports/`.
  - Płynne pionowe przewijanie zawartości stron (`CSS translateY`) przy unieruchomionej górnej belce nawigacyjnej.
  - Dedykowany slajd tytułowy (Intro) oraz slajd podsumowujący (Outro).
  - Indywidualnie konfigurowalny czas trwania każdego slajdu, parametry scrolla oraz opcja procentowego skalowania wielkości czcionki (`font_scale`).

### Zmieniono
- **Kompleksowa reorganizacja i dekompozycja dokumentacji (`README.md` oraz katalog `docs/`)**:
  - Odchudzenie i przebudowa `README.md` do zwięzłego, nowoczesnego formatu wizytówki projektu (~210 linii) skupionej na kluczowych wyróżnikach, tabeli widoków demonstracyjnych live na GitHub Pages, architekturze 5 modułów i szybkim starcie w 3 krokach.
  - Utworzenie dedykowanego katalogu `docs/` zawierającego wyczerpujące, tematyczne przewodniki:
    - `docs/modules.md`: szczegółowa specyfikacja wszystkich 5 modułów i centralnego orkiestratora.
    - `docs/configuration.md`: kompletny podręcznik pliku konfiguracyjnego `config.yaml`, zmiennych środowiskowych, konfiguracji kont pocztowych (Gmail App Passwords, SMTP) oraz parametrów frekwencji i bezpieczeństwa.
    - `docs/useful-scripts.md`: przeniesienie `useful-scripts.md` do katalogu `docs/`, rozszerzenie o Moduł 5 (`librus_web.py` z pełną listą flag CLI), aktualizacja architektury do 5 modułów i uaktualnienie odnośników w całym projekcie.
    - `docs/deployment.md`: kompletny przewodnik wdrożeniowy (Docker, Docker Compose, systemd Linux / Raspberry Pi, harmonogram cron, reverse proxy Nginx).
    - `docs/architecture.md`: architektura rozwiązania, paradygmat Local-First, format bazy danych `storage/`, modele Pydantic i diagramy przepływu danych.
    - `docs/development.md`: podręcznik deweloperski (pytest, ruff, generowanie raportów demo, publikacja wersji i aktualizacja changeloga).
    - `docs/faq-and-troubleshooting.md`: baza wiedzy, najczęstsze błędy (`NotLogged`, timeouty, hasła aplikacji Gmail) i odpowiedzi na pytania użytkowników.
- **Responsywność i ergonomia paska nawigacyjnego (Navbar)**:
  - Rozszerzenie kontenera nagłówka do `max-w-[1600px]` z płynnym dopasowaniem szerokości, co zapobiega ściskaniu elementów na ekranach laptopów (1280–1400 px).
  - Zastosowanie kompaktowej typografii i paddingów zakładek (`px-2.5 py-1.5`, `text-xs`) na ekranach `xl`, powiększającej się automatycznie do `px-3 py-2` i `text-sm` na dużych monitorach `2xl`.
  - Kompaktowy selektor motywu (kwadratowy przycisk 36x36 px z ikoną aktywnej skórki i strzałką menu) zwalniający cenną przestrzeń w nagłówku.
  - Zabezpieczenie kontenerów flex (`flex-shrink-0`) oraz zoptymalizowanie maksymalnych szerokości pól wyboru ucznia i rocznika archiwalnego.
- **Ergonomia nawigacji panelu WWW**:
  - Przeniesienie „Akcji CLI” z górnego paska nawigacyjnego do dedykowanej karty na samym dole zakładki „Ustawienia” z wygodnym przyciskiem przejścia i powrotną ścieżką breadcrumbs.
  - Zwolnienie miejsca w nagłówku aplikacji na przełącznik uczniów oraz wybór archiwalnych lat szkolnych.
- **Rozbudowa opisu archiwizacji w Ustawieniach**: Dodanie jasnej instrukcji informującej rodzica, że zarchiwizowane okresy można w każdej chwili przeglądać w menu wyboru ucznia na górnym pasku.

### Naprawione
- **Kontrast i czytelność trwającej lekcji w motywach ciemnych (Pulpit i Plan lekcji)**:
  - Rozwiązano problem niskiego kontrastu (jasna czcionka na jasnym tle) karty aktualnie trwającej lekcji (`TRWA TERAZ`, `⏱️ jeszcze X min`, godziny, sala, status `Lekcja w toku`) oraz banera przerwy międzylekcyjnej (`☕ Przerwa między lekcjami`) w motywach ciemnych (*Slate Dark*, *Midnight / Północ* i *Szmaragd*).
  - Wprowadzono dedykowane klasy semantyczne (`lesson-current-row`, `lesson-subject`, `lesson-time`, `lesson-classroom`, `lesson-current-time-badge`, `lesson-current-status-badge`, `lesson-break-banner`, `lesson-current-header-badge`, `lesson-today-btn`) wraz z precyzyjnie dobranymi regułami CSS i wariantami Tailwind `dark:`, zapewniającymi wysoki kontrast, głębokie ciemnozielone tła i wyraźny, czytelny tekst w każdym wariancie kolorystycznym.
- **Poprawki kontrastu i czytelności we wszystkich ciemnych motywach (Ciemny, Północ, Szmaragd)**:
  - Naprawiono widoczność nieaktywnych oraz aktywnych podzakładek w modułach Oceny („Aktualne oceny”, „Świadectwo”, „Optymalizator celu”) i Raporty.
  - Poprawiono czytelność boksów informacyjnych i poradników w zakładce Ustawienia (np. sekcja „Jak przeglądać dane z minionych lat?”).
  - Naprawiono czytelność datepickera `semester_split_date` (kontrast wybranej daty i tła kontrolki).
- **Poprawka weryfikacji trwających lekcji w nocy i rano**: Naprawiono błąd, w którym po północy lub wczesnym rankiem (przed rozpoczęciem pierwszej lekcji o 08:00) dzień był błędnie oznaczany jako „Dzisiaj (lekcje w toku)”. Wprowadzono precyzyjny podział na trzy stany dnia: przed rozpoczęciem lekcji (`🌅 Dzisiaj (przed lekcjami • start HH:MM)`), w trakcie lekcji (`🟢 Dzisiaj (lekcje w toku)`) oraz po ich zakończeniu (`Dzisiaj (lekcje zakończone)`).
- **Zabezpieczenie przed obcinaniem zakładek w nagłówku**: Wyeliminowano problem spychania przycisku „Ustawienia” poza ekran i ucinania etykiety „Raporty” na ekranach o szerokości około 1300 px.
- **Kalkulacja średniej ze świadectwa dla przedmiotów bez ocen**: Zabezpieczenie funkcji `calculate_subject_averages` oraz `calculate_certificate_summary` przed traktowaniem braku ocen jako stopnia 0 przy wyliczaniu średniej końcowej — przedmioty bez ocen otrzymują poprawny status „brak ocen” (`unrated_count`) i nie zaniżają średniej ze świadectwa.

---
## [2.6.0] – 2026-10-18

### Dodane
- separate section for excluded subjects in subject summary
- timeline sorting options, choose event types
- calendar settings options
- 5 day calendar of recent events

### Naprawione
- grades sorting fix

---
## [2.5.0] – 2026-10-15

### Dodane
- example reports, github pages
- 4 new raports

### Naprawione
- grades count fix

### Zmienione
- better exception handling and date parsing

---
## [2.4.0] – 2026-10-15

- **WERSJA NIEKOMPATYBILNA WSTECZNIE**, konieczność zainstalowania aplikacji ponownie (np. poprzez nowy wbudowany konfigurator)
- **Widok szczegółowy przedmiotu i zaawansowana analityka ocen w Panelu WWW (`/oceny/<przedmiot>`)**:
  - Dedykowany widok po kliknięciu na dowolny przedmiot w module ocen (`web/subject_detail.html` oraz endpointy `/oceny/<subject_name>` i `/przedmiot/<subject_name>`).
  - **Interaktywny wykres trajektorii ocen (Chart.js)**: wielkość i kolor punktu (bubble/scatter) odzwierciedla wagę pracy i stopień, z wykresem dynamicznej średniej kroczącej (Cumulative Moving Average) po każdej ocenie.
  - **Mini-histogram rozkładu ocen**: wizualizacja procentowa i ilościowa wystawionych ocen (stopnie 1–6).
  - **Analiza szansy podwyższenia oceny (`target_analysis`)**: precyzyjne wyliczenie dystansu punktowego do wyższego stopnia rocznego/śródrocznego oraz automatycznie generowane scenariusze (np. 1x sprawdzian o wadze 3 na stopień 5).
  - **Analiza ryzyka obniżenia oceny (`risk_analysis`)**: wyliczenie marginesu bezpieczeństwa nad dolnym prokiem bieżącej oceny oraz symulacje odporności na słabsze oceny (np. wpadka ze sprawdzianu o wadze 3 na 1).
  - **Interaktywny mini-symulator ocen na żywo**: dynamiczne przeliczanie nowej średniej i oceny bezpośrednio w przeglądarce za pomocą suwaków/list wyboru.
  - Pełne statystyki opisowe przedmiotu: średnia ważona, zwykła arytmetyczna, mediana, dominanta, min, max, suma wag i liczba prac.
  - Dodano 4 nowe testy jednostkowe i integracyjne w `tests/test_web.py`.

---
## [2.3.0] – 2026-10-13

- ** WERSJA NIEKOMPATYBILNA WSTECZNIE, konieczność zainstalowania aplikacji ponownie (np. poprzez nowy wbudowany konfigurator)
- **Usprawnienia wdrożenia Docker & Docker Compose oraz 100% wsparcie zmiennych ENV**:
  - Dedykowany, wyczerpujący podręcznik wdrożenia kontenerowego [docker/docker-installation.md](docker/docker-installation.md) z pełną tabelą zmiennych środowiskowych, architekturą non-root oraz instrukcją troubleshooting.
  - Przeniesienie wszystkich plików Docker do dedykowanego podkatalogu `docker/` (`Dockerfile`, `docker-compose.yml`, `.env.example`, `docker-installation.md`) dla czystości katalogu głównego.
  - Możliwość uruchomienia aplikacji w 100% w oparciu o zmienne środowiskowe (ENV / plik `.env`) bez konieczności montowania pliku `config.yaml` (`read_config` automatycznie inicjalizuje się z ENV).
  - Wzbogacenie modelu `AppSettings` o płaskie aliasy ENV (np. `LIBRUS_LOGIN`, `LIBRUS_PASSWORD`, `LIBRUS_MAIL_LOGIN`, `LIBRUS_SMTP_HOST`, `LIBRUS_WEB_PASSWORD`, `LIBRUS_SCHEDULE_MODE`).
  - Dodanie wzorcowego pliku [docker/.env.example](docker/.env.example) dla środowisk Docker.
  - Aktualizacja [docker/Dockerfile](docker/Dockerfile) (dodanie brakujących skryptów CLI, `EXPOSE 5000`) oraz [docker/docker-compose.yml](docker/docker-compose.yml) (usługa `student-report`, profile, obsługa `.env`).

---
## [2.2.0] – 2026-10-09

- **Typowane modele obiektów domenowych (Issue #8 - Etap 2)**:
  - Wprowadzenie dedykowanych modeli Pydantic v2 dla obiektów domenowych: `Grade` (ocena), `Message` (wiadomość prywatna), `Announcement` / `Notification` (ogłoszenie szkolne), `TimetableEntry` (terminarz) oraz `ScheduleLesson` / `ScheduleEntry` (plan lekcji).
  - Obiekty domenowe implementują `collections.abc.MutableMapping` zapewniając pełną zgodność z dotychczasowym dostępem słownikowym (`obj['field']`, `obj.get('field')`), rozpakowywaniem `{**obj}` oraz szablonami Jinja2.
  - Wyliczane właściwości pomocnicze w modelu `Grade`: `numeric_value` (automatyczne parsowanie stopnia na float, np. '5+' -> 5.5) oraz `weight_value` (parsowanie wagi).
  - Elastyczne aliasy pól w `Message` i `Announcement` (zarówno `date`, jak i `datetime`, oraz `author` i `sender`).
  - Pełna integracja z silnikami parsowania w `librus.py` oraz pamięcią stanu i historii ocen w `storage.py`.
- **Wczesna walidacja konfiguracji i typowane modele z Pydantic / pydantic-settings (Issue #8 - Etap 1)**:
  - Zastąpienie surowego, nietypowanego słownika konfiguracji silnie typowanymi modelami Pydantic v2 (`AppSettings`, `LibrusUserConfig`, `MailConfig`, `WebConfig`, `ScheduleConfig`, `NonGmailSettings`).
  - Natychmiastowa wczesna walidacja danych (fail-fast) przy starcie aplikacji — wyłapywanie błędnych adresów e-mail (`EmailStr`), nieprawidłowych typów czy brakujących danych logowania zanim aplikacja nawiąże połączenie sieciowe.
  - Zmienne środowiskowe i konteneryzacja (Docker / 12-factor): automatyczne nadpisywanie wartości z pliku YAML zmiennymi środowiskowymi z prefiksem `LIBRUS_` i zagnieżdżonym separatorem `__` (np. `LIBRUS_STORAGE_DIR`, `LIBRUS_MAIL__LOGIN`, `LIBRUS_MAIL__PASSWORD`).
  - Zunifikowanie i uproszczenie kluczy konfiguracyjnych: zerwanie z historycznymi aliasami na rzecz czytelnego standardu snake_case (`work_in_loop`, `delay_between_users_s`). Usunięto niepotrzebne parametry `do_not_send_first_parse` (ustanawianie bazy stanu przy pierwszym starcie odbywa się w pełni automatycznie) oraz `storage_type`.
  - Kanoniczne znaczniki czasu w bazie stanu JSON (`storage/`): usunięcie podwójnego zapisywania starych kluczy legacy (`last_updated`, `last_update_create`, `last_timetable_sync`, `last_schedule_sync`) na rzecz spójnych pól `last_collect_time`, `last_notify_time`, `timetable_last_sync`, `schedule_last_sync`.
  - Pełna integracja (interfejs `MutableMapping` / dostęp słownikowy `.get()`, `[]`, `to_dict()`) ze wszystkimi modułami, CLI i szablonami Jinja2.
- **Obsługa Google OAuth2 dla Gmail (`oauth2_file`)**:
  - Dodano alternatywną metodę uwierzytelniania konta pocztowego Gmail z użyciem pliku autoryzacyjnego OAuth2 (`client_secret.json` / plik tokenów autoryzacyjnych), zgodnie ze zgłoszeniem w Issue #5.
  - Wybór metody uwierzytelniania w kreatorze `/setup` oraz w zakładce `/ustawienia` (*Hasło do aplikacji (zalecane)* vs *Google OAuth2 (.json)*).
  - Wzbogacono klasę `GmailSender` o automatyczne inicjalizowanie klienta `yagmail.SMTP` z parametrem `oauth2_file` przy zachowaniu pełnej kompatybilności wstecznej z hasłami aplikacji.
  - Zaktualizowano przykładową konfigurację w `config-example.yaml`.
- **Kreator pierwszego uruchomienia w panelu WWW (`/setup`)**:
  - Automatyczne wykrywanie braku pliku `config.yaml` lub braku skonfigurowanych kont uczniów z płynnym przekierowaniem do kreatora onboardingowego.
  - Wygodny 4-krokowy Stepper UI: Krok 1: Profile uczniów i dzieci (z obsługą rodzeństwa oraz selekcją modułów ocen, terminarza, planu i wiadomości) -> Krok 2: Poczta e-mail (Gmail z hasłem aplikacji lub serwer SMTP) -> Krok 3: Harmonogram i automatyzacja -> Krok 4: Hasło i zabezpieczenia panelu WWW.
  - Bezpieczny zapis do pliku `config.yaml` oraz natychmiastowe odświeżenie konfiguracji w pamięci aplikacji i automatyczne zalogowanie do pulpitu rodzica.
- **Elastyczny harmonogram zadań i automatyzacja (`schedule`)**:
  - Intuicyjny wybór harmonogramu pobierania danych ze szkoły w `/setup` i `/ustawienia`:
    - Tryb o stałej porze dnia (`daily`): domyślnie codziennie o 16:00 z listą godzin (06:00–22:00 co 30 min) oraz wyborem dni (codziennie vs dni robocze pon.–pt.).
    - Tryb cykliczny w ciągu dnia (`interval`): odpytywanie co wybraną liczbę godzin (co 1h, 2h, 3h, 4h, 6h, 12h).
  - Harmonogram automatycznej wysyłki raportów postępów ucznia:
    - Możliwość skonfigurowania **więcej niż jednego raportu** (np. cotygodniowe podsumowanie w piątki oraz comiesięczny bilans ocen 1. dnia miesiąca).
    - Obsługa częstotliwości: co tydzień (`weekly` z wyborem dnia tygodnia) oraz co miesiąc (`monthly` z wyborem 1. dnia, 15. dnia lub ostatniego dnia miesiąca).
    - Elastyczny wybór zakresu dni dla każdego raportu (3, 7, 14, 30, 60 dni) oraz indywidualnej godziny wysyłki.
    - Przycisk dynamicznego dodawania kolejnych kart raportów („➕ Dodaj kolejny zaplanowany raport”) w formularzu WWW.
    - Automatyczne wyzwalanie zaplanowanych raportów w pętli `librus_collector.py` z niezależnym śledzeniem dat wysyłki per harmonogram (`report_key`) w pamięci stanu `storage.py`.
    - Uwzględnienie `schedule.reports` w CLI `librus_progress_report.py` jako domyślnego okresu analizy.
  - Interaktywny podgląd reguł dla linuksowego harmonogramu Crontab (`crontab -e`) generowany i aktualizowany na żywo w interfejsie WWW dla wszystkich aktywnych raportów.
- **Interaktywna weryfikacja logowania Librus („Testuj logowanie Librus”)**:
  - Przycisk sprawdzania poprawności danych logowania ucznia w locie z poziomu formularzy WWW.
  - Asynchroniczny endpoint API `/api/test-librus` oraz usługa backendowa `test_librus_credentials` wykonująca symulację logowania bez pobierania pełnych danych.
  - Dynamiczny wskaźnik oczekiwania i natychmiastowa informacja zwrotna o poprawności danych autoryzacyjnych lub przyczynie błędu.
- **Zakładka „Ustawienia” w panelu WWW (`/ustawienia`)**:
  - Nowa pozycja `⚙️ Ustawienia` w menu głównym (wersja desktop i mobile).
  - Wygodna edycja parametrów kont, powiadomień e-mail, harmonogramu odpytywania, raportów i ochrony panelu.
  - Bezpieczne zachowywanie dotychczasowych haseł (Librus, skrzynka e-mail, panel WWW) przy pozostawieniu pustych pól.
  - Automatyczne tworzenie kopii zapasowej konfiguracji (`config.yaml.bak`) przed nadpisaniem pliku.
- **Eksport statyczny nowych widoków**:
  - Integracja `web_setup.html` oraz `web_ustawienia.html` w silniku eksportu widoków (`export_web_views`) oraz skrypcie `examples/reports/regenerate_reports.sh`.

### Zmienione
- Usunięto surowy techniczny checkbox „Praca ciągła w nieskończonej pętli demona (systemd / Docker)” na rzecz czytelnych ustawień harmonogramu.
- Poprawiono etykietę interwału: „Odstęp pomiędzy ściąganiem danych kolejnych dzieci (sekundy)”.
- Wskazówka dotycząca hasła aplikacji Gmail jest teraz wyświetlana wyłącznie po zaznaczeniu opcji Gmail (dla SMTP pozostaje ukryta).

### Poprawione
- **Walidacja formularza kreatora konfiguracji (`/setup`)**:
  - Wyeliminowano błąd przeglądarki `An invalid form control with name='mail_login' is not focusable.` przy próbie zapisu konfiguracji na ostatnim kroku kreatora.
  - Wprowadzono atrybut `novalidate` na formularzu kreatora w połączeniu z automatyczną, sekwencyjną walidacją każdego kroku (krok po kroku i przy przeskakiwaniu kroków).
  - W przypadku jakichkolwiek brakujących lub błędnych danych w poprzednich krokach kreator automatycznie cofa widok do właściwego kroku, przewija ekran i podświetla pole z komunikatem pomocy.
  - Dostosowano typ pola loginu (`type="email"` dla Gmail, `type="text"` dla własnego serwera SMTP).

---
## [2.1.0] – 2026-10-07

### Dodane
- **Zakładka „Raporty” w panelu WWW (`/raporty`)**:
  - Nowa główna sekcja w menu nawigacyjnym z trzema zintegrowanymi podzakładkami analiz:
    - **Raport postępów** (`/raporty/postepy`): interaktywny raport postępów rodzica z wyborem horyzontu czasowego (3, 7, 14, 30 dni).
    - **Raport ucznia** (`/raporty/uczen`): karta motywacyjna z przełącznikiem stylu grupy wiekowej (Dzieci / `kids`, Nastolatki / `teens`, Młodzież / `youth`) oraz zakresem dni (3, 7, 14, 30 dni).
    - **Podsumowanie dzienne** (`/raporty/podsumowanie`): chronologiczne zestawienie powiadomień, ocen i wiadomości z date-pickerem oraz wygodną nawigacją dzień wstecz / dzień w przód (`‹ Poprzedni dzień`, `Następny dzień ›`).
- **Dynamiczne wersjonowanie panelu WWW (`get_app_version`)**:
  - Automatyczne pobieranie aktualnego numeru wersji aplikacji z tagów Gita (`git describe --tags --abbrev=0`), metadanych pakietu (`importlib.metadata`) oraz zmiennej `librus2mail.__version__`.
  - Wersja w stopce interfejsu WWW (`base.html`) automatycznie dopasowuje się do wydania na GitHubie bez ręcznego wpisywania w kodzie.
- **Czytelny format czasu synchronizacji (`format_human_timestamp`)**:
  - Konwersja surowego znacznika czasu ISO na naturalne określenia w języku polskim: `dzisiaj o 12:25 (przed chwilą)`, `dzisiaj o 12:25 (45 min temu)`, `dzisiaj o 10:00 (3 godz. temu)`, `wczoraj o 18:45`, `przedwczoraj o 20:10`, `30.09 o 09:15 (7 dni temu)`.
  - Rejestracja filtra Jinja2 `human_time` dla Flask oraz zachowanie pełnego znacznika ISO w atrybucie `title` (tooltip) na pulpicie.
- **Eksport raportów WWW do GitHub Pages**:
  - Rozszerzenie eksportera statycznego HTML (`export_web_views`) oraz skryptu `examples/reports/regenerate_reports.sh` o nowe widoki raportów (`web_raporty_postepy.html`, `web_raporty_uczen_kids.html`, `web_raporty_uczen_teens.html`, `web_raporty_uczen_youth.html`, `web_raporty_podsumowanie.html`).
  - Dodanie odnośników do raportów w workflow publikacji GitHub Pages (`.github/workflows/release.yml`).
- **Wektorowy favicon w barwach logo projektu**:
  - Nowa ikona karty przeglądarki (favicon) bazująca na motywie projektu (gradient indigo-sky + symbol szkoły 🏫).
  - Wdrożenie jako `data:image/svg+xml` w szablonie bazowym (działa natychmiast w trybie online, offline oraz na GitHub Pages) wraz z dedykowanymi endpointami serwera `/favicon.ico` oraz `/favicon.svg`.

### Zmienione
- **Refaktoryzacja magazynu danych (`storage.py`) na `pathlib.Path`**:
  - Zastąpienie wywołań `os.path.join`, `os.path.isfile`, `os.path.isdir` obiektową składnią `pathlib.Path`.
  - Wprowadzenie bezpiecznych, atomowych operacji na plikach JSON: `read_json_safe` oraz `write_json_atomic`.
- **Szablony powiadomień e-mail**:
  - Usunięcie przycisku „Zaloguj się do Librus Synergia” z widoku podsumowania dnia (`summary.html`), zapewniając spójny i czysty wygląd zarówno w wiadomościach pocztowych, jak i w serwisie WWW.

### Naprawione
- **Uruchamianie `librus_web.py` bezpośrednio ze środowiska venv**:
  - Dodanie ścieżki pakietu `src/` do `sys.path` w skrypcie `librus_web.py`, co zapobiega błędowi `ModuleNotFoundError: No module named 'librus2mail'` przy wywołaniu ze skopiowanego katalogu na serwerze.

---
## [2.0.1] – 2026-10-05

### Naprawione
- import base path
- refactor

---
## [2.0.0] – 2026-10-05

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

[Unreleased]: https://github.com/cackoarek/librus2mail/compare/v2.8.0...HEAD
[2.8.0]: https://github.com/cackoarek/librus2mail/compare/v2.7.0...v2.8.0
[2.7.0]: https://github.com/cackoarek/librus2mail/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/cackoarek/librus2mail/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/cackoarek/librus2mail/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/cackoarek/librus2mail/compare/v2.3.0...v2.4.0
[2.3.0]: https://github.com/cackoarek/librus2mail/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/cackoarek/librus2mail/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/cackoarek/librus2mail/compare/v2.0.1...v2.1.0
[2.0.1]: https://github.com/cackoarek/librus2mail/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/cackoarek/librus2mail/compare/v1.4.0...v2.0.0
[1.4.0]: https://github.com/cackoarek/librus2mail/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/cackoarek/librus2mail/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/cackoarek/librus2mail/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/cackoarek/librus2mail/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/cackoarek/librus2mail/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/cackoarek/librus2mail/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/cackoarek/librus2mail/releases/tag/v1.0.0
