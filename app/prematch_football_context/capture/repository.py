"""Append-only sanitized sources, post-commit attestations and ordered cutoffs.

A source unit (identity + complete retained facts) commits atomically first.
Only AFTER that durable commit succeeds is the injected clock sampled. A second
append-only transaction retains that observation as its registration receipt.
Readers require both. An interrupted acknowledgement leaves an unavailable,
complete orphan, never a partially replayable source or a invented commit time.

The acknowledgement attests the *source* commit, not its own future commit time.
An exact retry can attest an orphan only at the retry's fresh clock. No old cache
reader/backfill is present. Equal-time proofs additionally require the source
receipt itself to precede a durable decision marker in this store's write order.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Callable

from ..evidence import EvidenceUnavailable
from ..fingerprint import canonical_bytes, utc
from ..sources import (
    Candidate, CaptureOrder, PARSER, Query, SourceHeader, SourceKind, Timing,
    digest, history_query, target_query, validate_header, validate_retained_document,
)
from .schema import verify


class ImmutableConflict(ValueError):
    """One logical response completion was replayed with different material."""


@dataclass(frozen=True, slots=True)
class Registration:
    source_id: str
    registered_at: datetime
    ordering: int
    receipt_hash: str
    replayed: bool


@dataclass(frozen=True, slots=True)
class DecisionReceipt:
    """A cutoff sampled under the store's exclusive append lock; not inference."""
    cutoff: datetime
    ordering: int
    receipt_hash: str


def _stamp(value: str) -> datetime:
    return utc(datetime.fromisoformat(value.replace('Z', '+00:00')))


def _text(value: datetime) -> str:
    return utc(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _validate(material: dict[str, object]) -> tuple[Query, SourceKind, Timing]:
    keys = {'version', 'namespace', 'provider', 'parser', 'query', 'kind',
            'retrieval_completed_at', 'expiry', 'provider_updated_at', 'content_hash', 'content'}
    if set(material) != keys or (material['version'], material['namespace'], material['provider'], material['parser']) != (
            'FC_DURABLE_CAPTURE_V1', 'FC_DURABLE_SOURCE_V1', 'API_FOOTBALL', PARSER):
        raise ValueError('INVALID_CAPTURE_CONTRACT')
    q = material['query']
    if set(q) != {'endpoint', 'parameters'}:
        raise ValueError('INVALID_QUERY')
    query = Query(q['endpoint'], tuple(tuple(pair) for pair in q['parameters']))
    kind = SourceKind(material['kind'])
    params = dict(query.parameters)
    expected = target_query(params['id']) if kind == SourceKind.TARGET else history_query(params['league'], params['season'])
    if query != expected:
        raise ValueError('INVALID_QUERY')
    end, expiry = _stamp(material['retrieval_completed_at']), _stamp(material['expiry'])
    maximum = timedelta(minutes=15) if kind == SourceKind.TARGET else timedelta(hours=6 if kind == SourceKind.CURRENT else 24)
    updated = _stamp(material['provider_updated_at']) if material['provider_updated_at'] is not None else None
    if not timedelta(0) < expiry - end <= maximum or (updated is not None and updated > end):
        raise ValueError('INVALID_TIMING')
    content = json.loads(material['content'])
    validate_retained_document(content)
    if content['error'] == 'PROVIDER_ERROR' or canonical_bytes(content).decode() != material['content'] or digest(content) != material['content_hash']:
        raise ValueError('INVALID_CONTENT')
    normalized = material | {'query': query, 'kind': kind, 'retrieval_completed_at': end, 'expiry': expiry, 'provider_updated_at': updated}
    if canonical_bytes(normalized) != canonical_bytes(material):
        raise ValueError('NONCANONICAL_MATERIAL')
    return query, kind, Timing(end, None, None, expiry, provider_updated_at=updated)


def _capture_key(material: dict[str, object]) -> str:
    # Completion + exact request + role identifies one logical captured response.
    # Content/expiry/provider-time changes under that identity must conflict.
    return digest({key: material[key] for key in (
        'version', 'namespace', 'provider', 'parser', 'query', 'kind', 'retrieval_completed_at')})


class EvidenceRepository:
    """Explicit existing-store connection; read-only by default, never auto-migrates.

    Writers require an injected UTC clock and full SQLite durability. No ambient
    wall clock, provider, runtime cache, or production database default exists.
    """

    def __init__(self, path: Path, *, clock: Callable[[], datetime] | None = None,
                 writable: bool = False) -> None:
        if writable and clock is None:
            raise ValueError('REGISTRATION_CLOCK_REQUIRED')
        self.clock = clock
        self.writable = writable
        self.connection = sqlite3.connect(path.resolve().as_uri() + ('?mode=rw' if writable else '?mode=ro'),
                                          uri=True, timeout=0.1, isolation_level=None)
        try:
            self.connection.execute('PRAGMA foreign_keys=ON')
            self.connection.execute('PRAGMA synchronous=FULL')
            verify(self.connection)
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        """Close this isolated connection."""
        self.connection.close()

    def _begin(self) -> None:
        if not self.writable:
            raise ValueError('READ_ONLY_EVIDENCE_STORE')
        self.connection.execute('BEGIN IMMEDIATE')

    def _commit(self) -> None:
        self.connection.commit()

    def _receipt(self, row: tuple) -> tuple[int, str, str | None, datetime, str]:
        order, event, source_id, stamp, receipt_hash = row
        material = {'ordering': order, 'event': event, 'source_id': source_id, 'observed_at': stamp}
        if (type(order) is not int or order < 1 or event not in ('SOURCE', 'DECISION')
                or (source_id is None) != (event == 'DECISION') or _text(_stamp(stamp)) != stamp
                or digest(material) != receipt_hash):
            raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: CORRUPT_RECEIPT')
        return order, event, source_id, _stamp(stamp), receipt_hash

    def _append_receipt(self, event: str, source_id: str | None, stamp: datetime) -> tuple:
        last = self.connection.execute('SELECT * FROM fc_receipts ORDER BY ordering DESC LIMIT 1').fetchone()
        previous = self._receipt(last) if last else None
        if previous and stamp < previous[3]:
            raise ValueError('REGISTRATION_CLOCK_REGRESSED')
        order = previous[0] + 1 if previous else 1
        document = {'ordering': order, 'event': event, 'source_id': source_id, 'observed_at': _text(stamp)}
        hashed = digest(document)
        self.connection.execute('INSERT INTO fc_receipts VALUES (?,?,?,?,?)', (order, event, source_id, _text(stamp), hashed))
        return order, event, source_id, stamp, hashed

    def register(self, material: dict[str, object]) -> Registration:
        """Atomically retain a source, then acknowledge its completed durable commit.

        Exact retries recover the original receipt. A failed commit cannot issue
        a receipt. Missing acknowledgements remain unavailable, including on load.
        """
        _, _, timing = _validate(material)
        serialized = canonical_bytes(material).decode()
        source_id, key = digest(material), _capture_key(material)
        self._begin()
        try:
            old = self.connection.execute('SELECT source_id,material_json FROM fc_sources WHERE capture_key=?', (key,)).fetchone()
            if old is not None and old != (source_id, serialized):
                raise ImmutableConflict('IMMUTABLE_CAPTURE_CONFLICT')
            if old is not None:
                receipt = self.connection.execute('SELECT * FROM fc_receipts WHERE source_id=?', (source_id,)).fetchone()
                if receipt is not None:
                    order, _, _, registered, hashed = self._receipt(receipt)
                    self.load(source_id)  # Verify the full retained unit even for replay.
                    self._commit()
                    return Registration(source_id, registered, order, hashed, True)
            else:
                self.connection.execute('INSERT INTO fc_sources VALUES (?,?,?)', (source_id, key, serialized))
            self._commit()  # Identity and ALL facts now durably exist together.
        except BaseException:
            self.connection.rollback()
            raise
        # Acquire append lock before the clock; ordering is consistent across writers.
        self._begin()
        try:
            existing = self.connection.execute('SELECT * FROM fc_receipts WHERE source_id=?', (source_id,)).fetchone()
            if existing is not None:
                order, _, _, registered, hashed = self._receipt(existing)
                self.load(source_id)
                replayed = True
            else:
                registered = utc(self.clock())  # Strictly after successful source commit.
                if registered < timing.retrieval_completed_at:
                    raise ValueError('REGISTRATION_BEFORE_RETRIEVAL')
                order, _, _, registered, hashed = self._append_receipt('SOURCE', source_id, registered)
                replayed = False
            self._commit()  # Publish acknowledgement; no reader used it before this succeeds.
        except BaseException:
            self.connection.rollback()
            raise
        return Registration(source_id, registered, order, hashed, replayed)

    def capture_cutoff(self) -> DecisionReceipt:
        """Append an ordering marker only; no context, vector, inference or model work.

        T is sampled under the same write lock AFTER prior receipts committed.
        A caller cannot backdate T. Equal precision is proven by integer order.
        """
        self._begin()
        try:
            cutoff = utc(self.clock())
            order, _, _, cutoff, hashed = self._append_receipt('DECISION', None, cutoff)
            self._commit()
        except BaseException:
            self.connection.rollback()
            raise
        return DecisionReceipt(cutoff, order, hashed)

    def load(self, source_id: str, *, decision: DecisionReceipt | None = None) -> Candidate:
        """Load one exact retained source, optionally bind a proven equal-time cutoff.

        Never fetch, migrate, acknowledge an orphan, or consult the legacy cache.
        """
        try:
            row = self.connection.execute('SELECT capture_key,material_json FROM fc_sources WHERE source_id=?', (source_id,)).fetchone()
            receipt = self.connection.execute('SELECT * FROM fc_receipts WHERE source_id=?', (source_id,)).fetchone()
            if row is None or receipt is None:
                raise ValueError('SOURCE_OR_REGISTRATION_MISSING')
            key, serialized = row
            material = json.loads(serialized)
            query, kind, timing = _validate(material)
            if canonical_bytes(material).decode() != serialized or digest(material) != source_id or _capture_key(material) != key:
                raise ValueError('SOURCE_INTEGRITY')
            order, event, identity, registered, hashed = self._receipt(receipt)
            if event != 'SOURCE' or identity != source_id:
                raise ValueError('RECEIPT_BINDING')
            timing = replace(timing, registered_at=registered, known_at=registered)
            if decision is not None:
                marker = self.connection.execute('SELECT * FROM fc_receipts WHERE ordering=?', (decision.ordering,)).fetchone()
                if marker is None or self._receipt(marker) != (decision.ordering, 'DECISION', None, decision.cutoff, decision.receipt_hash):
                    raise ValueError('DECISION_RECEIPT_UNPROVEN')
                if order < decision.ordering and registered <= decision.cutoff:
                    proof = CaptureOrder(decision.cutoff, source_id, material['content_hash'], digest({
                        'source_receipt': hashed, 'decision_receipt': decision.receipt_hash,
                        'source_order': order, 'decision_order': decision.ordering,
                    }))
                    timing = replace(timing, before_capture=proof)
            header = SourceHeader(source_id, query, kind, timing, material['content_hash'], namespace=material['namespace'])
            if validate_header(header) != 'SELECTED':
                raise ValueError('SOURCE_TIMING_INTEGRITY')
            return Candidate(header, material['content'])
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError, sqlite3.DatabaseError) as exc:
            raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: INVALID_DURABLE_SOURCE') from exc

    def load_cutoff(self, receipt_hash: str) -> DecisionReceipt:
        """Recover an exact durable decision marker after restart, without a clock."""
        try:
            row = self.connection.execute('SELECT * FROM fc_receipts WHERE receipt_hash=?', (receipt_hash,)).fetchone()
            if row is None:
                raise ValueError('MISSING_CUTOFF')
            order, event, _, cutoff, hashed = self._receipt(row)
            if event != 'DECISION':
                raise ValueError('NOT_A_CUTOFF')
            return DecisionReceipt(cutoff, order, hashed)
        except (ValueError, TypeError, sqlite3.DatabaseError) as exc:
            raise EvidenceUnavailable('EVIDENCE_UNAVAILABLE: INVALID_DURABLE_CUTOFF') from exc

    def inspect(self) -> tuple[Registration, ...]:
        """Read verified registered identities/times/order; load exposes kind and hashes.

        Complete but unacknowledged orphans do not count as captured evidence.
        Failures/conflicts/replays are returned by the adapter's diagnostics.
        """
        output = []
        for row in self.connection.execute("SELECT * FROM fc_receipts WHERE event='SOURCE' ORDER BY ordering"):
            order, _, source_id, stamp, hashed = self._receipt(row)
            self.load(source_id)
            output.append(Registration(source_id, stamp, order, hashed, False))
        return tuple(output)
