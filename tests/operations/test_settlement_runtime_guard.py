"""Focused offline runtime, package and journal service-boundary regressions."""
from contextlib import nullcontext, redirect_stderr
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]/'operations/prematch-settlement-guard'
sys.path.insert(0, str(ROOT))
import runtime_guard as g
import guard_evidence as e

spec = importlib.util.spec_from_file_location('settlement_control', ROOT/'control.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
NOW = 1_790_000_000_000_000
SAFE = {'ActiveState':'inactive', 'SubState':'dead', 'InvocationID':'a'*32}


class RuntimeTests(unittest.TestCase):
    def invoke(self, states=None, deadlines=None):
        state = Mock(side_effect=states or [SAFE, SAFE])
        deadline = Mock(side_effect=deadlines or [NOW+300_000_000]*2)
        execute = Mock()
        output = io.StringIO()
        with (redirect_stderr(output), patch.object(socket,'socket',side_effect=AssertionError('network')),
                patch.object(sqlite3,'connect',side_effect=AssertionError('DB'))):
            result = g.run(state, deadline, lambda: NOW*1000, execute)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines),1)
        self.assertEqual(result,0)
        self.assertFalse(any(name == 'app' or name.startswith('app.') for name in sys.modules))
        return json.loads(lines[0]), execute, state, deadline

    def test_safe_exec_exact_argv_and_environment(self):
        before = dict(os.environ)
        record, execute, _, _ = self.invoke()
        execute.assert_called_once_with(g.SETTLEMENT_ARGV[0],list(g.SETTLEMENT_ARGV))
        self.assertEqual(record['code'],g.EXECUTED)
        self.assertEqual(dict(os.environ),before)

    def test_active_states_defer_without_reading_timer(self):
        for state in ('activating','active','deactivating'):
            with self.subTest(state=state):
                record, execute, _, timer = self.invoke([{**SAFE,'ActiveState':state}])
                self.assertEqual(record['code'],g.ACTIVE)
                self.assertEqual(record['discovery_invocation'],'a'*32)
                self.assertTrue(all(record[k] == 0 for k in ('api_calls','database_writes','telegram_sends')))
                execute.assert_not_called();timer.assert_not_called()

    def test_unreadable_malformed_failed_state(self):
        for state in (OSError('SECRET'),{}, {**SAFE,'ActiveState':'failed'},
                      {**SAFE,'SubState':'exited'},{**SAFE,'InvocationID':'SECRET'}):
            record, execute, _, _ = self.invoke([state])
            self.assertEqual(record['code'],g.UNAVAILABLE)
            self.assertNotIn('SECRET',json.dumps(record))
            execute.assert_not_called()

    def test_deadline_boundaries(self):
        for delta, allowed in ((-1,False),(0,False),(179999999,False),
                                (180000000,False),(180001000,True),(181000000,True)):
            with self.subTest(delta=delta):
                record, execute, _, _ = self.invoke(deadlines=[NOW+delta]*2)
                self.assertEqual(record['code'],g.EXECUTED if allowed else g.IMMINENT)
                self.assertEqual(execute.called,allowed)

    def test_race_inactive_to_active(self):
        record, execute, _, _ = self.invoke([SAFE,{**SAFE,'ActiveState':'active'}])
        self.assertEqual(record['code'],g.ACTIVE);execute.assert_not_called()

    def test_race_invocation_changed(self):
        record, execute, _, _ = self.invoke([SAFE,{**SAFE,'InvocationID':'b'*32}])
        self.assertEqual(record['code'],g.UNAVAILABLE);execute.assert_not_called()

    def test_race_timer_enters_horizon(self):
        record, execute, _, _ = self.invoke(deadlines=[NOW+300000000,NOW+180000000])
        self.assertEqual(record['code'],g.IMMINENT);execute.assert_not_called()

    def test_bad_deadlines_and_timeout(self):
        for deadline in (0,None,'bad',True,2**64-1,NOW+86401000000,subprocess.TimeoutExpired('secret',2)):
            record, execute, _, _ = self.invoke(deadlines=[deadline])
            self.assertEqual(record['code'],g.UNAVAILABLE);execute.assert_not_called()

    def test_seconds_field_is_bounded(self):
        record, _, _, _ = self.invoke(deadlines=[1])
        self.assertEqual(record['seconds_to_discovery'],-86400)

    def test_systemd_deadline_uses_numeric_microseconds(self):
        with patch.object(g,'show',return_value={'ActiveState':'active','SubState':'waiting'}),\
             patch.object(g,'command',return_value=json.dumps({'type':'t','data':NOW+180001000})) as command:
            self.assertEqual(g.next_elapse_us(),NOW+180001000)
            self.assertIn('NextElapseUSecRealtime',command.call_args.args[0])

    def test_missing_systemd_property_fails_closed(self):
        with patch.object(g,'command',return_value='ActiveState=inactive\n'):
            with self.assertRaises(ValueError):g.show(g.DISCOVERY)

    def test_exec_failure_is_nonzero(self):
        with redirect_stderr(io.StringIO()):
            status = g.run(lambda:SAFE, lambda:NOW+300000000, lambda:NOW*1000,
                           Mock(side_effect=OSError('secret')))
        self.assertEqual(status,126)

    def test_real_exec_replaces_pid_preserves_arguments_and_environment(self):
        # Child is a harmless standard-library probe; never executes settlement.
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'result.json'
            program = ("import os,json,sys;json.dump({'pid':os.getpid(),'argv':sys.argv[1:],"
                       "'environment':dict(os.environ)},open(sys.argv[1],'w'))")
            argv = [sys.executable,'-I','-S','-c',program,str(output),'space value','ø','$literal']
            source = ("import sys;sys.path.insert(0,"+repr(str(ROOT))+");import runtime_guard as g;"
                      "g.SETTLEMENT_ARGV="+repr(argv)+";g.run(lambda:"+repr(SAFE)+
                      ",lambda:2000000000000000,lambda:1999999700000000000)")
            env = {**os.environ,'GUARD_TEST_VALUE':'space $value ø','PYTHONPATH':'ignored-but-preserved'}
            child = subprocess.Popen([sys.executable,'-I','-S','-c',source],env=env,
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            _,stderr = child.communicate(timeout=10)
            self.assertEqual(child.returncode,0,stderr)
            data=json.loads(output.read_text())
            self.assertEqual(data['pid'],child.pid)
            self.assertEqual(data['argv'],argv[5:])
            self.assertEqual(data['environment'],env)

    def test_historical_projection(self):
        identity='4d931713a53b4404bae23bd990ccebdb'
        record,execute,_,_=self.invoke([{**SAFE,'ActiveState':'active','InvocationID':identity}])
        self.assertEqual(record['code'],g.ACTIVE)
        self.assertEqual(record['discovery_invocation'],identity)
        execute.assert_not_called()


class EvidenceTests(unittest.TestCase):
    def records(self, codes=(g.EXECUTED,)*6, error=None):
        start=datetime(2026,9,29,6,tzinfo=timezone.utc);end=start+timedelta(hours=1)
        rows=[];outputs=[]
        for number,unit in enumerate(e.base.REQUIRED):
            from calendar_proof import TARGET,evaluate
            ticks=evaluate(TARGET[unit.replace('.service','.timer')],start-timedelta(seconds=1),7)
            for index,tick in enumerate(ticks):
                if tick>=end:break
                inv=f'{number:02d}{index:030d}'
                def add(offset,message,manager=False):
                    rows.append({'__REALTIME_TIMESTAMP':str(int((tick+timedelta(seconds=offset)).timestamp()*1e6)),
                        '_PID':'1' if manager else '42','UNIT':unit,'_SYSTEMD_UNIT':unit,
                        'INVOCATION_ID':inv,'_SYSTEMD_INVOCATION_ID':inv,'MESSAGE':message})
                add(0,'Starting worker...',True)
                if unit==e.SETTLEMENT:
                    code=codes[index]
                    if code:
                        doc={'schema_version':g.SCHEMA,'guard_seconds':180,'code':code,
                             'status':'EXECUTED' if code==g.EXECUTED else 'DEFERRED',
                             'api_calls':0,'database_writes':0,'telegram_sends':0}
                        add(1,json.dumps(doc))
                elif number==0:outputs.append((tick+timedelta(seconds=2),{}))
                else:add(1,json.dumps({'stream':'PREMATCH','created_at':tick.isoformat(),'linkage':{},
                    'state':{},'metrics':{},'LIVE':'DISABLED','heavy_training':False,'api_calls':0,'telegram_sends':0}))
                if error:add(2,error)
                add(3,'worker: Deactivated successfully.',True)
        return rows,start,end,outputs

    def summarize(self,codes=(g.EXECUTED,)*6,error=None):
        return e.summarize(*self.records(codes,error))

    def test_six_executions_pass(self):
        report=self.summarize()
        self.assertEqual(report['verdict'],'PASS')
        self.assertEqual(report['guard_counts'][g.EXECUTED],6)

    def test_three_executions_plus_informational_deferrals_pass(self):
        report=self.summarize((g.ACTIVE,g.IMMINENT,g.ACTIVE,g.EXECUTED,g.EXECUTED,g.EXECUTED))
        self.assertEqual(report['verdict'],'PASS')
        self.assertEqual(report['guard_counts'][g.ACTIVE],2)
        self.assertEqual(report['guard_counts'][g.IMMINENT],1)
        self.assertEqual(report['services'][e.SETTLEMENT]['executed_scheduled_cycles'],3)

    def test_deferrals_do_not_meet_execution_minimum(self):
        report=self.summarize((g.ACTIVE,)*4+(g.EXECUTED,)*2)
        self.assertEqual(report['verdict'],'WAIT_OR_INCOMPLETE_EVIDENCE')

    def test_state_unavailable_blocks_pass(self):
        report=self.summarize((g.UNAVAILABLE,)+(g.EXECUTED,)*5)
        self.assertEqual(report['verdict'],'FAIL')
        self.assertEqual(report['guard_counts'][g.UNAVAILABLE],1)

    def test_missing_guard_marker_blocks_pass(self):
        self.assertEqual(self.summarize((None,)+(g.EXECUTED,)*5)['verdict'],'FAIL')

    def test_exhaustion_and_lock_still_fail_retry_informational(self):
        for error in ('QUOTA_DB_CONTENTION_EXHAUSTED','DATABASE_LOCK','SERVICE_FAILURE'):
            self.assertEqual(self.summarize(error=error)['verdict'],'FAIL')
        self.assertEqual(self.summarize(error='QUOTA_DB_CONTENTION_RETRY')['verdict'],'PASS')

    def test_duplicate_marker_fails(self):
        rows,start,end,outputs=self.records()
        rows.append(next(r for r in rows if g.EXECUTED in r['MESSAGE']))
        self.assertEqual(e.summarize(rows,start,end,outputs)['verdict'],'FAIL')

    def test_failed_exec_marker_does_not_count(self):
        rows,start,end,outputs=self.records()
        target=next(r for r in rows if r['UNIT']==e.SETTLEMENT and 'Deactivated' in r['MESSAGE'])
        target['MESSAGE']="worker: Failed with result 'exit-code'."
        report=e.summarize(rows,start,end,outputs)
        self.assertEqual(report['verdict'],'FAIL')
        self.assertEqual(report['services'][e.SETTLEMENT]['executed_scheduled_cycles'],5)


class PackageTests(unittest.TestCase):
    def test_hash_and_inventory_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'file').write_text('original')
            (root/'SHA256SUMS').write_text(c.sha(root/'file')+'  file\n')
            digest=c.sha(root/'SHA256SUMS');c.verify_package(root,digest)
            (root/'file').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'PACKAGE_TAMPER'):c.verify_package(root,digest)
            (root/'file').write_text('original');(root/'extra').touch()
            with self.assertRaisesRegex(ValueError,'INVENTORY'):c.verify_package(root,digest)
            with self.assertRaisesRegex(ValueError,'MANIFEST_TAMPER'):c.verify_package(root,'0'*64)

    def test_payload_changes_only_settlement_execstart(self):
        text=c.payload().decode()
        self.assertEqual(text.splitlines()[1:],[ '[Service]','ExecStart=', 'ExecStart='+' '.join(c.wrapped_argv())])
        self.assertEqual(g.SETTLEMENT_ARGV,('/home/arvis/GoalVisionAI/.venv/bin/python','-P','-m',
             'app.lab_combo','settle','--send','--adaptive-database','/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db'))

    def test_only_daemon_reload_control(self):
        with patch.object(c.subprocess,'run') as run:
            c.Host().reload()
        self.assertEqual(run.call_args.args[0],['/usr/bin/systemctl','daemon-reload'])
        self.assertFalse(any(hasattr(c.Host,name) for name in ('stop','restart','kill','start')))

    def test_vendored_evidence_is_byte_identical_to_stagger_v4(self):
        for name in ('forward_evidence.py','calendar_proof.py'):
            self.assertEqual((ROOT/'vendor'/name).read_bytes(),(ROOT.parent/'prematch-timer-stagger'/name).read_bytes())

    def test_schedule_proof_all_ticks_and_edges(self):
        report=json.loads((ROOT/'evidence/normal-schedule-proof.json').read_bytes())
        self.assertEqual([w['tick_count'] for w in report['windows']],[288,288,282])
        for window in report['windows']:
            self.assertEqual(window['minimum_25_55_seconds'],300)
            self.assertTrue(all(row['seconds_to_discovery']>180 for row in window['ticks']))




class FakeHost:
    def __init__(self, pins):
        self.props={}
        self.calls=[]
        self.reload_error=False
        for unit,entry in pins['units'].items():
            self.props[unit]={**entry['stable'],**entry['properties'],
                              'ActiveState':'inactive','SubState':'dead','NeedDaemonReload':'no'}
            if unit.endswith('.timer'):
                self.props[unit]['TimersCalendar']='{ OnCalendar='+entry['calendar']+' ; next_elapse=n/a }'
        self.props[c.SERVICE]['ExecStart']=self.exec_text(g.SETTLEMENT_ARGV)

    @staticmethod
    def exec_text(argv):
        return '{ path='+argv[0]+' ; argv[]='+' '.join(argv)+' ; ignore_errors=no ; pid=0 ; code=(null) ; status=0/0 }'

    def show(self,unit):
        return copy.deepcopy(self.props[unit])

    def protected(self):
        pass

    def reload(self):
        self.calls.append('daemon-reload')
        if self.reload_error:
            self.reload_error=False
            raise OSError('injected reload failure')
        present=c.route().exists()
        self.props[c.SERVICE]['DropInPaths']=str(c.route()) if present else ''
        self.props[c.SERVICE]['ExecStart']=self.exec_text(c.wrapped_argv() if present else g.SETTLEMENT_ARGV)
        self.props[c.SERVICE]['NeedDaemonReload']='no'


class TransactionTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);units=root/'units';units.mkdir();state=root/'state';state.mkdir()
        pin=c.baseline()
        for unit,entry in pin['units'].items():
            path=units/unit;path.write_text('synthetic unit '+unit)
            entry['files_sha256']={str(path):c.sha(path)}
            entry['properties']['DropInPaths']=''
            entry['stable']['FragmentPath']=str(path)
        pin['environment_files_sha256']={}
        self.pin=pin;self.host=FakeHost(pin)
        for key,value in (('UNIT_ROOT',units),('SEARCH_ROOTS',(units,)),('STATE',state),('RELEASE',root/'release')):
            p=patch.object(c,key,value);p.start();self.addCleanup(p.stop)
        for key,value in (('baseline',lambda:pin),('locked',nullcontext),('require_root_owned',lambda path:None)):
            p=patch.object(c,key,value);p.start();self.addCleanup(p.stop)
        p=patch.object(c.guard,'command',side_effect=lambda argv:json.dumps({'type':'t','data':__import__('time').time_ns()//1000+300000000}))
        p.start();self.addCleanup(p.stop)
        self.digest='a'*64

    def test_install_and_rollback_exact_original_exec(self):
        original=self.host.props[c.SERVICE]['ExecStart']
        before=copy.deepcopy(self.host.props)
        tx=c.change(self.host,'install',self.digest)
        self.assertEqual(tx['phase'],'installed')
        self.assertEqual(c.route().read_bytes(),c.payload())
        self.assertEqual((c.RELEASE/'runtime_guard.py').read_bytes(),(ROOT/'runtime_guard.py').read_bytes())
        self.assertEqual(self.host.calls,['daemon-reload'])
        tx=c.change(self.host,'rollback',self.digest)
        self.assertEqual(tx['phase'],'rolled_back')
        self.assertEqual(self.host.props[c.SERVICE]['ExecStart'],original)
        self.assertEqual(self.host.props,before)
        self.assertFalse(c.route().exists());self.assertFalse(c.RELEASE.exists())
        self.assertEqual(self.host.calls,['daemon-reload','daemon-reload'])
        c.change(self.host,'rollback',self.digest)
        self.assertEqual(len(self.host.calls),2)

    def test_active_settlement_refuses_install_and_rollback(self):
        self.host.props[c.SERVICE]['ActiveState']='activating'
        with self.assertRaisesRegex(ValueError,'NOT_IDLE'):c.change(self.host,'install',self.digest)
        self.assertFalse(c.route().exists());self.assertEqual(self.host.calls,[])
        self.host.props[c.SERVICE]['ActiveState']='inactive'
        c.change(self.host,'install',self.digest)
        self.host.props[c.SERVICE]['ActiveState']='activating'
        with self.assertRaisesRegex(ValueError,'NOT_IDLE'):c.change(self.host,'rollback',self.digest)
        self.assertTrue(c.route().exists())

    def test_unit_hash_drift_refuses(self):
        path=next(iter(self.pin['units'][c.SERVICE]['files_sha256']))
        Path(path).write_text('changed')
        with self.assertRaisesRegex(ValueError,'HASH_DRIFT'):c.inspect(self.host,False)

    def test_environment_and_sandbox_drift_refuse(self):
        for key in ('Environment_sha256','NoNewPrivileges','EnvironmentFiles','WorkingDirectory'):
            original=self.host.props[c.SERVICE][key]
            self.host.props[c.SERVICE][key]='changed'
            with self.assertRaisesRegex(ValueError,'PROPERTY_DRIFT'):c.inspect(self.host,False)
            self.host.props[c.SERVICE][key]=original

    def test_foreign_unloaded_dropin_refuses(self):
        directory=c.UNIT_ROOT/'service.d';directory.mkdir();(directory/'extra.conf').write_text('foreign')
        with self.assertRaisesRegex(ValueError,'UNLOADED_DROPIN'):c.inspect(self.host,False)

    def test_calendar_drift_refuses(self):
        self.host.props[g.TIMER]['TimersCalendar']='{ OnCalendar=wrong ; next_elapse=n/a }'
        with self.assertRaisesRegex(ValueError,'CALENDAR_DRIFT'):c.inspect(self.host,False)

    def test_exec_drift_refuses(self):
        self.host.props[c.SERVICE]['ExecStart']=self.host.exec_text(['/bin/false'])
        with self.assertRaisesRegex(ValueError,'EXECSTART_DRIFT'):c.inspect(self.host,False)

    def test_tampered_guard_rollback_refuses(self):
        c.change(self.host,'install',self.digest)
        (c.RELEASE/'runtime_guard.py').chmod(0o644)
        (c.RELEASE/'runtime_guard.py').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'GUARD_TAMPER'):c.change(self.host,'rollback',self.digest)
        self.assertTrue(c.route().exists())

    def test_tampered_routing_rollback_refuses(self):
        c.change(self.host,'install',self.digest)
        c.route().write_text('foreign')
        with self.assertRaisesRegex(ValueError,'ROUTING_TAMPER'):c.change(self.host,'rollback',self.digest)

    def test_failed_reload_receipt_allows_verified_rollback(self):
        self.host.reload_error=True
        with self.assertRaises(OSError):c.change(self.host,'install',self.digest)
        self.assertEqual(c.transaction()['phase'],'installing')
        self.assertEqual(c.change(self.host,'rollback',self.digest)['phase'],'rolled_back')
        self.assertEqual(c.exec_argv(self.host.props[c.SERVICE]['ExecStart']),' '.join(g.SETTLEMENT_ARGV))

    def test_transaction_package_mismatch_refuses(self):
        c.change(self.host,'install',self.digest)
        with self.assertRaisesRegex(ValueError,'PACKAGE_MISMATCH'):c.change(self.host,'rollback','b'*64)


if __name__ == '__main__':
    unittest.main()
