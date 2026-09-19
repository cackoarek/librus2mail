<div align="center">

# 📬 Librus2mail

**Nowoczesny, bezobsługowy asystent e-mail i analityk postępów dla e-dziennika Librus Synergia**

[![CI Status](https://img.shields.io/github/actions/workflow/status/cackoarek/librus2mail/ci.yml?branch=main&label=CI&style=flat-square&logo=githubactions&logoColor=white)](https://github.com/cackoarek/librus2mail/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Code Style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg?style=flat-square&logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest%20(50%20passed)-success.svg?style=flat-square&logo=pytest&logoColor=white)](tests/)
[![Packaging: PEP 517/518](https://img.shields.io/badge/packaging-PEP%20517%2F518-00599C.svg?style=flat-square)](pyproject.toml)
[![Docker Ready](https://img.shields.io/badge/docker-ready-2496ED.svg?style=flat-square&logo=docker&logoColor=white)](Dockerfile)
[![systemd Supported](https://img.shields.io/badge/systemd-supported-lightgrey.svg?style=flat-square&logo=linux&logoColor=white)](deploy/systemd/)
[![Templates: Jinja2](https://img.shields.io/badge/templates-Jinja2-B41717.svg?style=flat-square&logo=jinja&logoColor=white)](src/librus2mail/templates/emails/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)
[![GitHub Pages](https://img.shields.io/badge/demo-GitHub%20Pages-0969da.svg?style=flat-square&logo=github&logoColor=white)](https://cackoarek.github.io/librus2mail/)

<p align="center">
  Automatyczne powiadomienia e-mail o nowych ocenach, wiadomościach i ogłoszeniach<br>
  oraz zaawansowany silnik analizy trendów, wag ocen i symulator świadectwa z wyróżnieniem.
</p>

[🚀 Szybki start](#instalacja) • [⚙️ Konfiguracja](#konfiguracja) • [🐳 Docker](#konteneryzacja-docker-i-docker-compose) • [📊 Raport postępów](#moduł-raportu-postępów-dziecka-progress_reportpy) • [❓ FAQ](#najczęstsze-pytania-i-rozwiązywanie-problemów-faq)

</div>

---

### O projekcie

**Librus2mail** to zautomatyzowana usługa działająca jako demon systemowy (lub kontener Docker), która loguje się na konto rodzica w portalu **Librus Synergia**, cyklicznie monitoruje skrzynkę wiadomości (`/wiadomosci`), tablicę ogłoszeń szkolnych (`/ogloszenia`) oraz oceny ucznia (`/przegladaj_oceny/uczen`), a po wykryciu nowych wpisów natychmiast wysyła przejrzyste i estetyczne powiadomienia HTML (oparte na Jinja2) na wskazane adresy e-mail (Gmail lub własny serwer SMTP).

#### 🌟 Kluczowe wyróżniki:
* 🔔 **Bieżące powiadomienia bez opóźnień**: Otrzymuj informacje o nowych wpisach ze szkoły bezpośrednio na swój telefon w skrzynce e-mail, bez konieczności ciągłego ręcznego odświeżania portalu czy korzystania z płatnych aplikacji mobilnych.
* 👨‍👩‍👧‍👦 **Obsługa wielu dzieci (Multi-account)**: Monitorowanie wielu kont w jednej instancji z możliwością przypisania różnych odbiorców e-mail dla każdego dziecka (np. mama, tata, dziadkowie).
* 📊 **Analityka i Symulator Czerwonego Paska (100% offline)**: Niezależny moduł analityczny przeliczający średnie ważone, wskaźniki trendu (↗, ↘, ➡), kalkulator szans/zagrożeń na granicy oceny, weryfikację warunków świadectwa z wyróżnieniem i pedagogiczną diagnozę stylu nauki (sprawdziany vs praca bieżąca).
* 🐳 **Proste wdrożenie DevOps**: Gotowy obraz Docker, konfiguracja Docker Compose oraz produkcyjne jednostki `systemd` (usługa + timer) dla serwerów Linux, Raspberry Pi lub domowych serwerów NAS.
* 🛡️ **Prywatność i bezpieczeństwo**: Żadne dane uwierzytelniające ani oceny dzieci nie trafiają do zewnętrznych chmur – całość działa lokalnie na Twojej własnej maszynie.

---

### 📄 Przykładowe raporty (na żywo)
	
<div align="center">
Poniżej możesz zobaczyć jak wyglądają e-maile generowane przez projekt — bez instalacji czegokolwiek:

| Raport | Opis | Link |
|:---|:---|:---|
| 📬 **Powiadomienie e-mail** | Zbiorczy e-mail z ocenami, wiadomościami i ogłoszeniami | [→ Otwórz](https://cackoarek.github.io/librus2mail/latest/powiadomienie_collector.html) |
| 📊 **Raport postępów ucznia** | Analiza trendów, średnie ważone, symulator czerwonego paska | [→ Otwórz](https://cackoarek.github.io/librus2mail/latest/raport_8979296.html) |
| 📁 **Wszystkie wersje** | Archiwum raportów dla każdej wydanej wersji | [→ Przeglądaj](https://cackoarek.github.io/librus2mail/) |

> Raporty są automatycznie generowane i publikowane przy każdym wydaniu nowej wersji.

</div>

---

## Spis treści
1. [Główne możliwości](#główne-możliwości)
2. [Wymagania](#wymagania)
3. [Instalacja](#instalacja)
4. [Konfiguracja](#konfiguracja)
   - [Struktura pliku config.yaml](#struktura-pliku-configyaml)
   - [Konfiguracja kont Librus (librus_users)](#konfiguracja-kont-librus-librus_users)
   - [Konfiguracja wysyłki e-mail (mail)](#konfiguracja-wysyłki-e-mail-mail)
5. [Architektura 3 modułów i główny orkiestrator](#architektura-3-modułów-i-główny-orkiestrator)
6. [Usługa monitoringu i orkiestrator (collect_and_notify.py / librus_collector.py)](#usługa-monitoringu-i-zbierania-danych-collect_and_notifypy)
   - [Uruchomienie standardowe (pełny cykl demona)](#uruchomienie-standardowe-pełny-cykl-demona)
   - [Elastyczne tryby modułowe (przełączniki orkiestratora)](#elastyczne-tryby-modułowe-przełączniki-orkiestratora)
   - [Tryb symulacji i podglądu powiadomień](#tryb-symulacji-i-podglądu-powiadomień-bez-wysyłania-e-mail)
   - [Uruchomienie w tle (nohup / cron)](#uruchomienie-w-tle-nohup--cron)
7. [Moduł bieżących powiadomień (updates_notifier.py)](#moduł-bieżących-powiadomień-updates_notifierpy)
   - [Mechanizm znaczników czasu (watermarks) i uruchomień nieregularnych](#mechanizm-znaczników-czasu-watermarks-i-uruchomień-nieregularnych)
   - [Parametry CLI i przykłady użycia](#parametry-cli-i-przykłady-użycia)
8. [Moduł raportu postępów dziecka (progress_report.py)](#moduł-raportu-postępów-dziecka-progress_reportpy)
   - [Możliwości analizy](#możliwości-analizy)
   - [Sposób użycia i parametry CLI](#sposób-użycia-i-parametry-cli)
9. [Wdrożenie produkcyjne i konteneryzacja (Docker & systemd)](#wdrożenie-produkcyjne-i-konteneryzacja-docker--systemd)
   - [Konteneryzacja Docker i Docker Compose](#konteneryzacja-docker-i-docker-compose)
   - [Wdrożenie systemd (Linux / Raspberry Pi / VPS)](#wdrożenie-systemd-linux--raspberry-pi--vps)
10. [Szablony wiadomości e-mail (Jinja2)](#szablony-wiadomości-e-mail-jinja2)
11. [Architektura projektu](#architektura-projektu)
12. [Testy i jakość kodu](#testy-i-jakość-kodu)
13. [Najczęstsze pytania i rozwiązywanie problemów (FAQ)](#najczęstsze-pytania-i-rozwiązywanie-problemów-faq)
14. [Bezpieczeństwo](#bezpieczeństwo)
15. [Podziękowania](#podziękowania)
16. [Licencja](#licencja)

---

## Główne możliwości

* **Wsparcie dla wielu kont**: Możliwość jednoczesnego monitorowania kont dla kilkorga dzieci (każde konto może mieć przypisanych innych odbiorców powiadomień).
* **Nowoczesny przepływ OAuth**: Zgodność z aktualnym procesem autoryzacji Librus Synergia (uwzględniającym przekierowania `portalRodzina`, pominięcie ekranu 2FA oraz grant autoryzacyjny).
* **Obsługa wiadomości, ogłoszeń i ocen**: Monitorowanie wiadomości prywatnych od nauczycieli, ogólnych ogłoszeń szkolnych oraz nowo wystawionych ocen (cząstkowych, semestralnych i rocznych).
* **Elastyczna wysyłka e-mail**:
  * **Gmail**: zoptymalizowana obsługa przez bibliotekę `yagmail` (wymagane hasło aplikacji Google).
  * **SMTP**: standardowy protokół SMTP z szyfrowaniem STARTTLS (działa z dowolnym serwerem pocztowym: hostingodawcy, OVH, Cyberfolks, WP, Onet itp.).
* **Tryb pierwszego przebiegu (`do_not_send_first_parse`)**: Przy pierwszym uruchomieniu skrypt indeksuje aktualne wiadomości, ogłoszenia i oceny jako bazę i nie wysyła spamu ze wszystkimi historycznymi wpisami – kolejne uruchomienia wysyłają powiadomienia wyłącznie o nowych wpisach.
* **Nowoczesne szablony Jinja2**: Wszystkie e-maile generowane są z responsywnych szablonów HTML (`src/librus2mail/templates/emails/`), łatwych w dostosowywaniu stylów i kolorów.
* **Automatyczne alerty o awariach i błędach**: W razie braku połączenia do Librusa, problemów z sesją/autoryzacją lub błędu parsowania danych (np. po zmianie wyglądu dziennika), skrypt natychmiast wysyła e-mail z diagnozą i zalecanymi działaniami. Wbudowany mechanizm throttling / cooldown zapobiega zalewaniu skrzynki powtarzającymi się wiadomościami.
* **Dedykowany moduł analizy postępów dziecka (`progress_report.py`)**: Niezależny skrypt analityczny przeliczający średnie ważone przedmiotowe i ogólne, wskaźniki trendu (↗, ↘, ➡), sugerowane oceny roczne, rozkład ocen (histogram) oraz automatyczne wnioski rodzicielskie (sukcesy, zagrożenia, nieprzygotowania). Raport wysyłany jest w postaci nowoczesnego dashboardu HTML.

---

## Wymagania

* **Python 3.10+** (projekt wykorzystuje unie typów `X | Y` oraz walrus operator `:=`).
* Dostęp do internetu umożliwiający połączenie z `api.librus.pl` oraz `synergia.librus.pl`.
* Skrzynka pocztowa (Gmail lub dowolny serwer SMTP) do wysyłania powiadomień.

---

## Instalacja

Zaleca się instalację w dedykowanym wirtualnym środowisku (`venv`):

```bash
# 1. Klonowanie repozytorium (jeśli jeszcze nie sklonowano)
git clone <URL_REPOZYTORIUM>
cd librus2mail

# 2. Utworzenie środowiska wirtualnego
python3 -m venv venv

# 3. Aktywacja środowiska
source venv/bin/activate

# 4. Aktualizacja menedżera pip
pip install --upgrade pip

# 5. Instalacja projektu:
# Wariant A (zalecany): Nowoczesna instalacja standardem pyproject.toml (PEP 517/518):
pip install -e .

# Opcjonalnie: instalacja narzędzi deweloperskich (pytest, ruff):
pip install -e ".[dev]"

# Wariant B: Tradycyjna instalacja z pliku requirements.txt:
pip install -r requirements.txt
```

---

## Konfiguracja

Wszystkie ustawienia aplikacji znajdują się w pliku `config.yaml`. Na start skopiuj wzorcowy plik konfiguracyjny:

```bash
cp config.example.yaml config.yaml
# albo:
cp config.yaml.example config.yaml
```

Następnie otwórz `config.yaml` w edytorze i uzupełnij swoje dane.

### Struktura pliku `config.yaml`

```yaml
librus_users:
  - librus_login_name: "Konto Jasia"
    librus_login: "1234567"
    librus_password: "twoje_haslo_librus"
    read_messages: true
    read_grades: true
    one_summary_message: false
    do_not_send_first_parse: true
    notification_receivers:
      - "mama@example.com"
      - "tata@example.com"

wait_time_s: 3600
work-in-loop: true  # true: pętla z oczekiwaniem wait_time_s (domyślnie), false: pojedynczy przebieg (np. pod crona)
storage_dir: "storage"  # (opcjonalnie) katalog zapisu plików stanu JSON (domyślnie: storage)

mail:
  login: "twoj_email_powiadomien@gmail.com"
  password: "twoje_haslo_aplikacji"
  use_gmail: true
  non_gmail_settings:
    port: 587
    smtp_host: "smtp.twoj-hosting.pl"
```

### Konfiguracja kont Librus (`librus_users`)

Każdy element listy `librus_users` reprezentuje jedno konto w e-dzienniku:

| Parametr | Typ | Opis |
| :--- | :--- | :--- |
| `librus_login_name` | `string` | Przyjazna nazwa (np. imię dziecka). Ułatwia identyfikację konta w tytułach i treści e-maili. |
| `librus_login` | `string` | Login rodzica w Librus Synergia (zazwyczaj ciąg cyfr). |
| `librus_password` | `string` | Hasło do konta rodzica w Librus Synergia. |
| `read_messages` | `bool` | Czy skrypt ma wchodzić w szczegóły wiadomości i pobierać jej treść (`true`/`false`). **Domyślnie `true`**.<br>**UWAGA:** Wejście w wiadomość oznacza ją w portalu Librus jako przeczytaną przez rodzica. Jeśli wolisz otrzymywać powiadomienie wyłącznie o tytule i nadawcy (bez oznaczania na portalu), ustaw `false`. |
| `read_grades` | `bool` | Czy włączyć sprawdzanie i zbieranie ocen dla tego konta (`true`/`false`). **Domyślnie `true`**. |
| `one_summary_message` | `bool` | Jeśli `true`, zamiast wysyłać osobne maile dla wiadomości, ogłoszeń i ocen, wyśle **jeden zbiorczy e-mail** podsumowujący wszystkie nowości z danego cyklu. Domyślnie `false`. |
| `do_not_send_first_parse` | `bool` | Jeśli `true`, podczas pierwszego cyklu po uruchomieniu wiadomości zostaną tylko zaindeksowane, bez wysyłania e-maili o historii skrzynki. |
| `send_error_notifications` | `bool` | Opcjonalne włączenie/wyłączenie wysyłania maili o błędach dla danego konta (domyślnie: `true`). |
| `notification_receivers` | `list` | Lista adresów e-mail odbiorców, którzy mają otrzymać powiadomienie dla tego konta. |

### Parametry globalne

* `delay_between_users_s` (`int` / `float`): Czas oczekiwania w sekundach pomiędzy pobieraniem danych dla kolejnych kont dzieci (domyślnie: `3` sekundy). Zapobiega problemom z logowaniem i mechanizmami anty-botowymi / 2FA na serwerach Librusa przy odpytywaniu wielu kont z tego samego adresu IP.
* `wait_time_s` (`int`): Czas oczekiwania w sekundach pomiędzy kolejnymi cyklami sprawdzania e-dziennika (zalecane: minimum `3600`–`7200` sekund (1-2h), aby nie obciążać serwera i uniknąć blokad anty-botowych). Wykorzystywane, gdy `work-in-loop: true`.
* `work-in-loop` (`bool`): Tryb pracy:
  * `true` (domyślnie) – skrypt działa nieprzerwanie w pętli i po sprawdzeniu kont odczekuje `wait_time_s` sekund.
  * `false` – skrypt wykonuje dokładnie jeden pełny przebieg (sprawdza konta, wysyła e-maile, zapisuje stan do pliku) i natychmiast kończy pracę. Idealne do uruchamiania przez systemowy harmonogram zadań `cron`.
* `storage_dir` (`string`): Ścieżka do katalogu, w którym automatycznie zapisywany jest trwały stan aplikacji oraz pełna historia ocen w formacie JSON (np. `storage/8979295.json`). Domyślnie: `"storage"`.
* `send_error_notifications` (`bool`): Czy wysyłać e-mail z alertem o problemach (brak połączenia internetowego, awaria Librusa, wygaśnięcie sesji / wymóg zalogowania przez www, błąd parsowania HTML). Domyślnie `true`.
* `error_cooldown_s` (`int`): Minimalny czas w sekundach pomiędzy kolejnymi powiadomieniami o tym samym błędzie (domyślnie: `3600` sekund = 1h). Zapobiega zalewaniu skrzynki podczas trwającej awarii serwera. Po ustąpieniu problemu licznik resetuje się automatycznie.

### Konfiguracja wysyłki e-mail (`mail`)

* `login` (`string`): Adres e-mail nadawcy, z którego wysyłane będą powiadomienia.
* `password` (`string`): Hasło do konta pocztowego lub dedykowane hasło aplikacji.
* `use_gmail` (`bool`):
  * `true` – użycie biblioteki `yagmail` dedykowanej dla Google Mail.
  * `false` – użycie standardowego serwera SMTP określonego w `non_gmail_settings`.
* `non_gmail_settings`:
  * `smtp_host` (`string`): Adres serwera SMTP (np. `smtp.ct8.pl`, `poczta.o2.pl`, `smtp.mailgun.org`).
  * `port` (`int`): Port serwera pocztowego (standardowo `587` dla połączenia STARTTLS).

> [!TIP]
> **Wskazówka dla Gmaila:** Google wymaga włączenia weryfikacji dwuetapowej (2FA) i wygenerowania dedykowanego **hasła aplikacji** (App Password) w ustawieniach konta Google (`Konto Google -> Bezpieczeństwo -> Hasła do aplikacji`). Nie podawaj swojego głównego hasła do konta Google!

---

## Architektura 3 modułów i główny orkiestrator

System **Librus2mail** składa się z 3 niezależnych, wyspecjalizowanych modułów spiętych przez główny orkiestrator:

1. **Moduł 1: Collector (`librus_collector.py` / `librus-collector`)**:
   * Odpowiada wyłącznie za autoryzację OAuth w portalu Librus Synergia oraz pobieranie wiadomości, ogłoszeń i ocen z zachowaniem opóźnień anty-botowych.
   * Zapisuje stan i historię w lokalnej bazie JSON (`storage/`).
2. **Moduł 2: Updates Notifier (`updates_notifier.py` / `librus-notifier`)**:
   * Odpowiada za detekcję nowych wpisów (według stanu lub zadanego okna czasowego `--days`/`--hours`).
   * Generuje szablony HTML i wysyła powiadomienia e-mail (Gmail/SMTP) lub eksportuje do samodzielnego pliku HTML (`-o`). Działa w 100% offline.
3. **Moduł 3: Progress Report (`progress_report.py` / `librus-report`)**:
   * Niezależny silnik analityczny generujący okresowe podsumowania postępów (średnie ważone, wskaźniki PoP, szanse na czerwony pasek, styl uczenia się).
4. **Zintegrowany potok i orkiestrator (`collect_and_notify.py` / `librus-collect-and-notify`)**:
   * Spina pełny cykl demona (`Collector -> Notifier -> sleep`) lub pozwala wywołać wybrany moduł poleceniami: `--collect-only`, `--notify-only`, `--report`.

---

## Usługa monitoringu i zbierania danych (collect_and_notify.py)

### Uruchomienie standardowe (pełny cykl demona)

Upewnij się, że wirtualne środowisko jest aktywne:

```bash
source venv/bin/activate

# Wariant 1: Zintegrowany potok (pełny cykl Collector -> Notifier w pętli):
python collect_and_notify.py
# lub polecenia konsolowe:
librus-collect-and-notify
# lub:
librus2mail

# Wariant 2: Dedykowane polecenie modułu kolektora (tylko pobieranie):
python librus_collector.py
# lub:
librus-collector

# Wariant 3: Samodzielny moduł bieżących powiadomień (100% offline):
python updates_notifier.py
# lub:
librus-notifier
```

### Elastyczne tryby modułowe (przełączniki orkiestratora)

```bash
# 1. Tylko pobranie świeżych danych ze szkoły do storage (bez wysyłki maili):
python collect_and_notify.py --collect-only

# 2. Tylko wygenerowanie bieżących powiadomień z bazy (100% offline):
python collect_and_notify.py --notify-only --days 7 --dry-run

# 3. Uruchomienie modułu raportu postępów (Moduł 3):
python collect_and_notify.py --report -o raport.html
```

### Tryb symulacji i podglądu powiadomień (bez wysyłania e-mail)

Kolektor wspiera tryb symulacji i filtrowania po okresie czasowym, umożliwiający sprawdzenie wpisów za wybrany czas (dni/godziny), weryfikację w konsoli lub wyeksportowanie powiadomienia e-mail do pliku HTML bez wysyłania maili i bez modyfikacji bazy `storage/`:

```bash
# 1. Podgląd w konsoli wpisów z ostatnich 7 dni (--dry-run):
librus-collector --days 7 --dry-run

# 2. Zapisanie powiadomienia e-mail jako samodzielny plik HTML do weryfikacji wyglądu (-o / --save-html):
librus-collector --days 3 -o podglad_powiadomienia.html

# 3. Symulacja w trybie offline ze wskazanego katalogu bazy (np. przykładowe dane testowe):
librus-collector --offline -s examples/storage --days 14 -o examples/reports/powiadomienie_collector.html

# 4. Zawężenie sprawdzania do konkretnego konta dziecka:
librus-collector -u 8979296 --days 7 --dry-run
```

| Parametr | Krótka flaga | Opis |
| :--- | :--- | :--- |
| `--config <plik>` | `-c` | Ścieżka do pliku konfiguracyjnego YAML (domyślnie: `config.yaml`). |
| `--storage-dir <kat>` | `-s` | Ścieżka do katalogu pamięci stanu (nadpisuje konfigurację). |
| `--user <login/nazwa>` | `-u` | Filtruje wykonanie tylko do wskazanego konta ucznia. |
| `--days <N>` | `-d` | Uznaje wpisy z ostatnich `N` dni za nowe (automatycznie wyłącza pętlę demona). |
| `--hours <N>` | | Uznaje wpisy z ostatnich `N` godzin za nowe (np. `--hours 12`). |
| `--dry-run` | | Wyświetla podsumowanie wpisów w terminalu; nie wysyła maili ani nie modyfikuje `storage/`. |
| `--save-html <ścieżka>` | `-o` | Zapisuje powiadomienie jako samodzielny plik HTML do podglądu w przeglądarce. |
| `--offline` | | Odczytuje dane wyłącznie z lokalnego katalogu `storage/` bez łączenia z Librusem. |
| `--once`, `--no-loop` | | Wymusza pojedyncze wykonanie i natychmiastowe zakończenie (nadpisuje `work-in-loop: true`). |
| `--loop` | | Wymusza działanie w nieskończonej pętli z interwałem `wait_time_s` (nadpisuje `work-in-loop: false`). |

### Uruchomienie w tle (nohup / cron)

#### Wariant A: `nohup` (proste uruchomienie w tle)
```bash
nohup librus-collector >/dev/null 2>&1 &
```

> [!TIP]
> Do stałego wdrożenia produkcyjnego na serwerach Linux (VPS, Raspberry Pi, serwery domowe) zaleca się skorzystanie ze środowiska **Docker / Docker Compose** lub gotowych usług **systemd** z automatycznym wznawianiem po awarii. Szczegółowe instrukcje znajdziesz w sekcji [Wdrożenie produkcyjne i konteneryzacja (Docker & systemd)](#wdrożenie-produkcyjne-i-konteneryzacja-docker--systemd).

#### Wariant B: Harmonogram zadań `cron` (z `work-in-loop: false` lub `--once`)

Jeśli wolisz, aby skrypt nie działał jako ciągły proces w tle, lecz był wywoływany cyklicznie przez systemowego crona:
1. W pliku `config.yaml` ustaw:
   ```yaml
   work-in-loop: false
   ```
2. Dodaj wpis do tabeli zadań użytkownika poleceniem `crontab -e`:

   * **Uruchamianie co 15 minut:**
     ```cron
     */15 * * * * cd /sciezka/do/librus2mail && venv/bin/python librus_collector.py >> librus.log 2>&1
     ```

   * **Uruchamianie raz dziennie o 16:30 (codziennie):**
     ```cron
     30 16 * * * cd /sciezka/do/librus2mail && venv/bin/python librus_collector.py >> librus.log 2>&1
     ```

   * **Uruchamianie o 16:30 tylko w dni robocze/szkolne (od poniedziałku do piątku):**
     ```cron
     30 16 * * 1-5 cd /sciezka/do/librus2mail && venv/bin/python librus_collector.py >> librus.log 2>&1
     ```

> [!TIP]
> Po każdym cyklu skrypt automatycznie zapisuje stan i historię ocen do katalogu `storage/`, dzięki czemu kolejne uruchomienie wyśle powiadomienia tylko o faktycznie nowych wpisach.

---

## Moduł bieżących powiadomień (updates_notifier.py)

Dedykowany moduł powiadomień **`updates_notifier.py`** (`librus-notifier`) odpowiada za offline'ową analizę danych zebranych w `storage/` i wysyłkę wiadomości e-mail do rodziców lub eksport do pliku HTML / podgląd w terminalu.

### Mechanizm znaczników czasu (watermarks) i uruchomień nieregularnych

W pliku pamięci stanu ucznia (`storage/<login>.json`) utrzymywane są dwa kluczowe znaczniki czasowe:
* **`last_collect_time`**: data ostatniej pomyślnej synchronizacji z portalem Librus (zapisywana przez `librus_collector.py`).
* **`last_notify_time`** (alias **`last_update_create`**): data ostatniego faktycznie dostarczonego powiadomienia e-mail do rodzica (zapisywana przez `updates_notifier.py`).

Dzięki temu przy nieregularnym wywoływaniu powiadomień (np. z crona raz dziennie, podczas gdy kolektor zbiera dane co 30 minut):
1. **Tryb automatyczny (bez parametrów `--days` i `--hours`)**: Skrypt pobiera `last_notify_time` ze storage i filtruje wpisy dodane lub opublikowane po tej dacie. Rodzic zawsze otrzymuje dokładnie to, co pojawiło się od poprzedniego e-maila, bez dubli i bez pomijania wpisów.
2. **Ochrona podglądu**: Uruchomienie z `--dry-run` lub `-o / --save-html` **nie przesuwa znacznika** `last_notify_time`. Możesz weryfikować wygląd maila dowolną liczbę razy bez obawy o pominięcie powiadomień.
3. **Tryb jawny (`--days N` lub `--hours N`)**: Użytkownik wymusza sztywne okno czasowe (np. ostatnie 3 dni).

### Parametry CLI i przykłady użycia

```bash
# 1. Nieregularne powiadomienie e-mail (od ostatniego powiadomienia zapisanego w storage):
librus-notifier
# lub:
venv/bin/python updates_notifier.py

# 2. Podgląd w konsoli nowości z ostatnich 7 dni (--dry-run):
librus-notifier --days 7 --dry-run

# 3. Zapisanie powiadomienia jako plik HTML do weryfikacji wyglądu (-o / --save-html):
librus-notifier --days 3 -o podglad_powiadomienia.html

# 4. Sprawdzenie powiadomień ze wskazanego katalogu testowego:
librus-notifier -s examples/storage --days 14 -o examples/reports/powiadomienie.html
```

| Parametr | Krótka flaga | Opis |
| :--- | :--- | :--- |
| `--config <plik>` | `-c` | Ścieżka do pliku konfiguracyjnego YAML (domyślnie: `config.yaml`). |
| `--storage-dir <kat>` | `-s` | Ścieżka do katalogu pamięci stanu (nadpisuje konfigurację). |
| `--user <login/nazwa>` | `-u` | Filtruje wykonanie tylko do wskazanego konta ucznia. |
| `--days <N>` | `-d` | Uznaje wpisy z ostatnich `N` dni za nowe (nadpisuje znacznik `last_notify_time`). |
| `--hours <N>` | | Uznaje wpisy z ostatnich `N` godzin za nowe (np. `--hours 12`). |
| `--dry-run` | | Podgląd w konsoli bez wysyłania maili i bez aktualizacji `last_notify_time`. |
| `--save-html <ścieżka>` | `-o` | Zapisuje powiadomienie jako samodzielny plik HTML do podglądu w przeglądarce. |

---

## Moduł raportu postępów dziecka (progress_report.py)

Dedykowany moduł analityczny **`progress_report.py`** działa w **100% offline** na podstawie danych zebranych wcześniej przez `librus_collector.py` i zapisanych w katalogu `storage/`.

Dzięki takiemu podziałowi:
* ⚡ **Błyskawiczne działanie**: Raport generuje się w ułamku sekundy (brak konieczności łączenia się z siecią, logowania i czekania na opóźnienia anty-botowe).
* 🛡️ **Bezpieczeństwo konta**: Brak zbędnych sesji i odpytywania Librusa przy każdym wygenerowaniu raportu.
* 📶 **Dostępność**: Raport można wygenerować nawet wtedy, gdy portal Librusa ma chwilową przerwę techniczną.

### Możliwości analizy:
* **Średnie ważone**: Wyliczanie precyzyjnej średniej ważonej dla każdego przedmiotu oraz średniej ogólnej ucznia w oparciu o oficjalne wagi ocen z Librusa (uwzględniając modyfikatory `+` jako +0.5, `-` jako -0.25).
* **📈 Analiza wsteczna i porównanie z poprzednim okresem (Wskaźnik formy ucznia)**:
  * Automatyczne zestawienie bieżącego okresu (np. ostatnie 7 dni lub od ostatniego raportu) z **identycznym wcześniejszym oknem czasowym** (np. wcześniejsze 7 dni).
  * Wyliczanie dynamiki ocen: zmiana średniej okresowej ($\Delta$), przyrost ocen bdb/celujących (5–6), spadek lub wzrost ocen słabych (1–2), wpływ na średnią roczną ucznia oraz bilans nieprzygotowań.
  * Natychmiastowa diagnoza formy dla rodzica: **Wyraźny progres 🚀**, **Lekka poprawa ↗️**, **Stabilnie ➡️** lub **Ostrzeżenie o spadku wyników ⚠️** wraz ze wskazaniem przedmiotów o największym skoku i spadku.
* **Wskaźnik trendu wyników**: Analiza kierunku zmian średniej z danego przedmiotu w porównaniu z poprzednimi okresami:
  * ↗ *(np. +0.40)* – widoczna poprawa wyników,
  * ↘ *(np. -0.35)* – spadek średniej,
  * ➡ *(stabilnie)* – równe, powtarzalne oceny,
  * ✨ *(nowy wpis)* – pierwsza ocena z danego przedmiotu.
* **🏅 Symulator Czerwonego Paska (Świadectwo z wyróżnieniem)**:
  * Weryfikacja warunku średniej końcowej $\ge 4.75$ i braku ocen niedostatecznych.
  * Wyliczanie brakującego dystansu punktowego oraz wskazywanie kluczowych przedmiotów o najkrótszej drodze do podniesienia oceny.
* **🎯 Analiza „Na granicy oceny” (Kalkulator szans i zagrożeń)**:
  * **Szanse na wyższą ocenę**: Wykrywa przedmioty, gdzie uczeń traci $\le 0.25$ pkt do wyższego stopnia i wylicza, jaka ocena ze sprawdzianu (waga 2) lub kartkówki (waga 1) wystarczy, by przeskoczyć próg!
  * **Zagrożenia spadkiem**: Wskazuje przedmioty z małym marginesem bezpieczeństwa ($\le 0.12$ nad progiem), gdzie pojedyncza ocena niedostateczna grozi obniżeniem prognozy.
* **🔍 Styl nauki: Sprawdziany vs Bieżąca praca**:
  * Zestawienie średniej ze sprawdzianów i prac klasowych (wagi 2–3) ze średnią z kartkówek, odpowiedzi i zadań domowych (waga 1).
  * Diagnoza pedagogiczna: pozwala rodzicowi ocenić, czy uczeń ma trudności z powtórkami dużych partii materiału przed testami, czy z bieżącą dyscypliną i systematycznością.
* **⚖️ Wpływ wag ocen & Stabilność wyników (Sinusoida)**:
  * **Efekt wagowy**: Porównanie średniej ważonej z arytmetyczną (czy sprawdziany o dużej wadze ciągną wynik w górę, czy zaniżają średnią).
  * **Stabilność ocen**: Wykrywanie przedmiotów o stałych, powtarzalnych ocenach oraz przedmiotów o wysokich wahaniach (np. przeplatanka ocen 1 i 5).
* **⏱️ Analiza „Cichych przedmiotów”**:
  * Wczesne ostrzeżenie o przedmiotach, z których uczeń nie otrzymał żadnej oceny od ponad 30 dni (ryzyko kumulacji sprawdzianów przed końcem semestru).
* **Inteligentne alerty i wnioski rodzicielskie**:
  * 🌟 **Sukcesy**: Przedmioty ze średnią wyróżniającą, bardzo dobre oceny ze sprawdzianów o wysokich wagach, szanse na wyższe stopnie.
  * ⚠️ **Obszary do poprawy**: Ostrzeżenia o zagrożeniu oceną niedostateczną (< 2.0), niskie średnie (< 3.0), słabe oceny ze sprawdzianów o dużej wadze z sugestią poprawy, sumaryczna liczba nieprzygotowań i braków zadań domowych (`np`, `bz`).
* **Rozkład ocen (histogram)**: Wizualne zestawienie liczby poszczególnych stopni (1–6) w minionym okresie oraz w całym roku szkolnym.
* **📖 Przewodnik rodzica (Jak rozumieć wskaźniki)**: Zrozumiała legenda wyjaśniająca progi ocen, trendy, wagi oraz interpretację poszczególnych metryk dołączona bezpośrednio do każdego raportu (w e-mailu i w konsoli).
* **Nowoczesny dashboard e-mail**: Estetyczny, responsywny szablon HTML z kafelkami KPI, kolorowymi plakietkami ocen (badges), paskiem postępu do czerwonego paska, tabelami i szczegółami nowo wystawionych ocen.

### Sposób użycia i parametry CLI:

```bash
# 1. Wygenerowanie i wysłanie raportu postępów (okres od ostatniego raportu lub domyślne 7 dni)
librus-report
# lub:
venv/bin/python progress_report.py

# 2. Tryb symulacji (--dry-run) - pełna analiza i wydruk tabeli w terminalu bez wysyłania e-maila
librus-report --dry-run
# lub:
venv/bin/python progress_report.py --dry-run

# 3. Zapisanie raportu jako plik HTML do podglądu w przeglądarce (--save-html / -o)
librus-report --save-html raport.html
# lub dla konkretnego dziecka:
venv/bin/python progress_report.py -u 1234567 -o podglad.html

# 4. Wymuszenie analizy za określony czas, np. ostatnie 14 lub 30 dni (--days N)
librus-report --days 14

# 5. Zawężenie do konkretnego konta dziecka (--user)
librus-report --user 1234567
# albo po nazwie:
librus-report --user "Kasia"

# 6. Opcjonalne wymuszenie pobrania świeżych ocen przez sieć (--fetch)
librus-report --fetch

# 7. Wymuszenie wysyłki raportu nawet gdy w badanym okresie uczeń nie dostał nowych ocen (--force)
librus-report --force
```

| Parametr | Krótka flaga | Opis |
| :--- | :--- | :--- |
| `--config <plik>` | `-c` | Ścieżka do pliku konfiguracyjnego (domyślnie: `config.yaml`). |
| `--storage-dir <kat>` | `-s` | Ścieżka do katalogu bazy danych `storage` (nadpisuje ustawienie z `config.yaml`). |
| `--user <login/nazwa>` | `-u` | Filtruje wykonanie raportu tylko do wskazanego konta dziecka. |
| `--days <N>` | `-d` | Analizuje ostatnie `N` dni wstecz (zamiast daty poprzedniego raportu). |
| `--dry-run` | | Generuje analizę i wyświetla raport w terminalu; nie wysyła maila ani nie aktualizuje daty. |
| `--save-html <plik/katalog>` | `-o` | Zapisuje raport jako samodzielny plik HTML do podglądu w przeglądarce (pomija wysyłkę e-mail i nie aktualizuje daty raportu). |
| `--fetch` | | Opcjonalnie łączy się z Librusem i pobiera oceny przez sieć (domyślnie działa w 100% offline ze `storage/`). |
| `--force` | `-f` | Wysyła raport nawet jeśli w minionym okresie uczeń nie otrzymał żadnych nowych ocen. |

> [!TIP]
> Pełny podręcznik wszystkich możliwych wywołań, zaawansowanych kombinacji flag oraz przykładów dla każdego ze skryptów znajdziesz w dedykowanym dokumencie: **[useful-scripts.md](useful-scripts.md)**.

### Konfiguracja:
Skrypt `progress_report.py` korzysta z głównego pliku `config.yaml` (wykorzystuje zdefiniowane w nim konta dzieci, listę odbiorców oraz ustawienia skrzynki pocztowej `mail`), dzięki czemu nie wymaga żadnej osobnej konfiguracji. Okres analizy przy pierwszym uruchomieniu to domyślnie 7 dni (lub wartość przekazana parametrem `--days`).

### Harmonogram cron dla raportów:

Dzięki wydzieleniu skryptu do osobnego pliku, możesz w prosty i elastyczny sposób skonfigurować w cronie (`crontab -e`) wysyłkę raportu w dowolnym, dogodnym dla Ciebie momencie:

* **Raz w tygodniu w każdy piątek o 17:00 (podsumowanie całego tygodnia):**
  ```cron
  0 17 * * 5 cd /sciezka/do/librus2mail && venv/bin/python progress_report.py >> librus.log 2>&1
  ```

* **Raz w tygodniu w niedzielę o 19:00 (przygotowanie do nadchodzącego tygodnia):**
  ```cron
  0 19 * * 0 cd /sciezka/do/librus2mail && venv/bin/python progress_report.py >> librus.log 2>&1
  ```

* **W ostatni dzień każdego miesiąca o 18:00 (podsumowanie miesięczne za ostatnie 30 dni):**
  ```cron
  0 18 28-31 * * [ $(date -d tomorrow +\%d) -eq 1 ] && cd /sciezka/do/librus2mail && venv/bin/python progress_report.py --days 30 >> librus.log 2>&1
  ```

---

## Wdrożenie produkcyjne i konteneryzacja (Docker & systemd)

Dla środowisk produkcyjnych (serwer VPS, Raspberry Pi, serwer domowy / NAS) zaleca się uruchomienie usługi w kontenerze Docker lub jako demona `systemd` z automatycznym restartem po awarii.

### Konteneryzacja Docker i Docker Compose

Repozytorium zawiera gotowy [Dockerfile](file:///home/acacko/PycharmProjects/librus2mail/Dockerfile) oparty na lekkim obrazie `python:3.10-slim`.
* Działa w bezpiecznym trybie na nieuprzywilejowanym użytkowniku `librus` (UID 1000).
* Posiada skonfigurowaną polską strefę czasową (`TZ=Europe/Warsaw`) dla właściwego formatowania dat ocen i alertów.
* Obsługuje montowanie konfiguracji `config.yaml` w trybie tylko do odczytu (`:ro`) oraz wolumen danych dla trwałego zapisu `storage/`.

#### Szybki start z Docker Compose:

1. **Przygotuj plik `config.yaml`**:
   ```bash
   cp config.example.yaml config.yaml
   # uzupełnij dane logowania i listę odbiorców e-mail
   ```

2. **Uruchomienie demona monitorującego w tle**:
   ```bash
   docker-compose up -d --build
   ```

3. **Podgląd logów na żywo**:
   ```bash
   docker-compose logs -f collector
   ```

4. **Wygenerowanie raportu postępów ucznia z poziomu kontenera**:
   ```bash
   # Tryb testowy / symulacja (podgląd w terminalu bez wysyłania e-maila):
   docker-compose run --rm report librus-report --dry-run

   # Faktyczne wygenerowanie i wysłanie e-maila:
   docker-compose run --rm report
   ```

5. **Zatrzymanie demona**:
   ```bash
   docker-compose down
   ```

#### Uruchomienie czystym poleceniem `docker`:

```bash
# Budowanie obrazu:
docker build -t librus2mail .

# Uruchomienie usługi w tle:
docker run -d \
  --name librus2mail \
  --restart unless-stopped \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v $(pwd)/storage:/app/storage \
  librus2mail

# Wygenerowanie raportu postępów:
docker run --rm \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v $(pwd)/storage:/app/storage \
  librus2mail librus-report --dry-run
```

---

### Wdrożenie systemd (Linux / Raspberry Pi / VPS)

W katalogu [`deploy/systemd/`](file:///home/acacko/PycharmProjects/librus2mail/deploy/systemd/) przygotowano wzorcowe pliki jednostek dla menedżera usług `systemd`:
* [`librus2mail.service`](file:///home/acacko/PycharmProjects/librus2mail/deploy/systemd/librus2mail.service): ciągły demon monitorujący z automatycznym restartem po awarii sieci i zaostrzonym profilem bezpieczeństwa (`ProtectSystem=full`, `PrivateTmp=true`, `NoNewPrivileges=true`).
* [`librus2mail-report.service`](file:///home/acacko/PycharmProjects/librus2mail/deploy/systemd/librus2mail-report.service) & [`librus2mail-report.timer`](file:///home/acacko/PycharmProjects/librus2mail/deploy/systemd/librus2mail-report.timer): natywny zegar systemowy do cotygodniowej wysyłki raportu postępów (domyślnie w każdy piątek o 17:00), eliminujący konieczność konfiguracji crona.

Szczegółowy opis instalacji krok po kroku znajduje się w przewodniku [deploy/systemd/README.md](file:///home/acacko/PycharmProjects/librus2mail/deploy/systemd/README.md).

---

## Szablony wiadomości e-mail (Jinja2)

Wszystkie wiadomości i raporty HTML generowane są za pomocą silnika szablonów **Jinja2**. Szablony znajdują się wewnątrz pakietu w katalogu `src/librus2mail/templates/emails/`:
- `messages.html`: Powiadomienia o nowych wiadomościach od nauczycieli.
- `notifications.html`: Powiadomienia o nowych ogłoszeniach szkolnych.
- `grades.html`: Powiadomienia o nowo wystawionych ocenach.
- `summary.html`: Zbiorcze podsumowanie (gdy włączona jest opcja `one_summary_message: true`).
- `error_alert.html`: Alerty o błędach autoryzacji / połączenia z zaleceniami diagnostycznymi.
- `progress_report.html`: Kompleksowy dashboard postępów ucznia (KPI, kalkulator progów, wagi, czerwony pasek, histogram).

Dzięki rozdzieleniu logiki Pythona od warstwy prezentacji, możesz łatwo dostosować kolorystykę, czcionki i układ maili do własnych preferencji bez ingerencji w kod źródłowy.

---

## Architektura projektu

Projekt korzysta z nowoczesnego układu **`src/` layout** oraz pełnej zgodności ze standardem **PEP 8** (nazewnictwo `snake_case`):

```text
librus2mail/
├── .github/                    # Automatyzacja GitHub Actions i Dependabot
│   ├── workflows/
│   │   ├── ci.yml              # Pipeline CI (Ruff linter + pytest multi-Python 3.10-3.12)
│   │   └── docker.yml          # Budowanie, testy dymne i publikacja obrazu GHCR
│   └── dependabot.yml          # Cotygodniowe aktualizacje zależności i akcji
├── src/
│   └── librus2mail/            # Kanoniczny pakiet Pythona (src/ layout, PEP 8)
│       ├── __init__.py         # Eksporty kluczowych klas i funkcji pakietu
│       ├── base_logger.py      # Konfiguracja loggera ('librus')
│       ├── config.py           # Wczytywanie konfiguracji z pliku YAML
│       ├── gmail_sender.py     # Obsługa wysyłki przez Gmail (yagmail)
│       ├── librus.py           # Klient autoryzacji OAuth i scraping portalu Librus Synergia
│       ├── collect_and_notify.py # Główny orkiestrator CLI i runner potoku
│       ├── librus_collector.py # Moduł 1: Pobieranie danych i synchronizacja ze storage
│       ├── mail_sender.py      # Klasa bazowa z obsługą szablonów Jinja2
│       ├── progress_analyzer.py# Silnik analizy postępów (średnie, wagi, alerty)
│       ├── progress_report.py  # Moduł 3: Generator raportów postępów
│       ├── smtp_sender.py      # Obsługa wysyłki SMTP (STARTTLS)
│       ├── storage.py          # Trwały zapis stanu i historia ocen JSON (FileStorage)
│       ├── updates_notifier.py # Moduł 2: Powiadomienia bieżące offline (e-mail, HTML, CLI)
│       └── templates/emails/   # Szablony e-mail wewnątrz pakietu
│           ├── messages.html
│           ├── notifications.html
│           ├── grades.html
│           ├── summary.html
│           ├── error_alert.html
│           └── progress_report.html
├── examples/                   # Przykładowe dane i wygenerowane raporty
│   ├── storage/                # Przykładowa baza ucznia ze zmyślonymi ocenami
│   └── reports/                # Przykładowe wygenerowane raporty HTML
├── tests/                      # Pakiet testów jednostkowych
│   ├── test_librus.py          # Testy logowania, scrapingu, formatowania, watermarking i analityki
│   └── test_package_layout.py  # Testy struktury pakietu i eksportów
├── deploy/                     # Gotowe pliki wdrożeniowe
│   └── systemd/                # Jednostki systemd dla Linuksa (Raspberry Pi / VPS)
│       ├── librus2mail.service # Usługa demona zbierającego dane z restartem
│       ├── librus2mail-report.service # Usługa generowania raportu postępów
│       ├── librus2mail-report.timer   # Zegar cotygodniowej wysyłki raportu
│       └── README.md           # Instrukcja instalacji usług systemd
├── Dockerfile                  # Wielowarstwowy obraz kontenera OCI (Python 3.10-slim, non-root)
├── docker-compose.yml          # Definicja usług (kolektor w tle + raporty na żądanie)
├── .dockerignore               # Ochrona poufnych konfiguracji przed kopiowaniem do obrazu
├── pyproject.toml              # Nowoczesna konfiguracja projektu (PEP 517/518/621)
├── requirements.txt            # Tradycyjna lista zależności
├── config.example.yaml         # Wzorcowy szablon konfiguracji
├── collect_and_notify.py       # Główny punkt wejścia demona i orkiestratora (CLI)
├── librus_collector.py         # Moduł 1: CLI zbierania danych ze szkoły
├── updates_notifier.py         # Moduł 2: CLI bieżących powiadomień
├── progress_report.py          # Moduł 3: CLI generatora raportów postępów
├── useful-scripts.md           # Kompletny podręcznik wszystkich skryptów i opcji CLI
├── CHANGELOG.md                # Historia wydań i zmian (Keep a Changelog)
├── RELEASING.md                # Procedura wydawania wersji i konfiguracji GitHub Pages
├── README.md                   # Niniejsza dokumentacja
└── AGENTS.md                   # Instrukcje dla agentów AI i deweloperów
```

### Przepływ danych (Data Flow):
1. **Collector (`librus_collector.py`)**: Loguje się OAuth do portalu Librus Synergia, pobiera wiadomości, ogłoszenia i oceny, deduplikuje je i zapisuje w trwałych plikach `storage/<login>.json` wraz ze znacznikiem `last_collect_time`.
2. **Updates Notifier (`updates_notifier.py`)**: Weryfikuje nowe pozycje w bazie `storage/` od znacznika `last_notify_time` (lub zadanego okna czasowego `--days` / `--hours`) i wysyła powiadomienia e-mail (bądź generuje podgląd HTML / konsolowy).
3. **Progress Report (`progress_report.py`)**: Działa w 100% offline, analizuje historię ocen ze `storage/` za pomocą [`ProgressAnalyzer`](file:///home/acacko/PycharmProjects/librus2mail/src/librus2mail/progress_analyzer.py) i tworzy bogaty dashboard postępów ucznia.
4. **Orkiestrator (`collect_and_notify.py`)**: W domyślnym trybie demona spina Moduł 1 i Moduł 2 w ciągłą pętlę z przerwami `wait_time_s` (gdy `work-in-loop: true`), lub wykonuje pojedynczy przebieg (`work-in-loop: false` / `--once`). Umożliwia też uruchomienie dowolnego modułu w odosobnieniu.

---

## Testy i jakość kodu

Projekt wyposażony jest w automatyczne testy jednostkowe oraz konfigurację lintera **Ruff**:

```bash
# Aktywacja środowiska wirtualnego
source venv/bin/activate

# 1. Uruchomienie pełnego zestawu testów jednostkowych (pytest):
pytest

# 2. Uruchomienie testów z raportem pokrycia kodu (coverage):
pytest --cov=librus2mail

# 3. Sprawdzenie poprawności stylu kodu (Ruff):
ruff check

# 4. Automatyczna korekta drobnych niezgodności formatowania:
ruff check --fix
```

Bieżące zdarzenia i diagnostykę działania usługi można śledzić w pliku `librus.log`:

```bash
tail -f librus.log
```

---

## Najczęstsze pytania i rozwiązywanie problemów (FAQ)

### 1. W logach pojawia się błąd „Brak dostępu” (`NotLogged`)
* Sprawdź, czy dane logowania do konta Librus (`librus_login`, `librus_password`) w pliku konfiguracyjnym są poprawne.
* Zaloguj się na konto rodzica przez zwykłą przeglądarkę internetową. Librus może wymagać zaakceptowania nowego regulaminu, zmiany hasła lub wyświetlać obowiązkowy komunikat od szkoły. Po zaakceptowaniu w przeglądarce skrypt wznowi normalną pracę.

### 2. Wiadomości w portalu Librus oznaczają się jako przeczytane
* Flaga `read_messages` jest domyślnie włączona (`true`), co pozwala skryptowi pobrać pełną treść nowej wiadomości i umieścić ją w e-mailu. Zgodnie z działaniem portalu Librus Synergia, otwarcie szczegółów wiadomości powoduje oznaczenie jej jako przeczytanej przez rodzica na stronie WWW. Jeśli wolisz otrzymywać powiadomienia e-mail wyłącznie o tytule i nadawcy nowej wiadomości (bez oznaczania jej jako przeczytanej w e-dzienniku), ustaw w konfiguracji: `read_messages: false`.

### 3. Błąd uwierzytelnienia Gmaila (`SMTPAuthenticationError`)
* Jeśli korzystasz z konta Google, upewnij się, że nie wpisujesz zwykłego hasła do konta, lecz wygenerowane w Google **hasło do aplikacji** (16-znakowy ciąg).

### 4. Czy moje konto w Librusie może zostać zablokowane?
* Zbyt częste odpytywanie serwerów Librusa może skutkować tymczasową blokadą adresu IP lub wymuszeniem weryfikacji CAPTCHA. Dlatego parametr `wait_time_s` nie powinien być mniejszy niż 3600–7200 sekund (1-2h), a wbudowane opóźnienia `sleep(5)` pomiędzy kolejnymi zapytaniami powinny pozostać nienaruszone.

---

## Bezpieczeństwo

* Pliki `config.yaml`, `*_config.yaml`, `.env` oraz `*.log` zawierają poufne hasła, dane osobowe i adresy e-mail.
* **Nigdy nie dodawaj ich do repozytorium gita** (`.gitignore` w projekcie jest skonfigurowany tak, aby je chronić).
* Wszelkie przykłady i testy opieraj wyłącznie na szablonie `config.example.yaml`.

---

## Podziękowania

Projekt powstał w oparciu o analizę mechanizmu komunikacji z API Librusa zawartą w projekcie [Mati365/librus-api](https://github.com/Mati365/librus-api/).

---

## Licencja

Projekt udostępniany jest na warunkach otwartej licencji **MIT**. Szczegółowe informacje znajdują się w pliku [LICENSE](LICENSE).
