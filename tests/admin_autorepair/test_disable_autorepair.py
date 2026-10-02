"""Synthetic disconnection only: never call systemd or open production files."""
import importlib.util
import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = Path(__file__).parents[2]/'operations/admin-autorepair/disable_autorepair.py'
    spec = importlib.util.spec_from_file_location('disable_autorepair', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = tmp_path/'admin-alerts.json'
    original = {'autorepair': {'enabled':True,'spool':'keep'}, 'sender':{'enabled':True,'token':'PRIVATE'},
                'stdout':'keep','health_database':'keep'}
    config.write_text(json.dumps(original))
    config.chmod(0o640)
    marker = tmp_path/'DISABLED'
    lock = tmp_path/'scan.lock'; lock.touch()
    monkeypatch.setattr(module,'CONFIG',config)
    monkeypatch.setattr(module,'MARKER',marker)
    monkeypatch.setattr(module,'SCAN_LOCK',lock)
    monkeypatch.setattr(module.os,'fchown',lambda *a:None)
    states={module.TIMER:'active',module.WORKER:'inactive',module.MONITOR_TIMER:'active'}
    calls=[]
    def control(*args):
        calls.append(args)
        if args[0]=='show':
            unit,key=args[1],args[3]
            if key=='ActiveState': return states[unit]
            if key=='UnitFileState': return 'disabled' if states[unit]=='inactive' else 'enabled'
            if key=='MainPID': return '0'
        if args[:2]==('disable','--now'):
            assert args[2]==module.TIMER
            states[module.TIMER]='inactive'
        elif args[0]=='stop':
            assert args[1]==module.WORKER
            states[module.WORKER]='inactive'
        return ''
    monkeypatch.setattr(module,'control',control)
    return module,original,calls


def test_disconnect_is_idempotent_and_preserves_monitor_credentials_history(setup,tmp_path):
    m, original, calls=setup
    history=tmp_path/'old-job.json'; history.write_text('preserve failed job')
    result=m.disable()
    assert result['autorepair_enabled'] is False
    assert result['worker_timer']=='inactive' and result['worker_service']=='inactive'
    assert result['monitor_timer_unchanged']
    expected={**original,'autorepair':{**original['autorepair'],'enabled':False}}
    assert json.loads(m.CONFIG.read_text())==expected
    assert m.CONFIG.stat().st_mode & 0o777 == 0o640
    backups=list(tmp_path.glob('admin-alerts.before-autorepair-off-*.json'))
    assert len(backups)==1 and json.loads(backups[0].read_text())==original
    assert backups[0].stat().st_mode & 0o777==0o600
    assert 'PRIVATE' not in json.dumps(result)
    assert m.disable()==result
    assert len(list(tmp_path.glob('admin-alerts.before-autorepair-off-*.json')))==1
    assert history.read_text()=='preserve failed job'
    assert not any(c[0] in ('start','restart','mask','enable') for c in calls)


def test_bad_config_still_leaves_worker_stopped(setup):
    m, _, calls=setup
    m.CONFIG.write_text('bad json')
    with pytest.raises(ValueError): m.disable()
    assert m.MARKER.exists()
    assert ('disable','--now',m.TIMER) in calls
    assert ('stop',m.WORKER) in calls
    assert m.CONFIG.read_text()=='bad json'


def test_marker_symlink_refused(setup,tmp_path):
    m, _, calls=setup
    target=tmp_path/'protected'; target.write_text('preserve')
    m.MARKER.symlink_to(target)
    with pytest.raises(ValueError,match='SYMLINK'): m.disable()
    assert target.read_text()=='preserve'


def test_configuration_symlink_not_followed(setup,tmp_path):
    m, _, calls=setup
    target=tmp_path/'protected'
    m.CONFIG.rename(target)
    m.CONFIG.symlink_to(target)
    before=target.read_bytes()
    with pytest.raises(ValueError,match='SYMLINK_CONFIGURATION'): m.disable()
    assert target.read_bytes()==before and m.MARKER.exists()


def test_default_preview_has_no_controls(setup, monkeypatch, capsys):
    m, _, calls=setup
    monkeypatch.setattr('sys.argv',['disable-autorepair'])
    m.main()
    assert capsys.readouterr().out.startswith('PLAN=')
    assert not calls and not m.MARKER.exists()
