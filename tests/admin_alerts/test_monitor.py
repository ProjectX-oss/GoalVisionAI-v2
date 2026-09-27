"""Offline sidecar tests. All delivery uses fake transports and synthetic sources."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.admin_alerts.delivery import DeliveryError, SenderConfig, Telegram, dispatch
from app.admin_alerts.model import DISCOVERY, SCHEMA, UNITS, Event, alert, coverage
from app.admin_alerts.rules import compact, completed_health
from app.admin_alerts.sources import (MAX_LINE, MAX_READ, command, duration, health_rows,
    journal, readonly, service_rules, system_stamp, tail, unresolved)
from app.admin_alerts.store import Store, lock

NOW = 1790503200.0
ISO = datetime.fromtimestamp(NOW, timezone.utc).isoformat()


def record(**values: object) -> dict:
    return {'schema_version': SCHEMA, 'cycle_id': 'cycle-1', 'evaluated_at_utc': ISO,
            'analysis_status': 'COMPLETED', 'delivery_status': 'NOT_ATTEMPTED',
            'publication_cycle_persistence': {'persisted': True}, 'controlled_publication': {}, **values}


def faults(events: list[Event]) -> list[Event]:
    return [e for e in events if not e.healthy]


def props(result: str = 'success', status: str = '0', running: bool = False) -> dict:
    answer = {}
    for unit in UNITS:
        answer[unit] = {'InvocationID': 'abc123', 'Result': result, 'ExecMainStatus': status,
            'ActiveState': 'activating' if running else 'inactive', 'SubState': 'start' if running else 'dead',
            'ExecMainStartTimestampMonotonic': str(1000_000_000),
            'ExecMainExitTimestampMonotonic': '0' if running else str(1400_000_000),
            'TimeoutStartUSec': '30min'}
        answer[unit.replace('.service', '.timer')] = {'ActiveState': 'active', 'UnitFileState': 'enabled',
            'NextElapseUSecRealtime': 'Sun 2026-09-27 12:00:00 UTC', 'AccuracyUSec': '1min',
            'RandomizedDelayUSec': '0', 'LastTriggerUSec': 'Sun 2026-09-27 08:00:00 UTC'}
    return answer


class RuleTests(unittest.TestCase):
    def test_exit_zero_delivery_failures(self) -> None:
        for status in ('FAILED', 'DEGRADED', 'UNKNOWN'):
            with self.subTest(status=status):
                self.assertIn('DELIVERY_FAILURE', [e.rule for e in faults(compact(record(delivery_status=status), 'stdout', NOW))])

    def test_terminal_and_cycle_persistence(self) -> None:
        value = record(terminal_error={'message': 'secret'}, publication_cycle_persistence={'persisted': False})
        self.assertEqual({'ANALYSIS_FAILURE', 'CYCLE_PERSISTENCE'}, {e.rule for e in faults(compact(value, 's', NOW))})

    def test_acknowledged_without_receipt(self) -> None:
        value = record(controlled_publication={'deliveries': [{'prediction_id': 'p1', 'acknowledgement_received': True}]})
        event = faults(compact(value, 's', NOW))[0]
        self.assertEqual(event.rule, 'DELIVERY_UNCERTAIN')
        self.assertEqual(event.severity, 3)
        self.assertTrue(event.facts['acknowledgement_received'])

    def test_transport_unknown_and_receipt_failure(self) -> None:
        for value in ({'transport_attempted': True}, {'reconciliation_required': True},
                      {'acknowledgement_received': True, 'persistence_failure': 'RECEIPT'}):
            with self.subTest(value=value):
                events = compact(record(controlled_publication={'deliveries': [{'prediction_id': 'p1', **value}]}), 's', NOW)
                self.assertEqual(faults(events)[0].rule, 'DELIVERY_UNCERTAIN')

    def test_normal_no_ready_pending_and_policy(self) -> None:
        for reason in ('NO_READY_SELECTIONS', 'NIGHT_DISCOVERY_PAUSED', 'MATCH_PENDING', 'ODDS_STALE_WAITING_REFRESH',
                       'INSUFFICIENT_SAMPLE', 'LOST', 'LAB_PUBLICATION_RULE_BLOCKED'):
            with self.subTest(reason=reason):
                self.assertFalse(faults(compact(record(ready_candidate_count=0, telegram_sends=0,
                    controlled_publication={'reason': reason}), 's', NOW)))

    def test_quota_preservation_not_page(self) -> None:
        self.assertFalse(completed_health({'result': 'DEGRADED', 'quota': {'status': 'REDUCED_TO_PRESERVE_QUOTA'}}, DISCOVERY, 'a', NOW, 'h'))

    def test_no_success_while_running(self) -> None:
        events, _ = service_rules(props(running=True), {}, NOW, NOW-1400, NOW-1000, {})
        self.assertFalse([e for e in events if e.rule == 'SERVICE_FAILURE'])

    def test_successful_dead_oneshot(self) -> None:
        self.assertFalse(faults(service_rules(props(), {}, NOW, NOW-1400, NOW-1000, {})[0]))

    def test_exit_signal_timeout_oom(self) -> None:
        for result in ('exit-code', 'signal', 'timeout', 'oom-kill', 'core-dump'):
            with self.subTest(result=result):
                events, _ = service_rules(props(result, '1'), {}, NOW, NOW-1400, NOW-1000, {})
                self.assertEqual(len(faults(events)), 5)
                self.assertTrue(all(e.rule == 'SERVICE_FAILURE' for e in faults(events)))

    def test_eight_minutes_not_stuck(self) -> None:
        events, _ = service_rules(props(running=True), {}, NOW, NOW-1480, NOW-1000, {})
        self.assertFalse(faults(events))

    def test_timeout_used(self) -> None:
        events, _ = service_rules(props(running=True), {}, NOW, NOW-3000, NOW-2000, {})
        self.assertEqual({e.rule for e in faults(events)}, {'RUNNING_LONG'})

    def test_timer_inactive_startup_and_maintenance(self) -> None:
        value = props()
        value[DISCOVERY.replace('.service', '.timer')]['ActiveState'] = 'inactive'
        self.assertIn('TIMER_INACTIVE', {e.rule for e in faults(service_rules(value, {}, NOW, NOW-1400, NOW-500, {})[0])})
        self.assertFalse(faults(service_rules(value, {}, NOW, NOW-1400, NOW, {})[0]))
        maintenance = {'m': {'scope': DISCOVERY, 'until': NOW+1}}
        self.assertFalse(faults(service_rules(value, {}, NOW, NOW-1400, NOW-500, maintenance)[0]))
        maintenance['m']['until'] = NOW-1
        self.assertTrue(faults(service_rules(value, {}, NOW, NOW-1400, NOW-500, maintenance)[0]))

    def test_calendar_no_guessed_cadence(self) -> None:
        for local in ('2026-03-29T02:30:00', '2026-03-29T04:30:00', '2026-10-25T03:30:00', '2026-09-28T02:00:00'):
            with self.subTest(local=local):
                stamp = datetime.fromisoformat(local).replace(tzinfo=ZoneInfo('Europe/Riga')).timestamp()
                self.assertFalse(faults(service_rules(props(), {}, stamp, stamp-1400, stamp-1000, {})[0]))

    def test_missing_start_cached_deadline(self) -> None:
        due = NOW-500
        value = props()
        for unit in UNITS:
            value[unit]['ExecMainStartTimestampMonotonic'] = '1'
            value[unit.replace('.service', '.timer')]['LastTriggerUSec'] = ''
        events, states = service_rules(value, {u: {'next': due} for u in UNITS}, NOW, NOW-2000, NOW-1000, {})
        self.assertEqual(len([e for e in faults(events) if e.rule == 'MISSING_START']), 5)
        self.assertEqual(states[DISCOVERY]['next'], due)

    def test_next_elapse_unavailable_is_coverage(self) -> None:
        value = props()
        value[DISCOVERY.replace('.service', '.timer')]['NextElapseUSecRealtime'] = ''
        first, state = service_rules(value, {}, NOW, NOW-1400, NOW-1000, {})
        self.assertFalse(faults(first))
        self.assertEqual(faults(service_rules(value, state, NOW+181, NOW-1400, NOW-1000, {})[0])[0].rule, 'MONITORING_COVERAGE_DEGRADED')

    def test_secret_bearing_input_not_retained(self) -> None:
        secret = 'Bearer abc-secret https://api.telegram.org/bot123:SECRET/foo'
        value = record(terminal_error={'message': secret, 'locals': secret},
            controlled_publication={'failure': {'code': secret}, 'deliveries': [{'prediction_id': secret,
                'transport_attempted': True, 'traceback': secret, 'authorization': secret}]})
        result = json.dumps([e.document() for e in compact(value, 'stdout', NOW)])
        self.assertNotIn('Bearer', result)
        self.assertNotIn('SECRET', result)
        self.assertNotIn('https', result)


class Temporary(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()


class TailTests(Temporary):
    def setUp(self) -> None:
        super().setUp()
        self.path = self.root / 'output.log'

    def test_blank_and_partial(self) -> None:
        body = json.dumps(record()).encode()
        self.path.write_bytes(b'\n'+body[:25])
        records, issues, state, _ = tail(self.path, {}, NOW, running=True)
        self.assertFalse(records or issues)
        self.assertNotIn(body[:25].decode(), json.dumps(state))
        with self.path.open('ab') as stream:
            stream.write(body[25:]+b'\n')
        records, issues, _, _ = tail(self.path, state, NOW+1, running=False)
        self.assertEqual(len(records), 1)
        self.assertFalse(issues)

    def test_partial_grace_after_exit(self) -> None:
        self.path.write_bytes(b'{"secret":')
        _, issues, state, _ = tail(self.path, {}, NOW, running=False)
        self.assertFalse(issues)
        self.assertFalse(tail(self.path, state, NOW+179, running=False)[1])
        self.assertEqual(tail(self.path, state, NOW+181, running=False)[1][0].facts['reason'], 'INCOMPLETE_AFTER_EXIT')
        self.assertFalse(tail(self.path, state, NOW+181, running=True)[1])

    def test_oversized_does_not_lose_following_records(self) -> None:
        self.path.write_bytes(b'x' * (MAX_LINE * 3) + b'\n' + json.dumps(record()).encode()+b'\n')
        records, issues, _, read = tail(self.path, {}, NOW, running=False)
        self.assertEqual(len(records), 1)
        self.assertTrue(any(i.facts['reason'] == 'OVERSIZED_RECORD' for i in issues))
        self.assertLessEqual(read, MAX_READ)

    def test_old_megabytes_first_start_bounded(self) -> None:
        self.path.write_bytes(b'x' * (MAX_READ * 3) + b'\n' + json.dumps(record()).encode()+b'\n')
        records, issues, _, read = tail(self.path, {}, NOW, running=False)
        self.assertEqual(len(records), 1)
        self.assertLessEqual(read, MAX_READ)
        self.assertTrue(issues)

    def test_rotation_drains_old_inode(self) -> None:
        self.path.write_bytes(json.dumps(record()).encode()+b'\n')
        _, _, state, _ = tail(self.path, {}, NOW, running=False)
        with self.path.open('ab') as stream:
            stream.write(json.dumps(record(cycle_id='cycle-2')).encode()+b'\n')
        self.path.rename(self.root/'output.log.1')
        self.path.write_bytes(json.dumps(record(cycle_id='cycle-3')).encode()+b'\n')
        records, _, state, _ = tail(self.path, state, NOW+1, running=False)
        self.assertEqual(records[0][0]['cycle_id'], 'cycle-2')
        records, _, _, _ = tail(self.path, state, NOW+2, running=False)
        self.assertEqual(records[0][0]['cycle_id'], 'cycle-3')

    def test_truncation_missing_corrupt(self) -> None:
        self.assertTrue(tail(self.path, {}, NOW, running=False)[1])
        self.path.write_text('not json\n' + json.dumps(record())+'\n')
        _, issues, state, _ = tail(self.path, {}, NOW, running=False)
        self.assertEqual(issues[0].facts['reason'], 'MALFORMED_RECORD')
        self.path.write_text('\n')
        self.assertEqual(tail(self.path, state, NOW+1, running=False)[1][0].facts['reason'], 'FILE_TRUNCATED')

    def test_restart_replay(self) -> None:
        self.path.write_text(json.dumps(record())+'\n')
        _, _, state, _ = tail(self.path, {}, NOW, running=False)
        self.assertFalse(tail(self.path, json.loads(json.dumps(state)), NOW+1, running=False)[0])


class StoreTests(Temporary):
    def setUp(self) -> None:
        super().setUp()
        self.store = Store(self.root)
        self.event = Event(DISCOVERY, 'SERVICE_FAILURE', 'pipeline', 'inv-1', NOW, 'systemd', invocation='inv-1')

    def tearDown(self) -> None:
        self.store.close()
        super().tearDown()

    def test_atomic_ingestion_cursor_and_replay(self) -> None:
        self.store.ingest([self.event], {'stdout': {'offset': 100}}, NOW)
        self.store.ingest([self.event], {'stdout': {'offset': 100}}, NOW)
        self.assertEqual(self.store.db.execute('SELECT count FROM incidents').fetchone()[0], 1)
        self.assertEqual(self.store.get('stdout')['offset'], 100)

    def test_transaction_rollback(self) -> None:
        with patch.object(self.store, 'put', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.store.ingest([self.event], {'cursor': 5}, NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM incidents').fetchone()[0], 0)
        self.assertIsNone(self.store.get('cursor'))

    def test_cross_source_exact_invocation_dedup(self) -> None:
        self.store.ingest([self.event, replace(self.event, source='journal')], {}, NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM occurrences').fetchone()[0], 1)
        self.store.ingest([replace(self.event, rule='ANALYSIS_FAILURE', occurrence='cycle-1')], {}, NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM incidents').fetchone()[0], 1)

    def test_repeat_escalation_recovery(self) -> None:
        self.store.ingest([self.event], {}, NOW)
        self.store.ingest([replace(self.event, occurrence='inv-2', observed=NOW+1, severity=3)], {}, NOW+1)
        self.assertEqual(self.store.db.execute('SELECT state FROM incidents').fetchone()[0], 'ESCALATED')
        self.store.ingest([replace(self.event, occurrence='inv-3', observed=NOW+2, healthy=True)], {}, NOW+2)
        self.assertEqual(self.store.db.execute('SELECT state FROM incidents').fetchone()[0], 'RECOVERED')

    def test_distinct_delivery_objects_and_unrelated_recovery(self) -> None:
        values = [replace(self.event, rule='DELIVERY_UNCERTAIN', object_id=p) for p in ('p1', 'p2')]
        self.store.ingest(values, {}, NOW)
        self.store.ingest([replace(self.event, healthy=True, observed=NOW+1)], {}, NOW+1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM incidents WHERE state='OPEN'").fetchone()[0], 2)
        self.store.ingest([replace(values[0], healthy=True, observed=NOW+1)], {}, NOW+1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM incidents WHERE state='RECOVERED'").fetchone()[0], 1)

    def test_two_successive_completed_failures(self) -> None:
        event = replace(self.event, rule='PROVIDER_FAILURE', debounce=2)
        self.store.ingest([event], {}, NOW)
        self.store.enqueue(NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)
        self.store.ingest([replace(event, occurrence='inv-2', observed=NOW+1)], {}, NOW+1)
        self.store.enqueue(NOW+1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)

    def test_healthy_breaks_debounce(self) -> None:
        event = replace(self.event, rule='PROVIDER_FAILURE', debounce=2)
        self.store.ingest([event], {}, NOW)
        self.store.ingest([replace(event, healthy=True, occurrence='success', observed=NOW+1)], {}, NOW+1)
        self.store.ingest([replace(event, occurrence='inv-2', observed=NOW+2)], {}, NOW+2)
        self.store.enqueue(NOW+2)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)

    def test_no_growth_on_unchanged_state(self) -> None:
        for _ in range(100):
            self.store.ingest([self.event], {}, NOW)
            self.store.enqueue(NOW)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM occurrences').fetchone()[0], 1)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)

    def test_alert_and_report_sanitized(self) -> None:
        self.store.ingest([self.event], {}, NOW)
        report = self.store.report('current-commit')
        self.assertEqual(report['affected_invocation_release'], 'UNKNOWN')
        text = alert(dict(self.store.db.execute('SELECT * FROM incidents').fetchone()))
        self.assertIn('Latvija', text)
        self.assertLess(len(text), 3001)

    def test_exclusive_scan_lock(self) -> None:
        with lock(self.root):
            with self.assertRaises(BlockingIOError):
                with lock(self.root):
                    pass


class FakeTransport:
    def __init__(self, failure: DeliveryError | None = None, receipt: dict | None = None) -> None:
        self.failure = failure
        self.receipt = receipt or {'message_id': 42, 'chat': {'id': 123, 'type': 'private'}}
        self.messages: list[str] = []

    def validate(self) -> None:
        pass

    def send(self, text: str) -> dict:
        self.messages.append(text)
        if self.failure:
            raise self.failure
        return self.receipt


class DeliveryTests(Temporary):
    def setUp(self) -> None:
        super().setUp()
        self.store = Store(self.root)
        self.config = SenderConfig(True, '', 99, 'AdminBot', 123, True)
        self.event = Event(DISCOVERY, 'SERVICE_FAILURE', 'pipeline', 'inv-1', NOW, 'systemd')
        self.store.ingest([self.event], {}, NOW)
        self.store.enqueue(NOW)

    def tearDown(self) -> None:
        self.store.close()
        super().tearDown()

    def test_success_receipt(self) -> None:
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW), 1)
        row = self.store.db.execute('SELECT * FROM outbox').fetchone()
        self.assertEqual(row['state'], 'SENT')
        self.assertEqual(row['acknowledged'], 1)
        self.assertIn('message_id', row['receipt'])

    def test_timeout_uncertain_retry_identity(self) -> None:
        fake = FakeTransport(DeliveryError('TIMEOUT', uncertain=True))
        dispatch(self.store, self.config, fake, NOW)
        row = self.store.db.execute('SELECT * FROM outbox').fetchone()
        self.assertEqual(row['state'], 'UNCERTAIN')
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+10), 0)
        fake.failure = None
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+31), 1)
        self.assertEqual(fake.messages[0], fake.messages[1])

    def test_429_honored(self) -> None:
        fake = FakeTransport(DeliveryError('RATE_LIMIT', retry_after=120))
        dispatch(self.store, self.config, fake, NOW)
        self.assertEqual(self.store.db.execute('SELECT due FROM outbox').fetchone()[0], NOW+120)
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+60), 0)

    def test_permanent_auth_circuit(self) -> None:
        fake = FakeTransport(DeliveryError('HTTP_REJECTED', permanent=True))
        dispatch(self.store, self.config, fake, NOW)
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+36000), 0)
        self.assertEqual(len(fake.messages), 1)

    def test_wrong_chat_type_and_identity(self) -> None:
        for chat in ({'id': -123, 'type': 'channel'}, {'id': 999, 'type': 'private'}, {'id': 123, 'type': 'group'}):
            with self.subTest(chat=chat):
                fake = FakeTransport(receipt={'message_id': 42, 'chat': chat})
                dispatch(self.store, self.config, fake, NOW)
                self.assertNotEqual(self.store.db.execute('SELECT state FROM outbox').fetchone()[0], 'SENT')

    def test_sender_prerequisites(self) -> None:
        for config in (SenderConfig(), replace(self.config, operator_confirmed_start=False),
                       replace(self.config, private_chat_id=-100123), replace(self.config, bot_username='')):
            with self.subTest(config=config):
                with self.assertRaises(DeliveryError):
                    config.validate()

    def test_expected_bot_identity(self) -> None:
        telegram = object.__new__(Telegram)
        telegram.config = self.config
        with patch.object(telegram, '_call', return_value={'id': 100, 'username': 'AdminBot', 'is_bot': True}):
            with self.assertRaises(DeliveryError) as caught:
                telegram.validate()
        self.assertEqual(caught.exception.code, 'BOT_IDENTITY_MISMATCH')

    def test_retry_limit(self) -> None:
        fake = FakeTransport(DeliveryError('TIMEOUT', uncertain=True))
        for i in range(10):
            dispatch(self.store, self.config, fake, NOW+i*3600)
            self.store.enqueue(NOW+i*3600)
        self.assertEqual(len(fake.messages), 5)
        self.assertEqual(self.store.db.execute('SELECT state FROM outbox').fetchone()[0], 'EXHAUSTED')

    def test_backlog_summary(self) -> None:
        self.store.ingest([replace(self.event, object_id='p'+str(i)) for i in range(30)], {}, NOW)
        self.store.enqueue(NOW)
        fake = FakeTransport()
        self.assertEqual(dispatch(self.store, self.config, fake, NOW), 1)
        self.assertIn('kopsavilkums', fake.messages[0])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE state='SENT'").fetchone()[0], 31)

    def test_hourly_cap_and_no_silent_discard(self) -> None:
        with self.store.db:
            for _ in range(20):
                self.store.db.execute("INSERT INTO attempts(outbox,started,result) VALUES ('x',?,'ATTEMPTED')", (NOW,))
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW), 0)
        self.assertEqual(self.store.db.execute('SELECT state FROM outbox').fetchone()[0], 'PENDING')

    def test_crash_after_transport_before_receipt(self) -> None:
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET state='ATTEMPTING',attempts=1")
        self.store.enqueue(NOW+60)
        self.assertEqual(self.store.db.execute('SELECT state FROM outbox').fetchone()[0], 'UNCERTAIN')

    def test_reminder_thirty_minutes_and_recovery_once(self) -> None:
        fake = FakeTransport()
        dispatch(self.store, self.config, fake, NOW)
        self.store.enqueue(NOW+1799)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 1)
        self.store.enqueue(NOW+1801)
        dispatch(self.store, self.config, fake, NOW+1801)
        self.assertEqual(len(fake.messages), 2)
        self.store.ingest([replace(self.event, healthy=True, observed=NOW+1802)], {}, NOW+1802)
        self.store.enqueue(NOW+1802)
        dispatch(self.store, self.config, fake, NOW+1802)
        self.assertIn('Darbība atjaunota', fake.messages[-1])
        self.store.enqueue(NOW+99999)
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+99999), 0)


class SourceTests(Temporary):
    def test_bounded_subprocess(self) -> None:
        with self.assertRaises(ValueError):
            command(['python3', '-c', 'print("x"*10000)'], limit=100)
        with self.assertRaises(TimeoutError):
            command(['python3', '-c', 'import time; time.sleep(2)'], timeout=.03)

    def test_journal_allowlist_observation_and_sanitization(self) -> None:
        called = []
        def read(args: list[str]) -> str:
            called.extend(args)
            return json.dumps({'_SYSTEMD_UNIT': DISCOVERY, '_SYSTEMD_INVOCATION_ID': 'inv1',
                '__CURSOR': 'cursor1', '__REALTIME_TIMESTAMP': int(NOW*1e6),
                'MESSAGE': json.dumps({'football_context_observation': {'CONSTRUCTION_FAILED': 1}, 'secret': 'dontkeep'})})
        events, state = journal({}, NOW, read)
        self.assertEqual(events[0].rule, 'OBSERVATION_FAILURE')
        self.assertEqual(state['cursor'], 'cursor1')
        self.assertNotIn('dontkeep', json.dumps([e.document() for e in events]))
        self.assertEqual(called.count('-u'), 5)

    def test_journal_manager_failure_and_vacuum(self) -> None:
        value = {'UNIT': DISCOVERY, '_SYSTEMD_UNIT': 'init.scope', 'INVOCATION_ID': 'a',
                 'RESULT': 'oom-kill', '__CURSOR': 'c', '__REALTIME_TIMESTAMP': int(NOW*1e6)}
        events, _ = journal({}, NOW, lambda _: json.dumps(value))
        self.assertEqual(events[0].severity, 3)
        def fail(args: list[str]) -> str:
            raise OSError()
        events, state = journal({'cursor': 'vacuumed'}, NOW, fail)
        self.assertEqual(state, {})
        self.assertEqual(events[0].rule, 'MONITORING_COVERAGE_DEGRADED')

    def test_readonly_missing_never_creates(self) -> None:
        path = self.root/'missing.db'
        self.assertTrue(health_rows(path, {}, NOW)[0])
        self.assertFalse(path.exists())

    def test_producer_files_unchanged_and_query_bounds(self) -> None:
        path = self.root/'producer.db'
        c = sqlite3.connect(path)
        for table in ('cycle_health', 'observer_runs'):
            c.execute(f'CREATE TABLE {table}(id TEXT,created_at TEXT,stream TEXT,document TEXT)')
            c.execute(f'CREATE INDEX {table}_stream_time ON {table}(stream,created_at,id)')
            c.executemany(f'INSERT INTO {table} VALUES (?,?,?,?)', [(f'{i:05}', ISO, 'PREMATCH', json.dumps({'result': 'HEALTHY'})) for i in range(500)])
        c.commit(); c.close()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        events, state = health_rows(path, {}, NOW)
        self.assertEqual(state['cycle_health'][1], '00127')
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['producer.db'])
        c = readonly(path)
        with self.assertRaises(sqlite3.OperationalError):
            c.execute('DELETE FROM cycle_health')
        c.close()

    def test_live_wal_requires_readonly_mount(self) -> None:
        path = self.root/'wal.db'
        c = sqlite3.connect(path)
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE x(a)'); c.commit()
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()}
        with self.assertRaises(PermissionError):
            readonly(path)
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.iterdir()})
        c.close()

    def test_existing_unresolved_claim_exact_receipt(self) -> None:
        path = self.root/'ledger.db'
        c = sqlite3.connect(path)
        c.execute('CREATE TABLE evidence(kind TEXT,identity TEXT,document TEXT,PRIMARY KEY(kind,identity))')
        c.executemany('INSERT INTO evidence VALUES (?,?,?)', [('claim', 'single:p1', '{}'), ('claim', 'single:p2', '{}'), ('receipt', 'single:p2', '{}')])
        c.commit(); c.close()
        events, _ = unresolved(path, {}, NOW)
        self.assertEqual([e.object_id for e in faults(events)], ['p1'])
        self.assertEqual([e.object_id for e in events if e.healthy], ['p2'])

    def test_units_independent_and_disable_only_admin(self) -> None:
        folder = Path('operations/admin-alerts')
        service = (folder/'goalvision-admin-alerts.service').read_text()
        for coupling in ('Requires=', 'PartOf=', 'BindsTo=', 'ExecStartPre=', 'ExecStartPost=', 'OnFailure='):
            self.assertNotIn(coupling, service)
        disable = (folder/'disable-admin-alerts').read_text()
        self.assertNotIn('goalvision-lab-', disable)
        self.assertNotIn('rm ', disable)
        self.assertIn('ReadOnlyPaths=', service)


if __name__ == '__main__':
    unittest.main()
