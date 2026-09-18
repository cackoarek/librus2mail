# Wdrożenie za pomocą systemd (Linux / Raspberry Pi / VPS)

Katalog zawiera gotowe pliki jednostek `systemd` umożliwiające uruchomienie aplikacji Librus2mail jako usługi systemowej z automatycznym restartem oraz harmonogramem raportów.

---

## 1. Usługa monitorująca: `librus2mail.service`

Działa nieprzerwanie w tle, sprawdzając e-dziennik co zadany w `config.yaml` interwał.

### Instalacja:

1. **Dostosuj ścieżki i użytkownika w pliku `librus2mail.service`**:
   - `User=twoj_uzytkownik` (np. `pi` lub `ubuntu`)
   - `WorkingDirectory=/home/twoj_uzytkownik/librus2mail`
   - `ExecStart=/home/twoj_uzytkownik/librus2mail/venv/bin/librus-collector config.yaml`

2. **Skopiuj plik do katalogu systemd**:
   ```bash
   sudo cp deploy/systemd/librus2mail.service /etc/systemd/system/
   ```

3. **Przeładuj konfigurację i uruchom usługę**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now librus2mail.service
   ```

4. **Sprawdzenie statusu i podgląd logów w czasie rzeczywistym**:
   ```bash
   sudo systemctl status librus2mail.service
   journalctl -u librus2mail.service -f
   ```

---

## 2. Harmonogram raportów postępów: `librus2mail-report.timer`

Uruchamia generowanie i wysyłkę raportu postępów (np. co tydzień w piątek o 17:00) bez konieczności konfiguracji tradycyjnego crontaba.

### Instalacja:

1. **Dostosuj ścieżki w `librus2mail-report.service`**:
   - `User=twoj_uzytkownik`
   - `WorkingDirectory=/home/twoj_uzytkownik/librus2mail`
   - `ExecStart=/home/twoj_uzytkownik/librus2mail/venv/bin/librus-report`

2. **Opcjonalnie zmień czas w `librus2mail-report.timer`**:
   - Domyślnie: `OnCalendar=Fri *-*-* 17:00:00` (piątek 17:00)
   - Niedziela 19:00: `OnCalendar=Sun *-*-* 19:00:00`

3. **Skopiuj pliki do katalogu systemd**:
   ```bash
   sudo cp deploy/systemd/librus2mail-report.service /etc/systemd/system/
   sudo cp deploy/systemd/librus2mail-report.timer /etc/systemd/system/
   ```

4. **Aktywuj timer**:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now librus2mail-report.timer
   ```

5. **Sprawdzenie zaplanowanych wyzwalaczy**:
   ```bash
   systemctl list-timers --all | grep librus
   ```
