"""
Testy jednostkowe bezpieczeństwa aplikacji webowej (Faza 2 planu naprawczego):
- Ochrona adresu IP przed spoofingiem nagłówka X-Forwarded-For / X-Real-IP
- Ochrona przed omijaniem blokady brute-force (LoginRateLimiter)
- Flagi bezpieczeństwa ciasteczek sesyjnych Flask (HttpOnly, SameSite, Secure)
- Bezpieczna obsługa uszkodzonych plików w FileStorage
"""

import os
import stat

from werkzeug.middleware.proxy_fix import ProxyFix

from librus2mail.storage import read_json_safe, write_json_atomic
from librus2mail.web.app import create_app, get_or_create_persistent_secret_key
from librus2mail.web.auth import LoginRateLimiter, get_client_ip, is_ip_trusted


class DummyRequest:
    def __init__(self, headers=None, remote_addr='127.0.0.1'):
        self.headers = headers or {}
        self.remote_addr = remote_addr


class TestWebSecurity:
    def test_get_client_ip_untrusted_proxy_spoofing_ignored(self):
        """Żądanie z obcego adresu IP (np. Internet) próbujące podrobić X-Forwarded-For jest ignorowane."""
        req = DummyRequest(
            remote_addr="198.51.100.5",
            headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"},
        )
        assert get_client_ip(req) == "198.51.100.5"

    def test_get_client_ip_trusted_proxy_accepted(self):
        """Żądanie z zaufanego proxy (loopback 127.0.0.1 lub ::1) przyjmuje IP z nagłówka X-Forwarded-For/X-Real-IP."""
        req_xff = DummyRequest(
            remote_addr="127.0.0.1",
            headers={"X-Forwarded-For": "203.0.113.195, 70.41.3.18"},
        )
        assert get_client_ip(req_xff) == "203.0.113.195"

        req_real = DummyRequest(
            remote_addr="::1",
            headers={"X-Real-IP": "198.51.100.42"},
        )
        assert get_client_ip(req_real) == "198.51.100.42"

    def test_get_client_ip_custom_trusted_proxies(self):
        """Możliwość konfiguracji własnej listy zaufanych adresów IP proxy."""
        trusted = {"10.0.0.1", "10.0.0.2"}

        # Żądanie z zaufanego proxy w sieci prywatnej
        req_trusted = DummyRequest(
            remote_addr="10.0.0.1",
            headers={"X-Forwarded-For": "192.0.2.1"},
        )
        assert get_client_ip(req_trusted, trusted_proxies=trusted) == "192.0.2.1"

        # Żądanie z niezaufanego proxy
        req_untrusted = DummyRequest(
            remote_addr="10.0.0.99",
            headers={"X-Forwarded-For": "192.0.2.1"},
        )
        assert get_client_ip(req_untrusted, trusted_proxies=trusted) == "10.0.0.99"

    def test_login_rate_limiter_spoofing_attack_blocked(self):
        """
        Atakujący wysyłający błędne hasła z tego samego remote_addr, ale rotujący nagłówek
        X-Forwarded-For, zostaje skutecznie zablokowany na poziomie rzeczywistego IP.
        """
        limiter = LoginRateLimiter(max_attempts=3, lockout_duration_s=600, window_s=300)
        attacker_ip = "198.51.100.7"

        # 3 nieudane próby z różnymi fałszywymi nagłówkami X-Forwarded-For
        for fake_ip in ["1.1.1.1", "2.2.2.2", "3.3.3.3"]:
            req = DummyRequest(
                remote_addr=attacker_ip,
                headers={"X-Forwarded-For": fake_ip},
            )
            detected_ip = get_client_ip(req)
            assert detected_ip == attacker_ip  # Fałszywy nagłówek jest ignorowany
            locked, _, _ = limiter.record_failure(detected_ip)

        # Po 3 próbach atakujący IP jest zablokowany
        is_locked, remaining = limiter.is_locked(attacker_ip)
        assert is_locked is True
        assert remaining > 0

    def test_flask_session_cookie_security_flags(self, tmp_path):
        """Weryfikuje poprawne ustawienie flag HttpOnly, SameSite oraz Secure na ciasteczkach sesyjnych."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("librus_users: []\n", encoding="utf-8")

        # 1. Domyślna bezpieczna konfiguracja sesji
        app_default = create_app(config_path=str(config_path))
        assert app_default.config["SESSION_COOKIE_HTTPONLY"] is True
        assert app_default.config["SESSION_COOKIE_SAMESITE"] == "Lax"
        assert app_default.config["SESSION_COOKIE_SECURE"] is False

        # 2. Konfiguracja z włączonym wymuszeniem HTTPS / cookie_secure
        secure_config_path = tmp_path / "config_secure.yaml"
        secure_config_path.write_text(
            "librus_users: []\nweb:\n  cookie_secure: true\n  session_cookie_samesite: Strict\n",
            encoding="utf-8",
        )
        app_secure = create_app(config_path=str(secure_config_path))
        assert app_secure.config["SESSION_COOKIE_HTTPONLY"] is True
        assert app_secure.config["SESSION_COOKIE_SAMESITE"] == "Strict"
        assert app_secure.config["SESSION_COOKIE_SECURE"] is True

    def test_storage_read_corrupted_json(self, tmp_path):
        """Weryfikuje odporność read_json_safe na uszkodzone pliki JSON oraz tworzenie backupu."""
        corrupted_file = tmp_path / "broken.json"
        corrupted_file.write_text("{ niepoprawny json ...", encoding="utf-8")

        data = read_json_safe(corrupted_file)
        assert data == {}
        backup_file = tmp_path / "broken.json.corrupted"
        assert backup_file.exists()
        assert backup_file.read_text(encoding="utf-8") == "{ niepoprawny json ..."

    def test_storage_write_json_atomic_unserializable(self, tmp_path):
        """write_json_atomic nie rzuca nieobsłużonego błędu przy nieserializowalnych obiektach."""
        target_file = tmp_path / "test.json"
        write_json_atomic(target_file, {"invalid": object()})
        assert not target_file.exists()

    def test_is_ip_trusted_cidr(self):
        """Weryfikuje poprawne dopasowanie adresu IP do reguł CIDR oraz pojedynczych adresów."""
        trusted_proxies = {"127.0.0.1", "172.18.0.0/16", "10.0.0.0/8"}

        # Adresy w podsieci
        assert is_ip_trusted("127.0.0.1", trusted_proxies) is True
        assert is_ip_trusted("172.18.0.1", trusted_proxies) is True
        assert is_ip_trusted("172.18.254.10", trusted_proxies) is True
        assert is_ip_trusted("10.5.20.1", trusted_proxies) is True

        # Adresy poza zaufanymi podsieciami
        assert is_ip_trusted("172.19.0.1", trusted_proxies) is False
        assert is_ip_trusted("192.168.1.1", trusted_proxies) is False
        assert is_ip_trusted("8.8.8.8", trusted_proxies) is False

        # Zaufanie do wszystkich przy wildcard '*'
        assert is_ip_trusted("1.2.3.4", {"*"}) is True

        # Pusta lista lub niepoprawne IP
        assert is_ip_trusted("127.0.0.1", set()) is False
        assert is_ip_trusted("", trusted_proxies) is False
        assert is_ip_trusted("invalid_ip", trusted_proxies) is False

    def test_persistent_secret_key(self, tmp_path):
        """Weryfikuje generowanie, trwałość oraz uprawnienia 0600 pliku .secret_key w katalogu storage."""
        storage_dir = tmp_path / "storage"
        key_file = storage_dir / ".secret_key"

        # 1. Pierwsze wywołanie tworzy nowy plik klucza
        key1 = get_or_create_persistent_secret_key(storage_dir)
        assert len(key1) >= 32
        assert key_file.exists()
        assert key_file.read_text(encoding="utf-8").strip() == key1

        # Weryfikacja uprawnień (0600 na systemach POSIX)
        if os.name == "posix":
            file_mode = stat.S_IMODE(os.stat(key_file).st_mode)
            assert file_mode == 0o600

        # 2. Drugie wywołanie odczytuje dokładnie ten sam klucz (trwałość po restarcie)
        key2 = get_or_create_persistent_secret_key(storage_dir)
        assert key2 == key1

    def test_http_security_headers(self, tmp_path):
        """Weryfikuje obecność nagłówków bezpieczeństwa OWASP w odpowiedziach HTTP."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("librus_users: []\n", encoding="utf-8")

        app = create_app(config_path=str(config_path), storage_dir=str(tmp_path / "storage"), no_auth=True)
        client = app.test_client()

        res = client.get("/favicon.ico")
        assert res.headers.get("X-Content-Type-Options") == "nosniff"
        assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "mode=block" in res.headers.get("X-XSS-Protection", "")

    def test_proxy_fix_enabled(self, tmp_path):
        """Weryfikuje konfigurację ProxyFix middleware, gdy włączono behind_proxy."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text("librus_users: []\n", encoding="utf-8")

        app = create_app(
            config_path=str(config_path),
            storage_dir=str(tmp_path / "storage"),
            behind_proxy=True,
        )
        assert isinstance(app.wsgi_app, ProxyFix)

    def test_csrf_protection_lifecycle(self, tmp_path):
        """Weryfikuje cykl życia ochrony CSRF: blokowanie bez tokenu, akceptacja z poprawnym tokenem w formularzu i nagłówku."""
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "librus_users:\n  - librus_login: '123'\n    librus_login_name: 'Test'\n    librus_password: 'pass'\n",
            encoding="utf-8",
        )

        app = create_app(
            config_path=str(config_path),
            storage_dir=str(tmp_path / "storage"),
            no_auth=True,
            enable_csrf=True,
        )
        client = app.test_client()

        # 1. POST bez tokenu CSRF -> 400 Bad Request
        res_blocked = client.post("/api/whatif", data={"subject": "Matematyka", "grade": "5", "weight": "2"})
        assert res_blocked.status_code == 400
        assert "token" in res_blocked.get_data(as_text=True).lower()

        # 2. POST z błędnym tokenem CSRF -> 400 Bad Request
        res_invalid = client.post(
            "/api/whatif",
            data={"subject": "Matematyka", "grade": "5", "weight": "2", "csrf_token": "fake_token_123"},
        )
        assert res_invalid.status_code == 400

        # 3. GET pobiera stronę i inicjuje _csrf_token w sesji
        res_page = client.get("/")
        assert res_page.status_code in (200, 302)

        with client.session_transaction() as sess:
            valid_token = sess.get("_csrf_token")
            assert valid_token is not None
            assert len(valid_token) >= 32

        # 4. POST z prawidłowym tokenem w polu formularza `csrf_token` -> sukces (200)
        res_form_ok = client.post(
            "/api/whatif",
            data={"subject": "Matematyka", "grade": "5", "weight": "2", "csrf_token": valid_token},
        )
        assert res_form_ok.status_code == 200

        # 5. POST z prawidłowym tokenem w nagłówku HTTP `X-CSRFToken` -> sukces (200)
        res_header_ok = client.post(
            "/api/whatif",
            data={"subject": "Matematyka", "grade": "5", "weight": "2"},
            headers={"X-CSRFToken": valid_token},
        )
        assert res_header_ok.status_code == 200

