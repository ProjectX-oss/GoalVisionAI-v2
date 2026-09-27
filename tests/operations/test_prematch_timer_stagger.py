"""Operations tests only. Mutations are confined to temporary directories."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]/'operations/prematch-timer-stagger'
sys.path.insert(0, str(ROOT))
import control as c
import calendar_proof as cal
import forward_evidence as evidence


class FakeHost:
    def __init__(self, baseline):
        self.props = {u: copy.deepcopy(v['properties']) for u,v in baseline['units'].items()}
        self.calls = []
        self.fail_action = None
        self.admin_state = {'sender_enabled': True, 'config_sha256': 'unchanged', 'notification_epochs': [['epoch', 1, 'policy']]}

    def show(self, unit):
        p = copy.deepcopy(self.props[unit])
        if unit in c.CHANGED:
            installed = c.dropin(unit).exists()
            loaded = c.calendar_of(p) == [cal.TARGET[unit]]
            p['NeedDaemonReload'] = 'yes' if installed != loaded else 'no'
        return p

    def mutate(self, action, unit=None):
        self.calls.append((action, unit))
        if self.fail_action == (action, unit):
            self.fail_action = None
            raise RuntimeError('injected systemd failure')
        if action == 'daemon-reload':
            for u in c.CHANGED:
                installed = c.dropin(u).exists()
                self.props[u]['DropInPaths'] = str(c.dropin(u)) if installed else ''
                self.props[u]['TimersCalendar'] = '{ OnCalendar='+ (cal.TARGET if installed else cal.OLD)[u]+' ; next_elapse=n/a }'
        else:
            assert action == 'restart' and unit in c.CHANGED
            assert self.props[unit]['ActiveState'] == 'active'

    def admin(self):
        return copy.deepcopy(self.admin_state)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        units = root/'units'; units.mkdir()
        state = root/'state'; state.mkdir()
        baseline = json.loads((ROOT/'baseline.json').read_text())
        baseline['timezone'] = Path('/etc/timezone').read_text().strip()
        baseline['localtime_sha256'] = c.sha(Path('/etc/localtime'))
        for u, pin in baseline['units'].items():
            path = units/u;path.write_text('fixture for '+u)
            pin['files'] = {str(path):c.sha(path)}
            pin['properties']['FragmentPath'] = str(path)
            pin['properties']['DropInPaths'] = ''
        self.baseline = baseline
        self.host = FakeHost(baseline)
        for name, value in [('UNIT_ROOT',units),('UNIT_SEARCH_ROOTS',(units,)),('STATE',state),('BASELINE',baseline),('MANIFEST','a'*64)]:
            p = patch.object(c,name,value,create=True);p.start();self.addCleanup(p.stop)
        self.addCleanup(patch.stopall)
        patch.object(c,'deployment_lock',lambda: __import__('contextlib').nullcontext()).start()
        patch.object(c,'safe_rearm').start()
        patch.object(c,'verify_next',side_effect=lambda host,u,*args:host.show(u)).start()
        # Transaction tests isolate calendar-policy acceptance. Real calendar
        # tests below explicitly reject the unresolved weekly collision.
        patch.object(c,'proof',return_value={'zero_collisions':True}).start()
        patch.object(socket,'socket',side_effect=AssertionError('network forbidden')).start()

    def install(self):
        return c.change(self.host,'install')

    def test_exactly_three_dropins_and_no_service_controls(self):
        self.install()
        files = list(c.UNIT_ROOT.glob('*.timer.d/*.conf'))
        self.assertEqual({p.parent.name[:-2] for p in files},set(c.CHANGED))
        self.assertEqual(self.host.calls,[('daemon-reload',None),*[('restart',u) for u in c.CHANGED]])
        self.assertEqual(c.read_transaction()['phase'],'installed')
        self.assertTrue(all(p.read_bytes()==c.payload(p.parent.name[:-2]) for p in files))

    def test_original_units_discovery_research_and_admin_unchanged(self):
        before = {p: c.sha(Path(p)) for v in self.baseline['units'].values() for p in v['files']}
        admin = copy.deepcopy(self.host.admin_state)
        self.install(); c.change(self.host,'rollback')
        self.assertEqual(before,{p:c.sha(Path(p)) for p in before})
        self.assertEqual(admin,self.host.admin_state)
        self.assertFalse(list(c.UNIT_ROOT.glob('*.timer.d/*.conf')))
        for u in cal.NAMES:
            self.assertEqual(c.calendar_of(self.host.show(u)),[cal.OLD[u]])

    def test_inactive_timer_stays_inactive_and_never_restarted(self):
        u=c.CHANGED[1]; self.host.props[u]['ActiveState']='inactive'
        self.install();c.change(self.host,'rollback')
        self.assertNotIn(('restart',u),self.host.calls)
        self.assertEqual(self.host.show(u)['ActiveState'],'inactive')

    def test_hash_drift_rejected_before_mutation(self):
        Path(next(iter(self.baseline['units'][cal.NAMES[0]]['files']))).write_text('changed')
        with self.assertRaisesRegex(ValueError,'UNIT_HASH_DRIFT'): self.install()
        self.assertEqual(self.host.calls,[])
        self.assertFalse((c.STATE/'transaction.json').exists())

    def test_need_reload_drift_rejected(self):
        self.host.props[cal.NAMES[0]]['NeedDaemonReload']='yes'
        with self.assertRaisesRegex(ValueError,'NEED_DAEMON_RELOAD'): self.install()
        self.assertEqual(self.host.calls,[])

    def test_unloaded_foreign_dropin_rejected(self):
        p=c.UNIT_ROOT/(cal.NAMES[0]+'.d');p.mkdir();(p/'unexpected.conf').write_text('[Timer]\n')
        with self.assertRaisesRegex(ValueError,'UNLOADED_DROPIN_DRIFT'):self.install()
        self.assertEqual(self.host.calls,[])

    def test_owned_tamper_never_removed(self):
        self.install();p=c.dropin(c.CHANGED[0]);p.write_text('foreign content')
        calls=list(self.host.calls)
        with self.assertRaisesRegex(ValueError,'OWNED_DROPIN_DRIFT'):c.change(self.host,'rollback')
        self.assertEqual(p.read_text(),'foreign content');self.assertEqual(calls,self.host.calls)

    def test_timer_propagation_refused(self):
        u=c.CHANGED[0]
        for p in (self.baseline['units'][u]['properties'],self.host.props[u]):p['ConsistsOf']='worker.service'
        with self.assertRaisesRegex(ValueError,'TIMER_PROPAGATION_REFUSED'):self.install()
        self.assertEqual(self.host.calls,[])

    def test_reload_and_each_rearm_failure_restores_original(self):
        for fail in [('daemon-reload',None),*[('restart',u) for u in c.CHANGED]]:
            self.host.fail_action=fail
            with self.assertRaises(RuntimeError):self.install()
            self.assertEqual(c.read_transaction()['phase'],'rolled_back')
            self.assertFalse(any(c.dropin(u).exists() for u in c.CHANGED))
            for u in c.CHANGED:self.assertEqual(c.calendar_of(self.host.show(u)),[cal.OLD[u]])

    def test_interrupt_after_each_atomic_dropin_recovers_on_next_command(self):
        for count in range(1,4):
            tx={'phase':'installing','manifest':c.MANIFEST,'reload_pending':False,
                'timers':{u:{k:self.host.show(u)[k] for k in ('ActiveState','UnitFileState')} for u in cal.NAMES}}
            c.save_transaction(tx)
            for u in c.CHANGED[:count]:
                c.dropin(u).parent.mkdir(exist_ok=True);c.atomic(c.dropin(u),c.payload(u))
            # Simulated SIGKILL: no in-process exception cleanup ran.
            c.change(self.host,'install')
            self.assertEqual(c.read_transaction()['phase'],'rolled_back')
            self.assertFalse(any(c.dropin(u).exists() for u in c.CHANGED))

    def test_interrupt_after_unlink_before_reload_recovers(self):
        self.install();tx=c.read_transaction();tx.update(phase='rolling_back',reload_pending=True);c.save_transaction(tx)
        for u in c.CHANGED:c.dropin(u).unlink()
        c.change(self.host,'rollback')
        self.assertEqual(c.read_transaction()['phase'],'rolled_back')
        for u in c.CHANGED:self.assertEqual(c.calendar_of(self.host.show(u)),[cal.OLD[u]])

    def test_idempotent_rollback_does_not_reload(self):
        self.install();c.change(self.host,'rollback');calls=list(self.host.calls)
        c.change(self.host,'rollback');self.assertEqual(calls,self.host.calls)

    def test_original_preflight_is_read_only(self):
        before=set(Path(self.tmp.name).rglob('*'))
        c.check(self.host)
        self.assertEqual(before,set(Path(self.tmp.name).rglob('*')))
        self.assertEqual(self.host.calls,[])

    def test_collision_blocks_install_without_writing_dropins(self):
        with patch.object(c,'proof',return_value={'zero_collisions':False}):
            with self.assertRaisesRegex(ValueError,'TARGET_CALENDAR_COLLISION'):self.install()
        self.assertFalse(any(c.dropin(u).exists() for u in c.CHANGED));self.assertEqual(self.host.calls,[])


class BoundaryTests(unittest.TestCase):
    def test_control_allowlist_rejects_services_stop_kill_start_enable(self):
        host=c.Host()
        with patch.object(subprocess,'run') as run:
            for action,unit in [('restart',cal.NAMES[0]),('restart','goalvision-lab-combo-settle.service'),
                                ('stop',c.CHANGED[0]),('kill',c.CHANGED[0]),('start',c.CHANGED[0]),('enable',c.CHANGED[0]),
                                ('daemon-reload',c.CHANGED[0])]:
                with self.assertRaisesRegex(ValueError,'TIMER_ONLY_CONTROL'):host.mutate(action,unit)
            run.assert_not_called()

    def test_package_and_manifest_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'file').write_text('good')
            manifest=root/'SHA256SUMS';manifest.write_text(c.sha(root/'file')+'  file\n');digest=c.sha(manifest)
            c.verify_package(root,digest)
            (root/'file').write_text('bad')
            with self.assertRaisesRegex(ValueError,'PACKAGE_TAMPER'):c.verify_package(root,digest)
            manifest.write_text('changed')
            with self.assertRaisesRegex(ValueError,'MANIFEST_TAMPER'):c.verify_package(root,digest)

    def test_symlink_payload_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'real').write_text('good');(root/'link').symlink_to(root/'real')
            with self.assertRaisesRegex(ValueError,'SYMLINK_REFUSED'):c.atomic(root/'link',b'bad')
            self.assertEqual((root/'real').read_text(),'good')

    def test_persistent_catchup_refused(self):
        host=unittest.mock.Mock();host.show.return_value={'ActiveState':'active','Persistent':'yes','LastTriggerUSec':'old'}
        now=datetime.now(timezone.utc)
        with patch.object(c,'timestamp',return_value=now-timedelta(days=2)),patch.object(c,'evaluate',return_value=[now-timedelta(hours=1)]):
            with self.assertRaisesRegex(ValueError,'PERSISTENT_CATCHUP'):c.safe_rearm(host,c.CHANGED[0],cal.TARGET[c.CHANGED[0]])
        host.mutate.assert_not_called()

    def test_next_elapse_must_match_exact_calendar(self):
        host=unittest.mock.Mock();host.show.return_value={'ActiveState':'active','NextElapseUSecRealtime':'bad'}
        now=datetime.now(timezone.utc)
        with patch.object(c,'timestamp',return_value=now+timedelta(minutes=2)),patch.object(c,'evaluate',return_value=[now+timedelta(minutes=5)]):
            with self.assertRaisesRegex(ValueError,'NEXT_ELAPSE_UNVERIFIED'):
                c.verify_next(host,c.CHANGED[0],cal.TARGET[c.CHANGED[0]],'active',0)
        host.mutate.assert_not_called()

    def test_production_db_is_never_opened_by_sqlite(self):
        source=(ROOT/'control.py').read_text()
        self.assertEqual(source.count('sqlite3.connect('),1)
        self.assertIn("sqlite3.connect(':memory:')",source)
        self.assertNotIn('requests',source)
        self.assertNotIn('import app',source)


class CalendarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=cal.proof()

    def test_exact_requested_targets(self):
        self.assertEqual(cal.TARGET[cal.NAMES[1]],'*-*-* *:05,15,25,35,45,55:00')
        self.assertEqual(cal.TARGET[cal.NAMES[2]],'*-*-* *:08,38:00')
        self.assertEqual(cal.TARGET[cal.NAMES[3]],'Sun *-*-* 22:45:00 Europe/Riga')
        for u in c.CHANGED:self.assertEqual((ROOT/'drop-ins'/(u+'.conf')).read_bytes(),c.payload(u))

    def test_cadence_discovery_and_research_preserved_including_dst(self):
        for window in self.report['windows']:
            self.assertTrue(window['cadence_preserved'])
            self.assertTrue(window['discovery_unchanged']);self.assertTrue(window['research_unchanged'])
            self.assertEqual(window['counts'][cal.NAMES[3]],1)

    def test_three_frequent_timers_never_collide(self):
        for w in self.report['windows']:
            for pair, timestamps in w['collisions'].items():
                if cal.NAMES[3] not in pair:self.assertEqual(timestamps,[])

    def test_weekly_requirement_contradiction_detected(self):
        self.assertFalse(self.report['zero_collisions'])
        for w in self.report['windows']:
            self.assertEqual(len(w['collisions'][cal.NAMES[1]+' / '+cal.NAMES[3]]),1)

    def test_proposed_2248_resolves_weekly_collision(self):
        amended={**cal.TARGET,cal.NAMES[3]:'Sun *-*-* 22:48:00 Europe/Riga'}
        self.assertTrue(cal.proof(amended)['zero_collisions'])




class AdminReadTests(unittest.TestCase):
    def test_admin_sender_snapshot_never_changes_any_file(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'admin-alerts.json'
            config.write_text(json.dumps({'sender':{'enabled':True}}))
            (root/'scan.lock').write_bytes(b'')
            db=sqlite3.connect(root/'admin.sqlite')
            db.execute('CREATE TABLE notification_epochs(id TEXT,activated_at INTEGER,policy TEXT)')
            db.execute("INSERT INTO notification_epochs VALUES ('epoch',1,'policy')");db.commit();db.close()
            before={p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.iterdir()}
            with patch.object(c,'ADMIN_CONFIG',config),patch.object(c,'ADMIN_STATE',root),patch.object(socket,'socket',side_effect=AssertionError('network')):
                result=c.Host().admin()
            self.assertTrue(result['sender_enabled'])
            self.assertEqual(before,{p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.iterdir()})

    def test_wal_snapshot_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'config';config.write_text('{"sender":{"enabled":false}}')
            (root/'scan.lock').touch();(root/'admin.sqlite').touch();(root/'admin.sqlite-wal').touch()
            with patch.object(c,'ADMIN_CONFIG',config),patch.object(c,'ADMIN_STATE',root):
                with self.assertRaisesRegex(ValueError,'ADMIN_SNAPSHOT_UNSAFE'):c.Host().admin()


class EvidenceTests(unittest.TestCase):
    def make_records(self, fail=False, retry=False, omit_output=False):
        self.start=datetime.fromisoformat('2026-09-27T06:00:00+00:00')
        self.end=self.start+timedelta(minutes=40)
        records=[];outputs=[]
        for number,(unit,minimum) in enumerate(evidence.REQUIRED.items()):
            timer=unit.replace('.service','.timer')
            for index,t in enumerate(cal.evaluate(cal.TARGET[timer],self.start-timedelta(seconds=1),6)):
                if t>=self.end:break
                inv=('%02d%030d'%(number,index))
                def row(seconds,message,manager=False):
                    return {'__REALTIME_TIMESTAMP':str(int((t+timedelta(seconds=seconds)).timestamp()*1e6)),
                        '_PID':'1' if manager else '123','UNIT':unit,'_SYSTEMD_UNIT':unit,
                        'INVOCATION_ID':inv,'_SYSTEMD_INVOCATION_ID':inv,'MESSAGE':message}
                records.append(row(0,'Starting worker...',True))
                records.append(row(1,'ordinary stderr record'))
                if retry:records.append(row(2,'QUOTA_DB_CONTENTION_RETRY'))
                if fail:records.append(row(3,'QUOTA_DB_CONTENTION_EXHAUSTED database is locked'))
                if timer==cal.NAMES[2] and not omit_output:
                    records.append(row(4,json.dumps({'stream':'PREMATCH','created_at':t.isoformat(),
                        'linkage':{},'state':{},'metrics':{},'LIVE':'DISABLED','heavy_training':False,'api_calls':0,'telegram_sends':0})))
                if timer==cal.NAMES[0] and not omit_output:outputs.append((t+timedelta(seconds=4),{}))
                if fail:records.append(row(5,'worker: Main process exited, code=exited, status=1/FAILURE',True))
                records.append(row(6,"worker: Failed with result 'exit-code'." if fail else 'worker: Deactivated successfully.',True))
        return records,outputs

    def test_complete_scheduled_evidence_passes_with_transient_retry(self):
        rows,outputs=self.make_records(retry=True)
        report=evidence.summarize(rows,self.start,self.end,outputs)
        self.assertEqual(report['verdict'],'PASS')
        for s in report['services'].values():
            self.assertGreater(s['counts']['QUOTA_DB_CONTENTION_RETRY'],0)
            self.assertEqual(s['counts']['QUOTA_DB_CONTENTION_EXHAUSTED'],0)
            self.assertTrue(all(r['exit_status']==0 for r in s['invocations']))

    def test_exhausted_lock_and_nonzero_exit_fail(self):
        rows,outputs=self.make_records(fail=True)
        report=evidence.summarize(rows,self.start,self.end,outputs)
        self.assertEqual(report['verdict'],'FAIL')
        for s in report['services'].values():
            for rule in ('QUOTA_DB_CONTENTION_EXHAUSTED','DATABASE_LOCK','SERVICE_FAILURE'):
                self.assertGreater(s['counts'][rule],0)

    def test_empty_or_truncated_journal_never_passes(self):
        rows,outputs=self.make_records()
        self.assertNotEqual(evidence.summarize([],self.start,self.end)['verdict'],'PASS')
        self.assertNotEqual(evidence.summarize([r for r in rows if r['_PID']!='1'],self.start,self.end,outputs)['verdict'],'PASS')

    def test_output_contracts_discovery_observer_and_settlement_null(self):
        rows,outputs=self.make_records(omit_output=True)
        report=evidence.summarize(rows,self.start,self.end,outputs)
        self.assertGreater(report['services'][cal.NAMES[0].replace('.timer','.service')]['counts']['MISSING_OUTPUT'],0)
        self.assertEqual(report['services'][cal.NAMES[1].replace('.timer','.service')]['counts']['MISSING_OUTPUT'],0)
        self.assertGreater(report['services'][cal.NAMES[2].replace('.timer','.service')]['counts']['MISSING_OUTPUT'],0)

if __name__=='__main__':unittest.main()
