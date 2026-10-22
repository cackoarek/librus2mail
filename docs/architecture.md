# 🏛️ Architektura systemu i przepływ danych – Librus2mail

Niniejszy dokument przedstawia architekturę techniczną projektu **Librus2mail**, wzorce projektowe, strukturę bazy stanu oraz szczegółowy przepływ danych pomiędzy poszczególnymi warstwami aplikacji.

---

## 🎯 Zasady architektoniczne

1. **Local-first & Privacy by Design**:
   - Brak jakichkolwiek zewnętrznych serwerów chmurowych, telemetrycznych czy baz SaaS.
   - Wszystkie pobrane dane, hasła, historia ocen i wiadomości pozostają w 100% na urządzeniu użytkownika (w katalogu `storage/`).
2. **Pełna modułowość (Decoupled Design)**:
   - Każdy moduł (`collector`, `updates_notifier`, `progress_report`, `student_report`, `web`) ma pojedynczą odpowiedzialność (SRP) i może być uruchamiany niezależnie.
   - Komunikacja pomiędzy modułami opiera się wyłącznie na standaryzowanych strukturach danych i pamięci stanu (`BaseStorage`).
3. **Defensywny Scraping**:
   - Librus Synergia nie udostępnia oficjalnego publicznego API dla kont rodzicielskich. Komunikacja opiera się na symulacji przeglądarki.
   - Parsowanie HTML (`BeautifulSoup`) jest odporne na drobne zmiany struktury DOM (defensywne selektory, brak twardych indeksów, fallbacki).
4. **Atomowy zapis stanu**:
   - Operacje na plikach JSON realizowane są przez zapis do pliku tymczasowego z atomową zamianą nazwy (`os.replace`), co całkowicie eliminuje ryzyko uszkodzenia danych przy niespodziewanym wyłączeniu zasilania.

---

## 🏗️ Warstwy systemu i przepływ danych

```mermaid
flowchart TD
    subgraph Warstwa Źródłowa
        Librus["🏫 Portal Librus Synergia<br/>(OAuth / Gateway)"]
    end

    subgraph Warstwa Zbierania & Scrapingu
        LibrusClient["🔐 librus.py<br/>(OAuth Session & Requests)"]
        Parser["🔍 dom_parser.py<br/>(BeautifulSoup4 Parsers)"]
        Models["📦 domain_models.py<br/>(Domain Validation & Types)"]
    end

    subgraph Warstwa Pamięci Stanu (Storage)
        StorageInterface["📐 BaseStorage<br/>(Abstrakcyjny interfejs)"]
        FileStore["💾 FileStorage<br/>(storage/<login>.json)"]
    end

    subgraph Warstwa Analityki
        ProgAnalyzer["📈 ProgressAnalyzer<br/>(Średnie, trendy, alerty, frekwencja)"]
        StudAnalyzer["🏆 StudentAnalyzer<br/>(Psychologia motywacji, odznaki, supermoce)"]
        WebServices["⚙️ services.py<br/>(Agregacje dashboardu, symulator świadectwa)"]
    end

    subgraph Warstwa Prezentacji
        MailEngine["✉️ mail_sender.py<br/>(Jinja2 + Gmail / SMTP)"]
        WebEngine["🌐 web/app.py<br/>(Flask + HTMX + Tailwind Multi-Skin)"]
    end

    Librus -->|Żądania HTTPS + Cookies| LibrusClient
    LibrusClient -->|Surowy HTML| Parser
    Parser -->|Słowniki / Obiekty| Models
    Models -->|Zapis do bazy| StorageInterface
    StorageInterface --> FileStore
    FileStore -->|Odczyt historii| ProgAnalyzer
    FileStore -->|Odczyt ocen| StudAnalyzer
    FileStore -->|Odczyt kompletnego stanu| WebServices
    ProgAnalyzer -->|Dane do raportu postępów| MailEngine
    StudAnalyzer -->|Dane do raportu motywacyjnego| MailEngine
    WebServices -->|Kontekst widoków| WebEngine
```

---

## 🔄 Cykl życia danych (End-to-End Data Flow)

### 1. Faza autoryzacji (OAuth Flow)
1. **GET `OAUTH_URL`**: pobranie początkowego formularza logowania i wygenerowanie unikalnych tokenów sesyjnych.
2. **POST `AUTH_URL`**: przekazanie poświadczeń rodzica (`login`, `pass`).
3. **POST `2FA_URL`**: obsługa procedury pominięcia ekranu 2FA (jeśli nie jest wymuszony).
4. **GET `GRANT_URL`**: przejście przez bramkę uwierzytelniającą `synergia.librus.pl/gateway` i zapisanie finalnych ciasteczek autoryzacyjnych w sesji `requests.Session`.

### 2. Faza ekstrakcji danych (Scraping & DOM Parsing)
- Kolektor wykonuje sekwencję zapytań GET z zachowaniem 5-sekundowych przerw ochronnych:
  - Wiadomości (`/wiadomosci`)
  - Ogłoszenia (`/ogloszenia`)
  - Terminarz (`/terminarz`)
  - Plan lekcji (`/plan_lekcji`)
  - Oceny (`/przegladaj_oceny/uczen`)
  - Frekwencja (`/przegladaj_nb/uczen`)
- Parser `dom_parser.py` wyodrębnia dane tekstowe, identyfikatory oraz atrybuty `data-*` i tooltipy (nauczyciele, wagi, kategorie, usprawiedliwienia).
- Modele domenowe (`domain_models.py`) walidują poprawność typów.

### 3. Faza persystencji stanu (`storage.py`)
- Pobrane dane trafiają do instancji `FileStorage`.
- Tworzony jest unikalny plik JSON dla każdego konta ucznia: `storage/<login>.json`.
- Aktualizowane są listy znanych identyfikatorów (`known_grades`, `known_messages`, `known_notifications`) oraz znaczniki czasu synchronizacji.
- W razie potrzeby moduł archiwizacji rocznej przenosi dane z zakończonego roku szkolnego do podkatalogu `storage/archive/<rok>/`.

### 4. Faza analityki i reguł biznesowych
- **`ProgressAnalyzer`**:
  - Oblicza średnie ważone ocen w zadanym oknie czasowym (np. 7 dni).
  - Porównuje wyniki z bazą historyczną, określając trendy (wzrost, spadek, stabilizacja).
  - Weryfikuje zagrożenia ocenami niedostatecznymi oraz analizuje absencje.
- **`StudentAnalyzer`**:
  - Wyszukuje „Supermoce” (przedmioty z najwyższą średnią lub największą liczbą ocen 5/6).
  - Wylicza „Szanse na awans” (określa, ile ocen bardzo dobrych dzieli ucznia od przeskoczenia na wyższą ocenę semestralną).
  - Przyznaje motywacyjne odznaki za postępy.
- **`services.py` (Panel WWW)**:
  - Buduje zintegrowane kalendarium ostatnich N dni.
  - Wylicza symulację świadectwa z wyróżnieniem (próg średniej 4.75 i ocena z zachowania).
  - Udostępnia silnik optymalizatora celu edukacyjnego (*What-If Calculator*).

### 5. Faza prezentacji i dostarczania
- Szablony Jinja2 renderują responsywne wiadomości e-mail z osadzonymi stylami CSS (`yagmail` lub `smtplib`).
- Warstwa webowa serwuje interfejs HTML/HTMX z dynamicznymi aktualizacjami DOM bez przeładowywania całej strony.

---

## 📁 Struktura kodu źródłowego (`src/` layout)

Projekt zorganizowany jest zgodnie z zaleceniami PEP 517/518 w układzie `src/`:

```text
librus2mail/
├── src/
│   └── librus2mail/
│       ├── __init__.py           # Eksporty pakietu
│       ├── base_logger.py        # Centralna konfiguracja logowania (logger 'librus')
│       ├── config.py             # Parser i walidator konfiguracji YAML / ENV
│       ├── config_models.py      # Pydantic/dataclass modele ustawień
│       ├── date_utils.py         # Narzędzia parsowania dat i strefy czasowej Europe/Warsaw
│       ├── dom_parser.py         # Parsery BeautifulSoup (oceny, wiadomości, plan, frekwencja)
│       ├── domain_models.py      # Modele domenowe (Grade, Attendance, Schedule, Message)
│       ├── gmail_sender.py       # Klient pocztowy dla Gmaila (yagmail + OAuth2)
│       ├── librus.py             # Klient protokołu Synergia (OAuth i sesja HTTP)
│       ├── librus_collector.py   # Demon kolektora danych
│       ├── mail_sender.py        # Bazowy nadawca maili z silnikiem Jinja2
│       ├── progress_analyzer.py  # Silnik analizy postępów i trendów
│       ├── progress_report.py    # Moduł Raportu Postępów dla Rodziców
│       ├── smtp_sender.py        # Standardowy transport SMTP (STARTTLS / SSL)
│       ├── storage.py            # Warstwa bazy danych JSON i archiwizacji rocznej
│       ├── student_analyzer.py   # Silnik psychologii motywacji i odznak ucznia
│       ├── student_report.py     # Moduł Raportu Motywacyjnego dla Ucznia
│       ├── updates_notifier.py   # Moduł bieżących powiadomień e-mail
│       ├── web/                  # Moduł interaktywnego panelu WWW
│       │   ├── app.py            # Fabryka aplikacji Flask, routing, autoryzacja Parent Gate
│       │   ├── export.py         # Generator statycznych podglądów HTML do dokumentacji
│       │   └── services.py       # Usługi biznesowe dashboardu, terminarza i planu na żywo
│       └── templates/            # Szablony Jinja2
│           ├── emails/           # Szablony powiadomień i raportów e-mail
│           └── web/              # Szablony podstron panelu webowego (TailwindCSS)
├── tests/                        # Pełny zestaw testów automatycznych (pytest)
├── docs/                         # Szczegółowa dokumentacja techniczna i podręczniki
├── examples/                     # Przykłady konfiguracji, dane demonstracyjne i raporty
├── pyproject.toml                # Nowoczesna konfiguracja projektu i zależności (PEP 621)
└── requirements.txt              # Zgodność wsteczna dla tradycyjnych środowisk pip
```
