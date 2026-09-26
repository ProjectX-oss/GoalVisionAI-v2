"""Focused upgrade rehearsals: disposable paths and fake system administration."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from test_prematch_v2_rollout import rollout

SOURCE = Path(__file__).resolve().parents[1] / 'docs/operations/upgrade_prematch_reviewed.py'
sys.path.insert(0, str(SOURCE.parent))
import upgrade_prematch_reviewed as upgrade


@pytest.fixture(params=[False, True], ids=['initial-upgrade', 'protected-output-upgrade'])
def prepared(rollout, monkeypatch, tmp_path, request):
    r = rollout
    r.invoke()
    r.invoke('disable-new-picks')
    monkeypatch.setattr(upgrade, 'base', r.module)
    monkeypatch.setattr(upgrade.os, 'geteuid', lambda: tmp_path.stat().st_uid)
    monkeypatch.setattr(upgrade, 'JOURNAL', tmp_path / 'recovery/transaction.json')
    monkeypatch.setattr(upgrade, 'LOG_DIR', tmp_path / 'logs')
    monkeypatch.setattr(upgrade, 'LOG', tmp_path / 'logs/discovery-output.log')
    monkeypatch.setattr(upgrade, 'ROTATION', tmp_path / 'rotation.conf')
    # Host/release fingerprints are exercised through the common validator and
    # separate payload/drift tests. No actual administrator command may run.
    monkeypatch.setattr(upgrade, 'validate', lambda m: None)
    monkeypatch.setattr(upgrade, 'output_setup', lambda m: (upgrade.LOG.parent.mkdir(exist_ok=True), upgrade.LOG.touch(), upgrade.ROTATION.touch()))
    previous = copy.deepcopy(r.value)
    proposed = copy.deepcopy(previous)
    proposed['release_environment_file'] = str(tmp_path / 'upgraded.env')
    proposed['release'] = str(tmp_path / 'upgraded-release')
    proposed['commit'] = 'accepted-commit'
    r.upgrade_manifest = {'previous':previous,'proposed':proposed,'effective_static':{},
                          'expected_dropins':{s:hashlib.sha256(b).hexdigest() for s,b in r.files().items()}}
    r.upgrade_manifest['previous_protected_stdout'] = request.param
    if request.param:
        for service in r.services:
            r.module.write_atomic(r.etc/(service+'.d')/r.module.DROPIN,
                                  upgrade.render(r.upgrade_manifest, service, previous=True))
        r.upgrade_manifest['expected_dropins'] = {s: hashlib.sha256(b).hexdigest() for s,b in r.files().items()}
    r.before = r.files()
    r.calls.clear()
    r.upgrade = lambda action='upgrade': upgrade.operate(r.upgrade_manifest,action,'reviewed-sha')
    return r


def test_upgrade_and_monotonic_controls_and_compatible_recovery(prepared):
    r=prepared
    r.upgrade()
    after=r.files()
    assert all(after[s] == upgrade.render(r.upgrade_manifest,s) for s in r.services)
    assert '--send' not in after[r.services[0]].decode()
    assert 'StandardOutput=append:' in after[r.services[0]].decode()
    for action in ('disable-new-picks','disable-data-labels','disable-new-picks','disable-data-labels'):
        r.upgrade(action)
        assert '--send' not in r.files()[r.services[0]].decode()
    r.upgrade('recover')
    assert all(r.files()[s] == upgrade.render(r.upgrade_manifest,s,previous=True,observe=False,labels=False) for s in r.services)
    assert r.timer_states == r.original_timers
    if r.upgrade_manifest['previous_protected_stdout']:
        assert 'StandardOutput=append:' in r.files()[r.services[0]].decode()
    assert not upgrade.JOURNAL.exists()
    assert not any(call[:2] in (('systemctl','restart'),('systemctl','enable')) for call in r.calls)


@pytest.mark.parametrize('observe,labels', [(False,False),(True,False),(True,True)])
def test_preserves_each_already_disabled_capability(prepared,observe,labels):
    r=prepared
    for s in r.services:
        r.module.write_atomic(r.etc/(s+'.d')/r.module.DROPIN,upgrade.render(r.upgrade_manifest,s,previous=True,observe=observe,labels=labels))
    r.upgrade_manifest['expected_dropins']={s:hashlib.sha256(b).hexdigest() for s,b in r.files().items()}
    r.upgrade()
    assert upgrade.state(r.upgrade_manifest,r.files()) == (False,observe,labels)


@pytest.mark.parametrize('drift', ['dropin','base','loaded','timer','expected'])
def test_drift_rejected_before_timer_pause(prepared, drift):
    r=prepared
    if drift=='dropin':
        with (r.etc/(r.services[0]+'.d')/r.module.DROPIN).open('ab') as f: f.write(b'\nExecStart=/unknown --send\n')
    elif drift=='base':
        (r.etc/r.services[1]).write_text('unknown operational fix')
    elif drift=='loaded':
        r.loaded_dropins[r.services[0]] += ' /unexpected.conf'
    elif drift=='timer':
        r.timer_states[next(iter(r.timer_states))]='activating'
    else:
        r.upgrade_manifest['expected_dropins'][r.services[0]]='wrong'
    with pytest.raises(SystemExit): r.upgrade()
    assert not any(call[:2]==('systemctl','stop') for call in r.calls)


def test_concurrent_package_rejected(prepared):
    r=prepared
    with r.module.installer_lock():
        with pytest.raises(SystemExit,match='Another PREMATCH'):
            with r.module.installer_lock(): r.upgrade()
    assert r.files()==r.before


def test_drains_before_switch_and_gates_all_compatible_services(prepared,monkeypatch):
    r=prepared
    calls=0
    def idle(services):
        nonlocal calls
        calls+=1
        if calls<4:
            assert r.files()==r.before
            assert all(p.exists() for p in upgrade.gates().values())
            return False
        return True
    monkeypatch.setattr(r.module,'idle',idle)
    r.upgrade()
    assert calls>=4
    assert r.timer_states==r.original_timers


@pytest.mark.parametrize('failure', ['write','verify','reload','timer_restore','gate_cleanup'])
def test_failure_restores_exact_prior_compatible_configuration(prepared,monkeypatch,failure):
    r=prepared
    failed=False
    def run(*args):
        nonlocal failed
        switched=r.files()!=r.before
        should=(failure=='verify' and args[0]=='systemd-analyze') or (failure=='reload' and switched and args==('systemctl','daemon-reload')) or (failure=='timer_restore' and args[:2]==('systemctl','start')) or (failure=='gate_cleanup' and switched and args==('systemctl','daemon-reload') and not any(p.exists() for p in upgrade.gates().values()))
        if should and not failed:
            failed=True
            raise RuntimeError('injected admin failure')
        return r.run(*args)
    monkeypatch.setattr(r.module,'run',run)
    write=r.module.write_atomic
    def broken_write(path,content):
        nonlocal failed
        if failure=='write' and path == r.etc/(r.services[1]+'.d')/r.module.DROPIN and not failed:
            failed=True
            raise RuntimeError('injected write failure')
        write(path,content)
    monkeypatch.setattr(r.module,'write_atomic',broken_write)
    with pytest.raises(RuntimeError): r.upgrade()
    assert failed and r.files()==r.before
    assert r.timer_states==r.original_timers
    assert not any(p.exists() for p in upgrade.gates().values())
    assert not upgrade.JOURNAL.exists()


def test_failed_recovery_keeps_fence_and_explicit_recover_finishes(prepared,monkeypatch):
    r=prepared
    def run(*args):
        if args[0]=='systemd-analyze': raise RuntimeError('persistent verify failure')
        return r.run(*args)
    monkeypatch.setattr(r.module,'run',run)
    with pytest.raises(RuntimeError,match='Recovery incomplete'): r.upgrade()
    assert upgrade.JOURNAL.exists()
    assert all(p.exists() for p in upgrade.gates().values())
    assert all(v != 'active' for v in r.timer_states.values())
    monkeypatch.setattr(r.module,'run',r.run)
    r.upgrade('recover')
    assert r.files()==r.before
    assert r.timer_states==r.original_timers


def test_interrupted_partial_switch_recovered_without_deleting_dropins(prepared):
    r=prepared
    desired={s:upgrade.render(r.upgrade_manifest,s) for s in r.services}
    upgrade.save_journal({'manifest_sha256':'reviewed-sha','active_timers':[t for t,v in r.timer_states.items() if v=='active'],
                          'before':{s:b.decode() for s,b in r.before.items()},'after':{s:b.decode() for s,b in desired.items()}})
    upgrade.write_gates()
    r.module.write_atomic(r.etc/(r.services[0]+'.d')/r.module.DROPIN,desired[r.services[0]])
    r.upgrade('recover')
    assert r.files()==r.before


def test_payload_fingerprint_rejects_mutation(tmp_path):
    p=tmp_path/'payload';p.write_bytes(b'original')
    hashes={str(p):upgrade.sha(p)}
    upgrade.check_files(hashes)
    p.write_bytes(b'drift')
    with pytest.raises(SystemExit,match='drift'):upgrade.check_files(hashes)


def test_protected_append_preserves_complete_application_failure_and_exit(tmp_path):
    """Exercise accepted failure formatter, full stdout retention, real process status."""
    from app.lab_combo.service import DeliveryFacts,DeliveryFailure
    from app.lab_v2_shadow.cli import _persist_cycle_evidence
    from datetime import datetime,timezone
    class BrokenStore:
        def append(self,*args,**kwargs): raise OSError('SECRET_MUST_NOT_APPEAR')
    facts=DeliveryFacts(kind='single_prediction',prediction_id='lab-v2-single-'+'a'*64,
                        acknowledgement_received=True,acknowledgement={'message_id':123,'chat_id':-1003510920417},
                        receipt_persisted=False,reconciliation_required=True,persistence_failure='RECEIPT')
    report={'analysis_status':'COMPLETED','delivery_status':'FAILED','analysis_mode':'test','mode':'test',
            'publication_requested':True,'publication_enabled':True,'telegram_transport_constructed':True,
            'publication_attempt_count':1,'telegram_sends':0,'controlled_publication':{'failure':DeliveryFailure(facts).outcome}}
    output=_persist_cycle_evidence(BrokenStore(),report,datetime.now(timezone.utc))
    log=tmp_path/'output.log'
    log.touch(mode=0o640)
    with log.open('ab') as sink:
        done=subprocess.run([sys.executable,'-c','import sys; print(sys.argv[1]); raise SystemExit(7)',json.dumps(output)],stdout=sink,check=False)
    assert done.returncode==7
    read=json.loads(log.read_text())
    assert read['controlled_publication']['failure']['prediction_id']==facts.prediction_id
    assert read['controlled_publication']['failure']['acknowledgement']==facts.acknowledgement
    assert read['controlled_publication']['failure']['reconciliation_required'] is True
    assert read['publication_cycle_persistence']['persisted'] is False
    assert 'SECRET_MUST_NOT_APPEAR' not in log.read_text()
    assert log.stat().st_mode & 0o777 == 0o640


def test_manifest_validation_preserves_operational_arguments(tmp_path,monkeypatch):
    config={'release':str(tmp_path),'commit':'accepted','application_tree':'app-tree',
            'release_environment_file':str(tmp_path/'release.env'),'services':list(upgrade.base.SERVICES),
            'discovery_service':upgrade.base.SERVICES[0],'discovery_command':['/python','-P','-m','app.lab_v2_shadow','controlled-cycle','--send','--max-calls','400','--settlement-reserve','100'],
            'observation_arguments':['--football-context-root','/context','--football-context-registry','/context/registry.sqlite'],
            'ledger':'/ledger','regression_status':'PASSED'}
    Path(config['release_environment_file']).write_text('PYTHONPATH='+str(tmp_path)+'\n')
    config['release_environment_sha256']=upgrade.sha(Path(config['release_environment_file']))
    def run(*args):
        if args[0]=='git':
            return 'accepted' if args[-1]=='HEAD' else 'app-tree' if args[-1]=='HEAD:app' else ''
        return 'active'
    monkeypatch.setattr(upgrade.base,'run',run)
    m={'previous':config,'proposed':copy.deepcopy(config),'payload_sha256':{},'host_fingerprints':{},'host_metadata':{}}
    upgrade.validate(m)
    m['proposed']['discovery_command'][-1]='101'
    with pytest.raises(SystemExit,match='Operational arguments'):upgrade.validate(m)


def test_no_unloaded_dropin_can_be_activated_by_upgrade(tmp_path,monkeypatch):
    # Test directory inventory independently of host fingerprint validation.
    directory=tmp_path/'service.d';directory.mkdir()
    p=directory/'unreviewed.conf';p.write_text('ExecStart=/unknown --send')
    source=SOURCE.read_text()
    assert "Unloaded configuration drift" in source
    # Actual directory validation is exercised in a complete minimal manifest.
    config={'release':str(tmp_path),'commit':'accepted','application_tree':'tree','release_environment_file':str(tmp_path/'release.env')}
    Path(config['release_environment_file']).write_text('PYTHONPATH='+str(tmp_path)+'\n')
    config['release_environment_sha256']=upgrade.sha(Path(config['release_environment_file']))
    monkeypatch.setattr(upgrade.base,'validate_manifest',lambda m:None)
    monkeypatch.setattr(upgrade.base,'run',lambda *args:'accepted' if args[-1]=='HEAD' else 'tree' if args[-1]=='HEAD:app' else '')
    m={'previous':config,'proposed':config,'payload_sha256':{},'host_fingerprints':{},'host_metadata':{},'configuration_directories':{str(directory):[]}}
    with pytest.raises(SystemExit,match='Unloaded configuration drift'):upgrade.validate(m)


def test_output_setup_permission_and_drift_checks(tmp_path,monkeypatch):
    """Administrator calls stay fake; inspect protected modes and rotation bytes."""
    import os
    logdir=tmp_path/'logs'; log=logdir/'discovery-output.log'; rotation=tmp_path/'rotation.conf'
    source=tmp_path/'reviewed-rotation';source.write_text('/synthetic/output {\n daily\n rotate 14\n}\n')
    monkeypatch.setattr(upgrade,'LOG_DIR',logdir)
    monkeypatch.setattr(upgrade,'LOG',log)
    monkeypatch.setattr(upgrade,'ROTATION',rotation)
    # Cannot perform privileged chown. Map the expected uid to root only when
    # inspecting our disposable output paths, and record every fake chown.
    original_stat=Path.stat
    changes=[]
    monkeypatch.setattr(upgrade.os,'chown',lambda path,uid,gid:changes.append((path,uid,gid)))
    def file_stat(path,**kwargs):
        value=original_stat(path,**kwargs)
        if path in (logdir,log,rotation):
            fields=list(value);fields[4]=0;fields[5]=upgrade.pwd.getpwnam('arvis').pw_gid
            return os.stat_result(fields)
        return value
    monkeypatch.setattr(Path,'stat',file_stat)
    admin=[]
    monkeypatch.setattr(upgrade.base,'run',lambda *args:admin.append(args))
    upgrade.output_setup({'rotation_source':str(source)})
    assert (original_stat(logdir).st_mode & 0o777)==0o750
    assert (original_stat(log).st_mode & 0o777)==0o640
    assert len(changes)==2 and all(item[1]==0 for item in changes)
    assert admin==[('/usr/sbin/logrotate','--debug',str(rotation))]
    log.chmod(0o666)
    with pytest.raises(SystemExit,match='permissions'):upgrade.output_setup({'rotation_source':str(source)})


def test_stdout_record_larger_than_rotation_threshold_is_not_truncated(tmp_path):
    # append: is a direct descriptor, with no tee/logger pipe or line-size limit.
    long_id='prediction-'+'x'*(8*1024*1024)
    value={'prediction_id':long_id,'acknowledgement':{'message_id':123},'receipt_persisted':False,'reconciliation_required':True}
    p=tmp_path/'output';p.touch(mode=0o640)
    with p.open('a') as out: print(json.dumps(value),file=out)
    assert json.loads(p.read_text())==value
    assert p.stat().st_size>8*1024*1024


def test_timer_pause_failure_restores_without_switch(prepared,monkeypatch):
    r=prepared
    failed=False
    def run(*args):
        nonlocal failed
        if args[:2]==('systemctl','stop') and not failed:
            failed=True
            raise RuntimeError('cannot stop timers')
        return r.run(*args)
    monkeypatch.setattr(r.module,'run',run)
    with pytest.raises(RuntimeError):r.upgrade()
    assert r.files()==r.before
    assert r.timer_states==r.original_timers


def test_drain_timeout_keeps_compatible_files_and_recoverable_gate(prepared,monkeypatch):
    r=prepared
    monkeypatch.setattr(upgrade,'drain',lambda: (_ for _ in ()).throw(RuntimeError('drain timed out')))
    with pytest.raises(RuntimeError,match='Recovery incomplete'):r.upgrade()
    assert r.files()==r.before
    assert upgrade.JOURNAL.exists()
    assert all(p.exists() for p in upgrade.gates().values())


def test_effective_command_drift_after_reload_is_rejected(prepared,monkeypatch):
    r=prepared
    monkeypatch.setattr(r.module,'validate_configuration',lambda *a,**k:None)
    r.upgrade_manifest['effective_commands']={s:'/unchanged/python -m example' for s in r.services}
    r.upgrade_manifest['previous_stdout']={s:'null' for s in r.services}
    def run(*args):
        if args[4]=='EnvironmentFiles':return r.value['release_environment_file']+' (ignore_errors=no)'
        if args[4]=='ExecStart':return '{ path=/bad/python ; argv[]=/bad/python --send ; ignore_errors=no ; }'
        return r.run(*args)
    monkeypatch.setattr(r.module,'run',run)
    with pytest.raises(SystemExit,match='Effective command drift'):upgrade.configuration(r.upgrade_manifest,r.files())
