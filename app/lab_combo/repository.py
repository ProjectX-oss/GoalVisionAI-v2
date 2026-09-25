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

    def claim_publication(self, kind: str, prediction: dict, claim: dict) -> bool:
        """Atomically claim an economic selection across versions and legacy paths.

        Unknown delivery stays claimed. The economic key excludes model, label,
        quote and candidate IDs. Existing immutable historical claims also block.
        Singles and combos remain separate accounting products.
        """
        if kind not in {'single_prediction', 'combo_prediction', 'prediction'}:
            raise ValueError('Unsupported prediction claim')
        single = kind == 'single_prediction'

        def economic(value: dict) -> str:
            legs = [value] if single else value['legs']
            keys = sorted(f"{leg['fixture_id']}:{leg['market']}" for leg in legs)
            return ('SINGLE:' if single else 'COMBO:') + '|'.join(keys)

        key = economic(prediction)
        identity = kind + ':' + prediction['prediction_id']
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            if self.get('economic_claim', key) or self.get('claim', identity):
                return False
            for old in self.all('single_prediction' if single else 'prediction'):
                if economic(old) != key:
                    continue
                prefixes = ('single_prediction:',) if single else ('combo_prediction:', 'prediction:')
                if any(self.get(record, prefix + old['prediction_id'])
                       for prefix in prefixes for record in ('claim', 'receipt')):
                    return False
            for record, record_id, document in (
                ('economic_claim', key, {'publication_identity': identity, 'economic_key': key}),
                ('claim', identity, claim),
            ):
                self.connection.execute('INSERT INTO evidence VALUES (?,?,?,?)',
                    (record, record_id, fingerprint(document), canonical_json(document)))
        return True
