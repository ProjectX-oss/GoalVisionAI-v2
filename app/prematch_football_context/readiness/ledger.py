"""Small append-only run/attempt diagnostics; never stores feature values."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from ..fingerprint import canonical_bytes
from ..sources import digest

TABLE = 'fc_readiness_events'
KINDS = ('RUN', 'OPPORTUNITY', 'RESULT', 'END', 'REGISTRY_VIEW', 'REGISTRY_ACQUISITION',
         'REGISTRY_DECISION', 'REGULATION_PROOF', 'REGULATION_LINK')


def verify(connection: sqlite3.Connection) -> None:
    """Reject unrelated/incomplete stores without modifying them."""
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    triggers = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    if tables != {TABLE} or connection.execute('PRAGMA user_version').fetchone()[0] != 1 or not {
            TABLE + '_no_' + op for op in ('update', 'delete', 'replace')} <= triggers:
        raise ValueError('READINESS_SCHEMA_UNAVAILABLE')


def initialize(path: Path) -> None:
    """Explicit bootstrap of an isolated store; never repairs an existing store."""
    with closing(sqlite3.connect(path)) as c, c:
        c.execute('PRAGMA synchronous=FULL')
        c.execute('BEGIN IMMEDIATE')
        if c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() or c.execute('PRAGMA user_version').fetchone()[0]:
            verify(c)
            return
        c.execute('CREATE TABLE fc_readiness_events (kind TEXT NOT NULL, identity TEXT NOT NULL, document TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(kind,identity))')
        for op in ('UPDATE', 'DELETE'):
            c.execute(f"CREATE TRIGGER {TABLE}_no_{op.lower()} BEFORE {op} ON {TABLE} BEGIN SELECT RAISE(ABORT,'READINESS_IMMUTABLE'); END")
        c.execute(f"CREATE TRIGGER {TABLE}_no_replace BEFORE INSERT ON {TABLE} WHEN EXISTS(SELECT 1 FROM {TABLE} WHERE kind=NEW.kind AND identity=NEW.identity) BEGIN SELECT RAISE(ABORT,'READINESS_IMMUTABLE'); END")
        c.execute('PRAGMA user_version=1')
        verify(c)


class Ledger:
    """Existing-store connection, read-only unless explicitly requested."""

    def __init__(self, path: Path, *, writable: bool = False) -> None:
        self.writable = writable
        self.connection = sqlite3.connect(path.resolve().as_uri() + ('?mode=rw' if writable else '?mode=ro'),
                                          uri=True, timeout=.1, isolation_level=None)
        try:
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA synchronous=FULL')
            verify(self.connection)
        except Exception:
            self.connection.close()
            raise

    def append(self, kind: str, identity: str, document: dict[str, object]) -> None:
        """Exact retry is idempotent; first content cannot be overwritten."""
        if not self.writable or kind not in KINDS:
            raise ValueError('READINESS_WRITE_REJECTED')
        text = canonical_bytes(document).decode()
        hashed = digest((kind, identity, document))
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            old = self.connection.execute(f'SELECT document,hash FROM {TABLE} WHERE kind=? AND identity=?', (kind, identity)).fetchone()
            if old is None:
                self.connection.execute(f'INSERT INTO {TABLE} VALUES (?,?,?,?)', (kind, identity, text, hashed))
            elif old != (text, hashed):
                raise ValueError('READINESS_IMMUTABLE_CONFLICT')
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def read(self) -> tuple[list[tuple[str, str, dict[str, object]]], int]:
        """Return verified records and explicit corruption count, never silent skips."""
        records, corrupt = [], 0
        for kind, identity, text, hashed in self.connection.execute(f'SELECT * FROM {TABLE} ORDER BY kind,identity'):
            try:
                doc = json.loads(text)
                if kind not in KINDS or type(doc) is not dict or canonical_bytes(doc).decode() != text or digest((kind, identity, doc)) != hashed:
                    raise ValueError('CORRUPT')
                records.append((kind, identity, doc))
            except (ValueError, TypeError):
                corrupt += 1
        return records, corrupt

    def close(self) -> None:
        """Close the explicit connection."""
        self.connection.close()
