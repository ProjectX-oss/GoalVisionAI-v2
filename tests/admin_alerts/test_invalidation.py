"""Legacy invalidation, immutable audit, dispatch and scan regressions; offline."""
from dataclasses import replace
import json
import sqlite3
from unittest.mock import patch

from app.admin_alerts.cli import scan
from app.admin_alerts.delivery import SenderConfig, dispatch
from app.admin_alerts.invalidation import eligible
from app.admin_alerts.model import Event, UNITS, LABELS
from app.admin_alerts.store import Store
from test_monitor import Temporary, NOW, FakeTransport

INV = 'c' * 32


class InvalidationTests(Temporary):
    def setUp(self):
        super().setUp()
        self.store = Store(self.root)
        self.addCleanup(lambda: self.store.close())
        self.event = Event(UNITS[1], 'MISSING_OUTPUT', INV, INV, NOW, 'journal-output', invocation=INV)
        self.store.ingest([self.event], {'journal': {'cursor': 'preserved'}, 'stdout': {'offset': 9}}, NOW)
        self.store.enqueue(NOW)
        guard = patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN'))
        guard.start(); self.addCleanup(guard.stop)

    def incident(self):
        return dict(self.store.db.execute('SELECT * FROM incidents WHERE id=?', (self.event.signature,)).fetchone())

    def snapshot(self):
        return {name: [tuple(r) for r in self.store.db.execute('SELECT * FROM '+name)]
                for name in ('incidents', 'outbox', 'occurrences', 'attempts', 'metadata', 'invalidations')}

    def test_invalidates_preserves_original_and_durable_audit(self):
        original = self.incident()
        outbox = [dict(r) for r in self.store.db.execute('SELECT * FROM outbox')]
        self.assertEqual(self.store.invalidate_legacy_output(NOW+1), 1)
        self.assertEqual(self.incident(), {**original, 'state': 'INVALIDATED'})
        self.store.close(); self.store = Store(self.root)
        audit = self.store.db.execute('SELECT * FROM invalidations').fetchone()
        self.assertEqual(json.loads(audit['original_incident']), original)
        self.assertEqual(json.loads(audit['original_outbox']), outbox)
        self.assertEqual(json.loads(audit['evidence']), {'reason': 'OUTPUT_CONTRACT_NOT_APPLICABLE',
            'contract_source': 'NONE', 'contract_version': 1, 'invalidated_by': 'ADMIN_ALERTS_V1_2'})
        self.assertEqual(audit['invalidated_at'], NOW+1)
        for sql in ('DELETE FROM invalidations', "UPDATE invalidations SET evidence='{}'"):
            with self.assertRaises(sqlite3.IntegrityError):
                with self.store.db:
                    self.store.db.execute(sql)

    def test_pending_superseded_no_fake_send_or_validation_later(self):
        self.store.invalidate_legacy_output(NOW+1)
        self.store.enqueue(NOW+2)
        self.assertEqual(tuple(self.store.db.execute('SELECT state,attempts FROM outbox').fetchone()), ('SUPERSEDED', 0))
        transport = FakeTransport()
        with patch.object(transport, 'validate', side_effect=AssertionError('NO VALIDATION')):
            self.assertEqual(dispatch(self.store, SenderConfig(True, '', 99, 'AdminBot', 123, True), transport, NOW+3), 0)
        self.assertEqual(transport.messages, [])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 0)

    def test_second_scan_restart_replay_and_retention_are_idempotent(self):
        self.store.invalidate_legacy_output(NOW+1)
        before = self.snapshot()
        for restart in (False, True):
            if restart:
                self.store.close(); self.store = Store(self.root)
            self.assertEqual(self.store.invalidate_legacy_output(NOW+2), 0)
            self.store.ingest([self.event, replace(self.event, healthy=True, observed=NOW+10)], {}, NOW+10)
            self.store.enqueue(NOW+10)
            self.assertEqual(before, self.snapshot())
        self.store.retain(NOW+100*86400)
        after = self.snapshot()
        for name in ('incidents', 'outbox', 'occurrences', 'attempts', 'invalidations'):
            self.assertEqual(before[name], after[name])

    def test_attempted_acknowledged_and_uncertain_history_stays_exact(self):
        for state, attempts, ack, receipt in (('PENDING', 1, 0, None), ('UNCERTAIN', 1, 0, None),
                ('ATTEMPTING', 1, 0, None), ('SENT', 1, 1, '{}'), ('PENDING', 0, 1, '{}')):
            with self.subTest(state=state, ack=ack):
                root = self.root/(state+str(ack)); root.mkdir()
                store = Store(root)
                try:
                    store.ingest([self.event], {}, NOW); store.enqueue(NOW)
                    with store.db:
                        store.db.execute('UPDATE outbox SET state=?,attempts=?,acknowledged=?,receipt=?', (state, attempts, ack, receipt))
                        store.db.execute("INSERT INTO attempts(outbox,started,result) SELECT id,?,'HISTORY' FROM outbox", (NOW,))
                    before = [tuple(r) for r in store.db.execute('SELECT * FROM outbox')]
                    history = [tuple(r) for r in store.db.execute('SELECT * FROM attempts')]
                    store.invalidate_legacy_output(NOW+1); store.enqueue(NOW+2); store.retain(NOW+100*86400)
                    self.assertEqual(before, [tuple(r) for r in store.db.execute('SELECT * FROM outbox')])
                    self.assertEqual(history, [tuple(r) for r in store.db.execute('SELECT * FROM attempts')])
                    fake = FakeTransport()
                    self.assertEqual(dispatch(store, SenderConfig(True, '', 99, 'AdminBot', 123, True), fake, NOW+100*86400), 0)
                    self.assertEqual(fake.messages, [])
                finally:
                    store.close()

    def test_other_rules_discovery_and_structured_contracts_untouched(self):
        events = [replace(self.event, rule=rule, invocation='other', object_id=rule) for rule in LABELS if rule != 'MISSING_OUTPUT']
        events += [replace(self.event, service=u, source='stdout-window' if u == UNITS[0] else 'journal-output') for u in UNITS if u != UNITS[1]]
        self.store.ingest(events, {}, NOW)
        originals = {r['id']: dict(r) for r in self.store.db.execute('SELECT * FROM incidents') if r['id'] != self.event.signature}
        self.assertEqual(self.store.invalidate_legacy_output(NOW+1), 1)
        self.assertEqual(originals, {r['id']: dict(r) for r in self.store.db.execute('SELECT * FROM incidents') if r['id'] != self.event.signature})

    def test_contradictory_service_failure_veto_and_stays_actionable(self):
        self.store.ingest([replace(self.event, rule='SERVICE_FAILURE', source='systemd', facts={'status': 1})], {}, NOW)
        self.assertEqual(self.store.invalidate_legacy_output(NOW+1), 0)
        self.store.enqueue(NOW+1)
        self.assertEqual({r[0] for r in self.store.db.execute('SELECT state FROM incidents')}, {'OPEN'})
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 2)

    def test_unknown_evidence_no_review_or_terminal_state_refused(self):
        original = self.incident()
        for change in ({'source': 'unknown'}, {'facts': {'failed': True}}, {'healthy': True}, {'invocation': 'other'}):
            row = {**original, 'evidence': json.dumps({**json.loads(original['evidence']), **change})}
            self.assertFalse(eligible(self.store.db, row))
        for change in ({'service': 'unreviewed.service'}, {'state': 'RECOVERED'}, {'state': 'PENDING'}, {'state': 'INVALIDATED'}):
            self.assertFalse(eligible(self.store.db, {**original, **change}))

    def test_report_invalidated_is_not_recovered_or_active_or_degraded(self):
        self.store.invalidate_legacy_output(NOW+1)
        report = self.store.report('UNKNOWN')
        self.assertEqual(report['monitoring_state'], 'AVAILABLE')
        self.assertEqual(report['active_fault_count'], 0)
        self.assertEqual(report['incidents'][0]['state'], 'INVALIDATED')
        self.assertEqual(report['incidents'][0]['invalidation']['reason'], 'OUTPUT_CONTRACT_NOT_APPLICABLE')
        self.store.ingest([Event('monitor', 'MONITORING_COVERAGE_DEGRADED', 'journal', 'read', NOW+2, 'journal')], {}, NOW+2)
        self.assertEqual(self.store.report('UNKNOWN')['monitoring_state'], 'DEGRADED')

    def test_actual_scan_twice_preserves_sources_and_uses_no_network(self):
        output = self.root/'producer.log'; output.write_text('')
        config = {'stdout': str(output), 'health_database': str(self.root/'absent'),
                  'ledger_database': str(self.root/'absent'), 'release_environment': str(self.root/'absent'),
                  'sender': {'enabled': False}}
        self.store.close()
        with patch('app.admin_alerts.cli.systemd', return_value={}), \
             patch('app.admin_alerts.cli.service_rules', return_value=([], {})), \
             patch('app.admin_alerts.cli.journal', return_value=([], {})), \
             patch('app.admin_alerts.cli.health_rows', return_value=([], {})), \
             patch('app.admin_alerts.cli.Telegram', side_effect=AssertionError('NO TELEGRAM')):
            for _ in range(2):
                result = scan(config, self.root)
                self.assertEqual(result['telegram_sends'], 0)
                self.assertEqual(result['football_api_calls'], 0)
        self.store = Store(self.root)
        self.assertEqual(self.incident()['state'], 'INVALIDATED')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM invalidations').fetchone()[0], 1)
        self.assertEqual(output.read_bytes(), b'')
        self.assertFalse((self.root/'absent').exists())

    def test_failed_transition_rolls_back_incident_audit_and_outbox_together(self):
        before = self.snapshot()
        self.store.db.execute("CREATE TRIGGER injected_failure BEFORE UPDATE ON outbox BEGIN SELECT RAISE(ABORT, 'FAIL'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.invalidate_legacy_output(NOW+1)
        self.assertEqual(before, self.snapshot())

    def test_generic_none_contract_for_another_reviewed_service(self):
        from app.admin_alerts.output_contracts import CONTRACTS
        unit = 'reviewed-other.service'
        with patch.dict(CONTRACTS, {unit: CONTRACTS[UNITS[1]]}):
            event = replace(self.event, service=unit)
            self.store.ingest([event], {}, NOW)
            self.assertEqual(self.store.invalidate_legacy_output(NOW+1), 2)
            self.assertEqual(self.store.db.execute('SELECT state FROM incidents WHERE id=?', (event.signature,)).fetchone()[0], 'INVALIDATED')
