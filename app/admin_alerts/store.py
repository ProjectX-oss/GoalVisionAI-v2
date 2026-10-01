"""ADMIN-owned durable incidents, cursors and outbox; never opens a producer DB."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator

from .model import Event, alert, digest
from . import correlation
from .invalidation import eligible, REASON, idle_eligible, IDLE_REASON
from .output_contracts import CONTRACTS


@contextmanager
def lock(root: Path) -> Iterator[None]:
    """Serialize the entire scan, including network sends."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / 'scan.lock').open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Store:
    """Dedicated SQLite file; occurrences and cursor advance share a transaction."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        path = root / 'admin.sqlite'
        if path.is_symlink():
            raise ValueError('ADMIN_STORE_SYMLINK')
        self.db = sqlite3.connect(path, timeout=.2)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS incidents(
            id TEXT PRIMARY KEY, service TEXT NOT NULL, rule TEXT NOT NULL, object_id TEXT NOT NULL,
            state TEXT NOT NULL, severity INTEGER NOT NULL, count INTEGER NOT NULL,
            first_seen REAL NOT NULL,last_seen REAL NOT NULL,evidence TEXT NOT NULL,
            invocation TEXT NOT NULL,last_sent REAL NOT NULL DEFAULT 0, notified_state TEXT NOT NULL DEFAULT '',
            generation INTEGER NOT NULL DEFAULT 1, streak INTEGER NOT NULL DEFAULT 0, episode INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS occurrences(
            key TEXT PRIMARY KEY, incident TEXT NOT NULL, seen REAL NOT NULL, source TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS occurrence_time ON occurrences(seen);
        CREATE INDEX IF NOT EXISTS occurrence_incident ON occurrences(incident,seen DESC);
        CREATE TABLE IF NOT EXISTS outbox(
            id TEXT PRIMARY KEY,incident TEXT NOT NULL,generation INTEGER NOT NULL,body TEXT NOT NULL,
            state TEXT NOT NULL,created REAL NOT NULL,due REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
            acknowledged INTEGER NOT NULL DEFAULT 0,receipt TEXT, error TEXT);
        CREATE INDEX IF NOT EXISTS outbox_due ON outbox(state,due);
        CREATE TABLE IF NOT EXISTS attempts(
            id INTEGER PRIMARY KEY,outbox TEXT NOT NULL,started REAL NOT NULL,result TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS attempt_time ON attempts(started);
        CREATE TABLE IF NOT EXISTS invalidations(
            incident TEXT PRIMARY KEY, invalidated_at REAL NOT NULL, evidence TEXT NOT NULL,
            original_incident TEXT NOT NULL, original_outbox TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS invalidations_no_update BEFORE UPDATE ON invalidations
            BEGIN SELECT RAISE(ABORT, 'INVALIDATION_AUDIT_IMMUTABLE'); END;
        CREATE TRIGGER IF NOT EXISTS invalidations_no_delete BEFORE DELETE ON invalidations
            BEGIN SELECT RAISE(ABORT, 'INVALIDATION_AUDIT_IMMUTABLE'); END;
        ''')
        # Version-local migration is confined to the ADMIN file, never producer storage.
        if 'episode' not in {r[1] for r in self.db.execute('PRAGMA table_info(incidents)')}:
            self.db.execute('ALTER TABLE incidents ADD COLUMN episode INTEGER NOT NULL DEFAULT 1')
            self.db.commit()
        if 'episode' not in {r[1] for r in self.db.execute('PRAGMA table_info(outbox)')}:
            self.db.execute('ALTER TABLE outbox ADD COLUMN episode INTEGER')
            self.db.commit()
        correlation.initialize(self.db)
        from .autorepair import initialize
        initialize(self.db)
        os.chmod(path, 0o600)

    def close(self) -> None:
        self.db.close()

    def get(self, key: str, default: object = None) -> object:
        row = self.db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, key: str, value: object) -> None:
        self.db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, json.dumps(value, sort_keys=True)))

    def ingest(self, events: list[Event], cursors: dict, now: float) -> None:
        """Replay is idempotent. Unchanged snapshots don't append occurrences."""
        with self.db:
            for event in sorted(events, key=lambda e: (e.observed, e.healthy, not e.source.startswith('journal'))):
                self._event(event, now)
            for key, value in cursors.items():
                self.put(key, value)

    def _event(self, event: Event, now: float) -> None:
        signature = event.signature
        if event.rule == 'ADMIN_DELIVERY_DEGRADED' and self.db.execute(
                "SELECT 1 FROM invalidations WHERE incident=?", (signature,)).fetchone():
            # The false incident remains a terminal tombstone. Future real faults
            # share a separate stable identity, including their receipt recovery.
            signature = digest((signature, 'ADMIN_DELIVERY_AFTER_IDLE_INVALIDATION_V1'))
        if event.rule == 'DELIVERY_FAILURE':
            audit = self.db.execute('SELECT evidence,original_incident FROM invalidations WHERE incident=?',
                                    (signature,)).fetchone()
            if audit and json.loads(audit['evidence']).get('reason') == 'PRETRANSPORT_REJECTION_NOT_DELIVERY_FAILURE_V1':
                # Keep the proven false history terminal, but let later genuine
                # faults and their recovery use a fresh, alertable identity.
                proofs = json.loads(audit['evidence']).get('health_proofs', [])
                old_replay = any(event.occurrence == event.source == event.cycle == 'health-'+p['health_id']
                    and event.observed == p['observed'] and not event.healthy and event.facts == {}
                    for p in proofs)
                if not old_replay:
                    signature = digest((signature, 'DELIVERY_AFTER_PRETRANSPORT_INVALIDATION_V1'))
        # Reuse a legacy source identity only for the same rule and execution.
        # V1.3 never folds independent source rules into one incident.
        if event.invocation != 'UNKNOWN' and event.rule in correlation.EXECUTION_RULES:
            legacy = self.db.execute('SELECT id FROM incidents WHERE service=? AND rule=? AND invocation=?',
                (event.service, event.rule, event.invocation)).fetchone()
            if legacy:
                signature = legacy['id']
        if (event.rule == 'MONITORING_COVERAGE_DEGRADED' and event.source in ('ledger', 'weekly')
                and event.facts.get('reason') != 'UNRESOLVED_SCAN_IN_PROGRESS'):
            # Retain recovery of genuine v1.2 coverage faults; invalidated paging
            # tombstones get a new coverage identity so they cannot hide real faults.
            previous = self.db.execute("SELECT id FROM incidents WHERE service=? AND rule=? AND object_id=? AND state!='INVALIDATED' ORDER BY first_seen LIMIT 1",
                (event.service, event.rule, event.object_id)).fetchone()
            if previous:
                signature = previous['id']
        self.db.execute('INSERT OR IGNORE INTO source_evidence VALUES (?,?,?,?)',
            (digest((signature, event.occurrence, event.healthy, event.source, event.facts)), signature, now, json.dumps(event.document(), sort_keys=True)))
        row = self.db.execute('SELECT * FROM incidents WHERE id=?', (signature,)).fetchone()
        if row and row['state'] == 'INVALIDATED':
            return  # Terminal evidence tombstone; neither replay nor health is recovery.
        if event.healthy and not row:
            return
        episode = row['episode'] if row else 1
        if row and row['state'] == 'RECOVERED' and not event.healthy:
            episode += 1
        key = digest((signature, event.occurrence, event.healthy, episode))
        if self.db.execute('SELECT 1 FROM occurrences WHERE key=?', (key,)).fetchone():
            if row and row['invocation'] == 'UNKNOWN' and event.invocation != 'UNKNOWN':
                self.db.execute('UPDATE incidents SET invocation=? WHERE id=?', (event.invocation, signature))
            return
        # Never retain continual healthy snapshots of recovered incidents.
        if event.healthy and row['state'] in ('RECOVERED', 'PENDING'):
            if row['state'] == 'PENDING':
                self.db.execute("UPDATE incidents SET streak=0 WHERE id=?", (signature,))
            return
        if row and event.observed < row['last_seen']:
            return
        if event.healthy:
            self.db.execute("UPDATE incidents SET state='RECOVERED',last_seen=?,evidence=?,generation=generation+1,streak=0 WHERE id=?",
                            (event.observed, json.dumps(event.document()), signature))
        elif not row:
            state = 'OPEN' if event.debounce == 1 else 'PENDING'
            self.db.execute('''INSERT INTO incidents(id,service,rule,object_id,state,severity,count,first_seen,last_seen,evidence,invocation,streak)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,1)''',
                            (signature, event.service, event.rule, event.object_id, state, event.severity,
                             1, event.observed, event.observed, json.dumps(event.document()), event.invocation))
        else:
            severity = max(row['severity'], event.severity)
            streak = row['streak'] + 1
            state = ('ESCALATED' if severity > row['severity'] else 'REPEATED') if streak >= event.debounce else 'PENDING'
            if row['state'] == 'RECOVERED':
                state = 'OPEN' if event.debounce == 1 else 'PENDING'
                streak = 1
            changed = state != row['state'] and (state in ('OPEN', 'ESCALATED') or row['state'] == 'PENDING')
            self.db.execute('''UPDATE incidents SET state=?,severity=?,count=count+1,last_seen=?,evidence=?,
                invocation=?,streak=?,generation=generation+?,episode=? WHERE id=?''',
                (state, severity, event.observed, json.dumps(event.document()), event.invocation, streak, int(changed), episode, signature))
        self.db.execute('INSERT INTO occurrences VALUES (?,?,?,?)', (key, signature, now, event.source))

    def invalidate_legacy_output(self, now: float) -> int:
        """Atomically append audit evidence and retire unsupported absence work."""
        count = 0
        with self.db:
            # Lock before assessing contradictions or notification history.
            self.db.execute('BEGIN IMMEDIATE')
            rows = self.db.execute("""SELECT * FROM incidents WHERE rule='MISSING_OUTPUT'
                AND state IN ('OPEN','REPEATED','ESCALATED') AND id NOT IN
                (SELECT incident FROM invalidations)""").fetchall()
            for row in rows:
                if not eligible(self.db, row):
                    continue
                evidence = {'reason': REASON, 'contract_source': 'NONE',
                            'contract_version': CONTRACTS[row['service']].version,
                            'invalidated_by': 'ADMIN_ALERTS_V1_2'}
                outbox = [dict(r) for r in self.db.execute('SELECT * FROM outbox WHERE incident=?', (row['id'],))]
                self.db.execute('INSERT INTO invalidations VALUES (?,?,?,?,?)',
                    (row['id'], now, json.dumps(evidence, sort_keys=True),
                     json.dumps(dict(row), sort_keys=True), json.dumps(outbox, sort_keys=True)))
                self.db.execute("UPDATE incidents SET state='INVALIDATED' WHERE id=?", (row['id'],))
                self.db.execute("""UPDATE outbox SET state='SUPERSEDED' WHERE incident=?
                    AND state='PENDING' AND attempts=0 AND acknowledged=0 AND receipt IS NULL
                    AND NOT EXISTS (SELECT 1 FROM attempts a WHERE a.outbox=outbox.id)""", (row['id'],))
                # Attempted/acknowledged rows stay byte-identical. Dispatch's incident
                # state guard prevents retries without erasing uncertain/sent history.
                count += 1
        return count

    def invalidate_idle_delivery(self, now: float) -> int:
        """Audit the proven old idle defect without changing activation history."""
        count = 0
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            for row in self.db.execute("SELECT * FROM incidents WHERE rule='ADMIN_DELIVERY_DEGRADED'").fetchall():
                if not idle_eligible(self.db, row):
                    continue
                outbox = list(self.db.execute('SELECT * FROM outbox WHERE incident=?', (row['id'],)))
                self.db.execute('INSERT INTO invalidations VALUES (?,?,?,?,?)', (row['id'], now,
                    json.dumps({'reason': IDLE_REASON, 'invalidated_by': 'ADMIN_ALERTS_V1_3_1'}),
                    json.dumps(dict(row), sort_keys=True), json.dumps([dict(r) for r in outbox], sort_keys=True)))
                self.db.execute("UPDATE incidents SET state='INVALIDATED' WHERE id=?", (row['id'],))
                for notification in outbox:
                    correlation.supersede(self.db, notification, IDLE_REASON, now)
                count += 1
        return count

    def enqueue(self, now: float) -> None:
        """Persist notification identity before transport; coalesce pending repeats."""
        with self.db:
            projections = correlation.reconcile(self.db, now)
            interrupted = self.db.execute("SELECT * FROM outbox WHERE state='ATTEMPTING' AND incident NOT IN (SELECT id FROM incidents WHERE state='INVALIDATED')").fetchall()
            for pending in interrupted:
                if correlation.deliverable(self.db, pending['incident'], projections, pending):
                    self.db.execute("UPDATE outbox SET state=CASE WHEN attempts>=5 THEN 'EXHAUSTED' ELSE 'UNCERTAIN' END,error='INTERRUPTED_ATTEMPT' WHERE id=?", (pending['id'],))
            rows = self.db.execute("""SELECT * FROM incidents
                WHERE state IN ('OPEN','REPEATED','ESCALATED','RECOVERED')
                ORDER BY severity DESC,CASE WHEN last_sent=0 THEN 0 ELSE 1 END,last_seen DESC""")
            considered = 0
            for row in rows:
                if not correlation.allowed(self.db, dict(row), projections):
                    continue
                # Held pre-activation work cannot block a new episode or be
                # rewritten by recovery, escalation or generation supersession.
                notifications = [n for n in self.db.execute('SELECT * FROM outbox WHERE incident=?', (row['id'],))
                                 if not correlation.epoch_hold(self.db, dict(row), n)]
                attempted = any(n['attempts'] > 0 for n in notifications)
                activation_member = self.db.execute('SELECT 1 FROM epoch_incidents WHERE incident=?', (row['id'],)).fetchone()
                last_sent = row['last_sent'] if not activation_member or attempted else 0
                if row['state'] == 'RECOVERED' and not last_sent and not attempted:
                    for n in notifications:
                        if n['state'] == 'PENDING' and not n['attempts']:
                            self.db.execute("UPDATE outbox SET state='SUPERSEDED' WHERE id=?", (n['id'],))
                    continue
                if row['state'] == 'RECOVERED' and row['notified_state'] == 'RECOVERED':
                    continue
                if any(n['state'] in ('PERMANENT', 'EXHAUSTED') or
                       (n['generation'] == row['generation'] and n['state'] in ('PENDING','UNCERTAIN','ATTEMPTING')
                        and row['state'] != 'ESCALATED') for n in notifications):
                    continue
                if considered >= 1000:
                    break
                considered += 1
                due = (bool(activation_member) and not notifications) or row['notified_state'] != ('RECOVERED' if row['state'] == 'RECOVERED' else 'OPEN')
                escalation = row['state'] == 'ESCALATED'
                # Journal-derived database-lock incidents are evidence-driven. Do not
                # keep re-sending the same historical lock every 30 minutes after
                # it has already been acknowledged; a newer observed occurrence can
                # still alert again, and recovery remains a separate state change.
                if (row['rule'] == 'DATABASE_LOCK' and not due and not escalation
                        and row['last_sent'] and row['last_seen'] <= row['last_sent']):
                    continue
                if not due and not escalation and (row['state'] == 'RECOVERED' or now - row['last_sent'] < 1800):
                    continue
                pending = False
                for n in notifications:
                    if n['generation'] != row['generation'] and n['state'] in ('PENDING','UNCERTAIN'):
                        self.db.execute("UPDATE outbox SET state='SUPERSEDED' WHERE id=?", (n['id'],))
                        continue
                    if escalation and n['state'] in ('PENDING','UNCERTAIN'):
                        self.db.execute('UPDATE outbox SET due=?,body=? WHERE id=?',
                                        (now, self.notification(row, projections), n['id']))
                    pending |= n['state'] in ('PENDING','UNCERTAIN','ATTEMPTING','PERMANENT','EXHAUSTED')
                if pending:
                    continue
                group = next((g for g in projections if g['primary_incident'] == row['id']), None)
                decision = (group['correlation_id'], group['associations']) if group else None
                supersessions = self.db.execute("SELECT count(*) FROM outbox WHERE incident=? AND state='SUPERSEDED'", (row['id'],)).fetchone()[0]
                key = digest((row['id'], row['generation'], row['last_sent'], decision, supersessions))
                self.db.execute('INSERT OR IGNORE INTO outbox(id,incident,generation,body,state,created,due,episode) VALUES (?,?,?,?,?,?,?,?)',
                                (key, row['id'], row['generation'], self.notification(row, projections), 'PENDING', now, now, row['episode']))

    def notification(self, row: sqlite3.Row, projections: list[dict]) -> str:
        group = next((g for g in projections if g['primary_incident'] == row['id']), None)
        return alert(dict(row), group)

    def invalidate_scan_progress(self, now: float) -> int:
        """Retire only the old paging classification, without claiming recovery."""
        count = 0
        with self.db:
            for row in self.db.execute("SELECT * FROM incidents WHERE rule='MONITORING_COVERAGE_DEGRADED' AND state!='INVALIDATED'").fetchall():
                evidence = json.loads(row['evidence'])
                if (evidence.get('source') not in ('ledger', 'weekly') or
                        evidence.get('facts', {}).get('reason') != 'UNRESOLVED_SCAN_IN_PROGRESS'):
                    continue
                outbox = self.db.execute('SELECT * FROM outbox WHERE incident=?', (row['id'],)).fetchall()
                self.db.execute('INSERT INTO invalidations VALUES (?,?,?,?,?)', (row['id'], now,
                    json.dumps({'reason': 'SCAN_PROGRESS_NOT_MONITORING_FAILURE', 'invalidated_by': 'ADMIN_ALERTS_V1_3'}),
                    json.dumps(dict(row), sort_keys=True), json.dumps([dict(r) for r in outbox], sort_keys=True)))
                self.db.execute("UPDATE incidents SET state='INVALIDATED' WHERE id=?", (row['id'],))
                for notification in outbox:
                    correlation.supersede(self.db, notification, 'SCAN_PROGRESS_NOT_MONITORING_FAILURE', now)
                count += 1
        return count

    def report(self, configured_release: str) -> dict:
        """Bounded sanitized forwarding report, with explicit release uncertainty."""
        rows = self.db.execute("SELECT * FROM incidents ORDER BY severity DESC,last_seen DESC LIMIT 200").fetchall()
        audits = {r['incident']: {'invalidated_at': r['invalidated_at'], **json.loads(r['evidence'])}
                  for r in self.db.execute('SELECT incident,invalidated_at,evidence FROM invalidations WHERE incident IN ('
                      + ','.join('?' for _ in rows) + ')', [r['id'] for r in rows])}
        active = self.db.execute("SELECT count(*) FROM incidents WHERE state IN ('OPEN','REPEATED','ESCALATED')").fetchone()[0]
        degraded = self.db.execute("""SELECT 1 FROM incidents WHERE rule='MONITORING_COVERAGE_DEGRADED'
            AND state IN ('PENDING','OPEN','REPEATED','ESCALATED') LIMIT 1""").fetchone()
        return {'active_fault_count': active, 'alert_groups': correlation.groups(self.db), 'schema': 'goalvision-admin-incidents-v1', 'configured_release_now': configured_release,
                'affected_invocation_release': 'UNKNOWN', 'missing_evidence': [
                    'Invocation release is not recorded by systemd; current configuration is not historical proof.',
                    'No raw exception messages, message bodies, provider payloads, headers or locals retained.'],
                'diagnostic_read_procedure': [
                    'Inspect the listed invocation in journalctl, allowlisted service only, at most 100 entries.',
                    'Compare source cycle/prediction IDs with the existing receipt; do not retry PREMATCH sends.',
                    'Inspect loaded systemd properties and the exact deployment manifest; make no changes.'],
                'monitoring_state': 'DEGRADED' if degraded else 'AVAILABLE',
                'incidents': [{**dict(r), 'evidence': json.loads(r['evidence']),
                               'activation_hold': correlation.epoch_hold(self.db, dict(r)),
                               **({'invalidation': audits[r['id']]} if r['id'] in audits else {})} for r in rows],
                'truncated': self.db.execute('SELECT count(*) FROM incidents').fetchone()[0] > 200}

    def retain(self, now: float) -> None:
        """V1.3 preserves source and delivery history for correlation review."""
        return None
