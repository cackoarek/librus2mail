import socket

import pytest


@pytest.fixture(autouse=True, scope="session")
def block_external_librus_network():
    """
    Automatyczna blokada gwarantująca, że żaden test w całym pakiecie
    nie nawiąże rzeczywistego połączenia sieciowego z portalem Librus Synergia
    ani zewnętrznym internetem.
    """
    orig_connect = socket.socket.connect

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, (list, tuple)) else address
        host_str = str(host).lower()

        # Zezwalamy wyłącznie na lokalny loopback (gdyby testy używały wewnętrznego serwera testowego)
        if host_str in ("127.0.0.1", "localhost", "::1"):
            return orig_connect(self, address)

        raise RuntimeError(
            f"Wykryto niezamockowane połączenie sieciowe w teście do: '{host}'. "
            "Wszystkie zapytania HTTP do portalu Librus oraz zewnętrznych serwisów MUSZĄ być zamockowane!"
        )

    socket.socket.connect = guarded_connect
    try:
        yield
    finally:
        socket.socket.connect = orig_connect
