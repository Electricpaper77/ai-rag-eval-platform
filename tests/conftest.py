"""Pytest-only Windows compatibility for AnyIO's TestClient portal.

The host's native Windows socket.socketpair() blocks during Starlette/AnyIO
portal startup. A loopback TCP pair provides the same connected-socket
contract without changing application code or global OS networking settings.
"""
from __future__ import annotations

import socket
import sys


def _tcp_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
    if family != socket.AF_INET or type != socket.SOCK_STREAM:
        raise ValueError("test fallback supports AF_INET/SOCK_STREAM only")
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM, proto)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM, proto)
    client.connect(listener.getsockname())
    server, _ = listener.accept()
    listener.close()
    return client, server


if sys.platform == "win32":
    socket.socketpair = _tcp_socketpair
