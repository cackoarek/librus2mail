"""Mechanizm autoryzacji i ochrony rodzicielskiej dla panelu webowego z blokadą IP."""

import functools
import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


def get_client_ip(req) -> str:
    """Ustala rzeczywisty adres IP klienta z uwzględnieniem nagłówków proxy."""
    if xff := req.headers.get('X-Forwarded-For'):
        return xff.split(',')[0].strip()
    if x_real := req.headers.get('X-Real-IP'):
        return x_real.strip()
    return req.remote_addr or '127.0.0.1'


class LoginRateLimiter:
    """Ochrona przed atakami brute-force na hasło rodzica z blokowaniem adresu IP."""

    def __init__(self, max_attempts: int = 5, lockout_duration_s: int = 900, window_s: int = 300):
        self.max_attempts = max_attempts
        self.lockout_duration_s = lockout_duration_s
        self.window_s = window_s
        self._failed_attempts: dict[str, list[datetime]] = defaultdict(list)
        self._lockouts: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def is_locked(self, ip: str, now: datetime | None = None) -> tuple[bool, int]:
        """Sprawdza, czy dany adres IP jest zablokowany. Zwraca (czy_zablokowany, pozostałe_sekundy)."""
        current_time = now or datetime.now()
        with self._lock:
            if ip in self._lockouts:
                lock_expiry = self._lockouts[ip]
                if current_time < lock_expiry:
                    remaining = int((lock_expiry - current_time).total_seconds())
                    return True, max(1, remaining)
                else:
                    del self._lockouts[ip]
                    self._failed_attempts.pop(ip, None)
            return False, 0

    def record_failure(self, ip: str, now: datetime | None = None) -> tuple[bool, int, int]:
        """
        Rejestruje nieudaną próbę logowania.
        Zwraca (czy_zablokowany, pozostałe_sekundy_blokady, pozostałe_próby_przed_blokadą).
        """
        current_time = now or datetime.now()
        with self._lock:
            if ip in self._lockouts:
                lock_expiry = self._lockouts[ip]
                if current_time < lock_expiry:
                    remaining = int((lock_expiry - current_time).total_seconds())
                    return True, max(1, remaining), 0
                else:
                    del self._lockouts[ip]
                    self._failed_attempts.pop(ip, None)

            window_start = current_time - timedelta(seconds=self.window_s)
            recent = [t for t in self._failed_attempts[ip] if t >= window_start]
            recent.append(current_time)
            self._failed_attempts[ip] = recent

            if len(recent) >= self.max_attempts:
                expiry = current_time + timedelta(seconds=self.lockout_duration_s)
                self._lockouts[ip] = expiry
                self._failed_attempts.pop(ip, None)
                logger.warning(
                    f"Wykryto {len(recent)} nieudanych prób logowania z IP {ip}. "
                    f"Adres zablokowany na {self.lockout_duration_s}s."
                )
                return True, self.lockout_duration_s, 0

            remaining_attempts = max(0, self.max_attempts - len(recent))
            return False, 0, remaining_attempts

    def record_success(self, ip: str) -> None:
        """Resetuje historię błędnych prób danego IP po udanym logowaniu."""
        with self._lock:
            self._failed_attempts.pop(ip, None)
            self._lockouts.pop(ip, None)

    def reset(self) -> None:
        """Czyści cały stan limitera."""
        with self._lock:
            self._failed_attempts.clear()
            self._lockouts.clear()


def get_rate_limiter() -> LoginRateLimiter:
    """Zwraca instancję limitera logowań z konfiguracji aplikacji."""
    limiter = current_app.config.get('LOGIN_RATE_LIMITER')
    if limiter is None:
        limiter = LoginRateLimiter()
        current_app.config['LOGIN_RATE_LIMITER'] = limiter
    return limiter


def is_auth_enabled() -> bool:
    """Zwraca True, jeśli ochrona hasłem jest włączona."""
    return bool(current_app.config.get('WEB_PASSWORD'))


def is_authenticated() -> bool:
    """Sprawdza, czy bieżąca sesja jest uwierzytelniona."""
    if not is_auth_enabled():
        return True
    return bool(session.get('authenticated'))


def login_required(view_func):
    """Dekorator wymagający zalogowania przed dostępem do widoku."""
    @functools.wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not is_authenticated():
            next_url = request.url if request.method == 'GET' else url_for('web.dashboard')
            return redirect(url_for('auth.login', next=next_url))
        return view_func(*args, **kwargs)
    return wrapped_view


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Ekran logowania rodzica z ochroną brute-force i blokadą IP."""
    if not is_auth_enabled() or is_authenticated():
        return redirect(url_for('web.dashboard'))

    limiter = get_rate_limiter()
    client_ip = get_client_ip(request)
    is_locked, remaining_seconds = limiter.is_locked(client_ip)
    remaining_minutes = (remaining_seconds + 59) // 60 if remaining_seconds > 0 else 0

    next_url = request.args.get('next') or url_for('web.dashboard')
    error = None

    if is_locked:
        error = f"Zbyt wiele nieudanych prób logowania. Dostęp z adresu IP {client_ip} został zablokowany jeszcze przez {remaining_minutes} min."
        return render_template(
            'web/login.html',
            error=error,
            next=next_url,
            is_locked=True,
            remaining_minutes=remaining_minutes,
            client_ip=client_ip,
            max_attempts=limiter.max_attempts,
        ), 429

    if request.method == 'POST':
        password = request.form.get('password', '')
        configured_password = current_app.config.get('WEB_PASSWORD', '')

        if password and password == configured_password:
            limiter.record_success(client_ip)
            session['authenticated'] = True
            session.permanent = bool(request.form.get('remember'))
            flash("Zalogowano pomyślnie do panelu rodzica.", "success")
            return redirect(next_url)
        else:
            locked_now, lock_sec, remaining_attempts = limiter.record_failure(client_ip)
            if locked_now:
                lock_min = (lock_sec + 59) // 60
                error = f"Zbyt wiele nieudanych prób logowania! Twój adres IP ({client_ip}) został zablokowany na {lock_min} min."
                return render_template(
                    'web/login.html',
                    error=error,
                    next=next_url,
                    is_locked=True,
                    remaining_minutes=lock_min,
                    client_ip=client_ip,
                    max_attempts=limiter.max_attempts,
                ), 429
            else:
                error = f"Nieprawidłowe hasło rodzica. Pozostało prób: {remaining_attempts}."

    return render_template(
        'web/login.html',
        error=error,
        next=next_url,
        is_locked=False,
        remaining_minutes=0,
        client_ip=client_ip,
        max_attempts=limiter.max_attempts,
    )


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    """Wylogowanie z panelu rodzica."""
    session.pop('authenticated', None)
    flash("Wylogowano z panelu rodzica.", "info")
    return redirect(url_for('auth.login'))
