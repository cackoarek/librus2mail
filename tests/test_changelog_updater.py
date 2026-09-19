"""Testy dla automatycznego aktualizatora pliku CHANGELOG.md (.github/scripts/update_changelog.py)."""

import importlib.util
import os
import unittest

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", ".github", "scripts", "update_changelog.py")
spec = importlib.util.spec_from_file_location("update_changelog", os.path.abspath(SCRIPT_PATH))
update_changelog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(update_changelog)


class TestChangelogUpdater(unittest.TestCase):
    def setUp(self):
        self.sample_changelog = """# Changelog

Wszystkie istotne zmiany w projekcie są dokumentowane w tym pliku.

---

## [Unreleased]

---

## [1.1.0] – 2026-09-19

### Dodane
- Poprzednia funkcja

---

[Unreleased]: https://github.com/cackoarek/librus2mail/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/cackoarek/librus2mail/releases/tag/v1.1.0
"""

    def test_update_when_unreleased_has_manual_entries(self):
        content = """# Changelog

## [Unreleased]

### Dodane
- Własnoręcznie wpisana nowa funkcja

---

## [1.1.0] – 2026-09-19
"""
        res = update_changelog.update_changelog_content(
            content=content,
            version="1.1.1",
            tag="v1.1.1",
            prev_tag="v1.1.0",
            repo="cackoarek/librus2mail",
            release_date="2026-09-20",
        )

        self.assertIn("## [1.1.1] – 2026-09-20", res)
        self.assertIn("Własnoręcznie wpisana nowa funkcja", res)
        # Sekcja [Unreleased] powinna być wyczyszczona z tego wpisu
        unreleased_block = res.split("## [Unreleased]")[1].split("## [1.1.1]")[0]
        self.assertNotIn("Własnoręcznie wpisana nowa funkcja", unreleased_block)

    def test_update_when_unreleased_empty_generates_from_commits(self):
        commits = [
            "feat(collector): dodaj opcję x",
            "fix(librus): napraw błąd 2FA",
            "docs: zaktualizuj readme",
            "refactor: uprość kod",
            "chore(release): bump version to 1.1.1 [skip ci]",
        ]
        res = update_changelog.update_changelog_content(
            content=self.sample_changelog,
            version="1.1.1",
            tag="v1.1.1",
            prev_tag="v1.1.0",
            repo="cackoarek/librus2mail",
            release_date="2026-09-20",
            commits=commits,
        )

        self.assertIn("## [1.1.1] – 2026-09-20", res)
        self.assertIn("### Dodane", res)
        self.assertIn("- dodaj opcję x", res)
        self.assertIn("### Naprawione", res)
        self.assertIn("- napraw błąd 2FA", res)
        self.assertIn("### Dokumentacja", res)
        self.assertIn("- zaktualizuj readme", res)
        self.assertIn("### Zmienione", res)
        self.assertIn("- uprość kod", res)
        # Linki na dole
        self.assertIn("[Unreleased]: https://github.com/cackoarek/librus2mail/compare/v1.1.1...HEAD", res)
        self.assertIn("[1.1.1]: https://github.com/cackoarek/librus2mail/compare/v1.1.0...v1.1.1", res)

    def test_idempotent_when_version_already_in_changelog(self):
        res = update_changelog.update_changelog_content(
            content=self.sample_changelog,
            version="1.1.0",
            tag="v1.1.0",
            prev_tag="v1.0.0",
            repo="cackoarek/librus2mail",
            release_date="2026-09-20",
        )
        self.assertEqual(res, self.sample_changelog)


if __name__ == "__main__":
    unittest.main()
