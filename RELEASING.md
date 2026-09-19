# Jak wydawać wersje (Releasing)

Ten dokument opisuje proces wydawania nowych wersji projektu **librus2mail** z użyciem Git tagów i GitHub Actions.

---

## Strategia wersjonowania

Projekt stosuje **Semantic Versioning (SemVer)**:

```
MAJOR.MINOR.PATCH  →  np. 1.2.3
```

| Typ zmiany | Bump | Przykład |
|:---|:---|:---|
| Poprawka błędu | PATCH: `1.2.3 → 1.2.4` | naprawa parsowania ocen |
| Nowa funkcja (kompatybilna wstecz) | MINOR: `1.2.3 → 1.3.0` | nowy parametr CLI |
| Złamanie kompatybilności | MAJOR: `1.2.3 → 2.0.0` | zmiana formatu `config.yaml` |

---

## Pierwsze uruchomienie: konfiguracja GitHub Pages

> [!IMPORTANT]
> Ten krok wykonujesz **tylko raz** — przed pierwszym wydaniem. Po tej konfiguracji wszystko
> działa automatycznie przy każdym `git push origin vX.Y.Z`.

### Krok 1 – Włącz GitHub Pages w ustawieniach repozytorium

1. Wejdź na stronę repozytorium na GitHub
2. Kliknij zakładkę **Settings** (⚙️)
3. W lewym menu wybierz **Pages**
4. W sekcji **"Build and deployment"**:
   - **Source**: wybierz `Deploy from a branch`
   - **Branch**: wybierz `gh-pages` → folder `/ (root)`
5. Kliknij **Save**

> Gałąź `gh-pages` zostanie stworzona automatycznie przy pierwszym wydaniu.
> Jeśli jej jeszcze nie ma, GitHub pokaże błąd — to normalne, zniknie po pierwszym release.

### Krok 2 – Sprawdź uprawnienia workflow

W **Settings → Actions → General** upewnij się że:
- **Workflow permissions** → `Read and write permissions` jest zaznaczone

Bez tego `github-actions[bot]` nie będzie mógł pushować do `gh-pages`.

### Krok 3 – Wydaj pierwszą wersję

```bash
git tag v1.1.0 -m "Pierwsza wersja z GitHub Pages"
git push origin v1.1.0
```

Po ok. 2–3 minutach raporty będą dostępne pod:
- `https://cackoarek.github.io/librus2mail/latest/`
- `https://cackoarek.github.io/librus2mail/v1.1.0/`

---

## Standard commit messages: Conventional Commits

Każdy commit powinien zaczynać się od **type(scope): description**:

```
feat(notifier): dodaj parametr --actual-date
fix(librus): napraw parsowanie ocen z wagą 0
docs: zaktualizuj useful-scripts.md
chore: bump dependencies
ci: dodaj workflow release
refactor(storage): uprość FileStorage
test: dodaj testy do progress_report
```

Typy commit messages i ich znaczenie:

| Prefix | Opis |
|:---|:---|
| `feat:` | Nowa funkcja |
| `fix:` | Poprawka błędu |
| `docs:` | Tylko dokumentacja |
| `chore:` | Utrzymanie, zależności, konfiguracja |
| `ci:` | Zmiany w GitHub Actions / pipeline |
| `refactor:` | Refaktoryzacja bez zmiany zachowania |
| `test:` | Dodanie lub poprawa testów |
| `perf:` | Poprawa wydajności |

> [!TIP]
> Conventional Commits nie są wymagane przez workflow, ale ułatwiają czytanie historii Git
> i są automatycznie używane do generowania Release Notes przy wydaniu.

---

## Pipeline wydania (co robi GitHub Actions)

Po wypchnięciu tagu `v*` uruchamia się automatyczny pipeline w 4 krokach:

```
git push origin v1.1.0
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  1. TEST GATE (.github/workflows/release.yml)           │
│     • pytest (3.10)                                     │
│     • ruff check .                                      │
│     • ❌ Fail → pipeline zatrzymany, tag pozostaje      │
└─────────────────────┬───────────────────────────────────┘
                      │ ✅
                      ▼
┌─────────────────────────────────────────────────────────┐
│  2. BUMP VERSION & CHANGELOG                            │
│     • aktualizuje version w pyproject.toml              │
│     • aktualizuje __version__ w __init__.py             │
│     • aktualizuje CHANGELOG.md (z [Unreleased] lub gita)│
│     • commit "chore(release): bump version... [skip ci]"│
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  3. GITHUB RELEASE                                      │
│     • tworzy Release na stronie GitHub                  │
│     • generuje Release Notes z historii commitów        │
│       (z podziałem na feat/fix/docs/chore)              │
│     • pre-release jeśli tag zawiera myślnik (v1.0.0-rc1)│
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  4. DOCKER IMAGE (.github/workflows/docker.yml)         │
│     • build + smoke test                                │
│     • push do GHCR:                                     │
│       ghcr.io/<owner>/librus2mail:1.1.0                 │
│       ghcr.io/<owner>/librus2mail:1.1                   │
│       ghcr.io/<owner>/librus2mail:latest                │
└─────────────────────────────────────────────────────────┘
```

---

## Krok po kroku: jak zrobić release

### 1. Przygotuj kod

```bash
# Upewnij się że jesteś na main z najnowszymi zmianami
git checkout main
git pull

# Sprawdź czy testy przechodzą lokalnie
source venv/bin/activate
pytest
ruff check .
```

### 2. (Opcjonalnie) Uzupełnij sekcję [Unreleased] w CHANGELOG.md

Proces wydania w GitHub Actions automatycznie uzupełnia plik [`CHANGELOG.md`](CHANGELOG.md):
- Jeśli wpiszesz własne punkty w sekcji `## [Unreleased]`, skrypt przeniesie je do nowej wersji i zaktualizuje linki na dole.
- Jeśli sekcja `## [Unreleased]` pozostanie pusta, skrypt wygeneruje wpisy automatycznie na podstawie historii commitów Git (Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`).

Jeśli chcesz dodać własne notatki przed wydaniem:
```markdown
## [Unreleased]

### Dodane
- Moja nowa funkcja
```

Zacommituj ewentualne wpisy:
```bash
git add CHANGELOG.md
git commit -m "docs: przygotuj wpisy w changelog dla nowego wydania"
git push
```

### 3. Utwórz tag Git

```bash
# Format: vMAJOR.MINOR.PATCH
git tag v1.1.0 -m "Powiadomienia zbiorcze, --actual-date, komentarze do ocen"

# Pre-release (opcjonalnie):
git tag v1.1.0-rc1 -m "Release candidate 1"
```

### 4. Wypchnij tag – to wystarcza

```bash
git push origin v1.1.0
```

Od tego momentu GitHub Actions robi wszystko automatycznie (patrz diagram powyżej).

### 5. Weryfikacja

- Otwórz zakładkę **Actions** na GitHub → sprawdź czy pipeline `Release – Tag & Publish` przeszedł ✅
- Otwórz zakładkę **Releases** → sprawdź czy Release z Release Notes jest widoczny
- Opcjonalnie sprawdź **Packages** → czy Docker image jest dostępny z nowym tagiem

---

## Wersje pre-release (RC, Beta, Alpha)

Tag z myślnikiem jest automatycznie oznaczany jako pre-release:

```bash
git tag v2.0.0-rc1 -m "Release candidate – nowy format config"
git push origin v2.0.0-rc1
# → GitHub Release z flagą "Pre-release" (nie nadpisuje "latest")
```

---

## Cofnięcie tagu (jeśli coś poszło nie tak)

```bash
# Usuń tag lokalnie
git tag -d v1.1.0

# Usuń tag zdalnie (i usuń Release ręcznie na GitHub)
git push origin --delete v1.1.0
```

> [!CAUTION]
> Usunięcie tagu nie cofa automatycznie Docker image już opublikowanego do GHCR.
> Obraz możesz usunąć ręcznie w ustawieniach repozytorium → Packages.

---

## Pliki powiązane z procesem wydań

| Plik | Rola |
|:---|:---|
| [`CHANGELOG.md`](CHANGELOG.md) | Historia wersji (prowadzona ręcznie) |
| [`.github/workflows/release.yml`](.github/workflows/release.yml) | Workflow wydania (test → bump → release) |
| [`.github/workflows/docker.yml`](.github/workflows/docker.yml) | Build i push Docker image |
| [`.github/pull_request_template.md`](.github/pull_request_template.md) | Szablon PR z checklistą |
| [`pyproject.toml`](pyproject.toml) | Źródło prawdy dla numeru wersji |
| [`src/librus2mail/__init__.py`](src/librus2mail/__init__.py) | `__version__` synchronizowany przy release |
