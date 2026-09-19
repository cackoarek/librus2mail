# 🛠️ Przewodnik po skryptach i narzędziach CLI – Librus2mail

Niniejszy dokument zawiera kompletne zestawienie architektury, wszystkich skryptów, punktów wejścia CLI, dostępnych modyfikatorów, flag i opcji konfiguracyjnych w projekcie **Librus2mail** wraz ze szczegółowym wyjaśnieniem ich działania i przykładami użycia.

---

## 🏛️ Architektura 4 modułów i orkiestratora

Aplikacja zbudowana jest z **4 niezależnych, wyspecjalizowanych modułów** spiętych przez orkiestrator `librus_collect_and_notify.py`:

```mermaid
flowchart TD
    subgraph Źródło danych
        L[Librus Synergia Portal]
    end

    subgraph Moduł 1: Collector
        C[librus_collector.py / LibrusCollector]
    end

    subgraph Pamięć stanu
        S[(storage/<login>.json)]
    end

    subgraph Moduł 2: Updates Notifier
        N[librus_updates_notifier.py / UpdatesNotifier]
        N_HTML[Plik HTML / Podgląd CLI]
        N_MAIL[Bieżący E-mail o ocenach/wiadomościach]
    end

    subgraph Moduł 3: Progress Report (Dla Rodziców)
        PR[librus_progress_report.py + ProgressAnalyzer]
        PR_HTML[Dashboard HTML / Podgląd CLI]
        PR_MAIL[Okresowy Raport Statystyk E-mail]
    end

    subgraph Moduł 4: Student Report (Dla Ucznia)
        SR[librus_student_report.py + StudentAnalyzer]
        SR_HTML[Raport HTML / Podgląd CLI]
        SR_MAIL[E-mail Ucznia kids/teens/youth]
    end

    L -->|Pobranie OAuth + Scraping| C
    C -->|Zapis historii i stanu| S
    S -->|Odczyt stanu i diffing| N
    S -->|Odczyt historii ocen| PR
    S -->|Odczyt bazy ocen| SR
    N --> N_HTML
    N --> N_MAIL
    PR --> PR_HTML
    PR --> PR_MAIL
    SR --> SR_HTML
    SR --> SR_MAIL
```

1. **Moduł 1: Collector (`librus_collector.py`)** – odpowiada wyłącznie za autoryzację w portalu Librus Synergia, bezpieczne pobieranie surowych danych (z opóźnieniami rate-limiting) i synchronizację ich z bazą `storage/`.
2. **Moduł 2: Updates Notifier (`librus_updates_notifier.py`)** – odpowiada za weryfikację nowości (nowe wiadomości, ogłoszenia, oceny), formatowanie szablonów e-mail/HTML oraz wysyłkę do rodziców. Działa w 100% offline na bazie `storage/`.
3. **Moduł 3: Progress Report (`librus_progress_report.py`)** – długoterminowy analityczny raport postępów ucznia dla rodziców (średnie ważone, wskaźniki formy PoP, szanse na czerwony pasek, styl uczenia się, ciche przedmioty).
4. **Moduł 4: Student Report (`librus_student_report.py`)** – motywacyjny raport postępów przygotowany bezpośrednio dla ucznia (Supermoce, szybkie szanse na awans, odznaki, 3 warianty szablonów: kids/teens/youth). Działa w 100% offline.
5. **Orkiestrator (`librus_collect_and_notify.py`)** – fasada CLI łącząca moduły w potok automatyczny (np. demon w tle) lub umożliwiająca wywołanie wybranego modułu w odosobnieniu (`--collect-only`, `--notify-only`, `--report`, `--student-report`).

---

## 📑 Spis treści
1. [Sposoby uruchamiania poleceń](#1-sposoby-uruchamiania-poleceń)
2. [Główny orkiestrator – `librus_collect_and_notify.py` / `librus-collect-and-notify`](#2-zintegrowany-potok-i-orkiestrator--librus_collect_and_notifypy--librus-collect-and-notify)
3. [Moduł 1: Pobieranie danych (Collector) – `librus_collector.py`](#3-moduł-1-pobieranie-danych-collector--librus_collectorpy)
4. [Moduł 2: Powiadomienia bieżące (Updates Notifier) – `librus_updates_notifier.py`](#4-moduł-2-powiadomienia-bieżące-updates-notifier--librus_updates_notifierpy)
5. [Moduł 3: Generator raportów postępów dla rodziców – `librus_progress_report.py`](#5-moduł-3-generator-raportów-postępów-dla-rodziców--librus_progress_reportpy)
6. [Moduł 4: Generator raportów motywacyjnych dla ucznia – `librus_student_report.py`](#6-moduł-4-generator-raportów-motywacyjnych-dla-ucznia--librus_student_reportpy)
7. [Narzędzia deweloperskie i testowe (QA)](#7-narzędzia-deweloperskie-i-testowe-qa)
8. [Zarządzanie wdrożeniem (Docker & systemd)](#8-zarządzanie-wdrożeniem-docker--systemd)
9. [Tabela podsumowująca (Cheat Sheet)](#9-tabela-podsumowująca-cheat-sheet)

---

## 1. Sposoby uruchamiania poleceń

### Metoda A: Bezpośrednio przez interpreter Pythona (zalecana w venv)
```bash
source venv/bin/activate
python librus_collect_and_notify.py # Zintegrowany potok: Collector + Notifier
python librus_collector.py          # Moduł 1: Collector (pobieranie surowych danych)
python librus_updates_notifier.py   # Moduł 2: Updates Notifier (powiadomienia offline)
python librus_progress_report.py    # Moduł 3: Progress Report (analityka postępów dla rodziców)
python librus_student_report.py     # Moduł 4: Student Report (motywacja i cele dla ucznia)
```

### Metoda B: Przez zarejestrowane polecenia CLI (po instalacji pakietu `pip install -e .`)
```bash
librus-collect-and-notify  # zintegrowany potok (alias: librus2mail)
librus-collector           # moduł zbierania danych
librus-notifier            # moduł bieżących powiadomień
librus-report              # moduł okresowych raportów postępów dla rodziców
librus-student-report      # moduł raportów motywacyjnych dla ucznia
```

---

## 2. Zintegrowany potok i orkiestrator – `librus_collect_and_notify.py` / `librus-collect-and-notify`

### 🎯 Cel działania
Spina całe rozwiązanie w zintegrowany potok wykonawczy (**pobierz dane $\rightarrow$ wyślij powiadomienie**).
W domyślnym trybie działa jako demon ciągły: w pętli wywołuje najpierw pobranie świeżych danych ze szkoły (Collector), a następnie wysyłkę powiadomień (Notifier) i usypia proces na czas `wait_time_s`.

Dzięki przełącznikom trybów umożliwia również jednorazowe uruchomienie dowolnego z 4 modułów.

### 💻 Składnia polecenia
```bash
python librus_collect_and_notify.py [-h] [--collect-only] [--notify-only] [--report] [--student-report]
                             [-c CONFIG] [-s STORAGE_DIR] [-u USER] [-d DAYS]
                             [--hours HOURS] [--dry-run] [-o OUTPUT] [--offline]
                             [--fetch] [-f] [--once] [--loop] [--summary] [config]
# lub zarejestrowane polecenia CLI:
librus-collect-and-notify [opcje]
librus2mail [opcje]
```

### ⚙️ Dedykowane przełączniki trybów pracy

| Flaga | Moduł | Opis działania |
| :--- | :--- | :--- |
| *(brak flagi)* | **Potok pełny** | Standardowy cykl: `Collector (pobranie) -> UpdatesNotifier (powiadomienia) -> sleep`. Szanuje `work-in-loop` z configu. |
| `--collect-only`, `--sync-only` | **Moduł 1** | Uruchamia wyłącznie pobieranie danych z Librusa i zapis do `storage/` bez wysyłania maili. |
| `--notify-only` | **Moduł 2** | Uruchamia wyłącznie analizę bazy `storage/` i wysyłkę powiadomień (e-mail / terminal / HTML). Działa w 100% offline. |
| `--report` | **Moduł 3** | Uruchamia generator raportu analitycznego postępów dla rodziców (`librus_progress_report.py`). |
| `--student-report` | **Moduł 4** | Uruchamia generator motywacyjnego raportu dla ucznia (`librus_student_report.py`). |
| `--summary` | **Format e-mail** | Wymusza wysłanie 1 zbiorczego e-maila ze wszystkimi nowościami (zamiast osobnych wiadomości, ogłoszeń i ocen). Nadpisuje `one_summary_message`. |
| `--once`, `--no-loop` | **Sterowanie pętlą** | Wymusza pojedyncze wykonanie i natychmiastowe zakończenie procesu (nadpisuje `work-in-loop: true`). |
| `--loop` | **Sterowanie pętlą** | Wymusza działanie w nieskończonej pętli z interwałem `wait_time_s` (nadpisuje `work-in-loop: false`). |

### 🚀 Praktyczne przykłady użycia

```bash
# 1. Standardowe uruchomienie potoku w pętli demona:
venv/bin/python librus_collect_and_notify.py

# 2. Pojedynczy przebieg pod crona (pobranie + powiadomienie, bez pętli):
venv/bin/python librus_collect_and_notify.py --once

# 3. Tylko pobranie świeżych danych ze szkoły do storage (np. w osobnym cronie):
venv/bin/python librus_collect_and_notify.py --collect-only --once

# 4. Tylko wygenerowanie podglądu powiadomień z ostatnich 3 dni do pliku HTML (offline):
venv/bin/python librus_collect_and_notify.py --notify-only --days 3 -o podglad.html

# 5. Szybki podgląd w terminalu powiadomień ze wskazanego katalogu testowego:
venv/bin/python librus_collect_and_notify.py --notify-only -s examples/storage --days 14 --dry-run

# 6. Wysłanie przykładowego powiadomienia testowego na e-mail jako 1 zbiorczy mail:
venv/bin/python librus_collect_and_notify.py --notify-only -s examples/storage --days 14 --summary

# 7. Wygenerowanie pełnego raportu postępów (Moduł 3) do pliku HTML:
venv/bin/python librus_collect_and_notify.py --report --days 30 -o raport_miesieczny.html
```

---

## 3. Moduł 1: Pobieranie danych (Collector) – `librus_collector.py`

### 🎯 Cel działania
Odpowiada wyłącznie za:
1. Logowanie przez OAuth do portalu Librus Synergia.
2. Bezpieczne scrapowanie wiadomości (`/wiadomosci`), ogłoszeń (`/ogloszenia`) i ocen (`/przegladaj_oceny/uczen`).
3. Zapisywanie szczegółów do trwałej bazy JSON (`storage/<login>.json`).
4. Rejestrację błędów komunikacji (`save_last_error`).

### 💻 Składnia polecenia
```bash
python librus_collector.py [-h] [-c CONFIG] [-s STORAGE_DIR] [-u USER] [--sync-only] [-d DAYS] [--dry-run] [-o OUTPUT] [--offline] [--once] [--loop] [config]
# lub:
librus-collector [opcje]
```

### ⚙️ Parametry CLI

| Parametr / Flaga | Typ | Wartość domyślna | Opis działania |
| :--- | :--- | :--- | :--- |
| `-c`, `--config <plik>` | opcja | `config.yaml` | Ścieżka do pliku konfiguracyjnego YAML. |
| `-s`, `--storage-dir <kat>` | opcja | `storage` | Ścieżka do katalogu pamięci stanu. |
| `-u`, `--user <login/nazwa>` | opcja | `None` (wszyscy) | Zawęża pobieranie tylko do wskazanego ucznia. |
| `--sync-only` | flaga | `False` | Tylko synchronizuje dane z Librusem do storage (bez powiadomień). |
| `--offline` | flaga | `False` | Tryb testowy: symuluje pobieranie na podstawie lokalnego storage. |
| `--once`, `--no-loop` | flaga | `False` | Wymusza 1 przebieg i zakończenie (nadpisuje `work-in-loop: true`). |
| `--loop` | flaga | `False` | Wymusza nieskończoną pętlę (nadpisuje `work-in-loop: false`). |

### 🚀 Praktyczne przykłady użycia

```bash
# 1. Samodzielne pobranie i synchronizacja bazy bez wysyłki maili (np. jednorazowo w cronie):
venv/bin/python librus_collector.py --sync-only --once

# 2. Ciągły demon synchronizacji w tle (pętla z interwałem wait_time_s):
venv/bin/python librus_collector.py --sync-only

# 3. Uruchomienie kolektora dla konkretnego dziecka:
venv/bin/python librus_collector.py -u 8979296 --sync-only --once
```

---

## 4. Moduł 2: Powiadomienia bieżące (Updates Notifier) – `librus_updates_notifier.py`

### 🎯 Cel działania
Działa w **100% offline** na danych zebranych w `storage/`.
1. Porównuje stan bazy i identyfikuje nowe wiadomości, ogłoszenia oraz oceny (na podstawie stanu lub zadanego okna `--days` / `--hours`).
2. Generuje estetyczne powiadomienia e-mail (Jinja2).
3. Wysyła wiadomości pocztą elektroniczną (Gmail / SMTP) lub eksportuje do samodzielnego pliku HTML (`-o`) albo wyświetla w terminalu (`--dry-run`).

### 💻 Składnia polecenia
```bash
python librus_updates_notifier.py [-h] [-c CONFIG] [-s STORAGE_DIR] [-u USER] [-d DAYS] [--hours HOURS] [--dry-run] [-o OUTPUT] [--summary] [config]
# lub:
librus-notifier [opcje]
```

### ⚙️ Parametry CLI

| Parametr / Flaga | Krótka flaga | Wartość domyślna | Opis działania |
| :--- | :---: | :--- | :--- |
| `--days <N>` | `-d` | `None` | Uznaje wpisy z ostatnich `N` dni za "nowe" (filtr czasowy). |
| `--hours <N>` | — | `None` | Uznaje wpisy z ostatnich `N` godzin za "nowe" (np. `--hours 12`). |
| `--dry-run` | — | `False` | Wyświetla podsumowanie wpisów w terminalu bez wysyłki maila. |
| `--summary` | — | `False` (z configu) | Wymusza wysłanie 1 zbiorczego e-maila ze wszystkimi nowościami zamiast osobnych wiadomości, ogłoszeń i ocen (szablon `summary.html`). Nadpisuje `one_summary_message`. |
| `--save-html <plik>`<br>`--output <plik>` | `-o` | `None` | Zapisuje powiadomienie jako samodzielny plik HTML do weryfikacji w przeglądarce. |
| `--user <login/nazwa>` | `-u` | `None` | Filtruje powiadomienie do wybranego konta dziecka. |
| `--storage-dir <kat>` | `-s` | z configu | Ścieżka do katalogu pamięci stanu (np. `examples/storage`). |

### ⏱️ Mechanizm znaczników czasu i uruchomień nieregularnych (Watermarks)

W pliku stanu ucznia (`storage/<login>.json`) utrzymywane są dwa kluczowe znaczniki czasowe:
- `last_collect_time`: znacznik czasu ostatniej pomyślnej synchronizacji z portalem Librus (zapisywany przez `librus_collector.py`).
- `last_notify_time` (alias `last_update_create`): znacznik czasu ostatniego faktycznie dostarczonego powiadomienia do rodzica (zapisywany przez `librus_updates_notifier.py`).

**Jak skrypt określa okres nowości przy uruchomieniach nieregularnych:**
1. **Tryb jawny (`--days N` / `--hours N`)**: Użytkownik decyduje wprost o oknie czasowym (np. `now - timedelta(days=N)`). Nadpisuje to wszelkie znaczniki.
2. **Tryb automatyczny/asynchroniczny (bez flag `--days` i `--hours`)**:
   - `UpdatesNotifier` odczytuje `last_notify_time` z pliku stanu ucznia.
   - Za "nowe" uznawane są wyłącznie wpisy dodane lub opublikowane **po** dacie `last_notify_time`.
   - Po wysłaniu wiadomości znacznik `last_notify_time` jest aktualizowany do bieżącej chwili.
   - **Ochrona podglądu**: Uruchomienie w trybie podglądu (`--dry-run` lub `-o / --save-html`) **nigdy nie przesuwa** znacznika `last_notify_time`.
   - **Pierwszy start**: Jeśli brak jest znacznika `last_notify_time` oraz skonfigurowano `do_not_send_first_parse: true`, skrypt ustanawia punkt bazowy bez wysyłania powiadomień historycznych.

### 🚀 Praktyczne przykłady użycia

```bash
# 1. Nieregularne powiadomienie (od ostatniego powiadomienia w bazie storage):
venv/bin/python librus_updates_notifier.py

# 2. Podgląd w konsoli wpisów z ostatnich 7 dni:
venv/bin/python librus_updates_notifier.py --days 7 --dry-run

# 3. Zapisanie powiadomienia e-mail jako plik HTML do weryfikacji wyglądu (nie przesuwa znacznika):
venv/bin/python librus_updates_notifier.py --days 3 -o podglad_powiadomienia.html

# 4. Wygenerowanie powiadomienia ze wskazanego katalogu testowego:
venv/bin/python librus_updates_notifier.py -s examples/storage --days 14 -o examples/reports/powiadomienie_collector.html

# 4b. Powtarzalne generowanie – stała data referencyjna (okno --days liczy od tej daty):
venv/bin/python librus_updates_notifier.py -s examples/storage --days 14 --actual-date 2026-09-09 -o examples/reports/powiadomienie_collector.html

# 5. Wysłanie przykładowego powiadomienia ze storage testowego na skonfigurowany e-mail (1 zbiorczy mail):
venv/bin/python librus_updates_notifier.py -s examples/storage --days 14 --summary

# 5b. Wysłanie zbiorczego powiadomienia – stała data referencyjna:
venv/bin/python librus_updates_notifier.py -s examples/storage --days 14 --actual-date 2026-09-09 --summary

# 6. Sprawdzenie powiadomień dla konkretnego dziecka:
venv/bin/python librus_updates_notifier.py -u 8979296 --days 7 --dry-run
```

---

## 5. Moduł 3: Generator raportów postępów – `librus_progress_report.py`

### 🎯 Cel działania
Długoterminowy silnik analityczny bazujący na historii ocen w `storage/`:
* Oblicza średnie ważone (przedmiotowe i ogólną).
* Bada dynamikę formy ucznia (PoP – Period-over-Period) względem poprzedniego raportu.
* Symuluje szanse i drogę do świadectwa z wyróżnieniem (czerwony pasek – cel 4.75).
* Wykrywa przedmioty na granicy ocen (kalkulator szans podciągnięcia vs ryzyko spadku).
* Analizuje styl uczenia się (sprawdziany o wadze $\ge 2$ vs praca bieżąca o wadze 1).
* Wykrywa tzw. "ciche przedmioty" (brak ocen od ponad 30 dni).

### 💻 Składnia polecenia
```bash
python librus_progress_report.py [-h] [-c CONFIG] [-s STORAGE_DIR] [-u USER] [-d DAYS] [--dry-run] [-o OUTPUT] [--fetch] [-f]
# lub:
librus-report [opcje]
```

### ⚙️ Parametry CLI

| Parametr / Flaga | Krótka flaga | Wartość domyślna | Opis działania |
| :--- | :---: | :--- | :--- |
| `--days <N>` | `-d` | data ost. raportu lub 7 | Sztywny okres analizy za ostatnie `N` dni wstecz (np. `--days 30`). |
| `--dry-run` | — | `False` | Pełna analiza i wydruk dashboardu w terminalu ASCII bez wysyłki maila. |
| `--save-html <ścieżka>`<br>`--output <ścieżka>` | `-o` | `None` | Zapisuje pełny dashboard do samodzielnego pliku HTML (nie wysyła e-maila). |
| `--fetch` | — | `False` | Łączy się na żywo z Librus Synergia i pobiera oceny przed analizą. |
| `--force` | `-f` | `False` | Wymusza generowanie raportu nawet jeśli uczeń nie dostał żadnej nowej oceny. |
| `--user <login/nazwa>` | `-u` | `None` | Filtruje wykonanie do wybranego ucznia. |

### 🚀 Praktyczne przykłady użycia

```bash
# 1. Standardowa wysyłka okresowego raportu e-mailem:
venv/bin/python librus_progress_report.py

# 2. Podgląd raportu w terminalu:
venv/bin/python librus_progress_report.py --dry-run

# 3. Zapis raportu HTML do pliku:
venv/bin/python librus_progress_report.py -o podglad_raportu.html

# 4. Raport miesięczny (30 dni) ze wskazanego katalogu testowego:
venv/bin/python librus_progress_report.py -s examples/storage -o examples/reports/raport_przykladowy.html --days 30

# 4b. Powtarzalne generowanie – stała data referencyjna (okno --days zawsze liczy od tej daty):
venv/bin/python librus_progress_report.py -s examples/storage --days 14 --actual-date 2026-09-09 -o examples/reports/raport_postepow.html --force

# 5. Wymuszenie generowania raportu mimo braku nowych ocen:
venv/bin/python librus_progress_report.py --force -o raport_pelny.html
```

---

## 6. Moduł 4: Generator raportów motywacyjnych dla ucznia – `librus_student_report.py`

### 🎯 Cel działania
Niezależny moduł raportowy przygotowany ze szczególnym uwzględnieniem motywacji samego ucznia:
* Wskazuje **Supermoce** (przedmioty z najwyższą średnią i seriami dobrych ocen).
* Oblicza **Szybkie Punkty / Szanse na Awans (Quick Wins)** – przedmioty, w których minimalny wysiłek (np. jedna 5 z kartkówki lub odpowiedzi) przeskakuje próg wyższego stopnia.
* Formułuje łagodną **Tarczę Ochronną** – przypomnienia o powtórkach przed sprawdzianami bez pedagogicznego zniechęcania.
* Przyznaje **Odznaki Grywalizacyjne** (np. 🚀 As Przestworzy, 👑 Mistrzowski Poziom, ⚡ W Rytmie Nauki).
* Dopasowuje język i layout za pomocą 3 wariantów szablonów:
  * `kids` (klasy 4–6): Karta Mocy, misje, kolorowy układ gamifikacyjny.
  * `teens` (klasy 7–8): Weekly Briefing, ciemny motyw cyan/dark, mocne filary, kalkulator punktów.
  * `youth` (szkoła średnia / liceum): Student Performance Dashboard, analiza progów ocen semestralnych.

Moduł działa **w 100% lokalnie i offline** wyłącznie na bazie danych ze `storage/`.

### 💻 Składnia polecenia
```bash
python librus_student_report.py [-h] [-c CONFIG] [-s STORAGE_DIR] [-u USER] [-d DAYS] [-t {kids,teens,youth}] [--actual-date ACTUAL_DATE] [--dry-run] [-o OUTPUT]
# lub:
librus-student-report [opcje]
```

### ⚙️ Parametry CLI

| Parametr / Flaga | Krótka flaga | Wartość domyślna | Opis działania |
| :--- | :---: | :--- | :--- |
| `--config <plik>` | `-c` | `config.yaml` | Ścieżka do pliku konfiguracyjnego YAML. |
| `--storage-dir <kat>` | `-s` | z configu (`storage`) | Ścieżka do katalogu pamięci stanu `storage` (nadpisuje config). |
| `--user <login/nazwa>` | `-u` | `None` | Filtruje generowanie raportu tylko do wskazanego ucznia. |
| `--days <N>` | `-d` | `None` | Zawęża analizę ocen do ostatnich `N` dni. |
| `--template <typ>` | `-t` | z configu lub `kids` | Wymusza wariant szablonu: `kids`, `teens` lub `youth`. |
| `--output <plik/kat>` | `-o` | `None` | Zapisuje raport jako samodzielny plik HTML (pomija wysyłkę e-mail). |
| `--dry-run` | — | `False` | Podsumowanie w konsoli bez wysyłania maili i bez zapisu plików. |
| `--actual-date <data>` | — | `None` | Referencyjna data analizy (`YYYY-MM-DD`) dla powtarzalnych testów. |

### 🚀 Praktyczne przykłady użycia

```bash
# 1. Standardowa wysyłka raportu do ucznia (według sekcji student_report w config.yaml):
venv/bin/python librus_student_report.py

# 2. Podgląd motywacyjnego raportu w terminalu (--dry-run):
venv/bin/python librus_student_report.py --dry-run

# 3. Zapisanie raportu jako plik HTML dla szablonu kids (klasy 4-6):
venv/bin/python librus_student_report.py -t kids -o podglad_kids.html

# 4. Zapisanie raportu jako plik HTML dla szablonu teens (klasy 7-8):
venv/bin/python librus_student_report.py -t teens -o podglad_teens.html

# 5. Zapisanie raportu jako plik HTML dla szablonu youth (liceum):
venv/bin/python librus_student_report.py -t youth -o podglad_youth.html

# 6. Zawężenie analizy do ocen z ostatnich 14 dni dla konkretnego ucznia:
venv/bin/python librus_student_report.py -u 8979295 --days 14 -o raport_ucznia.html

# 7. Symulacja offline ze wskazanego katalogu storage ze stałą datą referencyjną:
venv/bin/python librus_student_report.py -s examples/storage --actual-date 2026-09-09 --dry-run
```

---

## 7. Narzędzia deweloperskie i testowe (QA)

W projekcie skonfigurowano zestaw narzędzi do weryfikacji jakości kodu i poprawności działania:

```bash
# 1. Uruchomienie pełnego pakietu testów jednostkowych (pytest):
venv/bin/pytest

# 2. Uruchomienie testów z raportem pokrycia kodu (coverage):
venv/bin/pytest --cov=librus2mail

# 3. Błyskawiczna analiza statyczna i linter (Ruff):
venv/bin/ruff check .

# 4. Automatyczna naprawa wykrytych problemów formatowania:
venv/bin/ruff check --fix .
```

---

## 8. Zarządzanie wdrożeniem (Docker & systemd)

### 🐳 Środowisko kontenerowe (Docker Compose)
```bash
# 1. Budowa i uruchomienie usługi w tle:
docker compose up -d --build

# 2. Podgląd logów na żywo:
docker compose logs -f

# 3. Wywołanie podglądu powiadomień wewnątrz kontenera:
docker compose exec librus2mail librus-notifier --days 7 --dry-run

# 4. Wywołanie raportu postępów wewnątrz kontenera:
docker compose exec librus2mail librus-report --dry-run

# 5. Wywołanie raportu ucznia wewnątrz kontenera:
docker compose exec librus2mail librus-student-report --dry-run
```

### 🐧 Usługa systemowa Linux (`systemd`)
```bash
# 1. Sprawdzenie statusu:
sudo systemctl status librus2mail

# 2. Restart usługi po aktualizacji kodu:
sudo systemctl restart librus2mail

# 3. Podgląd logów w journalctl:
sudo journalctl -u librus2mail -f -n 50
```

---

## 9. Tabela podsumowująca (Cheat Sheet)

| Zadanie | Rekomendowane polecenie |
| :--- | :--- |
| **Stały monitoring (pełny potok demona w pętli)** | `venv/bin/python librus_collect_and_notify.py` |
| **Pojedynczy przebieg monitoringu (bez pętli, pod crona)** | `venv/bin/python librus_collect_and_notify.py --once` |
| **Tylko synchronizacja danych z Librusa do storage (1x)** | `venv/bin/python librus_collect_and_notify.py --collect-only --once` |
| **Tylko wysyłka/podgląd powiadomień z bazy** | `venv/bin/python librus_collect_and_notify.py --notify-only` |
| **Nieregularne powiadomienie (od ost. wysyłki)** | `venv/bin/python librus_updates_notifier.py` |
| **Podgląd powiadomień w terminalu (np. ost. 7 dni)** | `venv/bin/python librus_updates_notifier.py --days 7 --dry-run` |
| **Zapis powiadomienia e-mail do pliku HTML** | `venv/bin/python librus_updates_notifier.py --days 3 -o podglad.html` |
| **Symulacja offline z zewnętrznego storage (HTML)** | `venv/bin/python librus_updates_notifier.py -s examples/storage --days 14 -o examples/reports/powiadomienie.html` |
| **Symulacja offline – stała data referencyjna (reprodukowalny)** | `venv/bin/python librus_updates_notifier.py -s examples/storage --days 14 --actual-date 2026-09-09 -o examples/reports/powiadomienie.html` |
| **Wysłanie testowego powiadomienia na e-mail (1 zbiorczy mail)** | `venv/bin/python librus_updates_notifier.py -s examples/storage --days 14 --summary` |
| **Okresowy raport postępów dla rodziców (e-mail)** | `venv/bin/python librus_progress_report.py` |
| **Podgląd raportu postępów dla rodziców w terminalu** | `venv/bin/python librus_progress_report.py --dry-run` |
| **Wygenerowanie raportu postępów HTML dla rodziców** | `venv/bin/python librus_progress_report.py -o raport.html` |
| **Motywacyjny raport ucznia (e-mail wg configu)** | `venv/bin/python librus_student_report.py` |
| **Podgląd motywacyjnego raportu ucznia w terminalu** | `venv/bin/python librus_student_report.py --dry-run` |
| **Wygenerowanie raportu ucznia HTML (szablon kids)** | `venv/bin/python librus_student_report.py -t kids -o raport_kids.html` |
| **Wygenerowanie raportu ucznia HTML (szablon teens)** | `venv/bin/python librus_student_report.py -t teens -o raport_teens.html` |
| **Wygenerowanie raportu ucznia HTML (szablon youth)** | `venv/bin/python librus_student_report.py -t youth -o raport_youth.html` |
| **Raport ucznia przez orkiestrator** | `venv/bin/python librus_collect_and_notify.py --student-report --days 7 --dry-run` |
| **Raport postępów dla rodziców z zewnętrznego storage** | `venv/bin/python librus_progress_report.py -s examples/storage -o examples/reports/raport.html --days 14` |
| **Raport postępów – stała data referencyjna (reprodukowalny)** | `venv/bin/python librus_progress_report.py -s examples/storage --days 14 --actual-date 2026-09-09 -o examples/reports/raport_postepow.html --force` |
| **Raport miesięczny dla rodziców przez orkiestrator** | `venv/bin/python librus_collect_and_notify.py --report --days 30 -o miesiac.html` |
| **Uruchomienie testów jednostkowych** | `venv/bin/pytest` |
| **Weryfikacja jakości kodu linterem** | `venv/bin/ruff check .` |
