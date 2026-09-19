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
│  2. BUMP VERSION                                        │
│     • aktualizuje version w pyproject.toml              │
│     • aktualizuje __version__ w __init__.py             │
│     • commit "chore(release): bump version to X.Y.Z"   │
│       (z [skip ci] – nie odpala CI ponownie)            │
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

### 2. Zaktualizuj CHANGELOG.md

Otwórz [`CHANGELOG.md`](CHANGELOG.md) i przesuń zawartość sekcji `[Unreleased]` do nowej wersji:

```markdown
## [1.1.0] – 2026-09-20

### Dodane
- Parametr --actual-date w updates_notifier i progress_report
- ...

## [Unreleased]
(sekcja pusta – gotowa na kolejne zmiany)
```

Zaktualizuj też linki na dole pliku:
```markdown
[Unreleased]: https://github.com/<owner>/librus2mail/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/<owner>/librus2mail/compare/v1.0.0...v1.1.0
```

Zacommituj zmianę:
```bash
git add CHANGELOG.md
git commit -m "docs: aktualizuj CHANGELOG do wersji 1.1.0"
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
