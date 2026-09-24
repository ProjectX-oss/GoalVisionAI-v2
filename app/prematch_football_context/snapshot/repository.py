"""Explicit separate append-only snapshot database; Phase C schema stays intact."""
from contextlib import closing
from dataclasses import fields
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from ..capture.repository import DecisionReceipt, EvidenceRepository, ImmutableConflict
from ..contracts import Classification
from ..evidence import Binding, EvidenceUnavailable
from ..fingerprint import canonical_bytes
from ..policy import Profile
from ..source_adapter import FormatEvidence
from .contracts import Opportunity, PrematchFootballContextV2Snapshot, Projection

TABLE = 'fc_v2_snapshots'


def _verify(connection: sqlite3.Connection) -> None:
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    guards = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    if (tables != {TABLE} or connection.execute('PRAGMA user_version').fetchone()[0] != 1
            or not {TABLE + '_no_' + op for op in ('update', 'delete', 'replace')} <= guards
            or connection.execute('PRAGMA journal_mode').fetchone()[0] not in ('delete', 'truncate', 'persist', 'wal')):
        raise ValueError('SNAPSHOT_SCHEMA_UNAVAILABLE')


def initialize(path: Path) -> None:
    """Explicitly create an empty isolated store; never migrate another schema."""
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('BEGIN IMMEDIATE')
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if tables or connection.execute('PRAGMA user_version').fetchone()[0]:
            _verify(connection)
            return
        connection.execute('''CREATE TABLE fc_v2_snapshots (
            snapshot_id TEXT PRIMARY KEY NOT NULL,
            opportunity_key TEXT UNIQUE NOT NULL,
            document TEXT NOT NULL
        )''')
        for operation in ('UPDATE', 'DELETE'):
            connection.execute(f'''CREATE TRIGGER {TABLE}_no_{operation.lower()}
                BEFORE {operation} ON {TABLE} BEGIN SELECT RAISE(ABORT,'FC_V2_IMMUTABLE'); END''')
        connection.execute('''CREATE TRIGGER fc_v2_snapshots_no_replace BEFORE INSERT ON fc_v2_snapshots
            WHEN EXISTS(SELECT 1 FROM fc_v2_snapshots WHERE snapshot_id=NEW.snapshot_id
                        OR opportunity_key=NEW.opportunity_key)
            BEGIN SELECT RAISE(ABORT,'FC_V2_IMMUTABLE'); END''')
        connection.execute('PRAGMA user_version=1')
        _verify(connection)


def decode(document: str) -> PrematchFootballContextV2Snapshot:
    """Strict executable-free canonical decoding, with all fingerprints checked."""
    try:
        doc = json.loads(document)
        if set(doc) != {f.name for f in fields(PrematchFootballContextV2Snapshot)}:
            raise ValueError('SNAPSHOT_KEYS')
        stamp = lambda text: datetime.fromisoformat(text.replace('Z', '+00:00'))
        b = doc['binding']
        classification = Classification(**(b['classification'] | {
            'profile': Profile(b['classification']['profile']), 'flags': tuple(b['classification']['flags'])}))
        formats = {}
        for name in ('current_format', 'previous_format'):
            fmt = b[name]
            formats[name] = FormatEvidence(**(fmt | {'known_at': stamp(fmt['known_at']) if fmt['known_at'] else None}))
        binding = Binding(**(b | formats | {'cutoff': stamp(b['cutoff']), 'classification': classification}))
        receipt = DecisionReceipt(**(doc['receipt'] | {'cutoff': stamp(doc['receipt']['cutoff'])}))
        p = doc['projection']
        projection = Projection(**(p | {'values': tuple(p['values']), 'missing': tuple(p['missing']),
                                      'reasons': tuple(tuple(r) for r in p['reasons']), 'names': tuple(p['names'])}))
        snapshot = PrematchFootballContextV2Snapshot(**(doc | {
            'opportunity': Opportunity(**doc['opportunity']), 'receipt': receipt, 'binding': binding,
            'projection': projection, 'source_candidates': tuple(tuple(ids) for ids in doc['source_candidates']),
            'selected_sources': tuple(doc['selected_sources']),
            'validations': tuple(tuple(v) for v in doc['validations']),
            'source_decisions': tuple(tuple(v) for v in doc['source_decisions']),
            'exclusions': tuple((v[0], tuple(v[1])) for v in doc['exclusions'])}))
        if not snapshot.snapshot_hash or canonical_bytes(snapshot).decode() != document:
            raise ValueError('NONCANONICAL_SNAPSHOT')
        return snapshot
    except (ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
        raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: CORRUPT_SNAPSHOT') from exc


class SnapshotRepository:
    """No automatic initialization; read-only by default; one atomic immutable row."""

    def __init__(self, path: Path, *, writable: bool = False) -> None:
        self.writable = writable
        self.connection = sqlite3.connect(path.resolve().as_uri() + ('?mode=rw' if writable else '?mode=ro'),
                                          uri=True, timeout=0.1, isolation_level=None)
        try:
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA synchronous=FULL')
            _verify(self.connection)
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        """Close the explicit connection."""
        self.connection.close()

    def load(self, opportunity_key: str) -> PrematchFootballContextV2Snapshot | None:
        """Read and validate one exact canonical opportunity; never mutate or repair."""
        row = self.connection.execute('SELECT snapshot_id,document FROM fc_v2_snapshots WHERE opportunity_key=?',
                                      (opportunity_key,)).fetchone()
        if row is None:
            return None
        value = decode(row[1])
        if value.snapshot_id != row[0] or value.opportunity.key != opportunity_key:
            raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: SNAPSHOT_IDENTITY')
        return value

    def _commit(self) -> None:
        self.connection.commit()

    def append(self, snapshot: PrematchFootballContextV2Snapshot) -> PrematchFootballContextV2Snapshot:
        """Exact replay idempotent; different material under the same key conflicts."""
        if not self.writable:
            raise ValueError('READ_ONLY_SNAPSHOT_STORE')
        document = canonical_bytes(snapshot).decode()
        decode(document)
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            old = self.load(snapshot.opportunity.key)
            if old is not None:
                if old != snapshot:
                    raise ImmutableConflict('IMMUTABLE_DECISION_CONFLICT')
            else:
                self.connection.execute('INSERT INTO fc_v2_snapshots VALUES (?,?,?)',
                                        (snapshot.snapshot_id, snapshot.opportunity.key, document))
            self._commit()
        except BaseException:
            self.connection.rollback()
            raise
        return snapshot

    def inspect(self, opportunity_key: str, evidence: EvidenceRepository) -> dict[str, object]:
        """Minimal verified read-only inspection; no outcomes or performance labels."""
        from .service import reproduce
        snapshot = self.load(opportunity_key)
        if snapshot is None:
            raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: SNAPSHOT_MISSING')
        reproduce(evidence, snapshot)
        return {'snapshot_id': snapshot.snapshot_id, 'opportunity_key': snapshot.opportunity.key,
                'candidate_id': snapshot.opportunity.candidate_id, 'cutoff': snapshot.receipt.cutoff,
                'receipt': snapshot.receipt, 'sources': snapshot.selected_sources,
                'values': dict(zip(snapshot.projection.names, snapshot.projection.values)),
                'missing_fields': tuple(n for n, m in zip(snapshot.projection.names, snapshot.projection.missing) if m),
                'reasons': snapshot.projection.reasons, 'validations': snapshot.validations,
                'source_decisions': snapshot.source_decisions,
                'exclusions': snapshot.exclusions, 'evidence_hash': snapshot.evidence_hash,
                'semantic_hash': snapshot.semantic_hash, 'input_hash': snapshot.input_hash,
                'result_hash': snapshot.result_hash, 'projection_hash': snapshot.projection_hash,
                'snapshot_hash': snapshot.snapshot_hash, 'reproduction': 'VERIFIED'}
