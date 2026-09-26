"""LIVE-only schema v1. Reads never initialize or migrate another database."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import fcntl
import json
from pathlib import Path
import sqlite3
from typing import Iterator

from .contracts import canonical, digest, utc

SCHEMA_VERSION = 1


class Store:
    """Fingerprinted append-only documents with optional immutable parent links."""

    def __init__(self, path: Path, *, readonly: bool = False) -> None:
        self.path = path.resolve()
        self.readonly = readonly
        if path.is_symlink():
            raise ValueError('LIVE_STORE_SYMLINK_REFUSED')
        if not readonly:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.connection = sqlite3.connect(self.path.as_uri() + ('?mode=ro' if readonly else '?mode=rwc'),
                                          uri=True, isolation_level=None, timeout=2)
        tables = {r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables - {'live_schema', 'live_documents'} or (readonly and not tables):
            self.close()
            raise ValueError('DEDICATED_LIVE_DATABASE_REQUIRED')
        self.connection.execute('PRAGMA foreign_keys=ON')
        if readonly:
            self.connection.execute('PRAGMA query_only=ON')
        else:
            self.connection.executescript('''
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS live_schema(version INTEGER PRIMARY KEY CHECK(version=1));
                INSERT OR IGNORE INTO live_schema VALUES(1);
                CREATE TABLE IF NOT EXISTS live_documents(
                    kind TEXT NOT NULL, id TEXT NOT NULL, created_at TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, document TEXT NOT NULL,
                    parent_kind TEXT, parent_id TEXT,
                    PRIMARY KEY(kind,id),
                    CHECK((parent_kind IS NULL) = (parent_id IS NULL)),
                    FOREIGN KEY(parent_kind,parent_id) REFERENCES live_documents(kind,id));
                CREATE INDEX IF NOT EXISTS live_time ON live_documents(kind,created_at);
                CREATE TRIGGER IF NOT EXISTS live_no_update BEFORE UPDATE ON live_documents
                    BEGIN SELECT RAISE(ABORT,'immutable LIVE evidence'); END;
                CREATE TRIGGER IF NOT EXISTS live_no_delete BEFORE DELETE ON live_documents
                    BEGIN SELECT RAISE(ABORT,'immutable LIVE evidence'); END;
                COMMIT;
            ''')

    @contextmanager
    def transaction(self) -> Iterator[None]:
        nested = self.connection.in_transaction
        if not nested:
            self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield
            if not nested:
                self.connection.commit()
        except BaseException:
            if not nested:
                self.connection.rollback()
            raise

    @contextmanager
    def opportunity_lock(self) -> Iterator[None]:
        """Serialize all LIVE workers without touching PREMATCH state or locks."""
        with self.path.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def append(self, kind: str, identity: str, value: dict, now: datetime,
               parent: tuple[str, str] | None = None) -> bool:
        """Identical replay is harmless; changed content at the same key fails."""
        body, fingerprint = canonical(value), digest(value)
        with self.transaction():
            row = self.connection.execute('SELECT fingerprint FROM live_documents WHERE kind=? AND id=?',
                                          (kind, identity)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise ValueError('LIVE_IMMUTABLE_CONFLICT')
                return False
            self.connection.execute('INSERT INTO live_documents VALUES(?,?,?,?,?,?,?)',
                                    (kind, identity, utc(now).isoformat(), fingerprint, body,
                                     *(parent or (None, None))))
        return True

    def get(self, kind: str, identity: str) -> dict | None:
        rows = self.connection.execute('SELECT document,fingerprint FROM live_documents WHERE kind=? AND id=?',
                                       (kind, identity)).fetchall()
        return self._verified(rows)[0] if rows else None

    def all(self, kind: str) -> list[dict]:
        return self._verified(self.connection.execute(
            'SELECT document,fingerprint FROM live_documents WHERE kind=? ORDER BY created_at,id', (kind,)).fetchall())

    @staticmethod
    def _verified(rows: list) -> list[dict]:
        values = []
        for body, fingerprint in rows:
            value = json.loads(body)
            if digest(value) != fingerprint:
                raise ValueError('LIVE_INTEGRITY_FAILURE')
            values.append(value)
        return values

    def close(self) -> None:
        self.connection.close()
