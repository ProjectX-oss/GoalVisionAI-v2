"""Append-only execution associations; source incident identities remain independent."""
from __future__ import annotations

import json
import sqlite3

from .model import digest

VERSION = 'ADMIN_CORRELATION_V1'
PRECEDENCE = {'QUOTA_DB_CONTENTION': 0, 'AUTH_FAILURE': 1, 'INTEGRITY_FAILURE': 1,
              'CYCLE_PERSISTENCE': 1, 'OBSERVATION_FAILURE': 1,
              'SERVICE_FAILURE': 2, 'ANALYSIS_FAILURE': 3, 'MISSING_OUTPUT': 4}
EXECUTION_RULES = frozenset(PRECEDENCE)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS source_evidence(
 id TEXT PRIMARY KEY, incident TEXT NOT NULL, recorded_at REAL NOT NULL, document TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS correlation_audit(
 id TEXT PRIMARY KEY, correlation_id TEXT NOT NULL, primary_incident TEXT NOT NULL,
 supporting_incidents TEXT NOT NULL, service TEXT NOT NULL, invocation TEXT NOT NULL,
 association TEXT NOT NULL, created_at REAL NOT NULL, rule_version TEXT NOT NULL,
 evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notification_audit(
 outbox TEXT PRIMARY KEY, reason TEXT NOT NULL, correlation_id TEXT,
 created_at REAL NOT NULL, original_outbox TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notification_epochs(
 id TEXT PRIMARY KEY, activated_at REAL NOT NULL, policy TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS epoch_incidents(
 incident TEXT PRIMARY KEY, epoch TEXT NOT NULL);
'''


def initialize(db: sqlite3.Connection) -> None:
    db.executescript(SCHEMA)
    for table in ('source_evidence', 'correlation_audit', 'notification_audit', 'notification_epochs', 'epoch_incidents'):
        for operation in ('UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'ADMIN_AUDIT_IMMUTABLE'); END''')
    db.commit()


def groups(db: sqlite3.Connection) -> list[dict]:
    """Exact identity wins; unknown persisted health needs a unique 30-second match.

    Recompute from preserved source rows so a later competing candidate cancels a
    temporal projection. Prior decisions remain immutable in the audit log.
    """
    rows = [dict(r) for r in db.execute("SELECT * FROM incidents WHERE state NOT IN ('INVALIDATED','PENDING')")
            if r['rule'] in EXECUTION_RULES]
    exact: dict[tuple, list] = {}
    unknown = []
    for row in rows:
        if row['invocation'] != 'UNKNOWN':
            exact.setdefault((row['service'], row['invocation']), []).append(row)
        else:
            unknown.append(row)
    associations = {}
    for row in unknown:
        evidence = json.loads(row['evidence'])
        candidates = [r for r in rows if r['rule'] == 'SERVICE_FAILURE'
                      and r['invocation'] != 'UNKNOWN' and r['service'] == row['service']
                      and abs(r['first_seen'] - row['first_seen']) <= 30]
        if row['rule'] == 'ANALYSIS_FAILURE' and evidence.get('source', '').startswith('health') and len(candidates) == 1:
            key = (row['service'], candidates[0]['invocation'])
            exact[key].append(row)
            associations[row['id']] = 'UNIQUE_TEMPORAL_SAME_SERVICE'
        else:
            exact[(row['service'], 'UNKNOWN:' + row['id'])] = [row]
    result = []
    for (service, invocation), members in exact.items():
        members.sort(key=lambda r: (PRECEDENCE[r['rule']], r['first_seen'], r['id']))
        result.append({'correlation_id': digest((VERSION, service, invocation)),
                       'primary_incident': members[0]['id'], 'members': members,
                       'service': service, 'invocation': invocation.split(':')[0],
                       'associations': {r['id']: associations.get(r['id'],
                           'INDEPENDENT' if invocation.startswith('UNKNOWN:') else 'EXACT_INVOCATION') for r in members}})
    return result


def supersede(db: sqlite3.Connection, row: sqlite3.Row, reason: str, now: float,
              correlation_id: str | None = None) -> bool:
    """Attempted, uncertain and acknowledged histories are never rewritten."""
    if (row['attempts'] or row['acknowledged'] or row['receipt'] is not None
            or row['state'] not in ('PENDING',) or db.execute('SELECT 1 FROM attempts WHERE outbox=?', (row['id'],)).fetchone()):
        return False
    db.execute('INSERT OR IGNORE INTO notification_audit VALUES (?,?,?,?,?)',
               (row['id'], reason, correlation_id, now, json.dumps(dict(row), sort_keys=True)))
    db.execute("UPDATE outbox SET state='SUPERSEDED' WHERE id=?", (row['id'],))
    return True


def reconcile(db: sqlite3.Connection, now: float) -> list[dict]:
    result = groups(db)
    for group in result:
        supporting = [r['id'] for r in group['members'][1:]]
        associations = group['associations']
        audit_id = digest((group['correlation_id'], group['primary_incident'], supporting, associations))
        db.execute('INSERT OR IGNORE INTO correlation_audit VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (audit_id, group['correlation_id'], group['primary_incident'], json.dumps(supporting),
                    group['service'], group['invocation'],
                    'UNIQUE_TEMPORAL_SAME_SERVICE' if 'UNIQUE_TEMPORAL_SAME_SERVICE' in associations.values()
                    else next(iter(associations.values())), now, VERSION,
                    json.dumps({'associations': associations, 'source_incidents': group['members']}, sort_keys=True)))
        ids = [r['id'] for r in group['members']]
        notifications = db.execute('SELECT * FROM outbox WHERE incident IN (' + ','.join('?' for _ in ids) + ')', ids).fetchall()
        attempted = any(r['attempts'] or r['acknowledged'] or r['receipt'] is not None
                        or db.execute('SELECT 1 FROM attempts WHERE outbox=?', (r['id'],)).fetchone() for r in notifications)
        for row in notifications:
            primary = group['members'][0]
            if row['incident'] != group['primary_incident'] or (attempted and primary['state'] != 'RECOVERED'):
                supersede(db, row, 'CORRELATED_EXECUTION_SUPPORT' if not attempted else 'EXECUTION_ALREADY_NOTIFIED',
                          now, group['correlation_id'])
            elif not row['attempts'] and row['state'] == 'PENDING':
                from .model import alert
                db.execute('UPDATE outbox SET body=? WHERE id=?', (alert(primary, group), row['id']))
    return result


def allowed(db: sqlite3.Connection, incident: dict, projections: list[dict]) -> bool:
    epoch = db.execute('SELECT activated_at FROM notification_epochs LIMIT 1').fetchone()
    if epoch and (incident['first_seen'] < epoch[0] or db.execute(
            'SELECT 1 FROM epoch_incidents WHERE incident=?', (incident['id'],)).fetchone()):
        return False
    for group in projections:
        ids = [r['id'] for r in group['members']]
        if incident['id'] not in ids:
            continue
        if incident['id'] != group['primary_incident']:
            return False
        if incident['state'] == 'RECOVERED':
            return True
        # Conservative escalation policy V1: no automatic second execution alert.
        # All stronger evidence is visible in the report. Uncertain retry history
        # is preserved, but correlated retries are held for operator reconciliation.
        return not db.execute('''SELECT 1 FROM outbox WHERE incident IN ('''
            + ','.join('?' for _ in ids) + ''') AND (attempts>0 OR acknowledged!=0 OR receipt IS NOT NULL
            OR EXISTS (SELECT 1 FROM attempts a WHERE a.outbox=outbox.id)) LIMIT 1''', ids).fetchone()
    return True


def deliverable(db: sqlite3.Connection, incident: str, projections: list[dict]) -> bool:
    """Hold supporting retries without altering their delivery history."""
    epoch = db.execute('SELECT activated_at FROM notification_epochs LIMIT 1').fetchone()
    if epoch:
        row = db.execute('SELECT first_seen FROM incidents WHERE id=?', (incident,)).fetchone()
        if row and (row[0] < epoch[0] or db.execute('SELECT 1 FROM epoch_incidents WHERE incident=?', (incident,)).fetchone()):
            return False
    for group in projections:
        ids = [r['id'] for r in group['members']]
        if incident not in ids:
            continue
        if incident != group['primary_incident']:
            return False
        others = [i for i in ids if i != incident]
        if others and db.execute('SELECT 1 FROM outbox WHERE incident IN (' + ','.join('?' for _ in others)
                + ') AND (attempts>0 OR acknowledged!=0 OR receipt IS NOT NULL OR EXISTS '
                + '(SELECT 1 FROM attempts a WHERE a.outbox=outbox.id))', others).fetchone():
            return False
    return True
