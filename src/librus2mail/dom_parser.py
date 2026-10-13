"""
Moduł defensywnego parsowania HTML portalu Librus Synergia (DOM Parser).
Zawiera odporne na zmiany layoutu helpery wyciągające dane dla wiadomości,
ogłoszeń, ocen, terminarza i planu lekcji. Działa w 100% offline na obiektach BeautifulSoup.
"""

import re
from collections.abc import Callable

from bs4 import BeautifulSoup, Tag

from .domain_models import Announcement, Grade, Message, ScheduleLesson, TimetableEntry

DEFAULT_LESSON_TIMES: dict[int, tuple[str, str]] = {
    1: ("08:00", "08:45"),
    2: ("08:55", "09:40"),
    3: ("09:50", "10:35"),
    4: ("10:45", "11:30"),
    5: ("11:50", "12:35"),
    6: ("12:50", "13:35"),
    7: ("13:45", "14:30"),
    8: ("14:35", "15:20"),
    9: ("15:25", "16:10"),
    10: ("16:15", "17:00"),
}


def ensure_soup(html_or_soup: str | BeautifulSoup) -> BeautifulSoup:
    """Zwraca obiekt BeautifulSoup z przekazanego ciągu znaków lub istniejącego soup."""
    if isinstance(html_or_soup, BeautifulSoup):
        return html_or_soup
    return BeautifulSoup(str(html_or_soup), "html.parser")


def safe_get_text(element: Tag | None, default: str = "", strip: bool = True, separator: str = " ") -> str:
    """Bezpiecznie pobiera tekst z elementu Tag, normalizując spacje i spacje niełamliwe."""
    if element is None:
        return default
    try:
        text = element.get_text(separator=separator, strip=strip).replace('\xa0', ' ')
        return text if text else default
    except Exception:
        return default


def parse_tooltip_kv(tooltip_raw: str | None) -> dict[str, str]:
    """
    Parsuje atrybut 'title' / tooltip formatowany w stylu Librusa:
    'Kategoria: Sprawdzian<br>Data: 2026-09-15<br>Nauczyciel: Jan Kowalski'
    do słownika par klucz-wartość z małymi literami w kluczach.
    """
    if not tooltip_raw:
        return {}

    clean = re.sub(r'<br\s*/?>', '\n', str(tooltip_raw))
    clean = re.sub(r'<[^>]+>', '', clean)

    res: dict[str, str] = {}
    for line in clean.split('\n'):
        line = line.strip().replace('\xa0', ' ')
        if ':' in line:
            k, v = line.split(':', 1)
            k_clean = k.strip().lower()
            v_clean = v.strip()
            if k_clean:
                res[k_clean] = v_clean
    return res


def correct_sender_name(sender_raw: str) -> str:
    """Normalizuje format nadawcy (np. 'Kowalski Jan (Nauczyciel)' -> 'Jan Kowalski')."""
    sender = sender_raw.strip().split('(')[0].strip()
    parts = sender.split()
    if len(parts) >= 2:
        return ' '.join(parts[::-1])
    return sender


def parse_messages_html(
    html_or_soup: str | BeautifulSoup,
    known_messages: set | None = None,
    fetch_body_fn: Callable[[str], str] | None = None,
    do_read_messages: bool = True,
) -> list[Message]:
    """
    Defensywnie parsuje stronę skrzynki wiadomości (/wiadomosci lub /wiadomosci/5).
    Zwraca listę obiektów Message posortowaną od najnowszych.
    """
    soup = ensure_soup(html_or_soup)
    known = known_messages or set()

    mess_tab = (
        soup.select_one('table.decorated.stretch')
        or soup.select_one('table.decorated')
        or soup.select_one('table.container-message table')
        or soup.find('table')
    )

    if not mess_tab:
        return []

    tbody = mess_tab.find('tbody') or mess_tab
    messages: list[Message] = []

    for msg_row in tbody.find_all('tr'):
        tds = msg_row.find_all('td')
        if len(tds) < 4:
            continue

        # Wyszukiwanie kolumn defensywnie
        # Zwykle: 0=checkbox, 1=załącznik, 2=nadawca, 3=temat, 4=data
        sender_td = None
        title_td = None
        date_td = None
        has_attachment = False

        if len(tds) >= 5:
            has_attachment = bool(tds[1].find('img'))
            sender_td = tds[2]
            title_td = tds[3]
            date_td = tds[4]
        else:
            # Układ skrócony (np. 4 kolumny: 0=załącznik, 1=nadawca, 2=temat, 3=data)
            has_attachment = bool(tds[0].find('img'))
            sender_td = tds[1]
            title_td = tds[2]
            date_td = tds[3]

        sender_raw = safe_get_text(sender_td)
        title = safe_get_text(title_td)
        dt = safe_get_text(date_td)

        if not title and not sender_raw and not dt:
            continue

        sender = correct_sender_name(sender_raw)
        link_elem = (sender_td.find('a') if sender_td else None) or (title_td.find('a') if title_td else None)
        link = link_elem.get('href', '').strip() if link_elem else ""

        composite_id = f"{title}{dt}{sender_raw}"
        is_unread = composite_id not in known

        body = ""
        if is_unread and do_read_messages and link and fetch_body_fn:
            try:
                body = fetch_body_fn(link)
            except Exception:
                body = ""

        # Weryfikacja pogrubienia (bold w stylu CSS)
        if sender_td and 'bold' in sender_td.get('style', '').lower():
            is_unread = True

        msg = Message.model_validate({
            'id': composite_id,
            'title': title or "Bez tytułu",
            'sender': sender or "Nieznany",
            'datetime': dt or "",
            'link': link,
            'has_attachment': has_attachment,
            'is_unread': is_unread,
            'body': body,
        })
        messages.append(msg)

    messages.sort(key=lambda m: m.datetime, reverse=True)
    return messages


def parse_announcements_html(
    html_or_soup: str | BeautifulSoup,
    known_notifications: set | None = None,
) -> list[Announcement]:
    """
    Defensywnie parsuje stronę ogłoszeń szkolnych (/ogloszenia).
    Zwraca listę obiektów Announcement posortowaną od najnowszych.
    """
    soup = ensure_soup(html_or_soup)
    known = known_notifications or set()

    notif_container = soup.find('div', attrs={'class': 'container-background'}) or soup
    notifications: list[Announcement] = []

    for notif_table in notif_container.find_all('table'):
        tds = notif_table.find_all('td')
        if len(tds) < 3:
            continue

        # Zwykle: 0=Tytuł, 1=Autor/Nadawca, 2=Data, 3=Treść
        title = safe_get_text(tds[0])
        sender = safe_get_text(tds[1])
        dt = safe_get_text(tds[2])
        body = safe_get_text(tds[3]) if len(tds) >= 4 else ""

        if not title and not sender and not dt:
            continue

        composite_id = f"{title}{sender}{dt}"
        is_unread = composite_id not in known

        notif = Announcement.model_validate({
            'id': composite_id,
            'title': title or "Ogłoszenie",
            'sender': sender or "Szkoła",
            'datetime': dt or "",
            'body': body,
            'is_unread': is_unread,
        })
        notifications.append(notif)

    notifications.sort(key=lambda m: m.datetime, reverse=True)
    return notifications


def parse_subjects_from_html(html_or_soup: str | BeautifulSoup) -> list[str]:
    """
    Defensywnie wyciąga listę wszystkich przedmiotów z tabeli ocen ucznia (/przegladaj_oceny/uczen).
    Wyszukuje wiersze przedmiotów (zarówno posiadających oceny, jak i bez ocen np. Taniec, Historia).
    """
    soup = ensure_soup(html_or_soup)
    visible_tables = [
        t for t in soup.find_all('table', class_='decorated')
        if 'display:none' not in t.get('style', '').replace(' ', '').lower()
    ]
    if not visible_tables:
        body = soup.find('div', id='body') or soup
        visible_tables = [
            t for t in body.find_all('table')
            if 'display:none' not in t.get('style', '').replace(' ', '').lower()
        ]

    subjects: list[str] = []
    # 1. Główny przebieg: wyszukiwanie węzłów drzewa Librusa (przedmioty_..._node)
    for t in visible_tables:
        for tr in t.find_all('tr'):
            tds = tr.find_all('td', recursive=False)
            if len(tds) >= 2:
                img = tds[0].find('img', id=lambda x: x and ('przedmioty_' in x or 'node' in x))
                if img:
                    subj = safe_get_text(tds[1])
                    if subj and subj not in subjects:
                        subjects.append(subj)

    # 2. Rezerwowy przebieg, jeśli tabela nie zawiera ikon drzewa (np. proste makiety)
    if not subjects:
        for t in visible_tables:
            for tr in t.find_all('tr'):
                tds = tr.find_all('td', recursive=False)
                if len(tds) >= 2:
                    candidate = safe_get_text(tds[1])
                    if candidate and candidate not in subjects and candidate not in ('Brak ocen', 'Ocena', 'Kategoria'):
                        if not candidate.startswith('Okres') and not candidate.startswith('Śr.'):
                            subjects.append(candidate)

    return subjects


def parse_grades_html(html_or_soup: str | BeautifulSoup) -> list[Grade]:
    """
    Defensywnie parsuje stronę ocen ucznia (/przegladaj_oceny/uczen).
    Ignoruje ukryte tabele-pułapki (display: none), obsługuje oceny cząstkowe,
    kształtujące oraz oceny zachowania (zachowanie_szczegoly) i deduplikuje oceny po unikalnym ID.
    """
    soup = ensure_soup(html_or_soup)

    visible_tables = [
        t for t in soup.find_all('table', class_='decorated')
        if 'display:none' not in t.get('style', '').replace(' ', '').lower()
    ]
    if not visible_tables:
        body = soup.find('div', id='body') or soup
        visible_tables = [
            t for t in body.find_all('table')
            if 'display:none' not in t.get('style', '').replace(' ', '').lower()
        ]

    raw_grades: list[Grade] = []
    for table in visible_tables:
        for a in table.find_all('a'):
            href = a.get('href', '').strip()
            is_std_grade = '/przegladaj_oceny/szczegoly/' in href
            is_beh_grade = '/przegladaj_oceny/zachowanie_szczegoly/' in href

            if not is_std_grade and not is_beh_grade:
                continue

            grade_id = href.split('/')[-1].split('?')[0]
            if not grade_id or grade_id == '000000':
                continue

            val = safe_get_text(a)
            title_attr = a.get('title', '')
            details = parse_tooltip_kv(title_attr)

            # Szukanie nazwy przedmiotu w wierszu lub wierszu nadrzędnym
            subject = ""
            tr = a.find_parent('tr')
            if tr:
                tds = tr.find_all('td', recursive=False)
                if len(tds) > 1:
                    subject = safe_get_text(tds[1])

            if not subject:
                parent_table = a.find_parent('table')
                if parent_table:
                    parent_tr = parent_table.find_parent('tr')
                    if parent_tr:
                        prev_tr = parent_tr.find_previous_sibling('tr')
                        if prev_tr:
                            prev_tds = prev_tr.find_all('td', recursive=False)
                            if len(prev_tds) > 1:
                                subject = safe_get_text(prev_tds[1])

            if not subject and is_beh_grade:
                subject = "Zachowanie"

            category = details.get('kategoria', '-')
            if category == '-' and is_beh_grade and title_attr:
                m_cat = re.match(r'^([^<(]+)', title_attr)
                if m_cat:
                    category = m_cat.group(1).strip()

            date_val = details.get('data', details.get('data wystawienia', '-'))
            teacher_val = details.get('nauczyciel', details.get('dodał', '-'))
            weight_val = details.get('waga', '-')

            grade_obj = Grade.model_validate({
                'id': grade_id,
                'subject': subject or "Inny przedmiot",
                'grade': val or "-",
                'category': category,
                'date': date_val,
                'teacher': teacher_val,
                'weight': weight_val,
                'comment': details.get('komentarz', '-'),
                'href': href,
            })
            raw_grades.append(grade_obj)

    # Deduplikacja po unikalnym identyfikatorze oceny
    unique_map: dict[str, Grade] = {}
    for g in raw_grades:
        if g.id not in unique_map:
            unique_map[g.id] = g

    return list(unique_map.values())


def parse_timetable_html(
    html_or_soup: str | BeautifulSoup,
    default_month: int | None = None,
    default_year: int | None = None,
) -> list[TimetableEntry]:
    """
    Defensywnie parsuje stronę terminarza (/terminarz).
    Wyciąga sprawdziany, kartkówki oraz nieobecności nauczycieli (szczegoly_wolne).
    """
    soup = ensure_soup(html_or_soup)

    m_sel = soup.find('select', {'name': 'miesiac'})
    r_sel = soup.find('select', {'name': 'rok'})
    cal_month = None
    cal_year = None
    if m_sel:
        selected_m = [opt.get('value') for opt in m_sel.find_all('option') if opt.get('selected') is not None]
        if selected_m and str(selected_m[0]).isdigit():
            cal_month = int(selected_m[0])
    if r_sel:
        selected_r = [opt.get('value') for opt in r_sel.find_all('option') if opt.get('selected') is not None]
        if selected_r and str(selected_r[0]).isdigit():
            cal_year = int(selected_r[0])

    cal_month = cal_month or default_month or 1
    cal_year = cal_year or default_year or 2026

    entries: list[TimetableEntry] = []
    for num_div in soup.find_all('div', class_='kalendarz-numer-dnia'):
        day_str = safe_get_text(num_div)
        if not day_str.isdigit():
            continue
        day = int(day_str)
        date_str = f"{cal_year:04d}-{cal_month:02d}-{day:02d}"

        parent_day = num_div.find_parent('div', class_='kalendarz-dzien')
        if not parent_day:
            continue

        for td in parent_day.find_all('td'):
            onclick = td.get('onclick', '')
            title_attr = td.get('title', '')

            if 'szczegoly_wolne' in onclick:
                m_id = re.search(r'/(\d+)', onclick)
                raw_id = m_id.group(1) if m_id else f"absence_{date_str}"
                entry_id = f"{raw_id}_{date_str}"

                text = safe_get_text(td, separator=' ')
                teacher = ""
                hours = "Cały dzień"
                if 'Nauczyciel:' in text:
                    t_part = text.split('Nauczyciel:')[1]
                    if 'Godziny:' in t_part:
                        teacher = t_part.split('Godziny:')[0].strip()
                        hours = t_part.split('Godziny:')[1].strip()
                    else:
                        teacher = t_part.strip()

                entries.append(TimetableEntry.model_validate({
                    'id': entry_id,
                    'date': date_str,
                    'type': 'absence',
                    'category': 'Nieobecność nauczyciela',
                    'teacher': teacher,
                    'time': hours,
                    'raw_text': text,
                }))

            elif 'szczegoly' in onclick:
                m_id = re.search(r'/(\d+)', onclick)
                entry_id = m_id.group(1) if m_id else None
                if not entry_id:
                    continue

                subject_span = td.find('span', class_='przedmiot')
                subject = safe_get_text(subject_span)

                details = parse_tooltip_kv(title_attr)
                teacher = details.get('nauczyciel', '')
                description = details.get('opis', '')
                add_date = details.get('data dodania', '')

                td_text = safe_get_text(td, separator='\n')
                td_lines = [line.strip().strip(',') for line in td_text.split('\n') if line.strip()]
                lesson_no = ''
                category = 'Inne'

                for line in td_lines:
                    if 'Nr lekcji:' in line:
                        lesson_no = line.replace('Nr lekcji:', '').strip().split(',')[0].strip()
                    for cat in ['Sprawdzian', 'Kartkówka', 'Praca klasowa', 'Zadanie domowe', 'Projekt', 'Wycieczka']:
                        if cat.lower() in line.lower():
                            category = cat
                            break

                entry_type = 'test' if any(cat in category for cat in ['Sprawdzian', 'Kartkówka', 'Praca klasowa']) else 'event'

                entries.append(TimetableEntry.model_validate({
                    'id': entry_id,
                    'date': date_str,
                    'type': entry_type,
                    'category': category,
                    'subject': subject,
                    'lesson_no': lesson_no,
                    'teacher': teacher,
                    'description': description,
                    'add_date': add_date,
                }))

    entries.sort(key=lambda e: (e.date, e.lesson_no or ''))
    return entries


def parse_schedule_html(
    html_or_soup: str | BeautifulSoup,
    default_times: dict[int, tuple[str, str]] | None = None,
) -> list[ScheduleLesson]:
    """
    Defensywnie parsuje stronę planu lekcji (/przegladaj_plan_lekcji).
    Rozpoznaje zastępstwa, odwołane lekcje, sale i nauczycieli.
    """
    soup = ensure_soup(html_or_soup)
    lesson_times = default_times or DEFAULT_LESSON_TIMES

    table = soup.find('table', class_=lambda c: c and 'plan-lekcji' in c)
    if not table:
        table = soup.find('table', class_=lambda c: c and 'decorated' in c and soup.find('td', id='timetableEntryBox'))
    if not table:
        return []

    header_dates: dict[int, str] = {}
    header_row = table.find('tr')
    if header_row:
        ths = header_row.find_all(['th', 'td'])
        for idx, th in enumerate(ths):
            th_text = safe_get_text(th)
            m_iso = re.search(r'(\d{4}-\d{2}-\d{2})', th_text)
            if m_iso:
                header_dates[idx] = m_iso.group(1)
            else:
                m_pl = re.search(r'(\d{2})\.(\d{2})\.(\d{4})', th_text)
                if m_pl:
                    header_dates[idx] = f"{m_pl.group(3)}-{m_pl.group(2)}-{m_pl.group(1)}"

    entries: list[ScheduleLesson] = []

    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue

        first_text = safe_get_text(cells[0])
        if not first_text.isdigit():
            continue
        lesson_no = int(first_text)

        row_time_from = ""
        row_time_to = ""
        for c in cells[:3]:
            c_text = safe_get_text(c)
            m_times = re.findall(r'\b\d{1,2}[:.]\d{2}\b', c_text)
            if len(m_times) >= 2:
                row_time_from = m_times[0].replace('.', ':').zfill(5)
                row_time_to = m_times[1].replace('.', ':').zfill(5)
                break
        if not row_time_from and lesson_no in lesson_times:
            row_time_from, row_time_to = lesson_times[lesson_no]

        for col_idx, cell in enumerate(cells):
            is_entry_box = cell.get('id') == 'timetableEntryBox' or 'timetableEntryBox' in cell.get('class', [])
            if not is_entry_box and col_idx not in header_dates:
                continue

            date_str = cell.get('data-date') or cell.get('date') or header_dates.get(col_idx)
            if not date_str:
                continue

            time_from = (
                cell.get('data-time_from')
                or cell.get('data-time-from')
                or cell.get('data-date-from')
                or cell.get('date_from')
                or row_time_from
            )
            time_to = (
                cell.get('data-time_to')
                or cell.get('data-time-to')
                or cell.get('data-date-to')
                or cell.get('date_to')
                or row_time_to
            )
            if time_from and len(time_from) < 5 and ':' in time_from:
                time_from = time_from.zfill(5)
            if time_to and len(time_to) < 5 and ':' in time_to:
                time_to = time_to.zfill(5)

            cell_text = safe_get_text(cell)
            if not cell_text or cell_text in ('-', '') or cell_text.isdigit():
                continue

            text_divs = cell.find_all('div', class_='text')
            blocks = text_divs if text_divs else [cell]

            info_div = cell.find('div', class_=lambda c: c and 'plan-lekcji-info' in c)
            info_text = safe_get_text(info_div)

            a_tag = cell.find('a')
            raw_title = a_tag.get('title', '') if a_tag else ''
            tooltip_attrs = parse_tooltip_kv(raw_title)

            for b_idx, block in enumerate(blocks):
                block_text = safe_get_text(block)
                if not block_text:
                    continue

                sub_tag = block.find('b')
                subject = ""
                rest = ""
                if sub_tag:
                    subject = safe_get_text(sub_tag)
                    rest = block_text.replace(subject, '', 1).strip(' -')
                elif '-' in block_text:
                    parts = block_text.split('-', 1)
                    subject = parts[0].strip()
                    rest = parts[1].strip()
                else:
                    m_split = re.search(r'^(.*?)(?:\s+(?:s\.|sala|\()\s*.*)$', block_text, re.IGNORECASE)
                    if m_split and m_split.group(1).strip():
                        subject = m_split.group(1).strip()
                        rest = block_text[len(subject):].strip(' -')
                    else:
                        subject = block_text

                subject = re.sub(r'\s+', ' ', subject).strip(' -')
                teacher = ""
                classroom = ""
                if rest:
                    m_room = re.search(r'(?:s\.|sala)\s*([0-9a-zA-Z_.-]+)', rest, re.IGNORECASE)
                    if m_room:
                        classroom = m_room.group(1).strip('. ')
                        teacher = re.sub(r'(?:s\.|sala)\s*([0-9a-zA-Z_.-]+)', '', rest, flags=re.IGNORECASE).strip(' ,.-')
                    else:
                        teacher = rest.strip(' ,()')

                teacher = re.sub(r'\s+', ' ', teacher).strip(' ,.-')
                if 'nauczyciel' in tooltip_attrs and not teacher:
                    teacher = re.sub(r'\s+', ' ', tooltip_attrs['nauczyciel']).strip()
                if 'sala' in tooltip_attrs and not classroom:
                    classroom = re.sub(r'\s+', ' ', tooltip_attrs['sala']).strip('. ')

                has_strike = bool(
                    block.find(['s', 'strike', 'del'])
                    or 'line-through' in block.get('style', '')
                    or 'line-through' in cell.get('style', '')
                    or 'odwolana' in block.get('class', [])
                    or 'odwolana' in cell.get('class', [])
                )

                all_context = f"{info_text} {cell_text} {raw_title} {' '.join(tooltip_attrs.values())}".lower()
                is_cancelled = False
                is_substitution = False
                is_moved = False
                substitution_info = ""

                if 'odwołan' in all_context or 'odwolana' in all_context or (has_strike and 'zastęp' not in all_context):
                    is_cancelled = True
                elif 'zastęp' in all_context or 'zastep' in all_context:
                    is_substitution = True
                    if tooltip_attrs:
                        sub_parts = []
                        if 'przedmiot' in tooltip_attrs:
                            sub_parts.append(tooltip_attrs['przedmiot'])
                        if 'nauczyciel' in tooltip_attrs:
                            sub_parts.append(f"p. {tooltip_attrs['nauczyciel']}")
                        if 'sala' in tooltip_attrs:
                            sub_parts.append(f"s. {tooltip_attrs['sala']}")
                        substitution_info = ", ".join(sub_parts)
                    elif info_text:
                        substitution_info = info_text
                elif 'przesunię' in all_context or 'przesunie' in all_context:
                    is_moved = True

                entry_id = f"sched_{date_str}_{lesson_no}_{subject}_{b_idx}"
                entries.append(ScheduleLesson.model_validate({
                    'id': entry_id,
                    'date': date_str,
                    'lesson_no': lesson_no,
                    'time_from': time_from,
                    'time_to': time_to,
                    'time_range': f"{time_from} - {time_to}" if time_from and time_to else "",
                    'subject': subject or "Lekcja",
                    'teacher': teacher,
                    'classroom': classroom,
                    'is_cancelled': is_cancelled,
                    'is_substitution': is_substitution,
                    'is_moved': is_moved,
                    'substitution_info': substitution_info,
                    'raw_entry': block_text,
                }))

    return entries
