"""V1.3 scan, immutable correlation, quota and activation contracts; fake network only."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

from test_monitor import Temporary, NOW, ISO, FakeTransport
from app.admin_alerts.activation import enable, prepare_epoch, projection, EPOCH
from app.admin_alerts.correlation import groups
from app.admin_alerts.delivery import SenderConfig, dispatch
from app.admin_alerts.model import Event, DISCOVERY, coverage
from app.admin_alerts.rules import completed_health, code_events
from app.admin_alerts.sources import unresolved, weekly_unresolved, scan_page, MAX_ROWS, journal
from app.admin_alerts.store import Store


class V13Tests(Temporary):
    def setUp(self):
        super().setUp()
        self.store = Store(self.root)
        self.addCleanup(self.store.close)
        self.config = SenderConfig(True, '', 99, 'AdminBot', 123, True)
        self.event = Event(DISCOVERY, 'SERVICE_FAILURE', 'pipeline', 'inv-1', NOW, 'journal-one', invocation='a'*32)

    def ingest(self, *events):
        self.store.ingest(list(events), {}, NOW)
        self.store.enqueue(NOW)

    def test_same_execution_keeps_three_sources_one_send(self):
        self.ingest(self.event)
        self.ingest(replace(self.event, rule='MISSING_OUTPUT', object_id='a'*32),
                    replace(self.event, rule='ANALYSIS_FAILURE', source='health-one', invocation='UNKNOWN', observed=NOW+20))
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM incidents').fetchone()[0], 3)
        self.assertEqual(len(groups(self.store.db)), 1)
        fake = FakeTransport()
        self.assertEqual(dispatch(self.store, self.config, fake, NOW), 1)
        self.assertIn('MISSING_OUTPUT', fake.messages[0])
        self.assertIn('ANALYSIS_FAILURE', fake.messages[0])
        self.assertIn('UNIQUE_TEMPORAL_SAME_SERVICE', self.store.db.execute('SELECT association FROM correlation_audit ORDER BY rowid DESC').fetchone()[0])
        self.assertEqual(self.store.db.execute("SELECT invocation FROM incidents WHERE rule='ANALYSIS_FAILURE'").fetchone()[0], 'UNKNOWN')

    def test_quota_primary_and_exact_journal_attribution(self):
        entry = {'__CURSOR':'s=1', '__REALTIME_TIMESTAMP':int(NOW*1e6), '_SYSTEMD_UNIT':DISCOVERY,
                 '_SYSTEMD_INVOCATION_ID':'a'*32, 'MESSAGE':'QUOTA_DB_CONTENTION_EXHAUSTED token=secret'}
        events, _ = journal({}, NOW, lambda _: json.dumps(entry))
        quota = next(e for e in events if e.rule=='QUOTA_DB_CONTENTION')
        self.assertEqual(quota.invocation, 'a'*32)
        self.ingest(self.event)
        self.ingest(quota)
        group = groups(self.store.db)[0]
        self.assertEqual(group['members'][0]['rule'], 'QUOTA_DB_CONTENTION')
        fake = FakeTransport()
        self.assertEqual(dispatch(self.store, self.config, fake, NOW), 1)
        self.assertIn('pieprasījums netika sākts', fake.messages[0])
        self.assertIn('QUOTA_DB_CONTENTION_EXHAUSTED', fake.messages[0])
        self.assertNotIn('secret', fake.messages[0])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE state='SUPERSEDED'").fetchone()[0], 1)

    def test_temporal_ambiguous_other_service_and_outside_window_independent(self):
        unknown = replace(self.event, rule='ANALYSIS_FAILURE', invocation='UNKNOWN', source='health-one')
        self.ingest(self.event, replace(self.event, invocation='b'*32, observed=NOW+10), unknown)
        self.assertEqual(len(groups(self.store.db)), 3)
        self.assertEqual(len({g['correlation_id'] for g in groups(self.store.db)}), 3)
        self.ingest(replace(unknown, service='other', occurrence='other'),
                    replace(unknown, observed=NOW+100, occurrence='late'))
        self.assertEqual(len(groups(self.store.db)), 5)

    def test_different_invocations_never_merge_and_restart_immutable_audit(self):
        self.ingest(self.event, replace(self.event, invocation='b'*32), replace(self.event, rule='MISSING_OUTPUT'))
        ids = [g['correlation_id'] for g in groups(self.store.db)]
        before = list(map(tuple, self.store.db.execute('SELECT * FROM correlation_audit')))
        self.store.close(); self.store = Store(self.root)
        self.store.enqueue(NOW+1)
        self.assertEqual(ids, [g['correlation_id'] for g in groups(self.store.db)])
        self.assertEqual(before, list(map(tuple, self.store.db.execute('SELECT * FROM correlation_audit'))))
        for sql in ('DELETE FROM correlation_audit', "UPDATE correlation_audit SET invocation='changed'"):
            with self.assertRaises(sqlite3.IntegrityError), self.store.db:
                self.store.db.execute(sql)

    def test_late_stronger_root_preserves_sent_and_holds_second_alert(self):
        self.ingest(self.event)
        fake = FakeTransport()
        dispatch(self.store, self.config, fake, NOW)
        before = tuple(self.store.db.execute('SELECT * FROM outbox').fetchone())
        self.ingest(replace(self.event, rule='QUOTA_DB_CONTENTION', severity=3, facts={'code':'QUOTA_DB_CONTENTION_EXHAUSTED'}))
        self.assertEqual(tuple(self.store.db.execute('SELECT * FROM outbox').fetchone()), before)
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+100), 0)
        self.assertEqual(len(fake.messages), 1)

    def test_attempted_support_preserved_and_not_retried(self):
        self.ingest(replace(self.event, rule='MISSING_OUTPUT'))
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET state='UNCERTAIN', attempts=1")
        before = tuple(self.store.db.execute('SELECT * FROM outbox').fetchone())
        self.ingest(self.event)
        self.assertEqual(before, tuple(self.store.db.execute('SELECT * FROM outbox').fetchone()))
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+100), 0)

    def test_legacy_scan_invalidation_preserves_original_and_does_not_mask_new_fault(self):
        old = coverage('ledger', NOW, 'UNRESOLVED_SCAN_IN_PROGRESS')
        self.ingest(old)
        original = dict(self.store.db.execute('SELECT * FROM incidents').fetchone())
        self.assertEqual(self.store.invalidate_scan_progress(NOW+1), 1)
        audit = self.store.db.execute('SELECT * FROM invalidations').fetchone()
        self.assertEqual(json.loads(audit['original_incident']), original)
        self.assertIn('SCAN_PROGRESS_NOT_MONITORING_FAILURE', audit['evidence'])
        self.assertEqual(self.store.db.execute('SELECT state FROM outbox').fetchone()[0], 'SUPERSEDED')
        self.assertEqual(self.store.invalidate_scan_progress(NOW+2), 0)
        self.ingest(coverage('ledger', NOW+5, 'READ_UNAVAILABLE'))
        self.assertEqual(self.store.report('UNKNOWN')['monitoring_state'], 'DEGRADED')
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM incidents WHERE state='INVALIDATED'").fetchone()[0], 1)

    def test_quota_retry_preservation_exhaustion_and_actual_unavailable(self):
        self.assertEqual(code_events('QUOTA_DB_CONTENTION_RETRY', DISCOVERY, 'x', NOW, 'journal'), [])
        self.assertEqual(completed_health({'result':'DEGRADED', 'quota':{'status':'REDUCED_TO_PRESERVE_QUOTA'}, 'failure':None}, DISCOVERY, 'x', NOW, 'health'), [])
        quota = completed_health({'result':'FAILED','failure':{'code':'QUOTA_DB_CONTENTION_EXHAUSTED'}}, DISCOVERY, 'x', NOW, 'health')
        self.ingest(*quota)
        self.assertEqual(groups(self.store.db)[0]['members'][0]['rule'], 'QUOTA_DB_CONTENTION')
        for key in ('first','second'):
            self.ingest(*completed_health({'result':'DEGRADED','quota':{'status':'QUOTA_UNAVAILABLE_STOP_AFTER_STATUS'}}, DISCOVERY, key, NOW, 'health'))
        self.assertEqual(self.store.db.execute("SELECT state FROM incidents WHERE rule='QUOTA_FAILURE'").fetchone()[0], 'REPEATED')

    def token_config(self):
        token = self.root/'token'; token.write_text('99:'+'a'*30); token.chmod(0o600)
        config = {'sender': {'enabled':False,'token_file':str(token),'bot_id':99,'bot_username':'AdminBot',
                             'private_chat_id':123,'operator_confirmed_start':True}, 'unrelated':'preserve'}
        path = self.root/'config.json'; path.write_text(json.dumps(config)); path.chmod(0o640)
        return path, config

    def test_prepare_readonly_epoch_suppression_post_epoch_and_restart(self):
        path, config = self.token_config()
        self.ingest(self.event)
        before = (self.root/'admin.sqlite').read_bytes()
        review = projection(self.store.db, config)
        self.assertEqual(review['unsent_pre_enablement_notifications'], 1)
        self.assertEqual(before, (self.root/'admin.sqlite').read_bytes())
        self.assertEqual(enable(path, self.store.db, NOW+10), 1)
        self.assertEqual(json.loads(path.read_text())['unrelated'], 'preserve')
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertTrue(json.loads(path.read_text())['sender']['enabled'])
        self.assertEqual(self.store.db.execute('SELECT id FROM notification_epochs').fetchone()[0], EPOCH)
        self.assertIn('PRE_ENABLEMENT_BACKLOG_SUPERSEDED', self.store.db.execute('SELECT reason FROM notification_audit').fetchone()[0])
        self.store.enqueue(NOW+11)
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+11), 0)
        new = replace(self.event, invocation='b'*32, observed=NOW+12)
        self.store.ingest([new], {}, NOW+12); self.store.enqueue(NOW+12)
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+12), 1)
        with self.assertRaises(ValueError):
            enable(path, self.store.db, NOW+13)
        self.store.close(); self.store = Store(self.root)
        self.assertTrue(json.loads(path.read_text())['sender']['enabled'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM notification_epochs').fetchone()[0], 1)

    def test_activation_failure_keeps_false_audit_failure_never_enables(self):
        path, _ = self.token_config()
        from app.admin_alerts.activation import write_config
        def fail_enabled(path, config):
            if config['sender']['enabled']:
                raise OSError('synthetic')
            return write_config(path, config)
        with patch('app.admin_alerts.activation.write_config', side_effect=fail_enabled):
            with self.assertRaises(OSError):
                enable(path, self.store.db, NOW+10)
        self.assertFalse(json.loads(path.read_text())['sender']['enabled'])
        with self.assertRaises(ValueError):
            enable(path, self.store.db, NOW+20)
        self.assertFalse(json.loads(path.read_text())['sender']['enabled'])

    def test_epoch_preserves_attempted_history_and_post_epoch_outbox(self):
        self.ingest(self.event, replace(self.event, invocation='b'*32))
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET attempts=1,state='UNCERTAIN' WHERE incident=?", (self.event.signature,))
            self.store.db.execute('UPDATE outbox SET created=? WHERE incident!=?', (NOW+100, self.event.signature))
        before = list(map(tuple, self.store.db.execute('SELECT * FROM outbox')))
        prepare_epoch(self.store.db, NOW+10)
        self.assertEqual(before, list(map(tuple, self.store.db.execute('SELECT * FROM outbox'))))

    def test_later_competing_candidate_restores_independent_alert_without_erasing_supersession(self):
        unknown = replace(self.event, rule='ANALYSIS_FAILURE', invocation='UNKNOWN', source='health-one', occurrence='health-one')
        self.ingest(unknown)
        self.ingest(self.event)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE incident=? AND state='SUPERSEDED'", (unknown.signature,)).fetchone()[0], 1)
        self.ingest(replace(self.event, invocation='b'*32, observed=NOW+10))
        self.assertEqual(len(groups(self.store.db)), 3)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE incident=? AND state='PENDING'", (unknown.signature,)).fetchone()[0], 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE incident=? AND state='SUPERSEDED'", (unknown.signature,)).fetchone()[0], 1)

    def test_attempting_support_remains_byte_identical(self):
        missing = replace(self.event, rule='MISSING_OUTPUT')
        self.ingest(missing)
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET state='ATTEMPTING',attempts=1")
        before = list(map(tuple,self.store.db.execute('SELECT * FROM outbox')))
        self.ingest(self.event)
        self.assertEqual(before,list(map(tuple,self.store.db.execute('SELECT * FROM outbox'))))

    def test_temporal_window_boundary_and_audit_immutability(self):
        unknown=replace(self.event,rule='ANALYSIS_FAILURE',invocation='UNKNOWN',source='health-one',observed=NOW+30)
        self.ingest(unknown)
        self.ingest(self.event)
        self.assertEqual(len(groups(self.store.db)),1)
        for sql in ("UPDATE notification_audit SET reason='changed'", "DELETE FROM notification_audit"):
            with self.assertRaises(sqlite3.IntegrityError), self.store.db:
                self.store.db.execute(sql)
        self.ingest(replace(unknown,occurrence='outside',observed=NOW+30.001))
        self.assertEqual(len(groups(self.store.db)),2)

    def test_legacy_weekly_invalidation_preserves_attempted_history(self):
        self.ingest(coverage('weekly', NOW, 'UNRESOLVED_SCAN_IN_PROGRESS'))
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET attempts=1,state='UNCERTAIN'")
        before=list(map(tuple,self.store.db.execute('SELECT * FROM outbox')))
        self.store.invalidate_scan_progress(NOW+1)
        self.store.enqueue(NOW+2)
        self.assertEqual(before,list(map(tuple,self.store.db.execute('SELECT * FROM outbox'))))
        self.assertEqual(dispatch(self.store,self.config,FakeTransport(),NOW+2),0)
        self.assertEqual(self.store.report('UNKNOWN')['monitoring_state'],'AVAILABLE')

    def test_legacy_genuine_coverage_fault_still_recovers(self):
        from app.admin_alerts.model import digest
        event=coverage('ledger',NOW,'READ_UNAVAILABLE')
        old_id=digest((1,'monitor','MONITORING_COVERAGE_DEGRADED','ledger'))
        with patch.object(Event, 'signature', property(lambda e: digest((1,e.service,e.rule,e.object_id)))):
            self.ingest(event)
        self.store.ingest([replace(event,healthy=True,occurrence='read-available',observed=NOW+10,facts={})],{},NOW+10)
        self.assertEqual(self.store.db.execute('SELECT state FROM incidents WHERE id=?',(old_id,)).fetchone()[0],'RECOVERED')
        self.assertEqual(self.store.report('UNKNOWN')['monitoring_state'],'AVAILABLE')


class ScanTests(Temporary):
    def test_ledger_and_weekly_normal_pages_future_sweep_unavailable(self):
        for source, reader in (('ledger', unresolved), ('weekly', weekly_unresolved)):
            path = self.root/(source+'.sqlite')
            db = sqlite3.connect(path)
            db.executescript('CREATE TABLE evidence(kind TEXT,identity TEXT,PRIMARY KEY(kind,identity));'
                             'CREATE TABLE weekly_claims(id TEXT PRIMARY KEY,stream TEXT);'
                             'CREATE TABLE weekly_receipts(id TEXT PRIMARY KEY,stream TEXT);')
            for n in range(MAX_ROWS+1):
                key = f'{n:06}'
                db.execute('INSERT INTO evidence VALUES (?,?)', ('claim',key))
                db.execute('INSERT INTO evidence VALUES (?,?)', ('receipt',key))
                db.execute('INSERT INTO weekly_claims VALUES (?,?)', (key,'PREMATCH'))
                db.execute('INSERT INTO weekly_receipts VALUES (?,?)', (key,'PREMATCH'))
            db.commit();db.close()
            store_root = self.root/(source+'-admin-alerts'); store_root.mkdir()
            store = Store(store_root)
            events, state = reader(path, {}, NOW)
            store.ingest(events, {source:state}, NOW); store.enqueue(NOW)
            self.assertEqual(store.report('UNKNOWN')['monitoring_state'], 'AVAILABLE')
            self.assertEqual(store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)
            store.close()
            self.assertEqual(state['status'], 'SCAN_IN_PROGRESS')
            self.assertTrue(state['read_available'] and state['progress'])
            self.assertFalse([e for e in events if not e.healthy])
            events, state = reader(path, state, NOW+300)
            self.assertEqual(state['status'], 'SCAN_COMPLETED')
            events, state = reader(path, state, NOW+600)
            self.assertEqual(state['status'], 'SCAN_IN_PROGRESS')
            self.assertFalse([e for e in events if not e.healthy])
            events, state = reader(self.root/'absent', state, NOW+900)
            self.assertTrue(events)
            self.assertFalse(state['read_available'])
            events, state = reader(path, {'after':123}, NOW)
            self.assertTrue(events)
            self.assertEqual(state['status'], 'SCAN_UNAVAILABLE')

    def test_stall_is_bounded_and_progress_resets_deadline(self):
        rows = [(f'{n:06}',) for n in range(MAX_ROWS)]
        state = {}
        self.assertFalse(scan_page(state, rows, NOW, 'ledger'))
        self.assertFalse(scan_page(state, rows, NOW+300, 'ledger'))
        self.assertTrue(scan_page(state, rows, NOW+1200, 'ledger'))
        self.assertEqual(state['status'], 'SCAN_STALLED')
        self.assertFalse(scan_page(state, [('999999',)], NOW+1500, 'ledger'))
        self.assertEqual(state['status'], 'SCAN_COMPLETED')
