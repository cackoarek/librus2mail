# ❓ Najczęstsze pytania i rozwiązywanie problemów (FAQ) – Librus2mail

Zbiór najczęstszych pytań, wątpliwości oraz sprawdzonych rozwiązań typowych problemów konfiguracyjnych i sieciowych w aplikacji **Librus2mail**.

---

## 🔐 1. W logach pojawia się błąd „Brak dostępu” (`NotLogged` lub błąd 403)

### Przyczyna:
Kolektor nie mógł zalogować się do portalu Librus Synergia przy użyciu podanych danych uwierzytelniających.

### Rozwiązanie:
1. **Sprawdź poprawność loginu i hasła**: upewnij się, że logujesz się danymi **konta rodzica**, a nie konta ucznia (login rodzica zazwyczaj kończy się literą `u` lub cyframi przypisanymi przez szkołę).
2. **Zaloguj się ręcznie przez przeglądarkę**: wejdź na stronę [portal.librus.pl/rodzina/synergia/loguj](https://portal.librus.pl/rodzina/synergia/loguj).
   - Librus okresowo (np. co 30 lub 90 dni) wymusza zmianę hasła. Jeśli na stronie pojawi się komunikat o konieczności zmiany hasła, zmień je w portalu, a następnie zaktualizuj w pliku `config.yaml` lub panelu `/ustawienia`.
   - Sprawdź, czy szkoła nie wyświetliła obowiązkowego komunikatu/ankiety wymagającej kliknięcia „Zapoznałem się z regulaminem” przed uzyskaniem dostępu do ocen.
3. **Wymuszone 2FA**: upewnij się, że na koncie nie włączono obowiązkowego uwierzytelniania dwuskładnikowego SMS/kodem aplikacji mobilnej.

---

## ✉️ 2. Wiadomości w oficjalnym portalu Librus oznaczają się jako przeczytane

### Przyczyna:
W systemie Librus Synergia wejście pod adres `/wiadomosci/szczegoly/...` jest jednoznaczne z oznaczeniem wiadomości jako odczytana przez rodzica. Domyślnie Librus2mail pobiera treść wiadomości, aby umieścić jej treść bezpośrednio w e-mailu.

### Rozwiązanie:
Jeśli zależy Ci, aby wiadomości pozostawały nieprzeczytane w portalu szkoły (np. aby drugi rodzic widział pogrubiony wpis w Synergii):
- Ustaw opcję `read_messages: false` w sekcji konta w pliku `config.yaml` lub odznacz odpowiednią opcję w zakładce `/ustawienia`.
- Kolektor pobierze wówczas jedynie metadane wiadomości (nadawcę, datę i tytuł), nie wchodząc w szczegóły treści, dzięki czemu status wiadomości w Synergii pozostanie nienaruszony.

---

## 📧 3. Błąd uwierzytelnienia Gmaila (`SMTPAuthenticationError`)

### Przyczyna:
Firma Google zablokowała możliwość logowania się do serwerów pocztowych za pomocą standardowego hasła do konta Google w ramach wycofywania tzw. „Mniej bezpiecznych aplikacji”.

### Rozwiązanie:
1. Wejdź na swoje konto Google: [myaccount.google.com](https://myaccount.google.com/).
2. W menu bocznym wybierz **Bezpieczeństwo**.
3. Upewnij się, że masz włączoną **Weryfikację dwuetapową (2FA)**.
4. W polu wyszukiwania u góry wpisz: **Hasła do aplikacji** (App Passwords).
5. Utwórz nowe hasło, wpisując nazwę np. `Librus2mail`.
6. Otrzymasz 16-znakowy ciąg znaków (np. `abcd efgh ijkl mnop`). Wklej go do `config.yaml` jako `mail.password`.
7. Alternatywnie możesz skorzystać z logowania przez protokół **OAuth 2.0** (`oauth2_file`).

---

## 🛡️ 4. Czy moje konto w Librusie może zostać zablokowane za scraping?

### Odpowiedź:
**Nie.** Librus2mail został zaprojektowany z zachowaniem najwyższych standardów bezpieczeństwa:
- **Sztywne opóźnienia (`sleep(5)`)**: kolektor odczekuje 5 sekund pomiędzy zapytaniami do kolejnych zakładek (oceny, wiadomości, terminarz, frekwencja), co generuje ruch nieodróżnialny od naturalnego przeglądania strony przez człowieka.
- **Rotacja User-Agent**: nagłówki zapytań imitują najpopularniejsze przeglądarki (Chrome, Firefox, Safari).
- **Rozsądny interwał odpytywania**: domyślny czas uśpienia wynosi 900 sekund (15 minut). Nigdy nie ustawiaj interwału mniejszego niż 300 sekund.

---

## 👨‍👩‍👧‍👦 5. Mam kilkoro dzieci w szkole – jak to skonfigurować?

Librus2mail natywnie wspiera dowolną liczbę dzieci:
1. Dodaj kolejne wpisy na liście `librus_users` w `config.yaml` (każde dziecko z osobnym loginem i hasłem rodzica).
2. Możesz przypisać różne adresy odbiorców dla każdego dziecka (np. mama otrzymuje maile o jednym dziecku, tata o drugim, lub oboje wspólnie).
3. Jeśli wolisz otrzymywać jeden zbiorczy e-mail ze statystykami wszystkich dzieci naraz, włącz opcję:
   ```yaml
   one_summary_message: true
   ```
4. W panelu WWW (`librus_web.py`) w prawym górnym rogu pojawi się wygodny przełącznik profili uczniów, umożliwiający błyskawiczne przełączanie podglądu.

---

## 🔑 6. Zapomniałem hasła do panelu rodzica WWW (`Parent Gate`)

Jeśli ustawiłeś hasło do panelu webowego i nie pamiętasz go:
- **Opcja 1 (Szybki restart)**: uruchom serwer z flagą `--no-auth`:
  ```bash
  python librus_web.py --no-auth
  ```
- **Opcja 2 (Podanie nowego hasła w CLI)**:
  ```bash
  python librus_web.py --password NoweBezpieczneHaslo
  ```
- **Opcja 3 (Edycja pliku)**: zmień wartość pola `web.password` bezpośrednio w pliku `config.yaml`.

---

## 🚫 7. Przedmiot bez ocen na świadectwie (np. religia/etyka, wychowanie do życia w rodzinie)

Jeśli uczeń nie uczęszcza na dany przedmiot lub jest on nieobowiązkowy:
1. Przejdź w panelu WWW do zakładki **Oceny** -> **Świadectwo z wyróżnieniem**.
2. W tabeli przedmiotów kliknij przełącznik w kolumnie **Na świadectwie**.
3. Przedmiot zostanie wyłączony z kalkulacji średniej końcowej, a wybór zostanie trwale zapamiętany w bazie `storage/`.
