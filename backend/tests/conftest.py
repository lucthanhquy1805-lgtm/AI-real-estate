"""Cấu hình chung cho test.

Nguyên tắc 9: test không gọi mạng thật. Mọi kết nối socket và truy vấn DNS tới host ngoài localhost đều bị chặn.
(psycopg dùng libpq nên kết nối DB test qua localhost không đi qua đây.)
"""

import socket

import pytest

_LOCAL = {"localhost", "127.0.0.1", "::1"}
_real_connect = socket.socket.connect
_real_getaddrinfo = socket.getaddrinfo


def _is_local(host: object) -> bool:
    return host in _LOCAL or host is None or (isinstance(host, str) and host.startswith("/"))


def _guarded_connect(self: socket.socket, address: object) -> None:
    host = address[0] if isinstance(address, tuple) else address
    if not _is_local(host):
        raise RuntimeError(f"Test không được gọi mạng thật (kết nối tới {host!r})")
    return _real_connect(self, address)


def _guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> list:
    if not _is_local(host):
        raise RuntimeError(f"Test không được gọi mạng thật (tra DNS {host!r})")
    return _real_getaddrinfo(host, *args, **kwargs)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
