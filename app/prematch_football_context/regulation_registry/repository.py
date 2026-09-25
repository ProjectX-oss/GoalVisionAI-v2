"""Explicit isolated SQLite store. No default path, migrations, or network."""
from contextlib import closing
from pathlib import Path
import sqlite3

from ..capture.repository import ImmutableConflict
from ..fingerprint import canonical_bytes
from .contracts import ReviewedCompetitionRegulation, decode

TABLE = 'fc_v2_reviewed_regulations'
SCHEMA = (
    f'CREATE TABLE {TABLE} (review_id TEXT PRIMARY KEY NOT NULL, fingerprint TEXT UNIQUE NOT NULL, document TEXT NOT NULL)',
    *(f"CREATE TRIGGER {TABLE}_no_{op.lower()} BEFORE {op} ON {TABLE} "
      "BEGIN SELECT RAISE(ABORT,'REGULATION_IMMUTABLE'); END" for op in ('UPDATE', 'DELETE')),
    f'CREATE TRIGGER {TABLE}_no_replace BEFORE INSERT ON {TABLE} '
    f'WHEN EXISTS(SELECT 1 FROM {TABLE} WHERE review_id=NEW.review_id OR fingerprint=NEW.fingerprint) '
    "BEGIN SELECT RAISE(ABORT,'REGULATION_IMMUTABLE'); END",
)


def _schema(connection: sqlite3.Connection) -> None:
    actual = {row[0] for row in connection.execute(
        "SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    if actual != set(SCHEMA) or connection.execute('PRAGMA user_version').fetchone()[0] != 1:
        raise ValueError('REGULATION_SCHEMA_UNAVAILABLE')


def initialize(path: Path) -> None:
    """Create a NEW isolated file only; never initialize an existing database."""
    # Exclusive filesystem creation prevents accidentally touching an evidence DB.
    with path.open('xb'):
        pass
    with closing(sqlite3.connect(path, timeout=0.1)) as connection, connection:
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('BEGIN IMMEDIATE')
        for statement in SCHEMA:
            connection.execute(statement)
        connection.execute('PRAGMA user_version=1')
        _schema(connection)


class Registry:
    """Read-only by default; explicit writable handle for operator import only."""

    def __init__(self, path: Path, *, writable: bool = False) -> None:
        self.writable = writable
        self.connection = sqlite3.connect(path.resolve().as_uri() + ('?mode=rw' if writable else '?mode=ro'),
                                          uri=True, timeout=0.1, isolation_level=None)
        try:
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA synchronous=FULL')
            _schema(self.connection)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        """Release the explicit connection."""
        self.connection.close()

    def records(self) -> tuple[ReviewedCompetitionRegulation, ...]:
        """Verify every row, including indexed identity, before supplying evidence."""
        result = []
        for identity, fingerprint, document in self.connection.execute(
                f'SELECT review_id,fingerprint,document FROM {TABLE} ORDER BY review_id'):
            record = decode(document)
            if (record.review_id != identity or record.evidence_fingerprint != fingerprint
                    or canonical_bytes(record).decode() != document):
                raise ValueError('REGULATION_ROW_INTEGRITY')
            result.append(record)
        return tuple(result)

    def verify(self) -> tuple[ReviewedCompetitionRegulation, ...]:
        """Check schema, SQLite integrity and all canonical review fingerprints."""
        _schema(self.connection)
        if (self.connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]
                or self.connection.execute('PRAGMA foreign_key_check').fetchall()):
            raise ValueError('REGULATION_STORE_INTEGRITY')
        return self.records()

    def append(self, record: ReviewedCompetitionRegulation) -> ReviewedCompetitionRegulation:
        """Exact replay is idempotent; same review identity with new content conflicts."""
        if not self.writable:
            raise ValueError('READ_ONLY_REGISTRY')
        document = canonical_bytes(record).decode()
        decode(document)
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            old = next((r for r in self.verify() if r.review_id == record.review_id), None)
            if old is not None:
                if old != record:
                    raise ImmutableConflict('REGULATION_REVIEW_CONFLICT')
            else:
                self.connection.execute(f'INSERT INTO {TABLE} VALUES (?,?,?)',
                                        (record.review_id, record.evidence_fingerprint, document))
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise
        return record
