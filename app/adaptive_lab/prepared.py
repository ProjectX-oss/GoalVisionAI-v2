"""Optimistic append batches: verified reads and computation precede the write lock.

Append-only high-water marks detect every concurrent insertion into a read table.
Mutable champion pointers are validated separately. A stale batch writes nothing.
No production snapshot, schema migration, or history mutation is performed.
"""
from __future__ import annotations
from contextlib import nullcontext
from copy import deepcopy
from typing import ContextManager
from .contracts import canonical, digest
from .repository import AuditRepository, PreparedAppend, PARENTS, TABLES


class AuditSnapshotChanged(RuntimeError):
    """Prepared evidence changed before the atomic commit; no writes escaped."""


class PreparedAudit:
    """Private immutable append batch with conservative table-level validation."""
    def __init__(self, repository: AuditRepository) -> None:
        if repository.connection.in_transaction:
            raise ValueError('PREPARE_OUTSIDE_WRITE_TRANSACTION_REQUIRED')
        self.repository = repository
        self.revisions: dict[str, int] = {}
        self.pointers: dict[str, str | None] = {}
        self.pending: list[PreparedAppend] = []
        self.pointer_changes: dict[str, str] = {}

    def _watch(self, table: str) -> None:
        if table not in self.revisions:
            self.revisions[table] = self.repository.revision(table)

    def get(self, table: str, identity: str) -> dict | None:
        import json
        for row in self.pending:
            if (row.table, row.identity) == (table, identity):
                return json.loads(row.encoded)
        self._watch(table)
        return self.repository.get(table, identity)

    def all(self, table: str, stream: str | None = None) -> list[dict]:
        import json
        self._watch(table)
        rows = self.repository.all(table, stream)
        return rows + [json.loads(r.encoded) for r in self.pending
                       if r.table == table and (stream is None or r.stream == stream)]

    def champion(self, stream: str) -> dict | None:
        if stream not in self.pointers:
            self.pointers[stream] = self.repository.pointer(stream)
        identity = self.pointer_changes.get(stream, self.pointers[stream])
        return self.get('champion_generations', identity) if identity else None

    def set_champion(self, stream: str, generation_id: str) -> None:
        self.champion(stream)
        self.pointer_changes[stream] = generation_id

    def matching_observations(self, stream: str, fixture_id: int, market: str) -> list[dict]:
        self._watch('learning_observations')
        return self.repository.matching_observations(stream, fixture_id, market)

    def quota_since(self, since: str) -> list[dict]:
        self._watch('quota_claims')
        return self.repository.quota_since(since)

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
        row = PreparedAppend(table, identity, stream, canonical(document), digest(document),
                             created_at, deepcopy(links))
        for pending in self.pending:
            if (pending.table, pending.identity) == (table, identity):
                if (pending.stream, pending.encoded, pending.links) != (stream, row.encoded, links):
                    raise ValueError('CONFLICTING_REPLAY')
                return False
        existing = self.get(table, identity)
        if existing is not None:
            # Immutable replays validate exact bytes and links without a writer lock.
            return self.repository.append_prepared(row)
        self.pending.append(row)
        return True

    def transaction(self) -> ContextManager[None]:
        """Service nesting is an in-memory batch, never a SQLite write transaction."""
        return nullcontext()

    def commit(self) -> None:
        """Validate read dependencies and persist the complete batch atomically."""
        if not self.pending and not self.pointer_changes:
            return
        with self.repository.transaction():
            if any(self.repository.revision(t) != v for t, v in self.revisions.items()) or any(
                    self.repository.pointer(s) != v for s, v in self.pointers.items()):
                raise AuditSnapshotChanged('AUDIT_SNAPSHOT_CHANGED')
            for row in self.pending:
                self.repository.append_prepared(row)
            for stream, identity in self.pointer_changes.items():
                self.repository.set_champion(stream, identity)
