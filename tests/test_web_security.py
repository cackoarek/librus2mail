"""
Testy jednostkowe bezpieczeństwa aplikacji webowej (Faza 2 planu naprawczego):
- Ochrona adresu IP przed spoofingiem nagłówka X-Forwarded-For / X-Real-IP
- Ochrona przed omijaniem blokady brute-force (LoginRateLimiter)
- Flagi bezpieczeństwa ciasteczek sesyjnych Flask (HttpOnly, SameSite, Secure)
- Bezpieczna obsługa uszkodzonych plików w FileStorage
"""

from librus2mail.storage import read_json_safe, write_json_atomic
from librus2mail.web.app import create_app
from librus2mail.web.auth import LoginRateLimiter, get_client_ip


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
