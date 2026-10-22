# ⚙️ Przewodnik po konfiguracji – Librus2mail

Konfiguracja aplikacji **Librus2mail** opiera się na pliku w formacie YAML (domyślnie `config.yaml`) lub na zmiennych środowiskowych (przydatnych m.in. w kontenerach Docker). Ustawienia można także w całości wyklikać w przeglądarce za pomocą **Kreatora pierwszego uruchomienia** (`/setup`) lub panelu **Ustawienia** (`/ustawienia`).

---

## 🚀 Szybki start: Dwa warianty plików przykładowych

W repozytorium znajdują się dwa gotowe szablony konfiguracyjne:
- **`config-minimal.yaml`**: zawiera wyłącznie parametry bezwzględnie wymagane do uruchomienia usługi.
- **`config-example.yaml`**: pełna demonstracyjna konfiguracja z wszystkimi opcjami, zaawansowanymi algorytmami i wyczerpującymi komentarzami.

Aby rozpocząć konfigurację ręczną:
```bash
cp config-minimal.yaml config.yaml
# lub
cp config-example.yaml config.yaml
```

---

## 📄 Kompletna struktura pliku `config.yaml`

Poniżej przedstawiono pełną strukturę pliku konfiguracyjnego z podziałem na logiczne sekcje.

### 1. Konta uczniów (`librus_users`)

Sekcja definiuje jedno lub więcej kont rodzica w portalu Librus Synergia. Aplikacja natywnie obsługuje rodziny wielodzietne.

```yaml
librus_users:
  - login: "1234567u"                         # Login rodzica do portalu Librus Synergia
    pass: "TwojeSekretneHaslo123"             # Hasło do konta Librus
    login_name: "Jan Kowalski"                # Czytelna nazwa / imię dziecka w nagłówkach i mailach
    recipients:                               # Lista odbiorców bieżących powiadomień e-mail
      - "mama@example.com"
      - "tata@example.com"
    read_messages: true                       # Czy pobierać i czytać treść wiadomości (UWAGA: oznacza wiadomość jako przeczytaną w portalu)
    read_grades: true                         # Czy pobierać oceny
    read_attendance: true                     # Czy pobierać dane o frekwencji i nieobecnościach
    student_report:                           # Konfiguracja okresowego raportu motywacyjnego dla ucznia
      enabled: true                           # Czy generować raport motywacyjny dla tego dziecka
      template: "teens"                       # Szablon wiekowy: 'kids' (kl. 1-4), 'teens' (kl. 5-8), 'youth' (szkoły średnie)
      recipients:                             # Adres e-mail dziecka (raport wysyłany bezpośrednio do ucznia)
        - "janek@example.com"

  # Opcjonalne kolejne dziecko:
  # - login: "7654321u"
  #   pass: "DrugieHaslo456"
  #   login_name: "Zofia Kowalska"
  #   recipients:
  #     - "rodzice@example.com"
  #   student_report:
  #     enabled: true
  #     template: "kids"
  #     recipients:
  #       - "mama@example.com"
```

> [!WARNING]
> Odwiedzenie szczegółów wiadomości w portalu Librus Synergia oznacza wiadomość jako przeczytaną. Jeśli chcesz, aby wiadomości pozostawały nieprzeczytane na oficjalnej stronie szkoły, ustaw parametr `read_messages: false`.

---

### 2. Parametry globalne usługi

```yaml
# Czas oczekiwania pomiędzy kolejnymi cyklami sprawdzania (w sekundach).
# Domyślnie 900 sekund (15 minut). Minimalna bezpieczna wartość to 300 s (5 min).
wait_time_s: 900

# Tryb pracy usługi:
# true  - praca ciągła w nieskończonej pętli demona (zalecane)
# false - pojedyncze sprawdzenie i zakończenie procesu (przydatne w cronie)
work_in_loop: true

# Ścieżka do katalogu z lokalną bazą stanu JSON:
storage_dir: "storage"

# Czy wysyłać pojedyncze, zbiorcze powiadomienie e-mail dla wszystkich dzieci naraz (true),
# czy osobne wiadomości dla każdego konta ucznia (false, domyślnie):
one_summary_message: false

# Czy wysyłać e-mail z alertem o błędzie logowania/połączenia do administratora:
send_error_notifications: true

# Przesunięcie dnia planu lekcji w powiadomieniu (w dniach, domyślnie 1 = jutro):
schedule_day_offset: 1

# Data podziału roku szkolnego na I i II semestr (format RRRR-MM-DD):
# Pozwala na precyzyjną kalkulację średnich semestralnych w panelu WWW i raportach.
semester_split_date: "2027-01-31"

# Algorytm predykcji oceny rocznej na świadectwie:
# - 'all_year_weighted'  - średnia ważona ze wszystkich ocen w całym roku szkolnym (domyślny)
# - 'semesters_average'  - średnia arytmetyczna z ocen wyliczonych w semestrze I i II
# - 'progress_favored'   - faworyzowanie postępów ucznia (wyższa waga dla ocen z II semestru)
annual_grade_algorithm: "all_year_weighted"
```

---

### 3. Konfiguracja wysyłki e-mail (`mail`)

Aplikacja obsługuje wysyłkę przez Gmail oraz dowolny serwer pocztowy SMTP.

#### Wariant 3A: Poczta Gmail (hasło aplikacji – najprostsze)
```yaml
mail:
  provider: "gmail"
  login: "twoj.adres@gmail.com"
  password: "xxxx xxxx xxxx xxxx"             # 16-znakowe Hasło Aplikacji wygenerowane w Google Security
```
> [!NOTE]
> Aby wygenerować hasło aplikacji w Gmail: wejdź na swoje konto Google -> *Bezpieczeństwo* -> włącz *Weryfikację dwuetapową (2FA)* -> przejdź do sekcji *Hasła do aplikacji* i wygeneruj nowe hasło dla aplikacji Librus2mail.

#### Wariant 3B: Poczta Gmail z OAuth 2.0 (bez przechowywania haseł)
```yaml
mail:
  provider: "gmail"
  login: "twoj.adres@gmail.com"
  oauth2_file: "client_secret.json"          # Plik poświadczeń pobrany z Google Cloud Console
```

#### Wariant 3C: Własny serwer SMTP (np. WP, Onet, Onet, prywatny serwer pocztowy)
```yaml
mail:
  provider: "smtp"
  smtp_host: "poczta.twojadomena.pl"
  smtp_port: 587                              # Port 587 (STARTTLS, zalecany) lub 465 (SSL)
  smtp_user: "librus@twojadomena.pl"
  smtp_pass: "TwojeSekretneHasloSMTP"
  use_ssl: false                              # true dla portu 465, false dla portu 587 (STARTTLS)
  use_tls: true                               # true dla portu 587 z STARTTLS
  from_name: "Asystent Librus2mail"           # Czytelna nazwa nadawcy w programie pocztowym
```

---

### 4. Konfiguracja modułu WWW (`web`)

Parametry interaktywnego panelu rodzica i API:

```yaml
web:
  port: 5000                                  # Port serwera WWW
  host: "127.0.0.1"                           # "127.0.0.1" (tylko lokalnie) lub "0.0.0.0" (dostęp w całej sieci LAN / Wi-Fi)
  password: "BezpieczneHasloDostepu"          # Hasło do panelu rodzica (Parent Gate)
  attendance_view_mode: "heatmap"             # Domyślny widok frekwencji: 'heatmap' (roczna heatmapa) lub 'month' (kalendarz miesiąca)
  max_login_attempts: 5                       # Liczba nieudanych prób logowania przed nałożeniem blokady
  lockout_duration_s: 900                     # Czas blokady adresu IP po przekroczeniu limitu prób (w sekundach)
```

---

### 5. Moduł kalendarium zdarzeń (`timeline`)

Konfiguracja kafelka kalendarium prezentowanego na pulpicie głównym:

```yaml
timeline:
  enabled: true                               # Czy wyświetlać moduł kalendarium na stronie głównej
  days: 5                                     # Liczba dni wstecz objętych kalendarium (od 1 do 14)
  hide_weekends: false                        # Czy ukrywać soboty i niedziele, pokazując tylko dni nauki szkolnej
  reverse_order: false                        # Czy odwrócić kolejność (dzień dzisiejszy na samej górze/początku)
  event_types:                                # Filtrowanie typów zdarzeń widocznych w kalendarium:
    - grades                                  # 📝 Nowo wystawione oceny
    - attendance                              # ⏱️ Frekwencja (nieobecności, spóźnienia, zwolnienia)
    - messages                                # ✉️ Wiadomości od nauczycieli
    - notifications                           # 📢 Ogłoszenia szkolne i komunikaty dyrekcji
    - tests                                   # 🔔 Sprawdziany i nowe zapowiedzi z terminarza
```

---

### 6. Harmonogram automatycznych raportów (`schedule`)

Określa, w jakie dni i o jakich godzinach demon powinien generować i wysyłać podsumowania okresowe:

```yaml
schedule:
  # Raport postępów dla rodziców:
  progress_report:
    enabled: true
    weekday: "friday"                         # Dzień tygodnia: 'monday' - 'sunday'
    hour: 17                                  # Godzina wysyłki (0-23)
    minute: 0                                 # Minuta wysyłki (0-59)
    days: 7                                   # Okno czasowe analizy (np. ostatnie 7 dni)
    recipients:
      - "rodzice@example.com"

  # Raport motywacyjny dla ucznia:
  student_report:
    enabled: true
    weekday: "friday"
    hour: 17
    minute: 15
```

---

## 🔒 Konfiguracja przez zmienne środowiskowe (Docker & Cloud)

W środowiskach kontenerowych zaleca się przekazywanie danych wrażliwych za pomocą zmiennych środowiskowych, co eliminuje konieczność zapisywania haseł w plikach:

| Zmienna środowiskowa | Odpowiednik w YAML | Opis / Przykład |
| :--- | :--- | :--- |
| `LIBRUS_USERS_JSON` | `librus_users` | Cała lista kont w formacie JSON |
| `MAIL_LOGIN` | `mail.login` | Adres e-mail nadawcy |
| `MAIL_PASSWORD` | `mail.password` | Hasło pocztowe / hasło aplikacji |
| `MAIL_PROVIDER` | `mail.provider` | `gmail` lub `smtp` |
| `SMTP_HOST` | `mail.smtp_host` | Adres serwera SMTP |
| `SMTP_PORT` | `mail.smtp_port` | Port serwera SMTP (np. `587`) |
| `SMTP_PASS` | `mail.smtp_pass` | Hasło użytkownika SMTP |
| `WEB_PASSWORD` | `web.password` | Hasło dostępu do panelu WWW |
| `FLASK_SECRET_KEY` | `web.secret_key` | Klucz szyfrowania ciasteczek sesyjnych |
| `WAIT_TIME_S` | `wait_time_s` | Czas uśpienia demona w sekundach |
| `STORAGE_DIR` | `storage_dir` | Ścieżka do pamięci stanu (domyślnie `/app/storage`) |

### Przykład pliku `.env` dla Docker Compose:
```env
LIBRUS_USERS_JSON=[{"login":"1234567u","pass":"SekretneHaslo123","login_name":"Jan Kowalski","recipients":["rodzic@example.com"]}]
MAIL_PROVIDER=gmail
MAIL_LOGIN=twoj.adres@gmail.com
MAIL_PASSWORD=xxxx xxxx xxxx xxxx
WEB_PASSWORD=MojeBezpieczneHasloWWW
WAIT_TIME_S=900
```

---

## 🛡️ Dobre praktyki bezpieczeństwa

1. **Nigdy nie publikuj pliku `config.yaml`**: plik ten znajduje się w `.gitignore`. Do repozytorium gita commituj wyłącznie `config-minimal.yaml` lub `config-example.yaml`.
2. **Hasła dedykowane**: do konta pocztowego Gmail stosuj wyłącznie 16-znakowe Hasła Aplikacji Google, nigdy nie podawaj głównego hasła do konta Google.
3. **Izolacja sieciowa**: jeśli uruchamiasz panel webowy na serwerze z publicznym IP, zawsze ustaw `web.host: "127.0.0.1"` i wystawiaj panel przez bezpieczny reverse proxy (Nginx / Caddy) z szyfrowaniem HTTPS.
