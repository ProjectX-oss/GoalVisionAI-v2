"""Activation episode regression: only disposable ADMIN stores and fake transport."""
from dataclasses import replace
import sqlite3

from test_monitor import Temporary, NOW, FakeTransport
from app.admin_alerts.activation import EPOCH, prepare_epoch, projection
from app.admin_alerts.correlation import EPOCH_POLICY, allowed, deliverable, groups
from app.admin_alerts.delivery import SenderConfig, dispatch
from app.admin_alerts.model import Event, DISCOVERY
from app.admin_alerts.store import Store


class ActivationRecurrenceTests(Temporary):
    def setUp(self):
        super().setUp()
        self.store = Store(self.root)
        self.addCleanup(lambda: self.store.close())
        self.config = SenderConfig(True, '', 99, 'AdminBot', 123, True)
        self.event = Event(DISCOVERY, 'TIMER_INACTIVE', 'timer', 'old-fault', NOW, 'systemd')

    def incident(self):
        return dict(self.store.db.execute('SELECT * FROM incidents WHERE id=?', (self.event.signature,)).fetchone())

    def observe(self, *, healthy=False, offset=20, severity=2):
        self.store.ingest([replace(self.event, healthy=healthy, observed=NOW+offset,
                                  occurrence=str(offset), severity=severity)], {}, NOW+offset)
        self.store.enqueue(NOW+offset)

    def activate(self):
        self.store.ingest([self.event], {}, NOW)
        self.store.enqueue(NOW)
        self.assertEqual(prepare_epoch(self.store.db, NOW+10), 1)
        return dict(self.store.db.execute('SELECT * FROM outbox').fetchone())

    def recurrence(self, restart):
        old = self.activate()
        audit = list(map(tuple, self.store.db.execute('SELECT * FROM notification_audit')))
        snapshot = dict(self.store.db.execute('SELECT * FROM epoch_incidents').fetchone())
        self.assertEqual(snapshot, dict(incident=self.event.signature, epoch=EPOCH,
                                      episode_at_activation=1, generation_at_activation=1))
        self.assertEqual(old['state'], 'SUPERSEDED')
        self.assertEqual(old['attempts'], 0)
        fake = FakeTransport()
        self.observe(offset=4000)  # A reminder cannot recreate activation backlog.
        self.assertFalse(allowed(self.store.db, self.incident(), groups(self.store.db)))
        self.assertFalse(deliverable(self.store.db, self.event.signature, groups(self.store.db)))
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+4000), 0)
        self.observe(healthy=True, offset=4001)
        self.assertEqual(self.incident()['state'], 'RECOVERED')
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+4001), 0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)
        if restart:
            self.store.close()
            self.store = Store(self.root)
        self.observe(offset=4002)
        row = self.incident()
        self.assertEqual(row['id'], old['incident'])
        self.assertEqual(row['first_seen'], NOW)
        self.assertEqual(row['episode'], 2)
        self.assertTrue(allowed(self.store.db, row, groups(self.store.db)))
        new = self.store.db.execute("SELECT * FROM outbox WHERE state='PENDING'").fetchone()
        self.assertIsNotNone(new)
        self.assertEqual(new['episode'], 2)
        self.assertGreater(new['generation'], old['generation'])
        self.assertNotEqual(new['id'], old['id'])
        self.assertTrue(deliverable(self.store.db, row['id'], groups(self.store.db), new))
        self.assertFalse(deliverable(self.store.db, row['id'], groups(self.store.db), old))
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+4002), 1)
        self.store.enqueue(NOW+4003)
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+4003), 0)
        self.assertEqual(len(fake.messages), 1)
        self.assertIn(self.event.rule, fake.messages[0])
        self.assertNotIn('✅', fake.messages[0])
        self.assertEqual(old, dict(self.store.db.execute('SELECT * FROM outbox WHERE id=?', (old['id'],)).fetchone()))
        self.assertEqual(audit, list(map(tuple, self.store.db.execute('SELECT * FROM notification_audit'))))
        self.assertEqual(snapshot, dict(self.store.db.execute('SELECT * FROM epoch_incidents').fetchone()))

    def test_stable_timer_recurrence(self):
        self.recurrence(False)

    def test_stable_recurrence_across_restart(self):
        self.recurrence(True)

    def test_provider_recurrence(self):
        self.event = replace(self.event, rule='PROVIDER_FAILURE')
        self.recurrence(True)

    def test_quota_recurrence(self):
        self.event = replace(self.event, rule='QUOTA_FAILURE')
        self.recurrence(False)

    def test_coverage_recurrence(self):
        self.event = replace(self.event, rule='MONITORING_COVERAGE_DEGRADED', source='ledger')
        self.recurrence(True)

    def test_execution_recurrence_and_distinct_invocation(self):
        self.event = replace(self.event, rule='SERVICE_FAILURE', invocation='a'*32)
        self.recurrence(True)
        new = replace(self.event, invocation='b'*32, occurrence='new-invocation', observed=NOW+4010)
        self.store.ingest([new], {}, NOW+4010)
        self.store.enqueue(NOW+4010)
        self.assertEqual(len(groups(self.store.db)), 2)
        fake = FakeTransport()
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+4010), 1)
        self.assertIn('b'*32, fake.messages[0])

    def test_escalation_same_episode_stays_suppressed(self):
        old = self.activate()
        self.observe(offset=20, severity=3)
        row = self.incident()
        self.assertEqual((row['state'], row['episode']), ('ESCALATED', 1))
        self.assertGreater(row['generation'], old['generation'])
        self.assertFalse(allowed(self.store.db, row, []))
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+20), 0)
        self.assertEqual(old, dict(self.store.db.execute('SELECT * FROM outbox').fetchone()))
        self.assertEqual(self.store.report('UNKNOWN')['incidents'][0]['severity'], 3)

    def test_new_incident_without_snapshot_never_uses_first_seen_gate(self):
        prepare_epoch(self.store.db, NOW+10)
        for offset, object_id in ((20, 'new'), (-20, 'late-source-evidence')):
            self.store.ingest([replace(self.event, object_id=object_id, observed=NOW+offset)], {}, NOW+20)
        self.store.enqueue(NOW+20)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM epoch_incidents').fetchone()[0], 0)
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+20), 2)

    def test_attempted_history_survives_recovery_recurrence_and_dispatch(self):
        for index, state in enumerate(('PENDING', 'UNCERTAIN', 'ATTEMPTING', 'SENT', 'PERMANENT', 'EXHAUSTED')):
            with self.subTest(state=state):
                self.store.close()
                root = self.root/str(index); root.mkdir()
                self.store = Store(root)
                self.store.ingest([self.event], {}, NOW)
                self.store.enqueue(NOW)
                with self.store.db:
                    self.store.db.execute('UPDATE outbox SET state=?,attempts=1,acknowledged=?,receipt=?',
                                          (state, int(state=='SENT'), 'retained-receipt' if state=='SENT' else None))
                    self.store.db.execute("INSERT INTO attempts(outbox,started,result) SELECT id,?,'UNCERTAIN' FROM outbox", (NOW,))
                    if state == 'SENT':
                        self.store.db.execute("UPDATE incidents SET last_sent=?,notified_state='OPEN'", (NOW,))
                old = dict(self.store.db.execute('SELECT * FROM outbox').fetchone())
                attempts = list(map(tuple, self.store.db.execute('SELECT * FROM attempts')))
                self.assertEqual(prepare_epoch(self.store.db, NOW+10), 0)
                self.observe(healthy=True)
                self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+20), 0)
                self.store.close(); self.store = Store(root)
                self.observe(offset=21)
                fake = FakeTransport()
                self.assertEqual(dispatch(self.store, self.config, fake, NOW+21), 1)
                self.assertEqual(len(fake.messages), 1)
                self.assertEqual(old, dict(self.store.db.execute('SELECT * FROM outbox WHERE id=?', (old['id'],)).fetchone()))
                self.assertEqual(attempts, list(map(tuple, self.store.db.execute('SELECT * FROM attempts WHERE outbox=?', (old['id'],)))))

    def test_immutable_snapshot_and_activation_replay(self):
        self.activate()
        for sql in ('DELETE FROM epoch_incidents', 'UPDATE epoch_incidents SET episode_at_activation=2',
                    'DELETE FROM notification_epochs',
                    'INSERT OR REPLACE INTO epoch_incidents SELECT incident,epoch,2,3 FROM epoch_incidents',
                    'INSERT OR REPLACE INTO notification_epochs SELECT * FROM notification_epochs'):
            with self.assertRaises(sqlite3.IntegrityError), self.store.db:
                self.store.db.execute(sql)
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_ALREADY_PREPARED'):
            prepare_epoch(self.store.db, NOW+30)

    def test_legacy_snapshot_migration_fails_closed_without_guessing(self):
        self.store.ingest([self.event], {}, NOW)
        self.store.enqueue(NOW)
        with self.store.db:
            self.store.db.execute('DROP TABLE epoch_incidents')
            self.store.db.execute('CREATE TABLE epoch_incidents(incident TEXT PRIMARY KEY, epoch TEXT NOT NULL)')
            self.store.db.execute('INSERT INTO epoch_incidents VALUES (?,?)', (self.event.signature, EPOCH))
            self.store.db.execute('INSERT INTO notification_epochs VALUES (?,?,?)', (EPOCH, NOW+10, 'ONLY_NEW_INCIDENTS_NO_PRE_ENABLEMENT_BACKLOG'))
        self.store.close(); self.store = Store(self.root)
        self.observe(healthy=True)
        self.observe(offset=21)
        snapshot = self.store.db.execute('SELECT * FROM epoch_incidents').fetchone()
        self.assertIsNone(snapshot['episode_at_activation'])
        self.assertIsNone(snapshot['generation_at_activation'])
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+21), 0)
        self.assertEqual(self.store.report('UNKNOWN')['incidents'][0]['activation_hold'], 'ACTIVATION_SNAPSHOT_REVIEW_REQUIRED')
        self.assertTrue(projection(self.store.db, {})['activation_review_required'])

    def test_malformed_snapshot_fails_closed(self):
        self.store.ingest([self.event], {}, NOW)
        with self.store.db:
            self.store.db.execute('INSERT INTO notification_epochs VALUES (?,?,?)', (EPOCH, NOW+10, EPOCH_POLICY))
            self.store.db.execute('INSERT INTO epoch_incidents VALUES (?,?,?,?)', (self.event.signature, EPOCH, None, 1))
        self.observe(healthy=True)
        self.observe(offset=21)
        self.assertFalse(allowed(self.store.db, self.incident(), []))
        self.assertTrue(projection(self.store.db, {})['activation_review_required'])
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+21), 0)

    def test_snapshot_captures_current_episode_and_generation(self):
        self.observe(offset=0)
        self.observe(healthy=True, offset=1)
        self.observe(offset=2)
        self.observe(offset=3, severity=3)
        current = self.incident()
        prepare_epoch(self.store.db, NOW+10)
        snapshot = self.store.db.execute('SELECT * FROM epoch_incidents').fetchone()
        self.assertEqual(snapshot['episode_at_activation'], 2)
        self.assertEqual(snapshot['generation_at_activation'], current['generation'])
        self.observe(healthy=True)
        self.observe(offset=21)
        self.assertEqual(self.incident()['episode'], 3)
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+21), 1)

    def test_invalid_incident_counters_refuse_activation_atomically(self):
        self.observe(offset=0)
        with self.store.db:
            self.store.db.execute('UPDATE incidents SET episode=0')
        before = list(map(tuple, self.store.db.execute('SELECT * FROM outbox')))
        with self.assertRaisesRegex(ValueError, 'ACTIVATION_SNAPSHOT_REVIEW_REQUIRED'):
            prepare_epoch(self.store.db, NOW+10)
        self.assertEqual(before, list(map(tuple, self.store.db.execute('SELECT * FROM outbox'))))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM notification_epochs').fetchone()[0], 0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM epoch_incidents').fetchone()[0], 0)

    def test_debounced_recurrence_gets_new_work_only_after_confirmation(self):
        self.event = replace(self.event, rule='PROVIDER_FAILURE', debounce=2)
        self.observe(offset=0)
        self.observe(offset=1)
        prepare_epoch(self.store.db, NOW+10)
        self.observe(healthy=True)
        self.observe(offset=21)
        self.assertEqual(self.incident()['episode'], 2)
        self.assertEqual(self.incident()['state'], 'PENDING')
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+21), 0)
        self.observe(offset=22)
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+22), 1)
