"""Generator i eksporter przykładowych statycznych widoków HTML panelu webowego."""

import logging
import os
import re
from datetime import datetime

from .app import create_app

logger = logging.getLogger(__name__)


def make_offline_friendly(html: str) -> str:
    """Zastępuje adresy URL względnymi odnośnikami do wygenerowanych plików HTML dla przeglądania offline."""
    replacements = [
        ('href="/"', 'href="web_dashboard.html"'),
        ('href="/plan"', 'href="web_plan.html"'),
        ('href="/oceny"', 'href="web_oceny.html"'),
        ('href="/terminarz"', 'href="web_terminarz.html"'),
        ('href="/wiadomosci"', 'href="web_wiadomosci.html"'),
        ('href="/raporty/podsumowanie"', 'href="web_raporty_podsumowanie.html"'),
        ('href="/raporty"', 'href="web_raporty_postepy.html"'),
        ('href="/akcje"', 'href="web_akcje.html"'),
        ('href="/ustawienia"', 'href="web_ustawienia.html"'),
        ('href="/setup"', 'href="web_setup.html"'),
        ('href="/logout"', 'href="web_login.html"'),
        ('href="/login"', 'href="web_login.html"'),
    ]
    for old, new in replacements:
        html = html.replace(old, new)

    # Linki podstron raportów z parametrami (days, variant, date)
    html = re.sub(r'href="/raporty/postepy(\?[^"]*)?"', 'href="web_raporty_postepy.html"', html)
    html = re.sub(r'href="/raporty/uczen\?[^"]*variant=kids[^"]*"', 'href="web_raporty_uczen_kids.html"', html)
    html = re.sub(r'href="/raporty/uczen\?[^"]*variant=youth[^"]*"', 'href="web_raporty_uczen_youth.html"', html)
    html = re.sub(r'href="/raporty/uczen(\?[^"]*)?"', 'href="web_raporty_uczen_teens.html"', html)
    html = re.sub(r'href="/raporty/podsumowanie(\?[^"]*)?"', 'href="web_raporty_podsumowanie.html"', html)

    # W podglądzie statycznym formularz logowania kieruje od razu na pulpit
    html = re.sub(r'action="/login[^"]*"', 'action="web_dashboard.html" method="GET"', html)
    return html


def export_web_views(
    output_dir: str,
    config_path: str = 'config.yaml',
    storage_dir: str | None = None,
    user_login: str | None = None,
    actual_date: datetime | str | None = None,
    make_links_relative: bool = True,
) -> dict[str, str]:
    """
    Generuje i zapisuje statyczne widoki HTML panelu webowego:
    - web_login.html (ekran przed zalogowaniem)
    - web_dashboard.html (pulpit główny po zalogowaniu)
    - web_plan.html (plan lekcji)
    - web_oceny.html (zestawienie ocen)
    - web_terminarz.html (terminarz)
    - web_wiadomosci.html (wiadomości i ogłoszenia)
    - web_akcje.html (centrum akcji CLI)

    Zwraca słownik {nazwa_pliku: ścieżka_do_pliku}.
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_files: dict[str, str] = {}

    # 1. Widok przed zalogowaniem (z wymuszonym hasłem i brakiem autoryzacji)
    app_locked = create_app(
        config_path=config_path,
        storage_dir=storage_dir,
        web_password='ExampleParentPassword123',
        no_auth=False,
        actual_date=actual_date,
    )
    client_locked = app_locked.test_client()
    login_res = client_locked.get('/login')
    login_html = login_res.data.decode('utf-8')
    if make_links_relative:
        login_html = make_offline_friendly(login_html)

    login_path = os.path.join(output_dir, 'web_login.html')
    with open(login_path, 'w', encoding='utf-8') as f:
        f.write(login_html)
    generated_files['web_login.html'] = login_path
    logger.info(f"Wygenerowano widok logowania: {login_path}")

    # 1b. Widok kreatora konfiguracji setup (dla demonstracji / dokumentacji)
    app_empty = create_app(
        config_path='non_existent_config.yaml',
        storage_dir=storage_dir,
        no_auth=True,
    )
    client_empty = app_empty.test_client()
    setup_res = client_empty.get('/setup')
    if setup_res.status_code == 200:
        setup_html = setup_res.data.decode('utf-8')
        if make_links_relative:
            setup_html = make_offline_friendly(setup_html)
        setup_path = os.path.join(output_dir, 'web_setup.html')
        with open(setup_path, 'w', encoding='utf-8') as f:
            f.write(setup_html)
        generated_files['web_setup.html'] = setup_path
        logger.info(f"Wygenerowano widok kreatora konfiguracji: {setup_path}")

    # 2. Widoki po zalogowaniu (autoryzowana sesja użytkownika)
    app_auth = create_app(
        config_path=config_path,
        storage_dir=storage_dir,
        web_password='ExampleParentPassword123',
        no_auth=False,
        actual_date=actual_date,
    )
    client_auth = app_auth.test_client()

    with client_auth.session_transaction() as sess:
        sess['authenticated'] = True
        if user_login:
            sess['active_student_login'] = str(user_login)

    views_to_export = [
        ('/', 'web_dashboard.html', "pulpit główny"),
        ('/plan', 'web_plan.html', "plan lekcji"),
        ('/oceny', 'web_oceny.html', "zestawienie ocen"),
        ('/terminarz', 'web_terminarz.html', "terminarz"),
        ('/wiadomosci', 'web_wiadomosci.html', "wiadomości"),
        ('/raporty/postepy', 'web_raporty_postepy.html', "raport postępów"),
        ('/raporty/uczen?variant=kids', 'web_raporty_uczen_kids.html', "raport ucznia (kids)"),
        ('/raporty/uczen?variant=teens', 'web_raporty_uczen_teens.html', "raport ucznia (teens)"),
        ('/raporty/uczen?variant=youth', 'web_raporty_uczen_youth.html', "raport ucznia (youth)"),
        ('/raporty/podsumowanie', 'web_raporty_podsumowanie.html', "podsumowanie powiadomień"),
        ('/akcje', 'web_akcje.html', "centrum akcji"),
        ('/ustawienia', 'web_ustawienia.html', "ustawienia systemu"),
    ]

    for route, filename, label in views_to_export:
        res = client_auth.get(route)
        if res.status_code == 200:
            content = res.data.decode('utf-8')
            if make_links_relative:
                content = make_offline_friendly(content)
            file_path = os.path.join(output_dir, filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            generated_files[filename] = file_path
            logger.info(f"Wygenerowano widok {label}: {file_path}")
        else:
            logger.warning(f"Nie udało się wygenerować widoku {route}: status {res.status_code}")

    return generated_files
