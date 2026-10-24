# 🚀 Wdrożenie produkcyjne i uruchamianie – Librus2mail

Niniejszy przewodnik opisuje rekomendowane metody wdrożenia produkcyjnego usługi **Librus2mail**: w kontenerach **Docker**, jako usługa systemowa **systemd** na minikomputerach (np. Raspberry Pi) lub serwerach VPS, a także z wykorzystaniem harmonogramu zadań **cron**.

---

## 🐳 Wariant 1: Konteneryzacja Docker & Docker Compose (Zalecane)

Konteneryzacja zapewnia pełną izolację zależności Pythona, automatyczne wznawianie pracy po restarcie serwera oraz łatwe zarządzanie za pomocą zmiennych środowiskowych.

### 1. Struktura katalogu wdrożeniowego
```text
librus-deploy/
├── docker-compose.yml
├── .env
├── config.yaml          (opcjonalnie, jeśli nie używasz .env)
└── storage/             (katalog zamontowany z danymi stanu)
```

### 2. Przykładowy plik `docker-compose.yml`

```yaml
version: '3.8'

services:
  # Główna usługa: Kolektor w tle i orkiestrator powiadomień e-mail
  librus-collector:
    image: python:3.10-slim
    container_name: librus2mail-collector
    restart: unless-stopped
    working_dir: /app
    volumes:
      - ./:/app
      - ./storage:/app/storage
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    env_file:
      - .env
    command: >
      bash -c "pip install --no-cache-dir -r requirements.txt &&
               python librus_collect_and_notify.py"

  # Opcjonalna usługa: Interaktywny Panel Rodzica WWW (dostępny w sieci domowej)
  librus-web:
    image: python:3.10-slim
    container_name: librus2mail-web
    restart: unless-stopped
    working_dir: /app
    ports:
      - "5000:5000"
    volumes:
      - ./:/app
      - ./storage:/app/storage
      - /etc/timezone:/etc/timezone:ro
      - /etc/localtime:/etc/localtime:ro
    env_file:
      - .env
    command: >
      bash -c "pip install --no-cache-dir -r requirements.txt &&
               python librus_web.py --host 0.0.0.0 --port 5000"
    depends_on:
      - librus-collector
```

### 3. Konfiguracja zmiennych w `.env`
Stwórz plik `.env` obok `docker-compose.yml`:
```env
LIBRUS_USERS_JSON=[{"login":"1234567u","pass":"MojeHasloLibrus","login_name":"Jan Kowalski","recipients":["rodzic@example.com"]}]
MAIL_PROVIDER=gmail
MAIL_LOGIN=twoj.adres@gmail.com
MAIL_PASSWORD=xxxx xxxx xxxx xxxx
WEB_PASSWORD=TajneHasloDoPaneluWWW
WAIT_TIME_S=900
```

### 4. Uruchomienie i zarządzanie
```bash
# Uruchomienie kontenerów w tle:
docker compose up -d

# Podgląd logów w czasie rzeczywistym:
docker compose logs -f librus-collector

# Zatrzymanie usługi:
docker compose down
```

---

## 🐧 Wariant 2: Usługa systemowa systemd (Raspberry Pi / Linux / VPS)

Jeśli uruchamiasz aplikację bezpośrednio w systemie Linux (np. Raspberry Pi OS, Debian, Ubuntu), najlepiej skonfigurować ją jako usługę `systemd`. Zagwarantuje to automatyczny start po włączeniu zasilania oraz restart w przypadku niespodziewanego błędu.

### 1. Przygotowanie środowiska i katalogu
```bash
# Załóżmy, że aplikacja znajduje się w katalogu /opt/librus2mail:
cd /opt/librus2mail
virtualenv venv -p python3.10
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Plik usługi kolektora: `/etc/systemd/system/librus2mail.service`
Utwórz plik jako root (`sudo nano /etc/systemd/system/librus2mail.service`):

```ini
[Unit]
Description=Librus2mail - Demon monitoringu dziennika Librus
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/librus2mail
ExecStart=/opt/librus2mail/venv/bin/python librus_collect_and_notify.py
Restart=always
RestartSec=30
Environment=PYTHONUNBUFFERED=1

# Ochrona i ograniczenia uprawnień:
ProtectSystem=full
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

### 3. Plik usługi panelu WWW: `/etc/systemd/system/librus2mail-web.service`
Opcjonalnie utwórz drugą usługę dla panelu webowego (`sudo nano /etc/systemd/system/librus2mail-web.service`):

```ini
[Unit]
Description=Librus2mail - Panel Rodzica WWW
After=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/librus2mail
ExecStart=/opt/librus2mail/venv/bin/python librus_web.py --host 0.0.0.0 --port 5000
Restart=always
RestartSec=15
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### 4. Aktywacja i sterowanie usługami
```bash
# Przeładowanie konfiguracji systemd:
sudo systemctl daemon-reload

# Włączenie autostartu przy starcie systemu:
sudo systemctl enable librus2mail.service
sudo systemctl enable librus2mail-web.service

# Uruchomienie usług:
sudo systemctl start librus2mail.service
sudo systemctl start librus2mail-web.service

# Sprawdzenie statusu:
sudo systemctl status librus2mail.service

# Śledzenie logów na żywo:
journalctl -u librus2mail.service -f
```

---

## ⏰ Wariant 3: Harmonogram zadań cron (Tryb oszczędny / bez demona)

Jeśli nie chcesz, aby proces Pythona działał nieprzerwanie w tle, możesz skonfigurować sprawdzanie ocen w trybie jednorazowym (`work_in_loop: false` lub flaga `--once`).

Otwórz edytor zadań cron (`crontab -e`):

```bash
# Sprawdzanie ocen i wiadomości od poniedziałku do piątku co 30 minut między 07:00 a 19:00:
*/30 7-19 * * 1-5 /opt/librus2mail/venv/bin/python /opt/librus2mail/librus_collect_and_notify.py --once >> /opt/librus2mail/cron.log 2>&1

# Generowanie i wysyłka Raportu Postępów dla rodziców w każdy piątek o 17:00:
0 17 * * 5 /opt/librus2mail/venv/bin/python /opt/librus2mail/librus_progress_report.py >> /opt/librus2mail/cron_reports.log 2>&1

# Generowanie i wysyłka Raportu Motywacyjnego dla ucznia w każdy piątek o 17:15:
15 17 * * 5 /opt/librus2mail/venv/bin/python /opt/librus2mail/librus_student_report.py >> /opt/librus2mail/cron_reports.log 2>&1
```

---

## 🔒 Wystawienie panelu WWW przez Reverse Proxy (Nginx + HTTPS)

Jeśli chcesz uzyskać bezpieczny dostęp do panelu rodzica poza domową siecią Wi-Fi (np. z internetu mobilnego w smartfonie), skonfiguruj serwer **Nginx** z certyfikatem **Let's Encrypt**:

```nginx
server {
    server_name librus.twojadomena.pl;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Obsługa strumieniowania HTMX i zapytań asynchronicznych:
        proxy_buffering off;
        proxy_read_timeout 120s;
    }

    listen 443 ssl http2;
    ssl_certificate /etc/letsencrypt/live/librus.twojadomena.pl/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/librus.twojadomena.pl/privkey.pem;
}
```

> [!TIP]
> Wbudowane mechanizmy bezpieczeństwa Librus2mail (ochrona przed atakami brute-force z blokadą IP, obsługa `X-Forwarded-For` oraz żetony CSRF) automatycznie współpracują z serwerami reverse proxy.

---

## ☁️ Wariant 4: Usługi chmurowe PaaS (RunxBuild, Render, Fly.io, Railway)

Platformy PaaS umożliwiają szybkie uruchomienie aplikacji z repozytorium Git z automatycznym certyfikatem HTTPS.

### 1. Trwałość danych (Persistent Disks / Volumes)
Większość platform PaaS korzysta z kontenerów z ulotnym systemem plików (ephemeral filesystem). Aby historia ocen, frekwencja oraz plik `config.yaml` nie uległy skasowaniu po restarcie lub wdrożeniu nowej wersji:
1. W panelu usługi podepnij dysk trwały (Persistent Volume / Disk), wskazując punkt montowania (np. `/data`).
2. Wskaż aplikacji ten katalog za pomocą zmiennej środowiskowej:
   ```env
   LIBRUS_DATA_DIR=/data
   ```
   lub parametru CLI:
   ```bash
   python librus_web.py -d /data
   ```

Aplikacja automatycznie umieści:
- Plik konfiguracyjny: `/data/config.yaml`
- Bazę danych JSON: `/data/storage/`
- Trwały klucz sesji logowania: `/data/storage/.secret_key`

### 2. Konfiguracja zmiennych środowiskowych
W panelu dostawcy chmury (sekcja *Environment Variables* / *Secrets*) skonfiguruj:
- `LIBRUS_LOGIN`, `LIBRUS_PASSWORD`, `LIBRUS_LOGIN_NAME`, `LIBRUS_NOTIFICATION_RECEIVERS` (lub `LIBRUS_USERS`)
- `LIBRUS_MAIL__LOGIN`, `LIBRUS_MAIL__PASSWORD`, `LIBRUS_MAIL__USE_GMAIL=true`
- `LIBRUS_WEB__PASSWORD` (hasło do panelu WWW)
- `LIBRUS_DATA_DIR=/data`
- `TZ=Europe/Warsaw`

### 3. Polecenie startowe i Procfile
W repozytorium znajduje się plik [`Procfile`](../Procfile) definiujący start usługi WWW:
```text
web: python librus_web.py
```
Aplikacja automatycznie odczytuje dynamiczny port przydzielony przez chmurę ze standardowej zmiennej środowiskowej `$PORT` oraz nasłuchuje na adresie `0.0.0.0`. Panel WWW automatycznie uruchamia w tle wątek kolektora pobierającego dane ze szkoły.
