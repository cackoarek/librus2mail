## Opis zmian

<!-- Krótki opis co i dlaczego zostało zmienione -->

## Typ zmiany

<!-- Zaznacz odpowiedni typ (ma wpływ na wersjonowanie SemVer): -->

| Typ commita | Przykład | Bump wersji |
|:---|:---|:---|
| `fix:` | `fix(librus): napraw parsowanie ocen` | PATCH (1.0.x) |
| `feat:` | `feat(notifier): dodaj --actual-date` | MINOR (1.x.0) |
| `feat!:` lub `BREAKING CHANGE:` | `feat!: zmień format config.yaml` | MAJOR (x.0.0) |
| `docs:` | `docs: zaktualizuj README` | — |
| `chore:` | `chore: bump dependencies` | — |
| `ci:` | `ci: dodaj workflow release` | — |
| `refactor:` | `refactor(storage): uprość FileStorage` | — |
| `test:` | `test: dodaj testy do progress_report` | — |

## Checklist

- [ ] Commit messages są zgodne z **Conventional Commits** (`type(scope): description`)
- [ ] Testy przechodzą lokalnie (`pytest`)
- [ ] Linter nie zgłasza błędów (`ruff check .`)
- [ ] Dokumentacja zaktualizowana (jeśli dotyczy)
- [ ] `config.yaml`, `*.log`, `.env` **nie są** w tym PR

## Powiązane zgłoszenia / Issues

<!-- Closes #123 -->
