"""Dedicated Lab audit schema; existing predictions/settlements remain authoritative.

No Official tables, credential lookup, imports with effects, or production migration.
All documents are immutable. The only mutable table is a transactionally checked
projection of the append-only champion generation ledger.
"""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
from typing import Iterator
from .contracts import canonical, digest, stream_name

SCHEMA_VERSION = 5
# Every parent is a real foreign key. Stream equality is enforced by composite keys.
PARENTS = {
    'weekly_claims': ('weekly_reports','report_id'),
    'weekly_receipts': ('weekly_claims','claim_id'),
    'weekly_delivery_unknown': ('weekly_claims','claim_id'),
    'learning_observations': ('source_records', 'source_id'),
    'learning_datasets': ('learning_cycles', 'cycle_id'),
    'split_assignments': ('learning_datasets', 'dataset_id'),
    'model_specs': ('learning_cycles', 'cycle_id'),
    'training_runs': ('model_specs', 'spec_id'),
    'model_artifacts': ('training_runs', 'run_id'),
    'validation_results': ('model_artifacts', 'artifact_id'),
    'holdout_results': ('model_artifacts', 'artifact_id'),
    'candidate_comparisons': ('model_artifacts', 'artifact_id'),
    'candidate_events': ('model_artifacts', 'artifact_id'),
    'shadow_runs': ('model_artifacts', 'artifact_id'),
    'shadow_predictions': ('shadow_runs', 'shadow_id'),
    'shadow_settlements': ('shadow_predictions', 'prediction_id'),
    'promotion_gates': ('shadow_runs', 'shadow_id'),
    'champion_generations': ('model_artifacts', 'artifact_id'),
    'champion_predictions': ('champion_generations', 'generation_id'),
    'activation_events': ('champion_generations', 'generation_id'),
    'rollback_events': ('champion_generations', 'generation_id'),
    'live_candidates': ('live_snapshots', 'snapshot_id'),
    'live_claims': ('live_candidates', 'selection_id'),
    'live_publications': ('live_claims', 'claim_id'),
    'live_settlements': ('live_publications', 'publication_id'),
    'live_result_claims': ('live_settlements', 'settlement_id'),
    'live_result_receipts': ('live_result_claims', 'claim_id'),
}
ROOTS = ('canonical_opportunities', 'canonical_results', 'source_records', 'learning_cycles', 'linkage_diagnostics', 'combo_analytics',
         'live_snapshots', 'live_diagnostics', 'quota_claims', 'quota_observations',
         'cycle_health', 'observer_runs', 'weekly_reports')
TABLES = (*ROOTS, *PARENTS)


class AuditRepository:
    """Explicit initialization; read-only inspection never creates a file or schema."""
    def __init__(self, path: Path | str, *, readonly: bool = False) -> None:
        self.readonly = readonly
        if readonly:
            self.connection = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        else:
            self.connection = sqlite3.connect(str(path), isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute('PRAGMA foreign_keys=ON')
        self.connection.execute('PRAGMA busy_timeout=5000')
        if readonly:
            self.connection.execute('PRAGMA query_only=ON')
        else:
            existing={r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            allowed=set(TABLES)|{'adaptive_schema','champion_pointers','sqlite_sequence'}
            if existing-allowed:
                self.connection.close()
                raise ValueError('DEDICATED_LAB_AUDIT_DATABASE_REQUIRED')
            self.migrate()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Serialize claims and pointer changes, including nested service operations."""
        if self.readonly:
            raise ValueError('READ_ONLY')
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

    def migrate(self) -> None:
        with self.transaction():
            self.connection.execute('CREATE TABLE IF NOT EXISTS adaptive_schema(version INTEGER PRIMARY KEY)')
            version = self.connection.execute('SELECT max(version) FROM adaptive_schema').fetchone()[0] or 0
            if version > SCHEMA_VERSION:
                raise ValueError('NEWER_SCHEMA_REQUIRES_NEWER_READER')
            for table in TABLES:
                parent = PARENTS.get(table)
                columns = []
                constraints = ['UNIQUE(id,stream)']
                if parent:
                    columns.append(f'{parent[1]} TEXT NOT NULL')
                    constraints.append(f'FOREIGN KEY({parent[1]},stream) REFERENCES {parent[0]}(id,stream)')
                if table == 'split_assignments':
                    columns.append('observation_id TEXT NOT NULL')
                    constraints.append('FOREIGN KEY(observation_id,stream) REFERENCES learning_observations(id,stream)')
                extra = ','.join([*columns,*constraints])
                self.connection.execute(f'''CREATE TABLE IF NOT EXISTS {table} (
                    id TEXT PRIMARY KEY, stream TEXT NOT NULL CHECK(stream IN ('PREMATCH','LIVE','COMBO')),
                    created_at TEXT NOT NULL, fingerprint TEXT NOT NULL, document TEXT NOT NULL,
                    {extra})''')
                self.connection.execute(f'CREATE INDEX IF NOT EXISTS {table}_stream_time ON {table}(stream,created_at,id)')
                for action in ('UPDATE', 'DELETE'):
                    self.connection.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()}
                        BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable adaptive evidence'); END''')
            self.connection.execute('''CREATE TABLE IF NOT EXISTS champion_pointers (
                stream TEXT PRIMARY KEY CHECK(stream IN ('PREMATCH','LIVE')), generation_id TEXT NOT NULL,
                FOREIGN KEY(generation_id,stream) REFERENCES champion_generations(id,stream))''')
            self.connection.execute('''CREATE UNIQUE INDEX IF NOT EXISTS observation_opportunity
                ON learning_observations(stream,json_extract(document,'$.opportunity_key'))''')
            self.connection.execute('''CREATE UNIQUE INDEX IF NOT EXISTS shadow_opportunity
                ON shadow_predictions(shadow_id,json_extract(document,'$.opportunity_key'))''')
            self.connection.execute('''CREATE UNIQUE INDEX IF NOT EXISTS live_publication_once ON live_publications(claim_id)''')
            self.connection.execute('INSERT OR IGNORE INTO adaptive_schema VALUES (1)')
            self.connection.execute('INSERT OR IGNORE INTO adaptive_schema VALUES (2)')
            self.connection.execute('INSERT OR IGNORE INTO adaptive_schema VALUES (4)')
            self.connection.execute('INSERT OR IGNORE INTO adaptive_schema VALUES (5)')

    def append(self, table: str, identity: str, stream: str, document: dict,
               created_at: str, **links: str) -> bool:
        if table not in TABLES or stream not in {'PREMATCH', 'LIVE', 'COMBO'}:
            raise ValueError('AUDIT_TABLE_OR_STREAM_INVALID')
        if stream == 'COMBO' and table != 'combo_analytics':
            raise ValueError('COMBO_IS_NOT_PREDICTIVE_LEARNING')
        required = {PARENTS[table][1]} if table in PARENTS else set()
        if table == 'split_assignments':
            required.add('observation_id')
        if set(links) != required:
            raise ValueError('AUDIT_LINKS_INVALID')
        encoded, fp = canonical(document), digest(document)
        with self.transaction():
            existing = self.connection.execute(f'SELECT * FROM {table} WHERE id=?', (identity,)).fetchone()
            if existing:
                if (existing['fingerprint'] != fp or existing['stream'] != stream or
                        any(existing[k] != v for k, v in links.items())):
                    raise ValueError('CONFLICTING_REPLAY')
                self.get(table, identity)
                return False
            columns = ['id', 'stream', 'created_at', 'fingerprint', 'document', *links]
            self.connection.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                    (identity, stream, created_at, fp, encoded, *links.values()))
            return True

    def get(self, table: str, identity: str) -> dict | None:
        if table not in TABLES:
            raise ValueError('AUDIT_TABLE_INVALID')
        row = self.connection.execute(f'SELECT * FROM {table} WHERE id=?', (identity,)).fetchone()
        if row is None:
            return None
        value = json.loads(row['document'])
        if digest(value) != row['fingerprint']:
            raise ValueError('ARTIFACT_INTEGRITY_FAILURE')
        return value

    def all(self, table: str, stream: str | None = None) -> list[dict]:
        if table not in TABLES:
            raise ValueError('AUDIT_TABLE_INVALID')
        where, args = (' WHERE stream=?', (stream,)) if stream else ('', ())
        ids = self.connection.execute(f'SELECT id FROM {table}{where} ORDER BY created_at,id', args)
        return [self.get(table, row[0]) for row in ids]

    def champion(self, stream: str) -> dict | None:
        stream_name(stream)
        row = self.connection.execute('SELECT generation_id FROM champion_pointers WHERE stream=?', (stream,)).fetchone()
        return self.get('champion_generations', row[0]) if row else None

    def quota_since(self, since: str) -> list[dict]:
        """Verify only potentially relevant claims, using existing stream/time indexes."""
        ids = self.connection.execute(
            "SELECT id FROM quota_claims WHERE stream IN ('PREMATCH','LIVE') AND created_at>=? ORDER BY created_at,id",
            (since,),
        ).fetchall()
        return [self.get('quota_claims', row[0]) for row in ids]

    def matching_observations(self, stream: str, fixture_id: int, market: str) -> list[dict]:
        """Read verified economic matches without deserializing unrelated history."""
        ids = self.connection.execute(
            "SELECT id FROM learning_observations WHERE stream=? "
            "AND json_extract(document,'$.fixture_id')=? AND json_extract(document,'$.market')=? "
            "ORDER BY created_at,id", (stream, fixture_id, market),
        ).fetchall()
        return [self.get('learning_observations', row[0]) for row in ids]

    def close(self) -> None:
        self.connection.close()
