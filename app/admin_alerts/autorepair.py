"""ADMIN-only immutable repair reservations and activation exclusions."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import TYPE_CHECKING

from app.admin_autorepair.protocol import atomic_json, check_spool, job_id, safe_reference, spool_lock
from .model import LABELS, UNITS
from .rules import CODE_RULES

if TYPE_CHECKING:
    from .store import Store

FIX_RULES = frozenset(('QUOTA_DB_CONTENTION', 'SERVICE_FAILURE', 'ANALYSIS_FAILURE',
    'CYCLE_PERSISTENCE', 'INTEGRITY_FAILURE', 'OBSERVATION_FAILURE', 'DATABASE_LOCK',
    'RUNNING_LONG', 'MISSING_OUTPUT', 'MONITORING_COVERAGE_DEGRADED'))
BOOL_FACTS = frozenset(('running', 'transport_attempted', 'acknowledgement_received',
    'receipt_persisted', 'reconciliation_required', 'claim_exists', 'read_available'))
NUMBER_FACTS = frozenset(('exit_status', 'contract_version', 'count', 'line'))
ENUM_FACTS = {
    'code': frozenset(CODE_RULES),
    'result': frozenset(('exit-code', 'signal', 'timeout', 'oom-kill', 'core-dump', 'success')),
    'association': frozenset(('TIME_WINDOW_ONLY', 'EXACT_INVOCATION')),
    'reason': frozenset(('MONITORING_GAP', 'READ_UNAVAILABLE', 'UNSUPPORTED_RECORD',
        'INVALID_RECORD_SHAPE', 'MISSING_TIMESTAMP', 'SOURCE_CLOCK_SKEW', 'NEXT_ELAPSE_UNKNOWN',
        'OUTPUT_CONTRACT_ROUTE_UNKNOWN', 'COMPLETION_ASSOCIATION_UNKNOWN', 'INVALID_DELIVERY')),
}


def initialize(db: sqlite3.Connection) -> None:
    """Migrate only the dedicated ADMIN store; durable history has mutation guards."""
    db.executescript('''
        CREATE TABLE IF NOT EXISTS repair_activation(id INTEGER PRIMARY KEY CHECK(id=1), created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS repair_exclusions(
            incident TEXT NOT NULL, episode INTEGER NOT NULL, reason TEXT NOT NULL,
            PRIMARY KEY(incident,episode));
        CREATE TABLE IF NOT EXISTS repair_jobs(
            id TEXT PRIMARY KEY,incident TEXT NOT NULL,episode INTEGER NOT NULL,
            created REAL NOT NULL,bundle TEXT NOT NULL,UNIQUE(incident,episode));
        CREATE TABLE IF NOT EXISTS operator_jobs(
            id TEXT PRIMARY KEY,state TEXT NOT NULL,sequence INTEGER NOT NULL,status TEXT NOT NULL,
            last_notice REAL NOT NULL DEFAULT 0,stall_generation INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS operator_outbox(
            id TEXT PRIMARY KEY,job TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,
            created REAL NOT NULL,state TEXT NOT NULL DEFAULT 'PENDING',due REAL NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,receipt TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS operator_attempts(
            id INTEGER PRIMARY KEY,outbox TEXT NOT NULL,started REAL NOT NULL,result TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS operator_attempt_time ON operator_attempts(started);
        CREATE INDEX IF NOT EXISTS operator_outbox_due ON operator_outbox(state,due);
    ''')
    for table in ('repair_activation', 'repair_exclusions', 'repair_jobs'):
        for action in ('UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table}
                BEGIN SELECT RAISE(ABORT, 'REPAIR_HISTORY_IMMUTABLE'); END''')
    db.commit()


def bundle(row: dict, now: float) -> dict:
    """Copy only typed allowlisted facts; hash non-opaque object/cycle references."""
    if row['service'] not in (*UNITS, 'monitor') or row['rule'] not in LABELS:
        raise ValueError('UNSUPPORTED_INCIDENT')
    evidence = json.loads(row['evidence'])
    source = evidence.get('facts', {})
    if not isinstance(source, dict):
        source = {}
    facts = {k: v for k, v in source.items() if
             (k in BOOL_FACTS and type(v) is bool) or
             (k in NUMBER_FACTS and type(v) is int and 0 <= v <= 10**6) or
             (k in ENUM_FACTS and isinstance(v, str) and v in ENUM_FACTS[k])}
    mode = 'FIX_ALLOWED' if row['rule'] in FIX_RULES else 'DIAGNOSE_ONLY'
    # Configuration and authentication uncertainty must never grant editing rights.
    if source.get('code') == 'LAB_BOT_IDENTITY_MISMATCH' or source.get('reason') in (
            'OUTPUT_CONTRACT_ROUTE_UNKNOWN', 'NEXT_ELAPSE_UNKNOWN'):
        mode = 'DIAGNOSE_ONLY'
    return {'version': 1, 'job_id': job_id(row['id'], row['episode']),
            'incident_id': row['id'], 'episode': row['episode'], 'generation': row['generation'],
            'service': row['service'], 'rule': row['rule'], 'severity': min(3, max(1, int(row['severity']))),
            'invocation': safe_reference(row['invocation']), 'cycle': safe_reference(evidence.get('cycle')),
            'object_id': safe_reference(row['object_id']), 'facts': facts, 'created_at': now,
            'target': 'ADMIN' if row['service'] == 'monitor' or row['rule'] in (
                'MONITORING_COVERAGE_DEGRADED', 'ADMIN_DELIVERY_DEGRADED') else 'PREMATCH', 'mode': mode}


def enqueue(store: Store, spool: Path, now: float) -> str | None:
    """Reserve before publishing; resume interrupted handoff without duplicate jobs.

    Called under the ADMIN scan lock. The shared lock fences worker renames during
    reconciliation. A missing/corrupt status never frees an outstanding slot.
    """
    check_spool(spool)
    with spool_lock(spool), store.db:
        store.db.execute('BEGIN IMMEDIATE')
        if not store.db.execute('SELECT 1 FROM repair_activation').fetchone():
            store.db.execute('INSERT INTO repair_activation VALUES (1,?)', (now,))
            store.db.execute('''INSERT OR IGNORE INTO repair_exclusions
                SELECT id,episode,'ACTIVATION_BASELINE' FROM incidents
                WHERE state IN ('PENDING','OPEN','REPEATED','ESCALATED')''')
            return None
        maintenance = store.get('maintenance', {})
        for entry in maintenance.values():
            if entry.get('until', 0) > now:
                store.db.execute('''INSERT OR IGNORE INTO repair_exclusions
                    SELECT id,episode,'MAINTENANCE' FROM incidents
                    WHERE state IN ('PENDING','OPEN','REPEATED','ESCALATED') AND (?='all' OR service=?)''',
                    (entry.get('scope'), entry.get('scope')))
        # Recover DB->filesystem interruption first, including a reservation whose
        # incident has since recovered. It is already accepted durable work.
        outstanding = store.db.execute('''SELECT r.* FROM repair_jobs r LEFT JOIN operator_jobs o ON o.id=r.id
            WHERE o.id IS NULL OR o.state NOT IN ('COMPLETED','FAILED','TIMEOUT') ORDER BY r.created,r.id''').fetchall()
        for row in outstanding:
            if not any((spool / d / (row['id'] + '.json')).exists() for d in ('queue', 'running', 'done')):
                atomic_json(spool / 'queue' / (row['id'] + '.json'), json.loads(row['bundle']))
                return row['id']
        physical = sum(1 for directory in ('queue', 'running') for _ in (spool / directory).glob('*.json'))
        if len(outstanding) >= 5 or physical >= 5:
            return None
        rows = store.db.execute('''SELECT i.* FROM incidents i
            WHERE state IN ('OPEN','REPEATED','ESCALATED')
            AND NOT EXISTS (SELECT 1 FROM repair_exclusions x WHERE x.incident=i.id AND x.episode=i.episode)
            AND NOT EXISTS (SELECT 1 FROM repair_jobs j WHERE j.incident=i.id AND j.episode=i.episode)
            ORDER BY severity DESC,last_seen,id''')
        selected = None
        for row in rows:
            try:
                selected = bundle(dict(row), now)
                break
            except (ValueError, TypeError):
                continue
        if selected is None:
            return None
        store.db.execute('INSERT INTO repair_jobs VALUES (?,?,?,?,?)', (selected['job_id'], selected['incident_id'],
            selected['episode'], now, json.dumps(selected, sort_keys=True)))
    # Commit reservation BEFORE publishing. Worker must never see untracked work.
    with spool_lock(spool):
        atomic_json(spool / 'queue' / (selected['job_id'] + '.json'), selected)
    return selected['job_id']
