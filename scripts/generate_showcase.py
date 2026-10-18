#!/usr/bin/env python3
"""
Skrypt do automatycznego generowania animowanego podglądu możliwości aplikacji (Showcase GIF)
na podstawie przykładowych raportów HTML z katalogu examples/reports/ oraz dedykowanych
slajdów wstępnych (Intro) i końcowych (Outro).

Wykorzystuje:
- Google Chrome / Chromium (headless) do bezstratnych zrzutów ekranu
- Precyzyjne przewijanie treści strony (CSS translateY) przy stałej górnej belce nawigacyjnej
- Dedykowane slajdy graficzne (Intro / Outro / Custom HTML)
- Opcję procentowego skalowania wielkości czcionki (font_scale) dla lepszego wypełnienia slajdu
- Indywidualnie konfigurowalny czas trwania każdego slajdu oraz parametry scrolla
- ffmpeg do optymalnego złożenia klatek w animację GIF / WebP o wysokiej jakości
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "examples" / "reports"
OUTPUT_DIR = REPO_ROOT / "docs" / "assets"
OUTPUT_GIF = OUTPUT_DIR / "librus2mail_showcase.gif"
OUTPUT_WEBP = OUTPUT_DIR / "librus2mail_showcase.webp"

# Konfiguracja slajdów prezentacji:
# Typy slajdów:
# 1. "intro"  - pełnoekranowy slajd tytułowy z logo, nagłówkiem, opisem i cechami kluczowymi
# 2. "page"   - widok strony z examples/reports/ z dolną belką i opcjonalnym płynnym scrollem
# 3. "outro"  - pełnoekranowy slajd końcowy podsumowujący dodatkowe możliwości i Call to Action
# 4. "custom" - dowolny własny kod HTML podany w kluczu "html"
#
# Dostępne opcje dla każdego slajdu:
# - font_scale: procentowe skalowanie czcionki (np. 120, "120%", 1.2 = powiększenie o 20%)
# - duration: całkowity czas wyświetlania slajdu w sekundach
# - scroll_target: głębokość przewinięcia w dół (w pikselach; 0 = slajd statyczny)
# - scroll_time: czas trwania samego ruchu przewijania w sekundach
# - top_pause / bottom_pause: pauzy na górze i dole strony
SLIDES = [
    # --- 1. SLAJD TYTUŁOWY (Intro) ---
    {
        "type": "intro",
        "badge": "📬 Open Source Assistant",
        "title": "Librus2mail",
        "subtitle": "Nowoczesny, bezobsługowy asystent szkolny rodzica i analityk postępów nauki dziecka dla e-dziennika Librus Synergia.",
        "features": [
            ("⚡", "Automatyczne powiadomienia e-mail"),
            ("📊", "Interaktywny Panel WWW"),
            ("🎓", "Symulator Czerwonego Paska"),
            ("🛡️", "100% Prywatności (Self-hosted)"),
        ],
        "duration": 4.0,
        "font_scale": 150,  # powiększenie czcionki o 50%
    },

    # --- 2. GŁÓWNE MODUŁY APLIKACJI (Widoki stron) ---
    {
        "type": "page",
        "file": "web_dashboard.html",
        "title": "Pulpit Rodzica (Dashboard)",
        "subtitle": "Bieżący podgląd dnia: ostatnie oceny, plan lekcji na dziś, ogłoszenia ze szkoły i status synchronizacji.",
        "icon": "📊",
        "tag": "Pulpit Główny",
        "duration": 8.5,
        "scroll_target": 1620,
        "scroll_time": 4.6,
        "top_pause": 1.4,
        "bottom_pause": 1.5,
    },
    {
        "type": "page",
        "file": "web_oceny.html",
        "title": "Zestawienie Ocen & Symulator Celu",
        "subtitle": "Średnie ważone, pigułki wliczania do świadectwa oraz interaktywny symulator ocen „Co jeśli…?”.",
        "icon": "🎯",
        "tag": "Symulator Ocen",
        "duration": 5.5,
        "scroll_target": 650,
        "scroll_time": 3.6,
        "top_pause": 1.4,
        "bottom_pause": 1.5,
    },
    {
        "type": "page",
        "file": "web_oceny_swiadectwo.html",
        "title": "Świadectwo z Wyróżnieniem",
        "subtitle": "Automatyczny kalkulator czerwonego paska, brakujące punkty do progu 4.75 i propozycje ocen.",
        "icon": "🎓",
        "tag": "Czerwony Pasek",
        "duration": 8.2,
        "scroll_target": 1160,
        "scroll_time": 4.5,
        "top_pause": 1.3,
        "bottom_pause": 1.4,
    },
    {
        "type": "page",
        "file": "web_przedmiot_matematyka.html",
        "title": "Szczegółowa Analiza Przedmiotu",
        "subtitle": "Wykres trajektorii ocen (Chart.js), histogram rozkładu stopni, predykcja celu oraz margines ryzyka.",
        "icon": "📈",
        "tag": "Analityka Chart.js",
        "duration": 12.5,
        "scroll_target": 1420,
        "scroll_time": 7.6,
        "top_pause": 1.4,
        "bottom_pause": 1.5,
    },
    {
        "type": "page",
        "file": "web_plan.html",
        "title": "Plan Lekcji ze Zmianami na Żywo",
        "subtitle": "Tygodniowy rozkład zajęć z automatycznym oznaczaniem zastępstw, odwołanych lekcji i numerów sal.",
        "icon": "📅",
        "tag": "Plan Lekcji",
        "duration": 5.5,
        "scroll_target": 360,
        "scroll_time": 2.8,
        "top_pause": 1.4,
        "bottom_pause": 1.5,
    },
    {
        "type": "page",
        "file": "powiadomienie_collector.html",
        "title": "Automatyczne Powiadomienia E-mail",
        "subtitle": "Natychmiastowe alerty HTML na Gmail / SMTP o nowych ocenach, wiadomościach i ogłoszeniach.",
        "icon": "📬",
        "tag": "E-mail Notifier",
        "duration": 3.2,
        "scroll_target": 400,
    },
    {
        "type": "page",
        "file": "raport_8979296.html",
        "title": "Przykładowy wygląd raportu tygodniowego z ocenami, analizami i uwagami",
        "subtitle": "Szczegółowe podsumowanie tygodnia w formie czytelnego maila z uwzględnieniem ocen, dokonań i analiz.",
        "icon": "🎮",
        "tag": "Przykładowy Raport Tygodniowy",
        "duration": 7.2,
        "scroll_target": 680,
        "scroll_time": 4.5,
        "top_pause": 1.3,
        "bottom_pause": 1.4,
    },

    # --- 3. SLAJD KOŃCOWY (Outro) ---
    {
        "type": "outro",
        "badge": "🚀 Ekosystem Librus2mail",
        "title": "I wiele, wiele więcej możliwości...",
        "subtitle": "Wszystko zaprojektowane z myślą o wygodzie rodzica, spokoju i motywacji ucznia.",
        "cards": [
            ("🧙", "Kreator Onboardingowy", "4-krokowy konfigurator w przeglądarce (/setup) z testem połączenia."),
            ("👨‍👩‍👧‍👦", "Obsługa Rodzeństwa", "Monitorowanie wielu dzieci z podziałem powiadomień na e-maile rodziców."),
            ("🗄️", "Archiwum Roczne", "Bezpieczna archiwizacja i przeglądanie ocen z poprzednich semestrów i klas."),
            ("🐳", "Docker & systemd", "Gotowe kontenery i usługi linuksowe na Raspberry Pi, NAS lub serwer."),
        ],
        "cta": "⭐ Wypróbuj na GitHubie: github.com/cackoarek/librus2mail",
        "duration": 4.5,
        "font_scale": 150,  # powiększenie czcionki o %
    },
]


def parse_scale(scale_val: int | float | str | None, default: float = 1.0) -> float:
    """
    Konwertuje parametr skali czcionki/powiększenia na mnożnik (float).
    Przykłady wejść:
    - 120 -> 1.2 (120%)
    - "125%" -> 1.25
    - 1.15 -> 1.15
    - None / 100 -> 1.0
    """
    if scale_val is None:
        return default
    if isinstance(scale_val, str):
        val_str = scale_val.strip().rstrip("%")
        try:
            val_num = float(val_str)
            return val_num / 100.0 if val_num > 5.0 else val_num
        except ValueError:
            return default
    if isinstance(scale_val, (int, float)):
        return float(scale_val) / 100.0 if scale_val > 5.0 else float(scale_val)
    return default


def find_chrome() -> str:
    """Wyszukuje dostępną binarkę Google Chrome lub Chromium."""
    candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    for c in candidates:
        path = shutil.which(c)
        if path:
            return path
    raise RuntimeError("Nie znaleziono Google Chrome ani Chromium w systemie!")


def find_ffmpeg() -> str:
    """Wyszukuje binarkę ffmpeg."""
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("Nie znaleziono ffmpeg w systemie!")
    return path


def get_scroll_steps(
    target_y: int,
    duration: float = 3.5,
    scroll_time: float | None = None,
    top_pause: float | None = None,
    bottom_pause: float | None = None,
    steps: int | None = None,
) -> list[tuple[int, float]]:
    """
    Generuje sekwencję (scroll_y, czas_trwania) z płynnym ruchem ease-in-out.
    Wszystkie parametry czasowe są elastycznie konfigurowalne per slajd.
    """
    if target_y <= 0:
        return [(0, duration)]

    if scroll_time is None:
        scroll_time = min(max(duration * 0.4, 1.0), max(duration - 1.0, 1.0))

    remaining_pause = max(duration - scroll_time, 0.6)

    if top_pause is not None and bottom_pause is not None:
        pass
    elif top_pause is not None:
        bottom_pause = max(remaining_pause - top_pause, 0.3)
    elif bottom_pause is not None:
        top_pause = max(remaining_pause - bottom_pause, 0.3)
    else:
        top_pause = round(remaining_pause * 0.45, 2)
        bottom_pause = round(remaining_pause - top_pause, 2)

    if steps is None:
        steps = max(5, min(12, int(scroll_time * 5)))

    frames = [(0, top_pause)]
    step_duration = round(scroll_time / steps, 3)

    for i in range(1, steps):
        t = i / steps
        ease = 3 * (t**2) - 2 * (t**3)
        y = int(target_y * ease)
        frames.append((y, step_duration))

    frames.append((target_y, bottom_pause))
    return frames


def build_scroll_css(html_content: str, scroll_y: int, page_zoom: float = 1.0) -> str:
    """
    Generuje reguły CSS przewijające właściwą treść strony w górę.
    Dla stron webowych unieruchamia <header> na samej górze (y=0) i przesuwa <main> w górę.
    Dla raportów e-mail przesuwa główny kontener treści.
    Opcjonalnie aplikuje powiększenie strony (page_zoom).
    """
    zoom_rule = f"zoom: {page_zoom} !important;" if page_zoom != 1.0 else ""

    if "<header" in html_content and "<main" in html_content:
        return f"""
<style>
header {{
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 50 !important;
    background-color: #ffffff !important;
}}
main {{
    margin-top: 64px !important;
    transform: translateY(-{scroll_y}px) !important;
    {zoom_rule}
}}
::-webkit-scrollbar {{ display: none !important; }}
html, body {{ scrollbar-width: none !important; }}
</style>
"""
    else:
        return f"""
<style>
body > div:first-of-type {{
    transform: translateY(-{scroll_y}px) !important;
    {zoom_rule}
}}
::-webkit-scrollbar {{ display: none !important; }}
html, body {{ scrollbar-width: none !important; }}
</style>
"""


def render_intro_html(slide: dict) -> str:
    """Generuje pełnoekranowy slajd tytułowy (Intro) z opcjonalną skalą czcionki."""
    scale = parse_scale(slide.get("font_scale") or slide.get("scale"))
    badge = slide.get("badge", "📬 Open Source Assistant")
    title = slide.get("title", "Librus2mail")
    subtitle = slide.get("subtitle", "")
    features = slide.get("features", [])

    main_title = title.replace("2mail", "<span>2mail</span>") if "2mail" in title else title

    # Przeliczenie rozmiarów czcionek i odstępów na podstawie scale
    badge_fs = round(13 * scale)
    badge_py = round(6 * scale)
    badge_px = round(18 * scale)
    title_fs = round(56 * scale)
    title_mb = round(18 * scale)
    subtitle_fs = round(21 * scale)
    subtitle_mb = round(40 * scale)
    sub_max_w = round(840 * min(scale, 1.3))
    feature_fs = round(14 * scale)
    card_py = round(12 * scale)
    card_px = round(22 * scale)
    card_gap = round(16 * scale)
    max_w = round(950 * min(scale, 1.25))

    features_html = "".join(
        f'<div class="feature-card"><span>{icon}</span> {text}</div>'
        for icon, text in features
    )

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            width: 1200px;
            height: 700px;
            background: radial-gradient(circle at 50% 25%, #1e1b4b 0%, #0f172a 60%, #020617 100%);
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 40px;
            overflow: hidden;
            position: relative;
        }}
        .glow {{
            position: absolute;
            width: 700px;
            height: 700px;
            background: radial-gradient(circle, rgba(99, 102, 241, 0.18) 0%, rgba(99, 102, 241, 0) 70%);
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 1;
        }}
        .content {{
            position: relative;
            z-index: 2;
            max-width: {max_w}px;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(99, 102, 241, 0.2);
            border: 1px solid rgba(129, 140, 248, 0.4);
            color: #c7d2fe;
            padding: {badge_py}px {badge_px}px;
            border-radius: 9999px;
            font-size: {badge_fs}px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 24px;
        }}
        h1 {{
            font-size: {title_fs}px;
            font-weight: 900;
            letter-spacing: -1.5px;
            line-height: 1.1;
            margin-bottom: {title_mb}px;
            background: linear-gradient(135deg, #ffffff 40%, #c7d2fe 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        h1 span {{
            background: linear-gradient(135deg, #818cf8, #38bdf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        p.subtitle {{
            font-size: {subtitle_fs}px;
            color: #cbd5e1;
            font-weight: 400;
            line-height: 1.5;
            margin-bottom: {subtitle_mb}px;
            max-width: {sub_max_w}px;
            margin-left: auto;
            margin-right: auto;
        }}
        .features {{
            display: flex;
            justify-content: center;
            gap: {card_gap}px;
            flex-wrap: wrap;
        }}
        .feature-card {{
            background: rgba(30, 41, 59, 0.65);
            border: 1px solid rgba(255, 255, 255, 0.12);
            backdrop-filter: blur(12px);
            padding: {card_py}px {card_px}px;
            border-radius: 12px;
            font-size: {feature_fs}px;
            font-weight: 600;
            color: #f1f5f9;
            display: flex;
            align-items: center;
            gap: 10px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        }}
    </style>
</head>
<body>
    <div class="glow"></div>
    <div class="content">
        <div class="badge"><span>{badge}</span></div>
        <h1>{main_title}</h1>
        <p class="subtitle">{subtitle}</p>
        <div class="features">{features_html}</div>
    </div>
</body>
</html>
"""


def render_outro_html(slide: dict) -> str:
    """Generuje pełnoekranowy slajd podsumowujący (Outro) z kartami możliwości i opcjonalną skalą czcionki."""
    scale = parse_scale(slide.get("font_scale") or slide.get("scale"))
    badge = slide.get("badge", "🚀 Ekosystem Librus2mail")
    title = slide.get("title", "I wiele, wiele więcej możliwości...")
    subtitle = slide.get("subtitle", "")
    cards = slide.get("cards", [])
    cta = slide.get("cta", "")

    # Przeliczenie rozmiarów czcionek i odstępów na podstawie scale
    badge_fs = round(13 * scale)
    badge_py = round(6 * scale)
    badge_px = round(18 * scale)
    title_fs = round(42 * scale)
    title_mb = round(12 * scale)
    subtitle_fs = round(18 * scale)
    subtitle_mb = round(34 * scale)
    sub_max_w = round(780 * min(scale, 1.3))
    card_title_fs = round(15 * scale)
    card_desc_fs = round(12 * scale)
    card_icon_fs = round(26 * scale)
    card_py = round(20 * scale)
    card_px = round(18 * scale)
    cta_fs = round(15 * scale)
    cta_py = round(12 * scale)
    cta_px = round(30 * scale)
    grid_gap = round(16 * scale)
    grid_max_w = round(1080 * min(scale, 1.2))

    cards_html = "".join(
        f"""
        <div class="card">
            <div class="card-icon">{icon}</div>
            <div class="card-title">{ctitle}</div>
            <div class="card-desc">{cdesc}</div>
        </div>
        """
        for icon, ctitle, cdesc in cards
    )

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
    <meta charset="UTF-8">
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            width: 1200px;
            height: 700px;
            background: radial-gradient(circle at 50% 30%, #1e1b4b 0%, #0f172a 60%, #020617 100%);
            color: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 40px;
            overflow: hidden;
            position: relative;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.2);
            border: 1px solid rgba(52, 211, 153, 0.4);
            color: #6ee7b7;
            padding: {badge_py}px {badge_px}px;
            border-radius: 9999px;
            font-size: {badge_fs}px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 20px;
        }}
        h2 {{
            font-size: {title_fs}px;
            font-weight: 900;
            letter-spacing: -0.8px;
            margin-bottom: {title_mb}px;
            background: linear-gradient(135deg, #ffffff 40%, #e0e7ff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        p.subtitle {{
            font-size: {subtitle_fs}px;
            color: #94a3b8;
            margin-bottom: {subtitle_mb}px;
            max-width: {sub_max_w}px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: {grid_gap}px;
            max-width: {grid_max_w}px;
            margin-bottom: 36px;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.7);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 14px;
            padding: {card_py}px {card_px}px;
            text-align: left;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.25);
        }}
        .card-icon {{ font-size: {card_icon_fs}px; margin-bottom: 10px; }}
        .card-title {{ font-size: {card_title_fs}px; font-weight: 800; color: #f8fafc; margin-bottom: 6px; }}
        .card-desc {{ font-size: {card_desc_fs}px; color: #94a3b8; line-height: 1.45; }}
        .cta {{
            display: inline-flex;
            align-items: center;
            gap: 12px;
            background: linear-gradient(135deg, #4f46e5, #6366f1);
            color: #ffffff;
            font-weight: 800;
            font-size: {cta_fs}px;
            padding: {cta_py}px {cta_px}px;
            border-radius: 12px;
            box-shadow: 0 10px 25px -5px rgba(79, 70, 229, 0.5);
            letter-spacing: 0.2px;
        }}
    </style>
</head>
<body>
    <div class="badge">{badge}</div>
    <h2>{title}</h2>
    <p class="subtitle">{subtitle}</p>
    <div class="grid">{cards_html}</div>
    <div class="cta"><span>{cta}</span></div>
</body>
</html>
"""


def create_banner_html(
    slide_index: int,
    total_slides: int,
    title: str,
    subtitle: str,
    icon: str,
    tag: str,
    banner_scale: float = 1.0,
) -> str:
    """Tworzy kod HTML estetycznej, nowoczesnej pływającej belki informacyjnej na dole ekranu."""
    badge_fs = round(11 * banner_scale)
    title_fs = round(15 * banner_scale)
    subtitle_fs = round(12 * banner_scale)
    icon_fs = round(17 * banner_scale)
    tag_fs = round(10 * banner_scale)
    brand_fs = round(10 * banner_scale)
    banner_py = round(12 * banner_scale)
    banner_px = round(22 * banner_scale)

    return f"""
<div id="showcase-banner" style="
    position: fixed;
    bottom: 16px;
    left: 20px;
    right: 20px;
    z-index: 999999;
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(30, 27, 75, 0.96));
    border: 1px solid rgba(99, 102, 241, 0.45);
    border-radius: 14px;
    padding: {banner_py}px {banner_px}px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    box-shadow: 0 12px 35px -5px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(12px);
    color: #ffffff;
">
    <div style="display: flex; align-items: center; gap: 16px;">
        <div style="
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            color: #ffffff;
            font-weight: 800;
            font-size: {badge_fs}px;
            padding: 4px 10px;
            border-radius: 9999px;
            letter-spacing: 0.5px;
            box-shadow: 0 2px 8px rgba(79, 70, 229, 0.4);
            white-space: nowrap;
        ">
            {slide_index} / {total_slides}
        </div>
        <div>
            <div style="
                font-size: {title_fs}px;
                font-weight: 800;
                color: #ffffff;
                letter-spacing: -0.2px;
                display: flex;
                align-items: center;
                gap: 8px;
                line-height: 1.2;
            ">
                <span style="font-size: {icon_fs}px;">{icon}</span>
                <span>{title}</span>
            </div>
            <div style="
                font-size: {subtitle_fs}px;
                color: #cbd5e1;
                margin-top: 3px;
                font-weight: 400;
                line-height: 1.3;
            ">
                {subtitle}
            </div>
        </div>
    </div>
    <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
        <span style="
            background: rgba(99, 102, 241, 0.2);
            border: 1px solid rgba(99, 102, 241, 0.4);
            color: #c7d2fe;
            font-size: {tag_fs}px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 0.6px;
        ">
            {tag}
        </span>
        <span style="
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: #f8fafc;
            font-size: {brand_fs}px;
            font-weight: 800;
            padding: 4px 10px;
            border-radius: 6px;
            letter-spacing: 0.5px;
        ">
            Librus2mail
        </span>
    </div>
</div>
"""


def capture_html(chrome_bin: str, html_content: str, output_png: Path, width: int = 1200, height: int = 700) -> None:
    """Zapisuje treść HTML do pliku tymczasowego i wykonuje zrzut ekranu przez Headless Chrome."""
    with tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False) as tmp_html:
        tmp_html.write(html_content)
        tmp_html_path = tmp_html.name

    try:
        cmd = [
            chrome_bin,
            "--headless=new",
            "--disable-gpu",
            f"--window-size={width},{height}",
            "--hide-scrollbars",
            "--virtual-time-budget=2000",
            f"--screenshot={output_png}",
            f"file://{tmp_html_path}",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0 or not output_png.exists():
            raise RuntimeError(f"Błąd Chrome przy zrzucie ekranu: {res.stderr}")
    finally:
        if os.path.exists(tmp_html_path):
            os.remove(tmp_html_path)


def capture_slide(
    chrome_bin: str,
    html_path: Path,
    output_png: Path,
    banner_html: str,
    scroll_y: int = 0,
    page_zoom: float = 1.0,
    width: int = 1200,
    height: int = 700,
) -> None:
    """Wstrzykuje reguły przewijania oraz belkę informacyjną i generuje zrzut ekranu przez Headless Chrome."""
    with open(html_path, encoding="utf-8") as f:
        content = f.read()

    scroll_css = build_scroll_css(content, scroll_y, page_zoom=page_zoom)

    if "</head>" in content:
        content = content.replace("</head>", f"{scroll_css}</head>")
    else:
        content = scroll_css + content

    if "</body>" in content:
        content = content.replace("</body>", f"{banner_html}</body>")
    else:
        content = content + banner_html

    capture_html(chrome_bin, content, output_png, width=width, height=height)


def generate_animation(ffmpeg_bin: str, frame_data: list[tuple[Path, float]], output_gif: Path, output_webp: Path) -> None:
    """Łączy klatki w zoptymalizowany animowany plik GIF oraz WebP za pomocą ffmpeg."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as concat_file:
        for png_path, duration in frame_data:
            concat_file.write(f"file '{png_path}'\n")
            concat_file.write(f"duration {duration}\n")
        concat_file.write(f"file '{frame_data[-1][0]}'\n")
        concat_path = concat_file.name

    try:
        # 1. Generowanie GIF (zoptymalizowana paleta kolorów)
        print("🎞️  Generuję zoptymalizowany animowany GIF...")
        gif_filter = "scale=1000:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=160:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3"
        cmd_gif = [
            ffmpeg_bin,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_path,
            "-vf", gif_filter,
            "-r", "10",
            str(output_gif),
        ]
        res = subprocess.run(cmd_gif, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Błąd ffmpeg przy generowaniu GIF: {res.stderr}")

        # 2. Generowanie animowanego WebP (format ultra-kompaktowy)
        print("🎞️  Generuję ultra-kompaktowy animowany WebP...")
        cmd_webp = [
            ffmpeg_bin,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_path,
            "-vf", "scale=1000:-1:flags=lanczos",
            "-vcodec", "libwebp",
            "-lossless", "0",
            "-q:v", "75",
            "-loop", "0",
            "-r", "10",
            str(output_webp),
        ]
        subprocess.run(cmd_webp, capture_output=True, text=True)

    finally:
        if os.path.exists(concat_path):
            os.remove(concat_path)


def main():
    print("🚀 Inicjalizuję generator animacji prezentacji Librus2mail (Intro + Moduły + Outro + Skalowanie czcionek)...")
    chrome_bin = find_chrome()
    ffmpeg_bin = find_ffmpeg()
    print(f"   ✓ Chrome: {chrome_bin}")
    print(f"   ✓ ffmpeg: {ffmpeg_bin}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    temp_dir = tempfile.mkdtemp(prefix="librus_showcase_")
    frame_data: list[tuple[Path, float]] = []

    try:
        # Wyznacz liczbę slajdów typu "page" do numeracji w belce
        page_slides_count = sum(1 for s in SLIDES if s.get("type", "page") == "page")
        page_counter = 0
        frame_counter = 0
        total_slides = len(SLIDES)

        for idx, slide in enumerate(SLIDES, start=1):
            stype = slide.get("type", "page")
            scale_val = parse_scale(slide.get("font_scale") or slide.get("scale"))
            scale_desc = f", czcionka: {int(scale_val * 100)}%" if scale_val != 1.0 else ""

            # A) SLAJD TYTUŁOWY (Intro)
            if stype == "intro":
                duration = slide.get("duration", 4.0)
                print(f"🌟 [{idx}/{total_slides}] Generuję slajd tytułowy (Intro) [czas: {duration:.1f}s{scale_desc}]...")
                intro_html = render_intro_html(slide)
                frame_counter += 1
                png_path = Path(temp_dir) / f"frame_{frame_counter:03d}.png"
                capture_html(chrome_bin, intro_html, png_path)
                frame_data.append((png_path, duration))
                continue

            # B) SLAJD PODSUMOWUJĄCY (Outro)
            if stype == "outro":
                duration = slide.get("duration", 4.5)
                print(f"✨ [{idx}/{total_slides}] Generuję slajd końcowy (Outro) [czas: {duration:.1f}s{scale_desc}]...")
                outro_html = render_outro_html(slide)
                frame_counter += 1
                png_path = Path(temp_dir) / f"frame_{frame_counter:03d}.png"
                capture_html(chrome_bin, outro_html, png_path)
                frame_data.append((png_path, duration))
                continue

            # C) WŁASNY KOD HTML (Custom)
            if stype == "custom":
                duration = slide.get("duration", 4.0)
                print(f"🎨 [{idx}/{total_slides}] Generuję slajd własny (Custom) [czas: {duration:.1f}s{scale_desc}]...")
                frame_counter += 1
                png_path = Path(temp_dir) / f"frame_{frame_counter:03d}.png"
                capture_html(chrome_bin, slide.get("html", ""), png_path)
                frame_data.append((png_path, duration))
                continue

            # D) STANDARDOWY WIDOK STRONY (Page)
            src_file = REPORTS_DIR / slide["file"]
            if not src_file.exists():
                print(f"⚠️  Pominięto brakujący plik: {slide['file']}")
                continue

            page_counter += 1
            target_scroll = slide.get("scroll_target", 0)
            duration = slide.get("duration", 3.5)
            scroll_time = slide.get("scroll_time")
            top_pause = slide.get("top_pause")
            bottom_pause = slide.get("bottom_pause")
            steps = slide.get("steps")
            page_zoom = parse_scale(slide.get("page_zoom") or slide.get("font_scale") if slide.get("page_zoom") else None)
            banner_scale = parse_scale(slide.get("banner_font_scale") or slide.get("banner_scale"), default=1.0)

            scroll_steps = get_scroll_steps(
                target_y=target_scroll,
                duration=duration,
                scroll_time=scroll_time,
                top_pause=top_pause,
                bottom_pause=bottom_pause,
                steps=steps,
            )

            total_slide_time = sum(d for _, d in scroll_steps)
            if target_scroll > 0:
                action_desc = f"czas: {total_slide_time:.1f}s, scroll: 0 -> {target_scroll}px"
            else:
                action_desc = f"czas: {total_slide_time:.1f}s, statyczny"

            print(f"📸 [{idx}/{total_slides}] Generuję klatki: {slide['title']} [Moduł {page_counter}/{page_slides_count}, {action_desc}{scale_desc}]...")

            banner = create_banner_html(
                slide_index=page_counter,
                total_slides=page_slides_count,
                title=slide["title"],
                subtitle=slide["subtitle"],
                icon=slide["icon"],
                tag=slide["tag"],
                banner_scale=banner_scale,
            )

            for step_idx, (scroll_y, dur) in enumerate(scroll_steps):
                frame_counter += 1
                png_path = Path(temp_dir) / f"frame_{frame_counter:03d}.png"
                capture_slide(
                    chrome_bin,
                    src_file,
                    png_path,
                    banner,
                    scroll_y=scroll_y,
                    page_zoom=page_zoom,
                    width=1200,
                    height=700,
                )
                frame_data.append((png_path, dur))

        if not frame_data:
            print("❌ Brak kadrów do wygenerowania animacji!")
            sys.exit(1)

        total_animation_time = sum(d for _, d in frame_data)
        print(f"📦 Wygenerowano łącznie {len(frame_data)} klatek animacji (łączny czas: {total_animation_time:.1f}s). Łączę za pomocą ffmpeg...")
        generate_animation(ffmpeg_bin, frame_data, OUTPUT_GIF, OUTPUT_WEBP)

        gif_size_kb = OUTPUT_GIF.stat().st_size / 1024
        print("\n✅ Pomyślnie wygenerowano animację GIF:")
        print(f"   📁 Plik: {OUTPUT_GIF}")
        print(f"   ⚖️  Rozmiar: {gif_size_kb:.1f} KB ({gif_size_kb / 1024:.2f} MB)")

        if OUTPUT_WEBP.exists():
            webp_size_kb = OUTPUT_WEBP.stat().st_size / 1024
            print("✅ Wygenerowano również wersję WebP:")
            print(f"   📁 Plik: {OUTPUT_WEBP}")
            print(f"   ⚖️  Rozmiar: {webp_size_kb:.1f} KB ({webp_size_kb / 1024:.2f} MB)")

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
