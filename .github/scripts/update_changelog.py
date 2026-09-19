#!/usr/bin/env python3
"""
Skrypt automatycznie aktualizujący plik CHANGELOG.md przy wydawaniu nowej wersji (GitHub Actions Release).
- Jeśli pod sekcją ## [Unreleased] znajdują się wpisy, przenosi je do nowej sekcji ## [VERSION] – RRRR-MM-DD.
- Jeśli sekcja ## [Unreleased] jest pusta, generuje wpisy automatycznie z historii commitów gita (Conventional Commits).
- Uaktualnia linki porównawcze na dole pliku.
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(description="Aktualizuj CHANGELOG.md dla nowej wersji")
    parser.add_argument("--version", default=os.environ.get("VERSION"), help="Numer wersji (np. 1.1.2)")
    parser.add_argument("--tag", default=os.environ.get("TAG"), help="Tag gita (np. v1.1.2)")
    parser.add_argument("--changelog", default="CHANGELOG.md", help="Ścieżka do pliku CHANGELOG.md")
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "cackoarek/librus2mail"),
        help="Właściciel/repozytorium na GitHub",
    )
    parser.add_argument("--date", default=None, help="Data wydania (domyślnie dzisiejsza: YYYY-MM-DD)")
    return parser.parse_args()


def get_git_tags(current_tag: str | None) -> list[str]:
    try:
        tags = subprocess.check_output(
            ["git", "tag", "--sort=-version:refname"], text=True
        ).splitlines()
        return [t.strip() for t in tags if t.strip()]
    except Exception:
        return []


def get_commits_between(prev_tag: str | None, target_ref: str) -> list[str]:
    cmd = ["git", "log"]
    if prev_tag:
        cmd.append(f"{prev_tag}..{target_ref}")
    else:
        cmd.extend(["-n", "30", target_ref])
    cmd.extend(["--pretty=format:%s", "--no-merges"])
    try:
        return subprocess.check_output(cmd, text=True).splitlines()
    except Exception:
        return []


def categorize_commits(commits: list[str]) -> list[str]:
    features = []
    fixes = []
    refactors = []
    docs = []
    other = []

    for c in commits:
        c = c.strip()
        if not c or c.startswith("chore(release):") or c.startswith("Merge "):
            continue

        if re.match(r"^feat(\([^)]+\))?:", c, re.IGNORECASE):
            desc = re.sub(r"^feat(\([^)]+\))?:\s*", "", c, flags=re.IGNORECASE)
            features.append(f"- {desc}")
        elif re.match(r"^fix(\([^)]+\))?:", c, re.IGNORECASE):
            desc = re.sub(r"^fix(\([^)]+\))?:\s*", "", c, flags=re.IGNORECASE)
            fixes.append(f"- {desc}")
        elif re.match(r"^refactor(\([^)]+\))?:", c, re.IGNORECASE):
            desc = re.sub(r"^refactor(\([^)]+\))?:\s*", "", c, flags=re.IGNORECASE)
            refactors.append(f"- {desc}")
        elif re.match(r"^docs(\([^)]+\))?:", c, re.IGNORECASE):
            desc = re.sub(r"^docs(\([^)]+\))?:\s*", "", c, flags=re.IGNORECASE)
            docs.append(f"- {desc}")
        else:
            other.append(f"- {c}")

    lines = []
    if features:
        lines.append("### Dodane")
        lines.extend(features)
        lines.append("")
    if fixes:
        lines.append("### Naprawione")
        lines.extend(fixes)
        lines.append("")
    if refactors:
        lines.append("### Zmienione")
        lines.extend(refactors)
        lines.append("")
    if docs:
        lines.append("### Dokumentacja")
        lines.extend(docs)
        lines.append("")
    if other and not (features or fixes or refactors or docs):
        lines.append("### Inne zmiany")
        lines.extend(other)
        lines.append("")

    return lines


def update_changelog_content(
    content: str,
    version: str,
    tag: str,
    prev_tag: str | None,
    repo: str,
    release_date: str,
    commits: list[str] | None = None,
) -> str:
    # 1. Jeśli ta wersja już istnieje w changelogu, nie duplikuj
    if f"## [{version}]" in content:
        print(f"ℹ️ Wersja [{version}] jest już udokumentowana w CHANGELOG.md.")
        return content

    # 2. Podział na nagłówek z ## [Unreleased] oraz resztę pliku
    if "## [Unreleased]" not in content:
        raise ValueError("Nie znaleziono sekcji '## [Unreleased]' w pliku CHANGELOG.md")

    parts = content.split("## [Unreleased]", 1)
    header = parts[0] + "## [Unreleased]\n\n"
    rest = parts[1]

    # Szukamy początku kolejnej sekcji wersji (np. \n## [1.1.0])
    next_ver_match = re.search(r"\n## \[", rest)
    if next_ver_match:
        unreleased_block = rest[:next_ver_match.start()].strip()
        remaining = rest[next_ver_match.start():]
    else:
        unreleased_block = rest.strip()
        remaining = ""

    # Usunięcie separatora '---' z bloku unreleased, jeśli jest
    clean_unreleased = re.sub(r"^\s*---\s*|\s*---\s*$", "", unreleased_block).strip()

    has_unreleased_entries = bool(re.search(r"###|\s*-\s+", clean_unreleased))

    if has_unreleased_entries:
        # Przenieś istniejące wpisy z [Unreleased] do nowej sekcji
        new_version_body = clean_unreleased
    else:
        # Wygeneruj wpisy z commitów
        categorized_lines = categorize_commits(commits or [])
        if categorized_lines:
            new_version_body = "\n".join(categorized_lines).strip()
        else:
            new_version_body = f"- Aktualizacja wydania {tag}"

    new_section = f"## [{version}] – {release_date}\n\n{new_version_body}"

    # Złożenie nowej zawartości
    assembled = f"{header}---\n\n{new_section}\n\n---{remaining}"

    # 3. Aktualizacja linków porównawczych na dole
    assembled = re.sub(
        r"\[Unreleased\]:\s*https://github\.com/[^\s]+/compare/[^\s]+\.\.\.HEAD",
        f"[Unreleased]: https://github.com/{repo}/compare/{tag}...HEAD",
        assembled,
    )

    if prev_tag:
        version_link = f"[{version}]: https://github.com/{repo}/compare/{prev_tag}...{tag}"
    else:
        version_link = f"[{version}]: https://github.com/{repo}/releases/tag/{tag}"

    if f"[{version}]:" not in assembled:
        assembled = re.sub(
            r"(\[Unreleased\]:[^\n]+\n)",
            f"\\1{version_link}\n",
            assembled,
            count=1,
        )

    return assembled


def main():
    args = parse_args()
    if not args.version:
        print("Błąd: Nie podano numeru wersji (--version lub zmienna VERSION).", file=sys.stderr)
        sys.exit(1)

    version = args.version.lstrip("v")
    tag = args.tag or f"v{version}"
    release_date = args.date or datetime.now().strftime("%Y-%m-%d")

    if not os.path.isfile(args.changelog):
        print(f"Błąd: Plik '{args.changelog}' nie istnieje.", file=sys.stderr)
        sys.exit(1)

    with open(args.changelog, encoding="utf-8") as f:
        content = f.read()

    tags = get_git_tags(tag)
    prev_tag = next((t for t in tags if t != tag), None)
    commits = get_commits_between(prev_tag, tag)

    new_content = update_changelog_content(
        content=content,
        version=version,
        tag=tag,
        prev_tag=prev_tag,
        repo=args.repo,
        release_date=release_date,
        commits=commits,
    )

    if new_content != content:
        with open(args.changelog, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"✅ Pomyślnie zaktualizowano {args.changelog} dla wersji {version} ({release_date}).")
    else:
        print(f"ℹ️ Brak zmian w {args.changelog}.")


if __name__ == "__main__":
    main()
