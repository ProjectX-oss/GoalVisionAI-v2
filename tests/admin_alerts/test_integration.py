"""Synthetic end-to-end scans, crash boundaries and resource measurements."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from app.admin_alerts.cli import scan
from app.admin_alerts.delivery import DeliveryError, dispatch
from app.admin_alerts.model import DISCOVERY, Event
from app.admin_alerts.rules import compact
from app.admin_alerts.sources import tail, weekly_unresolved
from test_monitor import NOW, FakeTransport, Temporary, props, record


class ScanTests(Temporary):
    def config(self) -> dict:
        stdout = self.root / 'output.log'
        stdout.write_text(json.dumps(record()) + '\n')
        return {'stdout': str(stdout), 'health_database': str(self.root/'missing-health'),
                'ledger_database': str(self.root/'missing-ledger'), 'release_environment': str(self.root/'no-env')}

    def test_no_send_end_to_end_and_coverage(self) -> None:
        with patch('app.admin_alerts.cli.systemd', return_value=props()), patch('app.admin_alerts.cli.journal', return_value=([], {})), patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('NO NETWORK')):
            result = scan(self.config(), self.root/'admin-alerts', no_send=True)
        self.assertEqual(result['telegram_sends'], 0)
        report = json.loads((self.root/'admin-alerts/incident-report.json').read_text())
        self.assertEqual(report['monitoring_state'], 'DEGRADED')
        self.assertTrue(any(i['rule'] == 'MONITORING_COVERAGE_DEGRADED' for i in report['incidents']))

    def test_store_failure_never_touches_sources(self) -> None:
        config = self.config()
        before = Path(config['stdout']).read_bytes()
        with patch('app.admin_alerts.cli.Store', side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError):
                scan(config, self.root/'admin-alerts')
        self.assertEqual(before, Path(config['stdout']).read_bytes())

    def test_disabled_scan_opens_no_sources(self) -> None:
        root = self.root/'admin-alerts'
        root.mkdir()
        (root/'DISABLED').touch()
        with patch('app.admin_alerts.cli.systemd', side_effect=AssertionError()):
            self.assertEqual(scan(self.config(), root)['status'], 'DISABLED')

    def test_reboot_gap_is_not_application_failure(self) -> None:
        config = self.config()
        from app.admin_alerts.store import Store
        root = self.root/'admin-alerts'
        root.mkdir()
        store = Store(root)
        with store.db:
            store.put('boot', 'old-boot')
            store.put('last_scan', time.time()-600)
        store.close()
        with patch('app.admin_alerts.cli.systemd', return_value=props()), patch('app.admin_alerts.cli.journal', return_value=([], {})):
            scan(config, root)
        report = json.loads((root/'incident-report.json').read_text())
        self.assertTrue(any(i['object_id'] == 'monitor-gap' for i in report['incidents']))
        self.assertFalse(any(i['rule'] == 'SERVICE_FAILURE' and i['state'] != 'RECOVERED' for i in report['incidents']))

    def test_missing_output_after_grace(self) -> None:
        from app.admin_alerts.store import Store
        config = self.config()
        root = self.root/'admin-alerts'
        root.mkdir()
        store = Store(root)
        with store.db:
            store.put('monitor_started', time.time()-1000)
        store.close()
        value = props()
        uptime = float(Path('/proc/uptime').read_text().split()[0])
        for unit in tuple(k for k in value if k.endswith('.service')):
            value[unit]['ExecMainStartTimestampMonotonic'] = str(int((uptime-500)*1e6))
            value[unit]['ExecMainExitTimestampMonotonic'] = str(int((uptime-400)*1e6))
        Path(config['stdout']).write_text('')
        with patch('app.admin_alerts.cli.systemd', return_value=value), patch('app.admin_alerts.cli.journal', return_value=([], {})):
            scan(config, root)
        report = json.loads((root/'incident-report.json').read_text())
        self.assertEqual(len([i for i in report['incidents'] if i['rule'] == 'MISSING_OUTPUT']), 5)

    def test_running_timer_next_elapse_unknown_does_not_page(self) -> None:
        from app.admin_alerts.sources import service_rules
        value = props(running=True)
        for unit in tuple(k for k in value if k.endswith('.timer')):
            value[unit]['NextElapseUSecRealtime'] = ''
        events, state = service_rules(value, {}, NOW, NOW-1400, NOW-1000, {})
        events, _ = service_rules(value, state, NOW+181, NOW-1400, NOW-1000, {})
        self.assertFalse([e for e in events if not e.healthy])

    def test_recorded_host_schedule_replay(self) -> None:
        from app.admin_alerts.sources import service_rules
        path = Path('docs/operations/PREMATCH_ADMIN_ALERTS_V1_HOST.json')
        data = json.loads(path.read_text())
        values = data['loaded_units']
        events, _ = service_rules(values, {}, NOW, NOW-10000, NOW, {})
        self.assertFalse([e for e in events if e.rule == 'MONITORING_COVERAGE_DEGRADED' and e.facts.get('reason') == 'NEXT_ELAPSE_UNKNOWN'])

    def test_safe_stack_frames_exclude_locals_and_urls(self) -> None:
        from app.admin_alerts.sources import journal
        base = {'_SYSTEMD_UNIT': DISCOVERY, '_SYSTEMD_INVOCATION_ID': 'inv1', '__REALTIME_TIMESTAMP': int(NOW*1e6)}
        records = [{**base, '__CURSOR': 'c1', 'MESSAGE': 'File "/home/app/lab_v2_shadow/cli.py", line 123, in run SECRET https://secret'},
                   {**base, '__CURSOR': 'c2', 'RESULT': 'exit-code', 'MESSAGE': 'secret locals=abc'}]
        events, state = journal({}, NOW, lambda _: '\n'.join(json.dumps(v) for v in records))
        serialized = json.dumps([e.document() for e in events])
        self.assertIn('cli.py', serialized)
        self.assertNotIn('SECRET', serialized)
        self.assertNotIn('locals', serialized)
        self.assertNotIn('https', serialized)

    def test_provider_debounce_waits_for_completed_invocation(self) -> None:
        from app.admin_alerts.store import Store
        root = self.root/'admin-alerts'
        config = self.config()
        event = Event(DISCOVERY, 'PROVIDER_FAILURE', 'pipeline', 'abc123', NOW, 'journal-c1',
                      invocation='abc123', debounce=2)
        with patch('app.admin_alerts.cli.systemd', return_value=props(running=True)), patch('app.admin_alerts.cli.journal', return_value=([event], {})):
            scan(config, root)
        store = Store(root)
        self.assertTrue(store.get('pending_completed_evidence'))
        self.assertEqual(store.db.execute("SELECT count(*) FROM incidents WHERE rule='PROVIDER_FAILURE'").fetchone()[0], 0)
        store.close()
        with patch('app.admin_alerts.cli.systemd', return_value=props()), patch('app.admin_alerts.cli.journal', return_value=([], {})):
            scan(config, root)
        store = Store(root)
        self.assertEqual(store.db.execute("SELECT state FROM incidents WHERE rule='PROVIDER_FAILURE'").fetchone()[0], 'PENDING')
        store.close()

    def test_invalid_nested_shape_degrades(self) -> None:
        for fields in ({'controlled_publication': 99}, {'controlled_publication': {'deliveries': 'bad'}},
                       {'publication_cycle_persistence': []}):
            with self.subTest(fields=fields):
                self.assertEqual(compact(record(**fields), 's', NOW)[0].rule, 'MONITORING_COVERAGE_DEGRADED')

    def test_copytruncate_regrown_file(self) -> None:
        path = self.root/'o.log'
        path.write_text(json.dumps(record())+'\n')
        _, _, state, _ = tail(path, {}, NOW, running=False)
        path.write_text(json.dumps(record(cycle_id='different', terminal_error=True))+'\n'*20)
        values, issues, _, _ = tail(path, state, NOW+1, running=False)
        self.assertEqual(values[0][0]['cycle_id'], 'different')
        self.assertTrue(any(e.facts['reason'] == 'FILE_REWRITTEN' for e in issues))

    def test_old_rotated_partial_does_not_block_replacement(self) -> None:
        path = self.root/'o.log'
        path.write_text('{')
        _, _, state, _ = tail(path, {}, NOW, running=False)
        path.rename(self.root/'o.log.1')
        path.write_text(json.dumps(record())+'\n')
        _, issues, state, _ = tail(path, state, NOW+181, running=False)
        self.assertTrue(issues)
        self.assertEqual(len(tail(path, state, NOW+182, running=False)[0]), 1)

    def test_weekly_unresolved_exact_identity(self) -> None:
        path = self.root/'weekly.db'
        c = sqlite3.connect(path)
        c.execute('CREATE TABLE weekly_claims(id TEXT PRIMARY KEY,stream TEXT)')
        c.execute('CREATE TABLE weekly_receipts(id TEXT PRIMARY KEY,stream TEXT)')
        c.execute("INSERT INTO weekly_claims VALUES ('week1','PREMATCH')")
        c.commit(); c.close()
        events, _ = weekly_unresolved(path, {}, NOW)
        self.assertEqual(events[0].object_id, 'week1')
        self.assertFalse(events[0].healthy)


class ExtraDeliveryTests(Temporary):
    def setUp(self) -> None:
        super().setUp()
        from app.admin_alerts.store import Store
        from app.admin_alerts.delivery import SenderConfig
        self.store = Store(self.root)
        self.config = SenderConfig(True, '', 99, 'AdminBot', 123, True)
        self.event = Event(DISCOVERY, 'SERVICE_FAILURE', 'pipeline', 'inv-1', NOW, 'systemd')
        self.store.ingest([self.event], {}, NOW)
        self.store.enqueue(NOW)

    def tearDown(self) -> None:
        self.store.close()
        super().tearDown()

    def test_recovery_supersedes_pending_failed_alert(self) -> None:
        fake = FakeTransport(DeliveryError('TIMEOUT', uncertain=True))
        dispatch(self.store, self.config, fake, NOW)
        self.store.ingest([replace(self.event, healthy=True, observed=NOW+1)], {}, NOW+1)
        self.store.enqueue(NOW+1)
        fake.failure = None
        dispatch(self.store, self.config, fake, NOW+60)
        self.assertIn('Darbība atjaunota', fake.messages[-1])

    def test_escalation_is_promptly_eligible(self) -> None:
        fake = FakeTransport()
        dispatch(self.store, self.config, fake, NOW)
        self.store.ingest([replace(self.event, severity=3, occurrence='inv2', observed=NOW+1)], {}, NOW+1)
        self.store.enqueue(NOW+1)
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+1), 1)

    def test_validation_failure_never_sends(self) -> None:
        fake = FakeTransport()
        with patch.object(fake, 'validate', side_effect=DeliveryError('BOT_IDENTITY_MISMATCH', permanent=True)):
            dispatch(self.store, self.config, fake, NOW)
        self.assertFalse(fake.messages)
        self.assertTrue(self.store.get('delivery')['permanent'])

    def test_repeated_outage_can_recover_again(self) -> None:
        for offset in (1, 3):
            self.store.ingest([replace(self.event, healthy=True, observed=NOW+offset)], {}, NOW+offset)
            self.assertEqual(self.store.db.execute('SELECT state FROM incidents').fetchone()[0], 'RECOVERED')
            self.store.ingest([replace(self.event, observed=NOW+offset+1)], {}, NOW+offset+1)
            self.assertEqual(self.store.db.execute('SELECT state FROM incidents').fetchone()[0], 'OPEN')

    def test_receipt_commit_failure_remains_uncertain(self) -> None:
        fake = FakeTransport()
        original = fake.send
        def send(text: str) -> dict:
            self.store.db.execute("CREATE TRIGGER fail_receipt BEFORE UPDATE ON outbox WHEN NEW.state='SENT' BEGIN SELECT RAISE(ABORT,'synthetic disk failure'); END")
            self.store.db.commit()
            return original(text)
        fake.send = send
        with self.assertRaises(sqlite3.IntegrityError):
            dispatch(self.store, self.config, fake, NOW)
        self.assertEqual(self.store.db.execute('SELECT state FROM outbox').fetchone()[0], 'ATTEMPTING')
        self.store.db.execute('DROP TRIGGER fail_receipt')
        self.store.db.commit()
        self.store.enqueue(NOW+60)
        self.assertEqual(self.store.db.execute('SELECT state FROM outbox').fetchone()[0], 'UNCERTAIN')

    def test_large_outbox_does_not_starve_later_incidents(self) -> None:
        self.store.ingest([replace(self.event, object_id='object-'+str(i)) for i in range(1001)], {}, NOW)
        self.store.enqueue(NOW)
        self.store.enqueue(NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1002)
