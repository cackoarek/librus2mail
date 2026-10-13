# 🐳 Wdrożenie i instalacja w środowisku Docker & Docker Compose

Ten przewodnik zawiera kompletne instrukcje uruchomienia **Librus2mail** w kontenerach Docker przy użyciu narzędzia **Docker Compose** lub czystego polecenia **Docker CLI**.

---

## Spis treści
1. [Architektura kontenera i bezpieczeństwo](#1-architektura-kontenera-i-bezpieczeństwo)
2. [Metody konfiguracji (YAML vs Zmienne ENV)](#2-metody-konfiguracji-yaml-vs-zmienne-env)
3. [Kompletna lista zmiennych środowiskowych (ENV)](#3-kompletna-lista-zmiennych-środowiskowych-env)
4. [Wdrożenie z Docker Compose (Zalecane)](#4-wdrożenie-z-docker-compose-zalecane)
5. [Wdrożenie czystym Docker CLI (`docker run`)](#5-wdrożenie-czystym-docker-cli-docker-run)
6. [Raporty na żądanie z poziomu kontenera](#6-raporty-na-żądanie-z-poziomu-kontenera)
7. [Interaktywny Panel WWW w kontenerze](#7-interaktywny-panel-www-w-kontenerze)
8. [Rozwiązywanie problemów i wskazówki (Troubleshooting)](#8-rozwiązywanie-problemów-i-wskazówki-troubleshooting)

---

## 1. Architektura kontenera i bezpieczeństwo

Obraz kontenera zdefiniowany w pliku [docker/Dockerfile](Dockerfile) bazuje na oficjalnym, zminimalizowanym obrazie `python:3.10-slim`:
* **Bezpieczeństwo (Non-Root)**: Aplikacja uruchamiana jest z prawami dedykowanego, nieuprzywilejowanego użytkownika `librus` (`UID: 1000`, `GID: 1000`).
* **Strefa czasowa**: Kontener ma wstępnie skonfigurowaną polską strefę czasową `TZ=Europe/Warsaw`, co gwarantuje prawidłowe obliczanie terminów sprawdzianów i godzin powiadomień.
* **Trwałość danych (Persistence)**: Katalog `/app/storage` stanowi wolumen trwałego zapisu stanu (`storage/*.json`), co zapobiega utracie historii ocen i powiadomień przy restartach kontenera.
* **Wielousługowość**: Ten sam obraz obsługuje demona monitorującego (`librus-collector`), panel WWW (`librus-web`), generator raportu postępów (`librus-report`) oraz raport motywacyjny ucznia (`librus-student-report`).

---

## 2. Metody konfiguracji (YAML vs Zmienne ENV)

Aplikacja wspiera **dwa równorzędne podejścia konfiguracyjne**:

### Wariant A: Plik konfiguracyjny `config.yaml` (montowany wolumen)
Tradycyjny plik YAML z pełną strukturą ustawień w katalogu głównym projektu.
```bash
cp config-example.yaml config.yaml
# lub wersja minimalistyczna:
cp config-minimal.yaml config.yaml
```
Plik jest montowany do kontenera pod ścieżką `/app/config.yaml`.

### Wariant B: Pełna konfiguracja wyłącznie przez ENV / plik `.env` (Bez pliku YAML!)
Jeśli wolisz rozwiązania w stylu *Twelve-Factor App* lub wdrażasz aplikację na platformie typu Portainer, Synology Container Manager, Kubernetes lub TrueNAS:
```bash
cp docker/.env.example .env
# edytuj plik .env wpisując swoje dane
```
W tym trybie **nie musisz tworzyć ani montować pliku `config.yaml`** – aplikacja automatycznie wykryje parametry ze środowiska i zainicjalizuje całe działanie.

> [!TIP]
> Zmienne środowiskowe mają wyższy priorytet niż plik `config.yaml`. Możesz używać pliku `config.yaml` jako bazy i nadpisywać wybrane parametry (np. hasła czy port) pojedynczymi zmiennymi ENV.

---

## 3. Kompletna lista zmiennych środowiskowych (ENV)

Wszystkie parametry konfiguracyjne Librus2mail można przekazać za pomocą zmiennych środowiskowych:

### 3.1. Konto ucznia w Librusie

| Zmienna ENV | Typ | Domyślnie | Opis |
| :--- | :--- | :--- | :--- |
| `LIBRUS_LOGIN` | `string` | *(wymagane)* | Login rodzica w portalu Librus Synergia (np. `1234567`). |
| `LIBRUS_PASSWORD` | `string` | *(wymagane)* | Hasło do konta Librus Synergia. |
| `LIBRUS_LOGIN_NAME` | `string` | `Uczeń (<login>)` | Imię i nazwisko dziecka do wyświetlania w nagłówkach i mailach. |
| `LIBRUS_NOTIFICATION_RECEIVERS` | `string` | `[]` | Adresy e-mail odbiorców powiadomień (rozdzielone przecinkami, np. `mama@gmail.com, tata@gmail.com`). |
| `LIBRUS_READ_MESSAGES` | `bool` | `true` | Czy pobierać i powiadamiać o nowych wiadomościach od nauczycieli. |
| `LIBRUS_READ_GRADES` | `bool` | `true` | Czy monitorować oceny cząstkowe. |
| `LIBRUS_READ_TIMETABLE` | `bool` | `true` | Czy analizować terminarz sprawdzianów i prac klasowych. |
| `LIBRUS_READ_SCHEDULE` | `bool` | `true` | Czy dołączać plan lekcji na kolejny dzień nauki. |
| `LIBRUS_ONE_SUMMARY_MESSAGE` | `bool` | `true` | Zbiorcze podsumowanie w jednym e-mailu (`true`) czy osobne maile (`false`). |
| `LIBRUS_STUDENT_REPORT_ENABLED` | `bool` | `true` | Czy włączyć raport motywacyjny dedykowany bezpośrednio dla dziecka. |
| `LIBRUS_STUDENT_REPORT_EMAIL` | `string` | `""` | Adres e-mail dziecka (jeśli ma otrzymywać własny raport motywacyjny). |
| `LIBRUS_STUDENT_REPORT_TEMPLATE` | `string` | `kids` | Szablon raportu motywacyjnego: `kids` (kl. 4–6), `teens` (kl. 7–8) lub `youth` (szkoła średnia). |

#### Wiele kont dzieci (Multi-account) przez ENV
W przypadku monitorowania więcej niż jednego dziecka, zamiast pojedynczych zmiennych `LIBRUS_LOGIN` / `LIBRUS_PASSWORD` przekaż całą listę jako tablicę JSON w zmiennej `LIBRUS_USERS`:
```bash
LIBRUS_USERS='[
  {
    "librus_login": "12345",
    "librus_password": "haslo_dziecka_1",
    "librus_login_name": "Kacper Kowalski",
    "notification_receivers": ["mama@gmail.com"]
  },
  {
    "librus_login": "67890",
    "librus_password": "haslo_dziecka_2",
    "librus_login_name": "Zosia Kowalska",
    "notification_receivers": ["mama@gmail.com", "tata@gmail.com"]
  }
]'
```

---

### 3.2. Wysyłka poczty e-mail (Mail)

| Zmienna ENV | Typ | Domyślnie | Opis |
| :--- | :--- | :--- | :--- |
| `LIBRUS_MAIL_LOGIN` | `string` | `""` | Adres e-mail nadawcy (np. konto Gmail lub konto SMTP). |
| `LIBRUS_MAIL_PASSWORD` | `string` | `""` | Hasło nadawcy (dla Gmaila: 16-znakowe Hasło Aplikacji). |
| `LIBRUS_MAIL_USE_GMAIL` | `bool` | `true` | `true` dla natywnej wysyłki przez Gmail (`yagmail`), `false` dla własnego SMTP. |
| `LIBRUS_SMTP_HOST` | `string` | `smtp.gmail.com` | Adres serwera SMTP (używane gdy `LIBRUS_MAIL_USE_GMAIL=false`). |
| `LIBRUS_SMTP_PORT` | `int` | `587` | Port serwera SMTP (zwykle `587` dla STARTTLS lub `465` dla SSL). |
| `LIBRUS_MAIL_OAUTH2_FILE` | `string` | `null` | Ścieżka do pliku poświadczeń Gmail OAuth2 (opcjonalnie). |

---

### 3.3. Interaktywny Panel WWW (Moduł 5)

| Zmienna ENV | Typ | Domyślnie | Opis |
| :--- | :--- | :--- | :--- |
| `LIBRUS_WEB_HOST` | `string` | `0.0.0.0` | Adres nasłuchiwania serwera WWW wewnątrz kontenera. |
| `LIBRUS_WEB_PORT` | `int` | `5000` | Port HTTP panelu WWW w kontenerze. |
| `LIBRUS_WEB_PASSWORD` | `string` | `null` | Hasło logowania do panelu webowego (jeśli puste, logowanie jest wyłączone). |
| `LIBRUS_WEB_SECRET_KEY` | `string` | `null` | Tajny klucz sesji Flask (losowy ciąg znaków). |
| `LIBRUS_WEB_MAX_LOGIN_ATTEMPTS` | `int` | `5` | Maksymalna liczba nieudanych prób logowania przed blokadą IP. |
| `LIBRUS_WEB_LOCKOUT_DURATION_S` | `int` | `900` | Czas trwania blokady IP po przekroczeniu limitu prób (w sekundach). |

---

### 3.4. Harmonogram zadań (Schedule)

| Zmienna ENV | Typ | Domyślnie | Opis |
| :--- | :--- | :--- | :--- |
| `LIBRUS_SCHEDULE_MODE` | `string` | `daily` | Tryb sprawdzania: `daily` (o stałej porze) lub `interval` (co zadany interwał). |
| `LIBRUS_SCHEDULE_TIME` | `string` | `16:00` | Godzina dziennego sprawdzania w trybie `daily` (format `HH:MM`). |
| `LIBRUS_SCHEDULE_DAYS` | `string` | `workdays` | Dni sprawdzania: `workdays` (pon–pt) lub `all` (cały tydzień). |
| `LIBRUS_SCHEDULE_INTERVAL_HOURS` | `int` | `1` | Odstęp w godzinach w trybie `interval`. |
| `LIBRUS_SCHEDULE_REPORTS` | `string` | `null` | Harmonogram automatycznych raportów w formacie JSON. |

---

### 3.5. Ustawienia demona i kolejki

| Zmienna ENV | Typ | Domyślnie | Opis |
| :--- | :--- | :--- | :--- |
| `TZ` | `string` | `Europe/Warsaw` | Strefa czasowa systemu (wymagana dla prawidłowych dat i godzin). |
| `LIBRUS_WAIT_TIME_S` | `int` | `3600` | Czas uśpienia pomiędzy kolejnymi obiegami pętli (w sekundach). |
| `LIBRUS_WORK_IN_LOOP` | `bool` | `true` | Czy demon ma pracować w ciągłej pętli (`true`), czy zakończyć się po 1 przebiegu (`false`). |
| `LIBRUS_STORAGE_DIR` | `string` | `storage` | Ścieżka katalogu bazy stanu wewnątrz kontenera (`/app/storage`). |
| `LIBRUS_DELAY_BETWEEN_USERS_S` | `int` | `10` | Odstęp anty-botowy w sekundach pomiędzy przetwarzaniem kolejnych kont dzieci. |
| `LIBRUS_LOGIN_RETRIES` | `int` | `2` | Liczba prób ponowienia logowania w razie chwilowego problemu sieciowego. |
| `LIBRUS_SEND_ERROR_NOTIFICATIONS` | `bool` | `true` | Czy wysyłać e-mail ostrzegawczy do rodzica w razie niepowodzenia logowania. |

---

## 4. Wdrożenie z Docker Compose (Zalecane)

Plik [docker/docker-compose.yml](docker-compose.yml) zawiera gotowe definicje wszystkich niezbędnych usług.

### Krok 1: Sklonowanie repozytorium i przejście do katalogu
```bash
git clone https://github.com/cackoarek/librus2mail.git
cd librus2mail
```

### Krok 2: Przygotowanie konfiguracji
Wybierz jedną z dwóch metod:

* **Opcja A (przez plik `.env`)**:
  ```bash
  cp docker/.env.example .env
  nano .env  # lub Twój ulubiony edytor
  ```

* **Opcja B (przez plik `config.yaml`)**:
  ```bash
  cp config-example.yaml config.yaml
  nano config.yaml
  ```

### Krok 3: Zbudowanie obrazu i uruchomienie usługi
Możesz uruchomić Docker Compose bezpośrednio z katalogu głównego projektu:
```bash
docker compose -f docker/docker-compose.yml up -d --build
```
*(lub przejść do katalogu `cd docker && docker compose up -d --build`)*

### Krok 4: Weryfikacja działania i logi na żywo
```bash
docker compose -f docker/docker-compose.yml logs -f collector
```

---

## 5. Wdrożenie czystym Docker CLI (`docker run`)

Jeśli nie korzystasz z Docker Compose, możesz uruchomić kontener bezpośrednio z katalogu głównego:

### 1. Zbudowanie obrazu
```bash
docker build -t librus2mail -f docker/Dockerfile .
```

### 2. Uruchomienie demona monitorującego:

**Wariant z plikiem `.env` (bez pliku YAML):**
```bash
docker run -d \
  --name librus2mail-collector \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/storage:/app/storage \
  librus2mail
```

**Wariant z montowanym plikiem `config.yaml`:**
```bash
docker run -d \
  --name librus2mail-collector \
  --restart unless-stopped \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v $(pwd)/storage:/app/storage \
  librus2mail
```

---

## 6. Raporty na żądanie z poziomu kontenera

Obraz kontenera umożliwia generowanie okresowych raportów postępów i raportów motywacyjnych na żądanie:

### Raport postępów dziecka (`librus-report`)
```bash
# 1. Symulacja (dry-run) - podgląd w terminalu bez wysyłania e-maila:
docker compose -f docker/docker-compose.yml run --rm report librus-report --dry-run

# 2. Rzeczywiste wygenerowanie i wysyłka e-maila do rodzica:
docker compose -f docker/docker-compose.yml run --rm report

# 3. Zapis raportu do lokalnego pliku HTML:
docker compose -f docker/docker-compose.yml run --rm report librus-report -o /app/storage/raport.html
```

### Raport motywacyjny dla ucznia (`librus-student-report`)
```bash
# 1. Symulacja dla wybranego szablonu (np. teens dla klas 7-8):
docker compose -f docker/docker-compose.yml run --rm student-report librus-student-report --dry-run --template teens

# 2. Rzeczywista wysyłka raportu motywacyjnego na skrzynkę ucznia:
docker compose -f docker/docker-compose.yml run --rm student-report
```

---

## 7. Interaktywny Panel WWW w kontenerze

W kontenerze możesz również uruchomić **nowoczesny panel webowy WWW (Moduł 5)** z dostępem w przeglądarce pod adresem `http://localhost:5000`:

### Uruchomienie panelu przez Docker Compose:
```bash
docker compose -f docker/docker-compose.yml --profile web up -d web
```

### Sprawdzenie statusu i logów:
```bash
docker compose -f docker/docker-compose.yml logs -f web
```

### Zatrzymanie panelu:
```bash
docker compose -f docker/docker-compose.yml --profile web down
```

> [!NOTE]
> Gdy uruchamiasz panel WWW po raz pierwszy bez pliku konfiguracji, wejdź w przeglądarce pod adres `http://localhost:5000/setup` – uruchomi się interaktywny kreator konfiguracji, który przetestuje połączenie ze szkołą i zapisze ustawienia.

---

## 8. Rozwiązywanie problemów i wskazówki (Troubleshooting)

### 🔴 1. Uprawnienia do katalogu `storage/`
Kontener działa jako użytkownik nieuprzywilejowany `librus` (`UID: 1000`). Jeśli na hoście katalog `storage/` ma uprawnienia roota, kontener nie będzie mógł zapisać plików stanu.
**Rozwiązanie:**
```bash
mkdir -p storage
chown -R 1000:1000 storage
```

### 🔴 2. Błąd: `config.yaml is a directory`
Jeśli w konfiguracji montujesz `config.yaml`, ale plik `config.yaml` nie istniał na hoście przed uruchomieniem kontenera, Docker automatycznie utworzy na hoście **katalog** o nazwie `config.yaml`.
**Rozwiązanie:**
Usuń powstały katalog i utwórz właściwy plik konfiguracyjny:
```bash
rm -rf config.yaml
cp config-example.yaml config.yaml  # lub touch config.yaml
```

### 🔴 3. Hasło do poczty Gmail (Błąd uwierzytelnienia SMTP)
Jeśli korzystasz z konta Gmail (`LIBRUS_MAIL_USE_GMAIL=true`):
* Nie używaj swojego głównego hasła do konta Google!
* Włącz weryfikację dwuetapową na koncie Google.
* Przejdź do: *Konto Google -> Bezpieczeństwo -> Hasła do aplikacji*, wygeneruj nowe 16-znakowe hasło i wklej je w zmiennej `LIBRUS_MAIL_PASSWORD` (ze spacjami lub bez).

### 🔴 4. Podgląd logów i ponowne uruchomienie
```bash
# Zobacz ostatnie 100 linii logów demona:
docker compose -f docker/docker-compose.yml logs --tail=100 -f collector

# Restart demona:
docker compose -f docker/docker-compose.yml restart collector

# Całkowite zatrzymanie:
docker compose -f docker/docker-compose.yml down
```
