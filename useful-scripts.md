# 🛠️ Przewodnik po skryptach i narzędziach CLI – Librus2mail

Niniejszy dokument zawiera kompletne zestawienie architektury, wszystkich skryptów, punktów wejścia CLI, dostępnych modyfikatorów, flag i opcji konfiguracyjnych w projekcie **Librus2mail** wraz ze szczegółowym wyjaśnieniem ich działania i przykładami użycia.

---

## 🏛️ Architektura 3 modułów i orkiestratora

Aplikacja zbudowana jest z **3 niezależnych, wyspecjalizowanych modułów** spiętych przez orkiestrator `collect_and_notify.py`:

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
        N[updates_notifier.py / UpdatesNotifier]
        N_HTML[Plik HTML / Podgląd CLI]
        N_MAIL[Bieżący E-mail o ocenach/wiadomościach]
    end

    subgraph Moduł 3: Progress Report
        PR[progress_report.py + ProgressAnalyzer]
        PR_HTML[Dashboard HTML / Podgląd CLI]
        PR_MAIL[Okresowy Raport Statystyk E-mail]
    end

    L -->|Pobranie OAuth + Scraping| C
    C -->|Zapis historii i stanu| S
    S -->|Odczyt stanu i diffing| N
    S -->|Odczyt historii ocen| PR
    N --> N_HTML
    N --> N_MAIL
    PR --> PR_HTML
    PR --> PR_MAIL
```

1. **Moduł 1: Collector (`librus_collector.py`)** – odpowiada wyłącznie za autoryzację w portalu Librus Synergia, bezpieczne pobieranie surowych danych (z opóźnieniami rate-limiting) i synchronizację ich z bazą `storage/`.
2. **Moduł 2: Updates Notifier (`updates_notifier.py`)** – odpowiada za weryfikację nowości (nowe wiadomości, ogłoszenia, oceny), formatowanie szablonów e-mail/HTML oraz wysyłkę do rodziców. Działa w 100% offline na bazie `storage/`.
3. **Moduł 3: Progress Report (`progress_report.py`)** – długoterminowy analityczny raport postępów ucznia (średnie ważone, wskaźniki formy PoP, szanse na czerwony pasek, styl uczenia się, ciche przedmioty).
4. **Orkiestrator (`collect_and_notify.py`)** – fasada CLI łącząca moduły w potok automatyczny (np. demon w tle) lub umożliwiająca wywołanie wybranego modułu w odosobnieniu (`--collect-only`, `--notify-only`, `--report`).

---

## 📑 Spis treści
1. [Sposoby uruchamiania poleceń](#1-sposoby-uruchamiania-poleceń)
2. [Główny orkiestrator – `collect_and_notify.py` / `librus-collect-and-notify`](#2-zintegrowany-potok-i-orkiestrator--collect_and_notifypy--librus-collect-and-notify)
3. [Moduł 1: Pobieranie danych (Collector) – `librus_collector.py`](#3-moduł-1-pobieranie-danych-collector--librus_collectorpy)
4. [Moduł 2: Powiadomienia bieżące (Updates Notifier) – `updates_notifier.py`](#4-moduł-2-powiadomienia-bieżące-updates-notifier--updates_notifierpy)
5. [Moduł 3: Generator raportów postępów – `progress_report.py`](#5-moduł-3-generator-raportów-postępów--progress_reportpy)
6. [Narzędzia deweloperskie i testowe (QA)](#6-narzędzia-deweloperskie-i-testowe-qa)
7. [Zarządzanie wdrożeniem (Docker & systemd)](#7-zarządzanie-wdrożeniem-docker--systemd)
8. [Tabela podsumowująca (Cheat Sheet)](#8-tabela-podsumowująca-cheat-sheet)

---

## 1. Sposoby uruchamiania poleceń

### Metoda A: Bezpośrednio przez interpreter Pythona (zalecana w venv)
```bash
source venv/bin/activate
python collect_and_notify.py # Zintegrowany potok: Collector + Notifier
python librus_collector.py   # Moduł 1: Collector (pobieranie surowych danych)
python updates_notifier.py   # Moduł 2: Updates Notifier (powiadomienia offline)
python progress_report.py    # Moduł 3: Progress Report (analityka postępów)
```

### Metoda B: Przez zarejestrowane polecenia CLI (po instalacji pakietu `pip install -e .`)
```bash
librus-collect-and-notify  # zintegrowany potok (alias: librus2mail)
librus-collector           # moduł zbierania danych
librus-notifier            # moduł bieżących powiadomień
librus-report              # moduł okresowych raportów postępów
```

---

## 2. Zintegrowany potok i orkiestrator – `collect_and_notify.py` / `librus-collect-and-notify`

### 🎯 Cel działania
Spina całe rozwiązanie w zintegrowany potok wykonawczy (**pobierz dane $\rightarrow$ wyślij powiadomienie**).
W domyślnym trybie działa jako demon ciągły: w pętli wywołuje najpierw pobranie świeżych danych ze szkoły (Collector), a następnie wysyłkę powiadomień (Notifier) i usypia proces na czas `wait_time_s`.

Dzięki przełącznikom trybów umożliwia również jednorazowe uruchomienie dowolnego z 3 modułów.

### 💻 Składnia polecenia
```bash
python collect_and_notify.py [-h] [--collect-only] [--notify-only] [--report]
                             [-c CONFIG] [-s STORAGE_DIR] [-u USER] [-d DAYS]
                             [--hours HOURS] [--dry-run] [-o OUTPUT] [--offline]
                             [--fetch] [-f] [--once] [--loop] [config]
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
| `--report` | **Moduł 3** | Uruchamia generator raportu analitycznego postępów (`progress_report.py`). |
| `--once`, `--no-loop` | **Sterowanie pętlą** | Wymusza pojedyncze wykonanie i natychmiastowe zakończenie procesu (nadpisuje `work-in-loop: true`). |
| `--loop` | **Sterowanie pętlą** | Wymusza działanie w nieskończonej pętli z interwałem `wait_time_s` (nadpisuje `work-in-loop: false`). |

### 🚀 Praktyczne przykłady użycia

```bash
# 1. Standardowe uruchomienie potoku w pętli demona:
venv/bin/python collect_and_notify.py

# 2. Pojedynczy przebieg pod crona (pobranie + powiadomienie, bez pętli):
venv/bin/python collect_and_notify.py --once

# 3. Tylko pobranie świeżych danych ze szkoły do storage (np. w osobnym cronie):
venv/bin/python collect_and_notify.py --collect-only --once

# 4. Tylko wygenerowanie podglądu powiadomień z ostatnich 3 dni do pliku HTML (offline):
venv/bin/python collect_and_notify.py --notify-only --days 3 -o podglad.html

# 5. Szybki podgląd w terminalu powiadomień ze wskazanego katalogu testowego:
venv/bin/python collect_and_notify.py --notify-only -s examples/storage --days 14 --dry-run

# 6. Wygenerowanie pełnego raportu postępów (Moduł 3) do pliku HTML:
venv/bin/python collect_and_notify.py --report --days 30 -o raport_miesieczny.html
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

## 4. Moduł 2: Powiadomienia bieżące (Updates Notifier) – `updates_notifier.py`

### 🎯 Cel działania
Działa w **100% offline** na danych zebranych w `storage/`.
1. Porównuje stan bazy i identyfikuje nowe wiadomości, ogłoszenia oraz oceny (na podstawie stanu lub zadanego okna `--days` / `--hours`).
2. Generuje estetyczne powiadomienia e-mail (Jinja2).
3. Wysyła wiadomości pocztą elektroniczną (Gmail / SMTP) lub eksportuje do samodzielnego pliku HTML (`-o`) albo wyświetla w terminalu (`--dry-run`).

### 💻 Składnia polecenia
```bash
python updates_notifier.py [-h] [-c CONFIG] [-s STORAGE_DIR] [-u USER] [-d DAYS] [--hours HOURS] [--dry-run] [-o OUTPUT] [config]
# lub:
librus-notifier [opcje]
```

### ⚙️ Parametry CLI

| Parametr / Flaga | Krótka flaga | Wartość domyślna | Opis działania |
| :--- | :---: | :--- | :--- |
| `--days <N>` | `-d` | `None` | Uznaje wpisy z ostatnich `N` dni za "nowe" (filtr czasowy). |
| `--hours <N>` | — | `None` | Uznaje wpisy z ostatnich `N` godzin za "nowe" (np. `--hours 12`). |
| `--dry-run` | — | `False` | Wyświetla podsumowanie wpisów w terminalu bez wysyłki maila. |
| `--save-html <plik>`<br>`--output <plik>` | `-o` | `None` | Zapisuje powiadomienie jako samodzielny plik HTML do weryfikacji w przeglądarce. |
| `--user <login/nazwa>` | `-u` | `None` | Filtruje powiadomienie do wybranego konta dziecka. |
| `--storage-dir <kat>` | `-s` | z configu | Ścieżka do katalogu pamięci stanu (np. `examples/storage`). |

### ⏱️ Mechanizm znaczników czasu i uruchomień nieregularnych (Watermarks)

W pliku stanu ucznia (`storage/<login>.json`) utrzymywane są dwa kluczowe znaczniki czasowe:
- `last_collect_time`: znacznik czasu ostatniej pomyślnej synchronizacji z portalem Librus (zapisywany przez `librus_collector.py`).
- `last_notify_time` (alias `last_update_create`): znacznik czasu ostatniego faktycznie dostarczonego powiadomienia do rodzica (zapisywany przez `updates_notifier.py`).

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
venv/bin/python updates_notifier.py

# 2. Podgląd w konsoli wpisów z ostatnich 7 dni:
venv/bin/python updates_notifier.py --days 7 --dry-run

# 3. Zapisanie powiadomienia e-mail jako plik HTML do weryfikacji wyglądu (nie przesuwa znacznika):
venv/bin/python updates_notifier.py --days 3 -o podglad_powiadomienia.html

# 4. Wygenerowanie powiadomienia ze wskazanego katalogu testowego:
venv/bin/python updates_notifier.py -s examples/storage --days 14 -o examples/reports/powiadomienie_collector.html

# 5. Sprawdzenie powiadomień dla konkretnego dziecka:
venv/bin/python updates_notifier.py -u 8979296 --days 7 --dry-run
```

---

## 5. Moduł 3: Generator raportów postępów – `progress_report.py`

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
python progress_report.py [-h] [-c CONFIG] [-s STORAGE_DIR] [-u USER] [-d DAYS] [--dry-run] [-o OUTPUT] [--fetch] [-f]
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
venv/bin/python progress_report.py

# 2. Podgląd raportu w terminalu:
venv/bin/python progress_report.py --dry-run

# 3. Zapis raportu HTML do pliku:
venv/bin/python progress_report.py -o podglad_raportu.html

# 4. Raport miesięczny (30 dni) ze wskazanego katalogu testowego:
venv/bin/python progress_report.py -s examples/storage -o examples/reports/raport_przykladowy.html --days 30

# 5. Wymuszenie generowania raportu mimo braku nowych ocen:
venv/bin/python progress_report.py --force -o raport_pelny.html
```

---

## 6. Narzędzia deweloperskie i testowe (QA)

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

## 7. Zarządzanie wdrożeniem (Docker & systemd)

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

## 8. Tabela podsumowująca (Cheat Sheet)

| Zadanie | Rekomendowane polecenie |
| :--- | :--- |
| **Stały monitoring (pełny potok demona w pętli)** | `venv/bin/python collect_and_notify.py` |
| **Pojedynczy przebieg monitoringu (bez pętli, pod crona)** | `venv/bin/python collect_and_notify.py --once` |
| **Tylko synchronizacja danych z Librusa do storage (1x)** | `venv/bin/python collect_and_notify.py --collect-only --once` |
| **Tylko wysyłka/podgląd powiadomień z bazy** | `venv/bin/python collect_and_notify.py --notify-only` |
| **Nieregularne powiadomienie (od ost. wysyłki)** | `venv/bin/python updates_notifier.py` |
| **Podgląd powiadomień w terminalu (np. ost. 7 dni)** | `venv/bin/python updates_notifier.py --days 7 --dry-run` |
| **Zapis powiadomienia e-mail do pliku HTML** | `venv/bin/python updates_notifier.py --days 3 -o podglad.html` |
| **Symulacja offline z zewnętrznego storage** | `venv/bin/python updates_notifier.py -s examples/storage --days 14 -o examples/reports/powiadomienie.html` |
| **Okresowy raport postępów ucznia (e-mail)** | `venv/bin/python progress_report.py` |
| **Podgląd raportu postępów w terminalu** | `venv/bin/python progress_report.py --dry-run` |
| **Wygenerowanie raportu HTML do podglądu** | `venv/bin/python progress_report.py -o raport.html` |
| **Raport postępów z zewnętrznego storage** | `venv/bin/python progress_report.py -s examples/storage -o examples/reports/raport.html --days 14` |
| **Raport miesięczny przez orkiestrator** | `venv/bin/python collect_and_notify.py --report --days 30 -o miesiac.html` |
| **Uruchomienie testów jednostkowych** | `venv/bin/pytest` |
| **Weryfikacja jakości kodu linterem** | `venv/bin/ruff check .` |
