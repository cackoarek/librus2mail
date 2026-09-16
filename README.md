# Librus2mail

Automatyczny demon / powiadamiacz e-mail dla systemu **Librus Synergia**. 

Skrypt loguje się na konto rodzica w portalu Librus Synergia, cyklicznie monitoruje skrzynkę wiadomości (`/wiadomosci`), tablicę ogłoszeń szkolnych (`/ogloszenia`) oraz oceny ucznia (`/przegladaj_oceny/uczen`), a w przypadku wykrycia nowych wpisów natychmiast wysyła estetyczne podsumowanie HTML na wskazane adresy e-mail.

---

## Spis treści
1. [Główne możliwości](#główne-możliwości)
2. [Wymagania](#wymagania)
3. [Instalacja](#instalacja)
4. [Konfiguracja](#konfiguracja)
   - [Struktura pliku config.yaml](#struktura-pliku-configyaml)
   - [Konfiguracja kont Librus (librus_users)](#konfiguracja-kont-librus-librus_users)
   - [Konfiguracja wysyłki e-mail (mail)](#konfiguracja-wysyłki-e-mail-mail)
5. [Uruchomienie](#uruchomienie)
   - [Uruchomienie standardowe](#uruchomienie-standardowe)
   - [Uruchomienie w tle (systemd / nohup)](#uruchomienie-w-tle-systemd--nohup)
6. [Architektura projektu](#architektura-projektu)
7. [Testy i diagnostyka](#testy-i-diagnostyka)
8. [Najczęstsze pytania i rozwiązywanie problemów (FAQ)](#najczęstsze-pytania-i-rozwiązywanie-problemów-faq)
9. [Bezpieczeństwo](#bezpieczeństwo)
10. [Podziękowania](#podziękowania)

---

## Główne możliwości

* **Wsparcie dla wielu kont**: Możliwość jednoczesnego monitorowania kont dla kilkorga dzieci (każde konto może mieć przypisanych innych odbiorców powiadomień).
* **Nowoczesny przepływ OAuth**: Zgodność z aktualnym procesem autoryzacji Librus Synergia (uwzględniającym przekierowania `portalRodzina`, pominięcie ekranu 2FA oraz grant autoryzacyjny).
* **Obsługa wiadomości, ogłoszeń i ocen**: Monitorowanie wiadomości prywatnych od nauczycieli, ogólnych ogłoszeń szkolnych oraz nowo wystawionych ocen (cząstkowych, semestralnych i rocznych).
* **Elastyczna wysyłka e-mail**:
  * **Gmail**: zoptymalizowana obsługa przez bibliotekę `yagmail` (wymagane hasło aplikacji Google).
  * **SMTP**: standardowy protokół SMTP z szyfrowaniem STARTTLS (działa z dowolnym serwerem pocztowym: hostingodawcy, OVH, Cyberfolks, WP, Onet itp.).
* **Tryb pierwszego przebiegu (`do_not_send_first_parse`)**: Przy pierwszym uruchomieniu skrypt indeksuje aktualne wiadomości, ogłoszenia i oceny jako bazę i nie wysyła spamu ze wszystkimi historycznymi wpisami – kolejne uruchomienia wysyłają powiadomienia wyłącznie o nowych wpisach.
* **Formatowanie HTML**: Czytelne tabele z wyróżnieniem nowych wiadomości **pogrubioną czcionką**, danymi nadawcy, tematem, datą nadania oraz tabelami ocen ze szczegółami (przedmiot, ocena, kategoria, waga, data, nauczyciel).

---

## Wymagania

* **Python 3.10+** (projekt wykorzystuje nowoczesne unie typów `X | Y` oraz walrus operator `:=`).
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

# 4. Aktualizacja pip i instalacja zależności
pip install --upgrade pip
pip install -r requirements.txt
```

---

## Konfiguracja

Wszystkie ustawienia aplikacji znajdują się w pliku `config.yaml`. Na start skopiuj wzorcowy plik konfiguracyjny:

```bash
cp config.example.yaml config.yaml
```

Następnie otwórz `config.yaml` w edytorze i uzupełnij swoje dane.

### Struktura pliku `config.yaml`

```yaml
librus_users:
  - librus_login_name: "Konto Jasia"
    librus_login: "1234567"
    librus_password: "twoje_haslo_librus"
    read_messages: false
    read_grades: true
    one_summary_message: false
    do_not_send_first_parse: true
    notification_receivers:
      - "mama@example.com"
      - "tata@example.com"

wait_time_s: 300
storage_type: "RAM" # "RAM" (domyślnie) lub "FILES" (stan zapisywany w katalogu storage/)

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
| `read_messages` | `bool` | Czy skrypt ma wchodzić w szczegóły wiadomości i pobierać jej treść (`true`/`false`).<br>**UWAGA:** Wejście w wiadomość oznacza ją w portalu Librus jako przeczytaną przez rodzica. Domyślnie zaleca się `false`. |
| `read_grades` | `bool` | Czy włączyć sprawdzanie i wysyłanie alertów o nowych ocenach dla tego konta (`true`/`false`). Domyślnie `false`. |
| `one_summary_message` | `bool` | Jeśli `true`, zamiast wysyłać osobne maile dla wiadomości, ogłoszeń i ocen, wyśle **jeden zbiorczy e-mail** podsumowujący wszystkie nowości z danego cyklu. Domyślnie `false`. |
| `do_not_send_first_parse` | `bool` | Jeśli `true`, podczas pierwszego cyklu po uruchomieniu wiadomości zostaną tylko zaindeksowane, bez wysyłania e-maili o historii skrzynki. |
| `notification_receivers` | `list` | Lista adresów e-mail odbiorców, którzy mają otrzymać powiadomienie dla tego konta. |

### Parametry globalne

* `wait_time_s` (`int`): Czas oczekiwania w sekundach pomiędzy kolejnymi cyklami sprawdzania e-dziennika (zalecane: minimum `120`–`300` sekund, aby nie obciążać serwera i uniknąć blokad anty-botowych).
* `storage_type` (`string`): Sposób zapamiętywania przeczytanych wpisów pomiędzy uruchomieniami:
  * `"RAM"` (domyślnie) – stan przechowywany wyłącznie w pamięci operacyjnej; po restarcie skryptu historia jest indeksowana od nowa.
  * `"FILES"` – stan zapisywany w plikach JSON w katalogu `storage/` (np. `storage/8979295.json`). Po restarcie aplikacji skrypt wczytuje poprzedni stan i natychmiast wykrywa wpisy, które pojawiły się w czasie, gdy usługa była wyłączona.

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

## Uruchomienie

### Uruchomienie standardowe

Upewnij się, że wirtualne środowisko jest aktywne:

```bash
source venv/bin/activate
python main.py
```

Skrypt uruchomi się w pętli nieskończonej, logując swoje działania jednocześnie do pliku `librus.log` oraz na konsolę.

### Uruchomienie w tle (systemd / nohup)

#### Wariant A: `nohup`
```bash
nohup venv/bin/python main.py >/dev/null 2>&1 &
```

#### Wariant B: Usługa `systemd` (zalecane dla serwerów Linux)
Utwórz plik `/etc/systemd/system/librus2mail.service`:

```ini
[Unit]
Description=Librus2mail Daemon
After=network.target

[Service]
Type=simple
User=twoj_uzytkownik
WorkingDirectory=/sciezka/do/librus2mail
ExecStart=/sciezka/do/librus2mail/venv/bin/python main.py
Restart=always
RestartSec=60

[Install]
WantedBy=multi-user.target
```

Następnie aktywuj usługę:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now librus2mail
sudo systemctl status librus2mail
```

---

## Architektura projektu

```text
librus2mail/
├── base_logger.py              # Konfiguracja loggera (zapis do librus.log oraz na konsolę)
├── config.py                   # Moduł wczytujący konfigurację z pliku YAML
├── config.example.yaml         # Bezpieczny szablon pliku konfiguracyjnego
├── GmailSender.py              # Klasa wysyłająca wiadomości przez yagmail (Gmail)
├── SmtpSender.py               # Klasa wysyłająca wiadomości przez standardowe smtplib + STARTTLS
├── MailSender.py               # Klasa bazowa z generatorami szablonów e-mail HTML
├── librus.py                   # Klient autoryzacji OAuth i scraper portalu Librus Synergia
├── main.py                     # Główny punkt wejścia i pętla odpytująca demona
├── requirements.txt            # Wymagane biblioteki Pythona
├── tests/
│   └── test_librus.py          # Testy jednostkowe parsera i obsługi sesji
├── AGENTS.md                   # Instrukcje architektury dla agentów AI
└── README.md                   # Niniejsza dokumentacja
```

### Przepływ danych (Data Flow):
1. [`main.py`](file:///home/acacko/PycharmProjects/librus2mail/main.py) wczytuje konfigurację za pomocą [`config.py`](file:///home/acacko/PycharmProjects/librus2mail/config.py) i inicjalizuje instancję mailera ([`GmailSender`](file:///home/acacko/PycharmProjects/librus2mail/GmailSender.py) lub [`SmtpSender`](file:///home/acacko/PycharmProjects/librus2mail/SmtpSender.py)).
2. Dla każdego użytkownika tworzona jest instancja klasy [`Librus`](file:///home/acacko/PycharmProjects/librus2mail/librus.py).
3. W każdym cyklu:
   * Wykonywane jest logowanie OAuth ([`librus.login()`](file:///home/acacko/PycharmProjects/librus2mail/librus.py#L44)).
   * Pobierane są wiadomości ([`librus.fetch_messages()`](file:///home/acacko/PycharmProjects/librus2mail/librus.py#L185)).
   * Pobierane są ogłoszenia ([`librus.fetch_notifications()`](file:///home/acacko/PycharmProjects/librus2mail/librus.py#L254)).
   * Pobierane są oceny ucznia ([`librus.fetch_grades()`](file:///home/acacko/PycharmProjects/librus2mail/librus.py#L309)).
   * Sprawdzane są nowe pozycje metodami `get_not_known_*`.
   * Jeśli pojawiły się nowe wpisy i nie jest to pierwszy przebieg (`dry-parse`), mailer generuje tabelę HTML i wysyła powiadomienie.
   * Skrypt odczekuje zdefiniowany czas `wait_time_s` przed kolejnym cyklem.

---

## Testy i diagnostyka

Projekt zawiera automatyczne testy jednostkowe weryfikujące parsowanie, odporność na zmiany DOM oraz obsługę sesji:

```bash
# Uruchomienie zestawu testów
source venv/bin/activate
python -m unittest discover -s tests
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
* Jeśli flaga `read_messages` jest ustawiona na `true`, skrypt otwiera szczegóły każdej nowej wiadomości w celu pobrania treści. System Librus automatycznie oznacza wówczas taką wiadomość jako przeczytaną w e-dzienniku. Aby tego uniknąć, ustaw `read_messages: false`.

### 3. Błąd uwierzytelnienia Gmaila (`SMTPAuthenticationError`)
* Jeśli korzystasz z konta Google, upewnij się, że nie wpisujesz zwykłego hasła do konta, lecz wygenerowane w Google **hasło do aplikacji** (16-znakowy ciąg).

### 4. Czy moje konto w Librusie może zostać zablokowane?
* Zbyt częste odpytywanie serwerów Librusa może skutkować tymczasową blokadą adresu IP lub wymuszeniem weryfikacji CAPTCHA. Dlatego parametr `wait_time_s` nie powinien być mniejszy niż 120–300 sekund, a wbudowane opóźnienia `sleep(5)` pomiędzy kolejnymi zapytaniami powinny pozostać nienaruszone.

---

## Bezpieczeństwo

* Pliki `config.yaml`, `*_config.yaml`, `.env` oraz `*.log` zawierają poufne hasła, dane osobowe i adresy e-mail.
* **Nigdy nie dodawaj ich do repozytorium gita** (`.gitignore` w projekcie jest skonfigurowany tak, aby je chronić).
* Wszelkie przykłady i testy opieraj wyłącznie na szablonie `config.example.yaml`.

---

## Podziękowania

Projekt powstał w oparciu o analizę mechanizmu komunikacji z API Librusa zawartą w projekcie [Mati365/librus-api](https://github.com/Mati365/librus-api/).
