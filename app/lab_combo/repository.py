"""Dedicated append-only Lab Combo evidence ledger, never an Official database."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint


class ComboRepository:
    """Store immutable documents with atomic insert-or-conflict replay semantics."""

    def __init__(self, path: Path) -> None:
        root = (Path.cwd() / 'var/lab_combo').resolve()
        if root not in path.resolve().parents:
            raise ValueError('Combo ledger must be beneath var/lab_combo/.')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute('PRAGMA busy_timeout=5000')
        with self.connection:
            self.connection.execute('CREATE TABLE IF NOT EXISTS evidence (kind TEXT NOT NULL, identity TEXT NOT NULL, fingerprint TEXT NOT NULL, document TEXT NOT NULL, PRIMARY KEY(kind, identity))')
            for action in ('UPDATE', 'DELETE'):
                self.connection.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{action.lower()} BEFORE {action} ON evidence BEGIN SELECT RAISE(ABORT, 'Immutable Lab Combo evidence'); END")

    def close(self) -> None:
        self.connection.close()

    def get(self, kind: str, identity: str) -> dict | None:
        row = self.connection.execute('SELECT document, fingerprint FROM evidence WHERE kind=? AND identity=?', (kind, identity)).fetchone()
        if row is None:
            return None
        value = json.loads(row[0])
        if fingerprint(value) != row[1]:
            raise ValueError('Lab Combo evidence integrity conflict')
        return value

    def append(self, kind: str, identity: str, value: dict) -> bool:
        """Return true only to the winner of an atomic durable claim."""
        encoded, digest = canonical_json(value), fingerprint(value)
        with self.connection:
            cursor = self.connection.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?,?)', (kind, identity, digest, encoded))
            if cursor.rowcount:
                return True
            if self.get(kind, identity) != json.loads(encoded):
                raise ValueError('Conflicting Lab Combo evidence replay')
            return False

    def all(self, kind: str) -> list[dict]:
        identities = [row[0] for row in self.connection.execute('SELECT identity FROM evidence WHERE kind=? ORDER BY identity', (kind,))]
        return [self.get(kind, identity) for identity in identities]
