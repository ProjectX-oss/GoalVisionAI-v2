"""Explicit additive bootstrap for the dedicated evidence database only.

Like the adjacent isolated ShadowEvidenceRepository, this store owns its schema;
no migration is allocated in the unrelated production Database lineage.
"""
from pathlib import Path
from contextlib import closing
import sqlite3

VERSION = 1
TABLES = ('fc_sources', 'fc_receipts')


def verify(connection: sqlite3.Connection) -> None:
    """Refuse wrong/incomplete schemas or nondurable journal settings."""
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    guards = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    required = {f'{table}_no_{operation}' for table in TABLES for operation in ('update', 'delete', 'replace')}
    if (connection.execute('PRAGMA user_version').fetchone()[0] != VERSION
            or tables != set(TABLES) or not required <= guards
            or connection.execute('PRAGMA journal_mode').fetchone()[0] not in ('delete', 'truncate', 'persist', 'wal')):
        raise ValueError('EVIDENCE_SCHEMA_UNAVAILABLE')


def initialize(path: Path) -> None:
    """Create/upgrade an empty dedicated store; refuse every unrelated database.

    No caller invokes this on import/startup. Existing version-one evidence is
    left intact. DDL, guards and version marker are committed atomically.
    """
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('BEGIN IMMEDIATE')
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if version == VERSION and tables == set(TABLES):
            verify(connection)
            return
        if version != 0 or tables:
            raise ValueError('NOT_AN_EMPTY_DEDICATED_EVIDENCE_STORE')
        connection.execute('''CREATE TABLE fc_sources (
            source_id TEXT PRIMARY KEY NOT NULL,
            capture_key TEXT UNIQUE NOT NULL,
            material_json TEXT NOT NULL
        )''')
        connection.execute('''CREATE TABLE fc_receipts (
            ordering INTEGER PRIMARY KEY CHECK(ordering > 0),
            event TEXT NOT NULL CHECK(event IN ('SOURCE', 'DECISION')),
            source_id TEXT UNIQUE REFERENCES fc_sources(source_id),
            observed_at TEXT NOT NULL,
            receipt_hash TEXT UNIQUE NOT NULL,
            CHECK((event='SOURCE' AND source_id IS NOT NULL) OR
                  (event='DECISION' AND source_id IS NULL))
        )''')
        for table in TABLES:
            for operation in ('UPDATE', 'DELETE'):
                connection.execute(f'''CREATE TRIGGER {table}_no_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN SELECT RAISE(ABORT, 'FC_IMMUTABLE'); END''')
        # REPLACE may otherwise delete implicitly without firing DELETE triggers.
        connection.execute('''CREATE TRIGGER fc_sources_no_replace BEFORE INSERT ON fc_sources
            WHEN EXISTS(SELECT 1 FROM fc_sources WHERE source_id=NEW.source_id OR capture_key=NEW.capture_key)
            BEGIN SELECT RAISE(ABORT, 'FC_IMMUTABLE'); END''')
        connection.execute('''CREATE TRIGGER fc_receipts_no_replace BEFORE INSERT ON fc_receipts
            WHEN EXISTS(SELECT 1 FROM fc_receipts WHERE ordering=NEW.ordering OR
                receipt_hash=NEW.receipt_hash OR source_id=NEW.source_id)
            BEGIN SELECT RAISE(ABORT, 'FC_IMMUTABLE'); END''')
        connection.execute(f'PRAGMA user_version={VERSION}')
        verify(connection)
