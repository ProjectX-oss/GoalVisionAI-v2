"""Run the specified pytest paths with real socket connections/DNS disabled."""
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def denied(*args, **kwargs):
    raise AssertionError('REAL_NETWORK_FORBIDDEN')


socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
socket.getaddrinfo = denied

import pytest

raise SystemExit(pytest.main(sys.argv[1:]))
