# 🧪 Przewodnik dla deweloperów i testy – Librus2mail

Niniejszy dokument przeznaczony jest dla programistów rozwijających projekt **Librus2mail**. Opisuje konfigurację środowiska deweloperskiego, zasady pisania testów, procedury kontroli jakości kodu oraz generowania materiałów demonstracyjnych.

---

## 🛠️ Konfiguracja środowiska deweloperskiego

Projekt wymaga interpretera **Python 3.10 lub nowszego** (wykorzystuje m.in. unie typów `X | Y`, operator mors `:=` oraz nowoczesne adnotacje typowania).

```bash
# 1. Klonowanie repozytorium
git clone https://github.com/acacko/librus2mail.git
cd librus2mail

# 2. Utworzenie i aktywacja środowiska wirtualnego
virtualenv venv -p python3.10
source venv/bin/activate

# 3. Instalacja projektu w trybie edytowalnym wraz z narzędziami deweloperskimi:
pip install -e ".[dev]"
```

Alternatywnie przy użyciu tradycyjnego `requirements.txt`:
```bash
pip install -r requirements.txt
pip install pytest pytest-cov ruff
```

---

## 🧪 Uruchamianie testów automatycznych

Testy zorganizowane są w katalogu `tests/` i wykorzystują framework `pytest`. Testy są w 100% niezależne od połączenia internetowego (mockują odpowiedzi HTTP oraz operacje I/O).

```bash
# Uruchomienie pełnego zestawu testów:
pytest tests/

# Uruchomienie testów z wyświetlaniem nazw i statusów:
pytest tests/ -v

# Uruchomienie konkretnego pliku testowego:
pytest tests/test_web.py

# Uruchomienie konkretnego testu po nazwie (parametr -k):
pytest tests/ -k "test_timeline_attendance_events"

# Uruchomienie testów z wyliczeniem pokrycia kodu (Coverage):
pytest --cov=src/librus2mail --cov-report=term-missing tests/
```

> [!IMPORTANT]
> **Zasada bezpiecznego testowania**:
> W testach jednostkowych i integracyjnych **nigdy** nie odpytujemy prawdziwych serwerów Librusa ani nie wysyłamy prawdziwych e-maili. Wykorzystuj mocki biblioteki `unittest.mock` (`patch`) oraz przykładowe bazy ze ścieżki `examples/storage/`.

---

## 🎨 Kontrola stylu i formatowanie kodu (Ruff)

W projekcie standardem formatowania i lintingu jest narzędzie **Ruff**. Zapewnia ono pełną zgodność z PEP 8 oraz natychmiastowe wykrywanie potencjalnych błędów.

```bash
# Sprawdzenie poprawności stylu i wykrycie błędów:
ruff check src/ tests/

# Automatyczna naprawa możliwych do skorygowania niezgodności:
ruff check --fix src/ tests/

# Sprawdzenie formatowania kodu:
ruff format --check src/ tests/

# Automatyczne sformatowanie plików projektu:
ruff format src/ tests/
```

### Konwencje kodowania:
- **Typowanie**: wszystkie nowe funkcje i metody powinny posiadać kompletne adnotacje typów (`list[dict[str, Any]]`, `Optional[str]`, `str | None`).
- **Logowanie**: w modułach używamy wyłącznie `logger = logging.getLogger(__name__)`. Nie używamy instrukcji `print()` (z wyjątkiem dedykowanych funkcji konsolowych w narzędziach CLI).
- **Język komentarzy i logów**: zachowujemy istniejącą konwencję polskojęzycznych komunikatów logów i komentarzy biznesowych.

---

## 📄 Regeneracja raportów demonstracyjnych

W repozytorium znajduje się zestaw 21 statycznych plików HTML w katalogu `examples/reports/`, prezentujących wszystkie ekrany panelu WWW oraz szablony e-mail w oparciu o anonimizowane dane testowe (`examples/storage/8979296.json`).

Aby zaktualizować wszystkie podglądy po wprowadzeniu zmian w szablonach HTML lub stylach CSS:

```bash
bash examples/reports/regenerate_reports.sh
```

Skrypt ten uruchomi generator dla:
- powiadomienia bieżącego kolektora (`powiadomienie_collector.html`),
- raportu postępów rodzica (`raport_8979296.html`),
- raportów ucznia w wersjach `kids`, `teens` i `youth`,
- wszystkich podstron panelu webowego (Dashboard, Plan, Oceny, Frekwencja, Terminarz, Ustawienia itd.).

---

## 🎬 Generowanie animowanego podglądu (Showcase GIF)

W katalogu `scripts/` znajduje się zautomatyzowany skrypt wykorzystujący bezgłową przeglądarkę Chromium / Chrome oraz narzędzie `ffmpeg` do nagrania płynnej animacji prezentującej aplikację:

```bash
# Wymagania: zainstalowany pakiet selenium oraz narzędzie ffmpeg w systemie:
sudo apt-get install ffmpeg chromium-browser

# Uruchomienie generatora klatek i renderowania GIF:
python scripts/generate_showcase.py
```

Skrypt wykonuje zrzuty ekranu ze stron demonstracyjnych `examples/reports/`, symuluje naturalne przewijanie zawartości i tworzy zoptymalizowany plik GIF / WebP w katalogu `docs/assets/`.

---

## 📦 Procedura wydań i wersjonowania

Projekt stosuje zasady **Semantic Versioning** (`MAJOR.MINOR.PATCH`) oraz format **Keep a Changelog**.

Przed utworzeniem nowego wydania:
1. Upewnij się, że wszystkie testy przechodzą: `pytest tests/` (249/249).
2. Sprawdź czystość kodu: `ruff check src/ tests/`.
3. Zaktualizuj plik `CHANGELOG.md` pod nagłówkiem `[Unreleased]`.
4. Wygeneruj świeże raporty demonstracyjne: `bash examples/reports/regenerate_reports.sh`.
5. Zgodnie z wytycznymi w [RELEASING.md](../RELEASING.md) podbij wersję w `pyproject.toml` i utwórz tag gita.
