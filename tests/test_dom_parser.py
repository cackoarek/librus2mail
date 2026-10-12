"""
Testy jednostkowe defensywnego parsera HTML (DOM Parser) działające w 100% offline.
Weryfikacja odporności na zmiany układu stron Librusa, obsługa fixture'ów oraz przypadków brzegowych.
"""

from pathlib import Path

from librus2mail.dom_parser import (
    parse_announcements_html,
    parse_grades_html,
    parse_messages_html,
    parse_schedule_html,
    parse_subjects_from_html,
    parse_timetable_html,
    parse_tooltip_kv,
    safe_get_text,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestDomParserHelpers:
    """Testy podstawowych funkcji pomocniczych parsera."""

    def test_safe_get_text(self):
        assert safe_get_text(None) == ""
        assert safe_get_text(None, default="brak") == "brak"

    def test_parse_tooltip_kv(self):
        tooltip = (
            "Kategoria: Sprawdzian<br/>"
            "Data: 2026-10-15<br />"
            "Nauczyciel: Jan Kowalski<br>"
            "Waga: 3<br>"
            "Komentarz: <b>Dział 1</b>"
        )
        res = parse_tooltip_kv(tooltip)
        assert res.get("kategoria") == "Sprawdzian"
        assert res.get("data") == "2026-10-15"
        assert res.get("nauczyciel") == "Jan Kowalski"
        assert res.get("waga") == "3"
        assert res.get("komentarz") == "Dział 1"

    def test_parse_tooltip_empty_or_malformed(self):
        assert parse_tooltip_kv(None) == {}
        assert parse_tooltip_kv("") == {}
        assert parse_tooltip_kv("Pojedynczy tekst bez dwukropka") == {}


class TestMessagesParser:
    """Testy parsowania skrzynki wiadomości."""

    def test_parse_messages_fixture(self):
        fixture_html = (FIXTURES_DIR / "messages.html").read_text(encoding="utf-8")
        messages = parse_messages_html(fixture_html, known_messages=set())

        assert len(messages) == 2
        # Najnowsza pierwsza
        m1 = messages[0]
        assert m1.title == "Wycieczka szkolna do teatru"
        assert m1.sender == "Anna Kowalska"
        assert m1.has_attachment is True
        assert m1.is_unread is True
        assert m1.link == "/wiadomosci/szczegoly/101"

        m2 = messages[1]
        assert m2.title == "Informacja o zebraniu rodziców"
        assert m2.sender == "Piotr Nowak"
        assert m2.has_attachment is False

    def test_parse_messages_with_known_set(self):
        fixture_html = (FIXTURES_DIR / "messages.html").read_text(encoding="utf-8")
        # Symulujemy, że wiadomość 2 jest już znana
        known = {"Informacja o zebraniu rodziców2026-10-10 14:15:00Nowak Piotr (Wychowawca)"}
        messages = parse_messages_html(fixture_html, known_messages=known)

        assert messages[0].is_unread is True
        assert messages[1].is_unread is False

    def test_parse_messages_empty_or_broken_html(self):
        assert parse_messages_html("<html><body>Brak wiadomości</body></html>") == []
        assert parse_messages_html("<table><tr><td>Za mało kolumn</td></tr></table>") == []


class TestAnnouncementsParser:
    """Testy parsowania ogłoszeń szkolnych."""

    def test_parse_announcements_fixture(self):
        fixture_html = (FIXTURES_DIR / "announcements.html").read_text(encoding="utf-8")
        announcements = parse_announcements_html(fixture_html)

        assert len(announcements) == 2
        a1 = announcements[0]
        assert a1.title == "Dni wolne od zajęć dydaktycznych"
        assert a1.sender == "Sekretariat"
        assert a1.datetime == "2026-09-05"
        assert "harmonogramie" in a1.body

        a2 = announcements[1]
        assert a2.title == "Rozpoczęcie roku szkolnego"
        assert a2.sender == "Dyrekcja Szkoły"

    def test_parse_announcements_empty_html(self):
        assert parse_announcements_html("<div>Brak ogłoszeń</div>") == []


class TestGradesParser:
    """Testy parsowania ocen ucznia."""

    def test_parse_grades_fixture(self):
        fixture_html = (FIXTURES_DIR / "grades.html").read_text(encoding="utf-8")
        grades = parse_grades_html(fixture_html)

        # 3 oceny (2 z polskiego, 1 z matematyki), ukryta ocena 999999 zignorowana
        assert len(grades) == 3
        ids = {g.id for g in grades}
        assert ids == {"1001", "1002", "1003"}
        assert "999999" not in ids

        g_polski_spr = next(g for g in grades if g.id == "1001")
        assert g_polski_spr.subject == "Język polski"
        assert g_polski_spr.grade == "5"
        assert g_polski_spr.category == "Sprawdzian"
        assert g_polski_spr.weight == "3"
        assert g_polski_spr.teacher == "Anna Nowak"
        assert g_polski_spr.comment == "Lektura"

        g_polski_kart = next(g for g in grades if g.id == "1002")
        assert g_polski_kart.grade == "4+"
        assert g_polski_kart.weight == "1"

        g_mat = next(g for g in grades if g.id == "1003")
        assert g_mat.subject == "Matematyka"
        assert g_mat.grade == "6"
        assert g_mat.category == "Praca klasowa"

    def test_parse_grades_empty_html(self):
        assert parse_grades_html("<html><body>Nie ma ocen</body></html>") == []

    def test_parse_real_grades_fixture_and_zachowanie(self):
        """Testuje parsowanie realistycznego layoutu Librus Synergia wraz z oceną z zachowania."""
        fixture_html = (FIXTURES_DIR / "real_grades_anon.html").read_text(encoding="utf-8")
        grades = parse_grades_html(fixture_html)
        subjects = parse_subjects_from_html(fixture_html)

        # Sprawdzenie wyciągnięcia 17 przedmiotów (w tym Taniec, Historia bez ocen)
        assert len(subjects) == 17
        assert "Taniec" in subjects
        assert "Zachowanie" in subjects
        assert "Historia" in subjects
        assert "Język polski" in subjects
        assert "Matematyka" in subjects

        # Sprawdzenie wyciągnięcia oceny z zachowania
        zach_grades = [g for g in grades if g.subject == "Zachowanie"]
        assert len(zach_grades) == 1
        g_zach = zach_grades[0]
        assert g_zach.id == "79640"
        assert g_zach.grade == "1"
        assert g_zach.category == "poszanowanie norm etycznych"
        assert g_zach.date == "2026-10-12"
        assert g_zach.teacher == "Maria Nauczycielka"

        # Łączna liczba ocen: 31 przedmiotowych + 1 z zachowania = 32
        assert len(grades) == 32


class TestTimetableParser:
    """Testy parsowania terminarza (sprawdziany i nieobecności nauczycieli)."""

    def test_parse_timetable_fixture(self):
        fixture_html = (FIXTURES_DIR / "timetable.html").read_text(encoding="utf-8")
        entries = parse_timetable_html(fixture_html)

        assert len(entries) == 2

        # Sprawdzian z matematyki
        test_entry = next(e for e in entries if e.id == "501")
        assert test_entry.date == "2026-10-15"
        assert test_entry.type == "test"
        assert test_entry.category == "Sprawdzian"
        assert test_entry.subject == "Matematyka"
        assert test_entry.lesson_no == "3"
        assert test_entry.teacher == "Jan Kowalski"
        assert test_entry.description == "Sprawdzian z działu 1"

        # Nieobecność nauczyciela
        absence_entry = next(e for e in entries if "801" in e.id)
        assert absence_entry.date == "2026-10-16"
        assert absence_entry.type == "absence"
        assert absence_entry.teacher == "Anna Nowak"
        assert absence_entry.time == "1-4"

    def test_parse_timetable_empty_html(self):
        assert parse_timetable_html("<div>Brak terminarza</div>") == []


class TestScheduleParser:
    """Testy parsowania planu lekcji."""

    def test_parse_schedule_fixture(self):
        fixture_html = (FIXTURES_DIR / "schedule.html").read_text(encoding="utf-8")
        lessons = parse_schedule_html(fixture_html)

        # 3 lekcje znalezione w planie:
        # 1. Poniedziałek lekcja 1: Język polski (normalna)
        # 2. Wtorek lekcja 1: Historia (odwołana)
        # 3. Poniedziałek lekcja 2: Matematyka (zastępstwo)
        assert len(lessons) == 3

        l_normal = next(les for les in lessons if les.date == "2026-10-12" and les.lesson_no == 1)
        assert l_normal.subject == "Język polski"
        assert l_normal.classroom == "12"
        assert l_normal.teacher == "Anna Nowak"
        assert l_normal.is_cancelled is False
        assert l_normal.is_substitution is False

        l_cancelled = next(les for les in lessons if les.date == "2026-10-13" and les.lesson_no == 1)
        assert l_cancelled.subject == "Historia"
        assert l_cancelled.is_cancelled is True

        l_sub = next(les for les in lessons if les.date == "2026-10-12" and les.lesson_no == 2)
        assert l_sub.is_substitution is True
        assert "Biologia" in l_sub.substitution_info or "Zielińska" in l_sub.substitution_info

    def test_parse_schedule_empty_html(self):
        assert parse_schedule_html("<div>Brak planu</div>") == []
