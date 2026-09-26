"""Bounded read-only LAB delivery clearance. No application imports or reconciliation."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time
from typing import Iterator

LIMIT = 200
MAX_BYTES = 64 * 1024 * 1024
DEADLINE_SECONDS = 15


@contextmanager
def read(path: str) -> Iterator[sqlite3.Connection]:
    """Open an existing database read-only, with a query deadline and snapshot."""
    connection = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=3)
    deadline = time.monotonic() + DEADLINE_SECONDS
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        yield connection
    finally:
        connection.rollback()
        connection.close()


def delivery_flags(value: object) -> tuple[int, int]:
    """Count explicit unpersisted acknowledgements and unresolved delivery facts."""
    acknowledged = unresolved = 0
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            acknowledged += int(bool(item.get('acknowledgement_received')) and not item.get('receipt_persisted'))
            unresolved += int(bool(item.get('reconciliation_required'))
                              or item.get('delivery_status') in ('UNKNOWN', 'FAILED', 'DELIVERY_UNKNOWN')
                              or (bool(item.get('transport_attempted')) and not item.get('receipt_persisted')))
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return acknowledged, unresolved


def stdout_records(path: str) -> list[dict]:
    """Inspect the latest 200 complete records, reading at most 64 MiB of stdout."""
    with Path(path).open('rb') as stream:
        size = stream.seek(0, 2)
        offset = max(0, size - MAX_BYTES)
        stream.seek(offset)
        raw = stream.read(MAX_BYTES)
    if not raw.endswith(b'\n'):
        raise ValueError('Incomplete or empty protected stdout evidence')
    lines = raw.splitlines()
    if offset:
        lines = lines[1:]
        if len(lines) < LIMIT:
            raise ValueError('Protected stdout evidence exceeds inspection bound')
    records = [json.loads(line) for line in lines[-LIMIT:]]
    if not records or any(not isinstance(value, dict) for value in records):
        raise ValueError('Malformed protected stdout evidence')
    if records[-1].get('schema_version') != 'goalvision-lab-v2-operator-cycle-v1':
        raise ValueError('Latest protected stdout is not accepted compact output')
    return records


def inventory(paths: dict[str, str]) -> dict:
    """Count all durable blockers; bound recent JSON inspection without writing history.

    This one-time re-enablement conservatively requires zero pending published
    settlements, so none can conceal a pending settlement integrity blocker.
    Database snapshots are separate. The installer repeats this check after drain.
    """
    blockers: dict[str, int] = {}
    with read(paths['ledger']) as c:
        queries = {
            'unreceipted_publication_claims': """SELECT count(*) FROM evidence c WHERE c.kind='claim'
                AND NOT EXISTS (SELECT 1 FROM evidence r WHERE r.kind='receipt' AND r.identity=c.identity)""",
            'delivery_unknown': "SELECT count(*) FROM evidence WHERE kind='delivery_unknown'",
            'economic_claims_without_receipts': """SELECT count(*) FROM evidence c WHERE c.kind='economic_claim'
                AND NOT EXISTS (SELECT 1 FROM evidence r WHERE r.kind='receipt'
                AND r.identity=json_extract(c.document,'$.publication_identity'))""",
            'invalid_receipts': """SELECT count(*) FROM evidence WHERE kind='receipt' AND
                (json_extract(document,'$.status') IS NOT 'SENT' OR json_extract(document,'$.sent') IS NOT 1
                 OR coalesce(json_extract(document,'$.message_id'),0)<=0)""",
            'pending_settlement_integrity_blockers': """SELECT count(*) FROM evidence r
                WHERE r.kind='receipt' AND
                ((r.identity GLOB 'single_prediction:*' AND NOT EXISTS
                    (SELECT 1 FROM evidence s WHERE s.kind='single_settlement'
                     AND 'single_prediction:'||s.identity=r.identity))
                 OR (r.identity GLOB 'combo_prediction:*' AND NOT EXISTS
                    (SELECT 1 FROM evidence s WHERE s.kind='settlement'
                     AND 'combo_prediction:'||s.identity=r.identity))
                 OR (r.identity GLOB 'prediction:*' AND NOT EXISTS
                    (SELECT 1 FROM evidence s WHERE s.kind='settlement'
                     AND 'prediction:'||s.identity=r.identity)))""",
        }
        for name, query in queries.items():
            blockers[name] = c.execute(query).fetchone()[0]
    with read(paths['adaptive']) as c:
        blockers['weekly_delivery_unknown'] = c.execute(
            "SELECT count(*) FROM weekly_delivery_unknown WHERE stream='PREMATCH'").fetchone()[0]
        blockers['weekly_unreceipted_claims'] = c.execute("""SELECT count(*) FROM weekly_claims q WHERE stream='PREMATCH'
            AND NOT EXISTS(SELECT 1 FROM weekly_receipts r WHERE r.claim_id=q.id AND r.stream=q.stream)""").fetchone()[0]
    acknowledged = unresolved = total_bytes = cycles = 0
    with read(paths['shadow']) as c:
        # Check lengths before materializing large reports into Python.
        for identity, length in c.execute("""SELECT identity,length(CAST(document_json AS BLOB))
                FROM lab_v2_shadow_evidence WHERE kind='publication_cycle'
                ORDER BY created_at_utc DESC,identity DESC LIMIT ?""", (LIMIT,)):
            total_bytes += length
            if total_bytes > MAX_BYTES:
                raise ValueError('Recent cycle evidence exceeds inspection bound')
            value = json.loads(c.execute("SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='publication_cycle' AND identity=?", (identity,)).fetchone()[0])
            if not isinstance(value, dict):
                raise ValueError('Malformed publication cycle')
            ack, pending = delivery_flags(value)
            acknowledged += ack
            unresolved += pending
            cycles += 1
    records = stdout_records(paths['stdout'])
    for value in records:
        ack, pending = delivery_flags(value)
        acknowledged += ack
        unresolved += pending
    blockers['acknowledged_unpersisted_delivery_evidence'] = acknowledged
    blockers['unresolved_delivery_evidence'] = unresolved
    return {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'blockers': blockers,
            'recent_cycles_checked': cycles, 'stdout_records_checked': len(records),
            'bounds': {'recent_cycles': LIMIT, 'stdout_records': LIMIT, 'bytes_per_source': MAX_BYTES,
                       'sql_seconds_per_database': DEADLINE_SECONDS},
            'pending_policy': 'Any pending published settlement blocks this one-time re-enablement.'}
