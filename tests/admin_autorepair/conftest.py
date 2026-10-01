"""Synthetic filesystem and network-denied fixtures; no real Codex invocation."""
import socket
import pytest

from app.admin_alerts.store import Store
from app.admin_autorepair.protocol import DIRECTORIES


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('NETWORK_FORBIDDEN')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)


@pytest.fixture
def spool(tmp_path):
    root = tmp_path / 'spool'
    root.mkdir()
    for name in DIRECTORIES:
        (root / name).mkdir()
    return root


@pytest.fixture
def store(tmp_path):
    root = tmp_path / 'admin-alerts'
    root.mkdir()
    value = Store(root)
    yield value
    value.close()
