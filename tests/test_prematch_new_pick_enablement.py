"""Offline re-enablement rehearsals; administration is fake and stores disposable."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest
from test_prematch_reviewed_upgrade import prepared, upgrade
from test_prematch_v2_rollout import rollout
import prematch_enable_history as history


@pytest.fixture
def enabled_package(prepared, monkeypatch):
    r = prepared
    r.upgrade()
    r.upgrade_manifest['proposed']['commit'] = upgrade.ACCEPTED_APPLICATION
    r.upgrade_manifest['previous_protected_stdout'] = True
    r.upgrade_manifest['enablement'] = {'application': upgrade.ACCEPTED_APPLICATION,
                                      'operations': upgrade.ACCEPTED_OPERATIONS}
    r.upgrade_manifest['expected_dropins'] = {s: hashlib.sha256(b).hexdigest() for s,b in r.files().items()}
    r.before = r.files()
    r.calls.clear()
    monkeypatch.setattr(upgrade, 'protected_output', lambda m: None)
    monkeypatch.setattr(upgrade, 'require_history', lambda m: {'blockers': {}})
    return r


def test_exact_only_discovery_send_transition_and_kill_switch(enabled_package):
    r = enabled_package
    r.upgrade('enable-new-picks')
    after = r.files()
    assert upgrade.state(r.upgrade_manifest, after) == (False, True, True, True)
    assert after[r.services[0]] == r.before[r.services[0]].replace(b'controlled-cycle ', b'controlled-cycle --send ')
    assert all(after[s] == r.before[s] for s in r.services[1:])
    assert b'--max-calls 400 --settlement-reserve 100' in after[r.services[0]]
    assert b'StandardOutput=append:' in after[r.services[0]]
    assert r.timer_states == r.original_timers
    assert not upgrade.JOURNAL.exists()
    for _ in range(3):
        r.upgrade('disable-new-picks')
        assert r.files() == r.before
        assert upgrade.state(r.upgrade_manifest, r.files()) == (False, False, True, True)
    # Every start is a prior active timer. No service, application, provider or send command.
    assert all(call[0] in ('systemctl', 'systemd-analyze') for call in r.calls)
    assert all(set(call[2:]).issubset(r.original_timers) for call in r.calls if call[:2] == ('systemctl','start'))


@pytest.mark.parametrize('drift', ['old-release','commit','observe','labels','dropin','base','loaded','expected','journal','stdout','profile'])
def test_enable_drift_rejects_before_any_mutation(enabled_package, monkeypatch, drift):
    r = enabled_package
    if drift in ('old-release','observe','labels'):
        for s in r.services:
            r.module.write_atomic(r.etc/(s+'.d')/r.module.DROPIN, upgrade.render(r.upgrade_manifest,s,
                previous=drift=='old-release', observe=drift!='observe', labels=drift not in ('observe','labels')))
    elif drift == 'commit': r.upgrade_manifest['proposed']['commit'] = 'unaccepted'
    elif drift == 'profile': r.upgrade_manifest.pop('enablement')
    elif drift == 'dropin':
        p=r.etc/(r.services[0]+'.d')/r.module.DROPIN
        p.write_bytes(p.read_bytes().replace(b'400',b'401'))
    elif drift == 'base': (r.etc/r.services[1]).write_text('drift')
    elif drift == 'loaded': r.loaded_dropins[r.services[0]] += ' /unknown.conf'
    elif drift == 'expected': r.upgrade_manifest['expected_dropins'][r.services[0]] = 'wrong'
    elif drift == 'journal': upgrade.save_journal({'unfinished':True})
    elif drift == 'stdout':
        monkeypatch.setattr(upgrade,'protected_output',lambda m: (_ for _ in ()).throw(SystemExit('missing stdout')))
    before=r.files()
    with pytest.raises(SystemExit): r.upgrade('enable-new-picks')
    assert r.files()==before
    assert not any(call[:2] in (('systemctl','stop'),('systemctl','daemon-reload')) for call in r.calls)


@pytest.mark.parametrize('phase', ['preflight','after-drain'])
def test_current_history_rechecked_and_blocks(enabled_package, monkeypatch, phase):
    r=enabled_package
    calls=0
    def check(m):
        nonlocal calls
        calls+=1
        if calls == (1 if phase=='preflight' else 2):
            if phase=='after-drain':
                assert all(p.exists() for p in upgrade.gates().values())
                assert not any(v=='active' for v in r.timer_states.values())
            raise SystemExit('history blocker')
        return {}
    monkeypatch.setattr(upgrade,'require_history',check)
    with pytest.raises(SystemExit,match='history blocker'):r.upgrade('enable-new-picks')
    assert r.files()==r.before
    assert r.timer_states==r.original_timers
    assert not upgrade.JOURNAL.exists()
    if phase=='preflight': assert not any(call[:2]==('systemctl','stop') for call in r.calls)


@pytest.mark.parametrize('action', ['enable-new-picks','disable-new-picks'])
@pytest.mark.parametrize('failure', ['write','verify','reload','timer-restore','gate-cleanup'])
def test_failure_recovers_compact_no_send(enabled_package, monkeypatch, action, failure):
    r=enabled_package
    if action=='disable-new-picks':r.upgrade('enable-new-picks')
    failed=False
    def run(*args):
        nonlocal failed
        should=(failure=='verify' and args[0]=='systemd-analyze'
                or failure=='reload' and args==('systemctl','daemon-reload') and r.files()!=r.before
                or failure=='timer-restore' and args[:2]==('systemctl','start')
                or failure=='gate-cleanup' and args==('systemctl','daemon-reload') and not any(p.exists() for p in upgrade.gates().values()))
        if should and not failed:
            failed=True
            raise RuntimeError('injected')
        return r.run(*args)
    write=r.module.write_atomic
    def broken_write(path,content):
        nonlocal failed
        if failure=='write' and path==r.etc/(r.services[1]+'.d')/r.module.DROPIN and not failed:
            failed=True
            raise RuntimeError('injected')
        write(path,content)
    monkeypatch.setattr(r.module,'run',run)
    monkeypatch.setattr(r.module,'write_atomic',broken_write)
    with pytest.raises(RuntimeError):r.upgrade(action)
    assert failed and r.files()==r.before
    assert r.timer_states==r.original_timers
    assert not upgrade.JOURNAL.exists()


@pytest.mark.parametrize('action', ['enable-new-picks','disable-new-picks'])
def test_failed_recovery_stays_fenced_then_recovers_exact_compact_release(enabled_package,monkeypatch,action):
    r=enabled_package
    if action=='disable-new-picks':r.upgrade('enable-new-picks')
    def broken(*args):
        if args[0]=='systemd-analyze':raise RuntimeError('persistent')
        return r.run(*args)
    monkeypatch.setattr(r.module,'run',broken)
    with pytest.raises(RuntimeError,match='Recovery incomplete'):r.upgrade(action)
    assert upgrade.JOURNAL.exists()
    assert all(p.exists() for p in upgrade.gates().values())
    assert not any(v=='active' for v in r.timer_states.values())
    monkeypatch.setattr(r.module,'run',r.run)
    r.upgrade('recover')
    assert r.files()==r.before
    assert r.timer_states==r.original_timers
    with pytest.raises(SystemExit,match='no release rollback'):r.upgrade('recover')


def test_concurrent_enablement_rejected_at_cli_lock(enabled_package,monkeypatch,tmp_path):
    r=enabled_package
    manifest=tmp_path/'enable.json';manifest.write_text(json.dumps(r.upgrade_manifest))
    monkeypatch.setattr(upgrade.os,'geteuid',lambda:0)
    monkeypatch.setattr(sys,'argv',['installer',str(manifest),'enable-new-picks','--sha256',upgrade.sha(manifest)])
    with r.module.installer_lock():
        with pytest.raises(SystemExit,match='Another PREMATCH'):upgrade.main()
    assert r.files()==r.before
    assert not r.calls


@pytest.fixture
def history_paths(tmp_path):
    paths={key:str(tmp_path/(key+'.db')) for key in ('ledger','adaptive','shadow')}
    with sqlite3.connect(paths['ledger']) as c:
        c.execute('CREATE TABLE evidence (kind TEXT, identity TEXT, document TEXT, PRIMARY KEY(kind,identity))')
    with sqlite3.connect(paths['adaptive']) as c:
        c.execute('CREATE TABLE weekly_delivery_unknown (stream TEXT)')
        c.execute('CREATE TABLE weekly_claims (id TEXT, stream TEXT)')
        c.execute('CREATE TABLE weekly_receipts (claim_id TEXT, stream TEXT)')
    with sqlite3.connect(paths['shadow']) as c:
        c.execute('CREATE TABLE lab_v2_shadow_evidence (kind TEXT,identity TEXT,created_at_utc TEXT,document_json TEXT)')
    paths['stdout']=str(tmp_path/'stdout')
    Path(paths['stdout']).write_text(json.dumps({'schema_version':'goalvision-lab-v2-operator-cycle-v1'})+'\n')
    return paths


@pytest.mark.parametrize('kind,key', [
    ('claim','unreceipted_publication_claims'),('delivery_unknown','delivery_unknown'),
    ('economic_claim','economic_claims_without_receipts'),('receipt','pending_settlement_integrity_blockers'),
    ('invalid','invalid_receipts'),('weekly_unknown','weekly_delivery_unknown'),
    ('weekly_claim','weekly_unreceipted_claims'),('ack','acknowledged_unpersisted_delivery_evidence'),
    ('stdout_ack','acknowledged_unpersisted_delivery_evidence'),('unknown_cycle','unresolved_delivery_evidence'),
])
def test_history_blockers_fail_closed_and_do_not_change_database(history_paths,kind,key):
    paths=history_paths
    assert not any(history.inventory(paths)['blockers'].values())
    if kind.startswith('weekly'):
        with sqlite3.connect(paths['adaptive']) as c:
            if kind=='weekly_unknown':c.execute("INSERT INTO weekly_delivery_unknown VALUES ('PREMATCH')")
            else:c.execute("INSERT INTO weekly_claims VALUES ('q','PREMATCH')")
    elif kind in ('ack','stdout_ack','unknown_cycle'):
        value={'acknowledgement_received':True,'receipt_persisted':False} if kind!='unknown_cycle' else {'delivery_status':'UNKNOWN'}
        if kind=='stdout_ack':
            value['schema_version']='goalvision-lab-v2-operator-cycle-v1'
            Path(paths['stdout']).write_text(json.dumps(value)+'\n')
        else:
            with sqlite3.connect(paths['shadow']) as c:
                c.execute("INSERT INTO lab_v2_shadow_evidence VALUES ('publication_cycle','c','2026',?)",(json.dumps(value),))
    else:
        with sqlite3.connect(paths['ledger']) as c:
            c.execute('INSERT INTO evidence VALUES (?,?,?)',('receipt' if kind=='invalid' else kind,'single_prediction:p',
                      json.dumps({'status':'SENT','sent':True,'message_id':1} if kind=='receipt' else {})))
    before={k:Path(p).read_bytes() for k,p in paths.items()}
    assert history.inventory(paths)['blockers'][key]>0
    with pytest.raises(SystemExit,match='history blocks'):upgrade.require_history({'history_paths':paths})
    assert before=={k:Path(p).read_bytes() for k,p in paths.items()}


@pytest.mark.parametrize('failure',['missing','malformed','partial','large','old-schema','sql'])
def test_unreadable_or_unbounded_history_is_not_clearance(history_paths,monkeypatch,failure):
    paths=history_paths
    if failure=='missing':Path(paths['ledger']).unlink()
    elif failure=='malformed':Path(paths['stdout']).write_text('not-json\n')
    elif failure=='partial':Path(paths['stdout']).write_text('{}')
    elif failure=='old-schema':Path(paths['stdout']).write_text('{}\n')
    elif failure=='large':monkeypatch.setattr(history,'MAX_BYTES',8)
    else:
        with sqlite3.connect(paths['ledger']) as c:c.execute('DROP TABLE evidence')
    with pytest.raises((ValueError,sqlite3.Error)):history.inventory(paths)


def test_disable_does_not_require_clean_delivery_history(enabled_package,monkeypatch):
    r=enabled_package
    r.upgrade('enable-new-picks')
    monkeypatch.setattr(upgrade,'require_history',lambda m: (_ for _ in ()).throw(AssertionError('kill switch must not check history')))
    r.upgrade('disable-new-picks')
    assert r.files()==r.before


def test_sql_deadline_fails_closed(history_paths,monkeypatch):
    with sqlite3.connect(history_paths['ledger']) as c:
        c.executemany('INSERT INTO evidence VALUES (?,?,?)', [('claim',str(i),'{}') for i in range(2000)])
    monkeypatch.setattr(history,'DEADLINE_SECONDS',-1)
    with pytest.raises(sqlite3.OperationalError,match='interrupted'):history.inventory(history_paths)


@pytest.mark.parametrize('drift',['missing','symlink','permissions','rotation','none'])
def test_protected_output_is_read_only_and_fail_closed(tmp_path,monkeypatch,drift):
    import os
    logdir=tmp_path/'logs'; logdir.mkdir(mode=0o750)
    log=logdir/'discovery-output.log';log.write_text('evidence');log.chmod(0o640)
    rotation=tmp_path/'rotation';rotation.write_text('reviewed');rotation.chmod(0o644)
    source=tmp_path/'source';source.write_text('reviewed')
    monkeypatch.setattr(upgrade,'LOG_DIR',logdir)
    monkeypatch.setattr(upgrade,'LOG',log)
    monkeypatch.setattr(upgrade,'ROTATION',rotation)
    original_stat=Path.stat
    def file_stat(path,**kwargs):
        result=original_stat(path,**kwargs)
        if path in (logdir,log,rotation):
            fields=list(result);fields[4]=0;fields[5]=0 if path==rotation else upgrade.pwd.getpwnam('arvis').pw_gid
            return os.stat_result(fields)
        return result
    monkeypatch.setattr(Path,'stat',file_stat)
    if drift=='missing':log.unlink()
    elif drift=='symlink':log.unlink();log.symlink_to(source)
    elif drift=='permissions':log.chmod(0o666)
    elif drift=='rotation':rotation.write_text('changed')
    if drift=='none':upgrade.protected_output({'rotation_source':str(source)})
    else:
        with pytest.raises(SystemExit):upgrade.protected_output({'rotation_source':str(source)})
    assert source.read_text()=='reviewed'
    if drift=='missing':assert not log.exists()
