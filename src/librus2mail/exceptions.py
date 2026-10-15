"""
Dedykowana hierarchia wyjątków domenowych dla Librus2mail.
"""

import requests


class LibrusError(Exception):
    """Bazowy wyjątek dla wszystkich błędów powiązanych z obsługą portalu Librus Synergia."""

    def __init__(self, message: str = "Błąd obsługi Librus Synergia"):
        self.message = message
        super().__init__(self.message)


class LibrusNetworkError(LibrusError, requests.RequestException):
    """Błąd sieciowy, timeout lub tymczasowa niedostępność serwerów Librusa (kody 5xx, brak połączenia)."""

    def __init__(self, message: str = "Błąd sieciowy Librus Synergia", request=None, response=None):
        LibrusError.__init__(self, message)
        requests.RequestException.__init__(self, message, request=request, response=response)


class LibrusAuthError(LibrusError):
    """Błąd uwierzytelniania: nieprawidłowy login/hasło, zablokowane konto, brak uprawnień lub wymagane 2FA."""
    pass


class LibrusParsingError(LibrusError):
    """Błąd parsowania struktury HTML (nieoczekiwana zmiana układu stron lub brak wymaganych selektorów)."""
    pass


class NotLogged(LibrusAuthError):
    """Wyjątek zgłaszany przy próbie wykonania operacji bez aktywnej autoryzacji w Librus Synergia."""
    pass
