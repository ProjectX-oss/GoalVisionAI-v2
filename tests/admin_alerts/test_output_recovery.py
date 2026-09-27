"""Output contract and exact late-recovery regressions; no live sources or network."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from unittest.mock import patch

from app.admin_alerts.cli import scan
from app.admin_alerts.delivery import SenderConfig, dispatch
from app.admin_alerts.model import Event, UNITS
from app.admin_alerts.output_contracts import CONTRACTS, expected_document
from app.admin_alerts.sources import invocation_output, journal, service_rules
from app.admin_alerts.store import Store
from test_monitor import Temporary, FakeTransport, NOW, props

UNIT = UNITS[4]
INV = 'a' * 32
OTHER = 'b' * 32


def line(inv=INV, doc=None, **extra):
    return json.dumps({'_SYSTEMD_UNIT': UNIT, '_SYSTEMD_INVOCATION_ID': inv,
        '__REALTIME_TIMESTAMP': int((NOW-1000)*1e6), '__CURSOR': 'cursor-' + inv,
        'MESSAGE': json.dumps(doc if doc is not None else {'status': 'ALREADY_SENT', 'sent': False}), **extra})


class RecoveryTests(Temporary):
    def setUp(self):
        super().setUp()
        self.network = patch('socket.socket.connect', side_effect=AssertionError('NO NETWORK'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def open_incident(self, unit=UNIT):
        store = Store(self.root)
        event = Event(unit, 'MISSING_OUTPUT', INV, INV, NOW, 'journal-output', invocation=INV)
        store.ingest([event], {}, NOW)
        store.enqueue(NOW)
        return store, event

    def test_same_invocation_late_output_supersedes_unsent_and_sends_nothing(self):
        store, fault = self.open_incident()
        try:
            events, state = journal({}, NOW+1, lambda _: line())
            self.assertTrue(events[0].healthy)
            self.assertEqual(events[0].signature, fault.signature)
            # Journal timestamp predates fault; proof is newly acquired now.
            store.ingest(events, {'journal': state}, NOW+1)
            store.enqueue(NOW+1)
            self.assertEqual(store.db.execute('select state from incidents').fetchone()[0], 'RECOVERED')
            self.assertEqual(tuple(store.db.execute('select state,attempts from outbox').fetchone()), ('SUPERSEDED', 0))
            transport = FakeTransport()
            self.assertEqual(dispatch(store, SenderConfig(True, '', 99, 'AdminBot', 123, True), transport, NOW+2), 0)
            self.assertEqual(transport.messages, [])
            self.assertEqual(store.db.execute('select count(*) from outbox').fetchone()[0], 1)
            store.ingest(journal(state, NOW+3, lambda _: line())[0], {}, NOW+3)
            store.enqueue(NOW+3)
            self.assertEqual(store.db.execute('select count(*) from occurrences').fetchone()[0], 2)
        finally:
            store.close()

    def test_different_invocation_does_not_recover(self):
        store, _ = self.open_incident()
        store.ingest(journal({}, NOW+1, lambda _: line(OTHER))[0], {}, NOW+1)
        self.assertEqual(store.db.execute('select state from incidents').fetchone()[0], 'OPEN')
        store.close()

    def test_arbitrary_json_and_manager_id_are_not_proof(self):
        for value in (line(doc={'status': 'ALREADY_SENT'}), line(doc={'diagnostic': 1}),
                      line(_SYSTEMD_INVOCATION_ID=None, INVOCATION_ID=INV)):
            events, state = journal({}, NOW+1, lambda _: value)
            self.assertFalse([e for e in events if e.rule == 'MISSING_OUTPUT'])
            self.assertFalse(state.get('output_proofs_v1'))

    def test_exact_lookup_is_bounded_and_rejects_other_identity(self):
        calls = []
        def read(args):
            calls.append(args)
            return line(OTHER) + '\n' + line()
        events = invocation_output(UNIT, INV, NOW+1, read)
        self.assertEqual(len(events), 1)
        self.assertIn('_SYSTEMD_INVOCATION_ID='+INV, calls[0])
        self.assertEqual(calls[0][calls[0].index('-n')+1], '100')
        self.assertEqual(invocation_output(UNITS[1], INV, NOW, read), [])
        self.assertEqual(len(calls), 1)

    def test_none_contract_and_real_failure(self):
        self.assertEqual(CONTRACTS[UNITS[1]].source, 'NONE')
        self.assertFalse(expected_document(UNITS[1], {'settled': 3}))
        events, _ = service_rules(props('exit-code', '1'), {}, NOW, NOW-1400, NOW-1000, {})
        self.assertTrue(any(e.service == UNITS[1] and e.rule == 'SERVICE_FAILURE' and not e.healthy for e in events))

    def test_proofs_survive_cursor_loss_without_mutating_previous(self):
        _, previous = journal({}, NOW, lambda _: line())
        before = json.dumps(previous, sort_keys=True)
        journal(previous, NOW+1, lambda _: line(OTHER))
        self.assertEqual(json.dumps(previous, sort_keys=True), before)
        def lost(_):
            raise OSError()
        _, state = journal(previous, NOW+1, lost)
        self.assertIn(INV, state['output_proofs_v1'][UNIT])
        self.assertNotIn('cursor', state)

    def test_scan_completion_grace_restart_historical_recovery_and_source_immutability(self):
        root = self.root/'admin-alerts'
        root.mkdir()
        output = self.root/'output.log'; output.write_text('')
        database = self.root/'producer.db'
        db = sqlite3.connect(database); db.execute('create table sentinel(value)'); db.commit(); db.close()
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (output, database)}
        config = {'stdout': str(output), 'health_database': str(database), 'ledger_database': str(database),
                  'release_environment': str(self.root/'absent'), 'sender': {'enabled': False}}
        store = Store(root)
        with store.db:
            store.put('monitor_started', time.time()-1000)
            store.put('last_database_poll', time.time())
        store.close()
        value = props()
        uptime = float(Path('/proc/uptime').read_text().split()[0])
        for unit in UNITS:
            value[unit].update(InvocationID=INV, ExecMainStartTimestampMonotonic=str(int((uptime-500)*1e6)),
                              ExecMainExitTimestampMonotonic=str(int((uptime-100)*1e6)))
        value[UNITS[1]]['StandardOutput'] = 'null'
        def run(journal_result=([], {}), recovery=None):
            with patch('app.admin_alerts.cli.systemd', return_value=value), \
                 patch('app.admin_alerts.cli.journal', return_value=journal_result), \
                 patch('app.admin_alerts.cli.invocation_output', side_effect=recovery or (lambda *a: [])):
                scan(config, root)
        run()
        store = Store(root)
        self.assertEqual(store.db.execute("select count(*) from incidents where rule='MISSING_OUTPUT'").fetchone()[0], 0)
        store.close()
        for unit in UNITS:
            value[unit]['ExecMainExitTimestampMonotonic'] = str(int((uptime-400)*1e6))
        run()
        store = Store(root)
        rows = store.db.execute("select service,state from incidents where rule='MISSING_OUTPUT'").fetchall()
        self.assertEqual(len(rows), 4)
        self.assertNotIn(UNITS[1], [r[0] for r in rows])
        with store.db:
            store.put('output_recheck_after', '')
        store.close()
        # New process / newer systemd invocation; old output is behind global cursor.
        for unit in UNITS:
            value[unit]['InvocationID'] = OTHER
        def recover(unit, inv, now):
            return invocation_output(unit, inv, now, lambda _: line())
        for _ in range(5):  # two per scan reaches eight execution-specific candidates
            run(recovery=recover)
        store = Store(root)
        self.assertEqual(store.db.execute("select state from incidents where service=? and object_id=?", (UNIT, INV)).fetchone()[0], 'RECOVERED')
        self.assertEqual(store.db.execute("select state from incidents where service=? and object_id=?", (UNIT, OTHER)).fetchone()[0], 'OPEN')
        store.close()
        # Lost cursor must not reopen the proven terminal invocation.
        value[UNIT]['InvocationID'] = INV
        run()
        store = Store(root)
        self.assertEqual(store.db.execute("select state from incidents where service=? and object_id=?", (UNIT, INV)).fetchone()[0], 'RECOVERED')
        store.close()
        self.assertEqual(before, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (output, database)})
        self.assertFalse(Path(str(database)+'-wal').exists())
        self.assertFalse(Path(str(database)+'-shm').exists())

    def test_contract_final_shapes_for_every_journal_service(self):
        observer = {'stream': 'PREMATCH', 'created_at': '2026-09-27T00:00:00+00:00',
                    'linkage': {}, 'state': {}, 'metrics': {}, 'LIVE': 'DISABLED',
                    'heavy_training': False, 'api_calls': 0, 'telegram_sends': 0}
        research = {'stream': 'PREMATCH', 'research_due': False, 'next_threshold': {},
                    'status': 'INSUFFICIENT_SAMPLE', 'stage': 'OBSERVE', 'resolved': 0, 'days_covered': 0}
        self.assertTrue(expected_document(UNITS[2], observer))
        self.assertTrue(expected_document(UNITS[3], research))
        self.assertTrue(expected_document(UNITS[3], {'status': 'CONCURRENT_CYCLE_COMPLETED'}))
        self.assertFalse(expected_document(UNITS[2], {'football_context_observation': {}}))
        self.assertFalse(expected_document(UNITS[3], {'status': 'RANDOM_DIAGNOSTIC'}))
        self.assertFalse(expected_document(UNITS[3], {'status': []}))

    def test_discovery_window_never_claims_exact_recovery(self):
        from test_monitor import record
        self.assertEqual(CONTRACTS[UNITS[0]].association, 'TIME_WINDOW_ONLY')
        events, state = journal({}, NOW, lambda _: line(doc=record(), _SYSTEMD_UNIT=UNITS[0]))
        self.assertFalse(any(e.rule == 'MISSING_OUTPUT' and e.healthy for e in events))
        self.assertFalse(state.get('output_proofs_v1'))
        self.assertEqual(invocation_output(UNITS[0], INV, NOW, lambda _: line(doc=record())), [])
