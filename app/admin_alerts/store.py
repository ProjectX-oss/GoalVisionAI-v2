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
        ''')
        # Version-local migration is confined to the ADMIN file, never producer storage.
        if 'episode' not in {r[1] for r in self.db.execute('PRAGMA table_info(incidents)')}:
            self.db.execute('ALTER TABLE incidents ADD COLUMN episode INTEGER NOT NULL DEFAULT 1')
            self.db.commit()
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
        # Exact invocation correlation only. Timestamp proximity alone isn't proof.
        if event.invocation != 'UNKNOWN' and event.rule in ('SERVICE_FAILURE', 'ANALYSIS_FAILURE'):
            correlated = self.db.execute('''SELECT id FROM incidents WHERE service=? AND invocation=?
                AND rule IN ('SERVICE_FAILURE','ANALYSIS_FAILURE') ORDER BY first_seen LIMIT 1''',
                (event.service, event.invocation)).fetchone()
            if correlated:
                signature = correlated['id']
        row = self.db.execute('SELECT * FROM incidents WHERE id=?', (signature,)).fetchone()
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

    def enqueue(self, now: float) -> None:
        """Persist notification identity before transport; coalesce pending repeats."""
        with self.db:
            self.db.execute("UPDATE outbox SET state=CASE WHEN attempts>=5 THEN 'EXHAUSTED' ELSE 'UNCERTAIN' END,error='INTERRUPTED_ATTEMPT' WHERE state='ATTEMPTING'")
            rows = self.db.execute('''SELECT i.* FROM incidents i WHERE state!='PENDING'
                AND (state!='RECOVERED' OR (notified_state!='RECOVERED' AND
                    (last_sent>0 OR EXISTS (SELECT 1 FROM outbox o WHERE o.incident=i.id AND o.attempts>0))))
                AND NOT EXISTS (SELECT 1 FROM outbox o WHERE o.incident=i.id AND
                    (o.state IN ('PERMANENT','EXHAUSTED') OR
                     (o.generation=i.generation AND o.state IN ('PENDING','UNCERTAIN','ATTEMPTING') AND i.state!='ESCALATED')))
                ORDER BY severity DESC,CASE WHEN last_sent=0 THEN 0 ELSE 1 END,last_seen DESC LIMIT 1000''').fetchall()
            self.db.execute("""UPDATE outbox SET state='SUPERSEDED' WHERE attempts=0 AND state='PENDING'
                AND incident IN (SELECT id FROM incidents WHERE state='RECOVERED' AND last_sent=0)""")
            for row in rows:
                attempted = self.db.execute('SELECT 1 FROM outbox WHERE incident=? AND attempts>0 LIMIT 1', (row['id'],)).fetchone()
                if row['state'] == 'RECOVERED' and not row['last_sent'] and not attempted:
                    # Avoid sending a stale fault after its explicit recovery.
                    self.db.execute("UPDATE outbox SET state='SUPERSEDED' WHERE incident=? AND state IN ('PENDING','UNCERTAIN')", (row['id'],))
                    continue
                due = row['notified_state'] != ('RECOVERED' if row['state'] == 'RECOVERED' else 'OPEN')
                escalation = row['state'] == 'ESCALATED'
                if not due and not escalation and (row['state'] == 'RECOVERED' or now - row['last_sent'] < 1800):
                    continue
                self.db.execute("UPDATE outbox SET state='SUPERSEDED' WHERE incident=? AND generation!=? AND state IN ('PENDING','UNCERTAIN')",
                                (row['id'], row['generation']))
                if escalation:
                    self.db.execute("UPDATE outbox SET due=?,body=? WHERE incident=? AND state IN ('PENDING','UNCERTAIN')",
                                    (now, alert(dict(row)), row['id']))
                pending = self.db.execute("SELECT 1 FROM outbox WHERE incident=? AND state IN ('PENDING','UNCERTAIN','ATTEMPTING','PERMANENT','EXHAUSTED')", (row['id'],)).fetchone()
                if pending:
                    continue
                key = digest((row['id'], row['generation'], row['last_sent']))
                self.db.execute('INSERT OR IGNORE INTO outbox(id,incident,generation,body,state,created,due) VALUES (?,?,?,?,?,?,?)',
                                (key, row['id'], row['generation'], alert(dict(row)), 'PENDING', now, now))

    def report(self, configured_release: str) -> dict:
        """Bounded sanitized forwarding report, with explicit release uncertainty."""
        rows = self.db.execute("SELECT * FROM incidents ORDER BY severity DESC,last_seen DESC LIMIT 200").fetchall()
        return {'schema': 'goalvision-admin-incidents-v1', 'configured_release_now': configured_release,
                'affected_invocation_release': 'UNKNOWN', 'missing_evidence': [
                    'Invocation release is not recorded by systemd; current configuration is not historical proof.',
                    'No raw exception messages, message bodies, provider payloads, headers or locals retained.'],
                'diagnostic_read_procedure': [
                    'Inspect the listed invocation in journalctl, allowlisted service only, at most 100 entries.',
                    'Compare source cycle/prediction IDs with the existing receipt; do not retry PREMATCH sends.',
                    'Inspect loaded systemd properties and the exact deployment manifest; make no changes.'],
                'monitoring_state': 'DEGRADED' if any(r['rule'] == 'MONITORING_COVERAGE_DEGRADED' and r['state'] != 'RECOVERED' for r in rows) else 'AVAILABLE',
                'incidents': [{**dict(r), 'evidence': json.loads(r['evidence'])} for r in rows],
                'truncated': self.db.execute('SELECT count(*) FROM incidents').fetchone()[0] > 200}

    def retain(self, now: float) -> None:
        """Retain unresolved evidence; prune resolved details after 90 days in batches."""
        with self.db:
            self.db.execute('''DELETE FROM attempts WHERE id IN (SELECT a.id FROM attempts a JOIN outbox o ON o.id=a.outbox
                JOIN incidents i ON i.id=o.incident WHERE i.state='RECOVERED' AND i.last_seen<? LIMIT 500)''', (now - 90 * 86400,))
            self.db.execute('''DELETE FROM occurrences WHERE key IN (SELECT o.key FROM occurrences o JOIN incidents i ON i.id=o.incident
                WHERE i.state='RECOVERED' AND i.last_seen<? LIMIT 500)''', (now - 90 * 86400,))
            self.db.execute('''DELETE FROM attempts WHERE id IN (SELECT id FROM attempts WHERE started<? LIMIT 500)''', (now - 90 * 86400,))
            self.db.execute('''DELETE FROM outbox WHERE id IN (SELECT id FROM outbox WHERE state IN ('SENT','SUPERSEDED')
                AND created<? LIMIT 500)''', (now - 90 * 86400,))
            # Keep incident tombstones/cursors for replay protection. Bound repeated open evidence
            # to the newest 100 occurrences per incident; count and first/last seen remain durable.
            after = self.get('retention_cursor', '')
            rows = self.db.execute('SELECT id FROM incidents WHERE id>? ORDER BY id LIMIT 10', (after,)).fetchall()
            for row in rows:
                self.db.execute('''DELETE FROM occurrences WHERE key IN
                    (SELECT key FROM occurrences WHERE incident=? ORDER BY seen DESC LIMIT 500 OFFSET 100)''', (row['id'],))
            self.put('retention_cursor', rows[-1]['id'] if len(rows) == 10 else '')
