"""Offline operator-package tests: no system service or transport calls."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

@pytest.fixture
def rig(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1]/'operations/dixon-coles-forward/repair_evaluation.py'
    spec = importlib.util.spec_from_file_location('dc_verification_repair', source)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    for key, name in [('BASE','base'),('TARGET','target'),('SYSTEM','system'),('JOURNALS','journals')]:
        monkeypatch.setattr(m,key,tmp_path/name)
    patch=m.BASE/'application'/m.PATCH; patch.parent.mkdir(parents=True);patch.write_text('old')
    monkeypatch.setattr(m,'PATCH_BASE_SHA',m.h.sha(patch))
    m.SYSTEM.mkdir();(m.SYSTEM/m.SERVICE).write_text('original unit')
    package=tmp_path/'package';package.mkdir()
    for name in ('repair_evaluation.py','update.py','service.py'):
        (package/name).write_text('new' if name=='service.py' else name)
    base_routes={u:{'WorkingDirectory':str(m.BASE/'application'),'DropInPaths':''} for u in m.UNITS}
    enabled_routes=json.loads(json.dumps(base_routes))
    enabled_routes[m.SERVICE].update(WorkingDirectory=str(m.TARGET/'application'),DropInPaths=str(m.override()))
    state={'active':'active','pid':'0','service':'inactive','reload':False,'fail_reload':False}
    calls=[]
    def control(*args):
        calls.append(args)
        if args==('stop',m.TIMER):state['active']='inactive'
        elif args==('start',m.TIMER):state['active']='active'
        elif args==('daemon-reload',):
            if state['fail_reload']:raise RuntimeError('reload failed')
            state['reload']=True
        else:raise AssertionError(args)
        return ''
    def prop(unit,key):
        return {(m.TIMER,'ActiveState'):state['active'],(m.TIMER,'UnitFileState'):'enabled',
                (m.SERVICE,'MainPID'):state['pid'],(m.SERVICE,'ActiveState'):state['service'],
                (m.SERVICE,'Environment'):'PYTHONDONTWRITEBYTECODE=1'}[(unit,key)]
    monkeypatch.setattr(m.h,'control',control);monkeypatch.setattr(m.h,'prop',prop)
    monkeypatch.setattr(m.h,'disabled_admin',lambda:None)
    monkeypatch.setattr(m,'routes',lambda:enabled_routes if state['reload'] else base_routes)
    meta={'base':str(m.BASE),'target':str(m.TARGET),'patch':m.PATCH,
          'base_manifest':m.manifest(m.BASE/'application'),
          'patch_sha256':m.h.sha(package/'service.py'),
          'package_files':{n:m.h.sha(package/n) for n in ('repair_evaluation.py','update.py','service.py')},
          'configuration_files':m.configs(),'routes':base_routes,
          'forward_environment':'PYTHONDONTWRITEBYTECODE=1','timer_unit_file_state':'enabled'}
    def save():(package/'metadata.json').write_text(json.dumps(meta))
    save()
    return SimpleNamespace(m=m,package=package,meta=meta,state=state,calls=calls,save=save)

def test_readonly_preflight_does_not_stage_or_control(rig):
    r=rig;r.m.main(['--package',str(r.package)])
    assert r.calls==[] and not r.m.TARGET.exists() and not r.m.JOURNALS.exists()

@pytest.mark.parametrize('active',['active','inactive'])
def test_stage_and_route_preserve_timer_and_protected_files(rig,active):
    r=rig;r.state['active']=active
    before=r.m.manifest(r.m.BASE/'application')
    r.m.stage(r.package,r.meta);r.m.route(r.meta)
    assert r.m.validate(r.package)[1]=='ENABLED'
    assert r.m.manifest(r.m.BASE/'application')==before
    assert r.state['active']==active
    assert all(c in [('stop',r.m.TIMER),('start',r.m.TIMER),('daemon-reload',)] for c in r.calls)
    assert (r.m.TARGET/'application'/r.m.PATCH).read_text()=='new'
    assert (r.m.TARGET/'application'/r.m.PATCH).stat().st_mode & 0o222==0
    r.m.stage(r.package,r.meta) # idempotent exact successor

@pytest.mark.parametrize('drift',['package','base','scope','set','patch_hash','configuration','environment','enablement','symlink'])
def test_preflight_refuses_drift(rig,drift,monkeypatch):
    r=rig
    if drift=='package':(r.package/'service.py').write_text('bad')
    elif drift=='base':(r.m.BASE/'application'/r.m.PATCH).write_text('bad')
    elif drift=='scope':r.meta['target']='/unexpected';r.save()
    elif drift=='set':r.meta['package_files'].pop('update.py');r.save()
    elif drift=='patch_hash':r.meta['patch_sha256']='bad';r.save()
    elif drift=='configuration':(r.m.SYSTEM/r.m.SERVICE).write_text('changed')
    elif drift=='environment':r.meta['forward_environment']='PYTHONPATH=/other';r.save()
    elif drift=='enablement':r.meta['timer_unit_file_state']='disabled';r.save()
    elif drift=='symlink':
        p=r.package/'service.py';p.unlink();p.symlink_to(r.package/'update.py')
    with pytest.raises(ValueError):r.m.validate(r.package)
    assert r.calls==[] and not r.m.TARGET.exists()

def test_running_service_is_never_killed_on_drain_timeout(rig,monkeypatch):
    r=rig;r.state['pid']='123';r.state['service']='activating'
    clock=iter([0,76]);monkeypatch.setattr(r.m.time,'monotonic',lambda:next(clock))
    with pytest.raises(RuntimeError,match='NATURAL_DRAIN_TIMEOUT'):r.m.route(r.meta)
    assert r.calls==[('stop',r.m.TIMER),('start',r.m.TIMER)]
    assert not r.m.override().exists()

def test_partial_install_stops_timer_without_rollback(rig):
    r=rig;r.state['fail_reload']=True;r.m.stage(r.package,r.meta)
    with pytest.raises(RuntimeError,match='PARTIAL_INSTALL_NO_AUTOMATIC_ROLLBACK'):r.m.route(r.meta)
    assert r.m.override().exists() and r.state['active']=='inactive'
    assert ('start',r.m.TIMER) not in r.calls
    journal=json.loads(next(r.m.JOURNALS.glob('*.json')).read_text())
    assert journal['status']=='OPERATOR_REVIEW_REQUIRED' and not journal['automatic_rollback']

def test_existing_target_tamper_refused(rig):
    r=rig;r.m.stage(r.package,r.meta)
    p=r.m.TARGET/'application'/r.m.PATCH;p.chmod(0o644);p.write_text('bad')
    with pytest.raises(ValueError,match='EXISTING_TARGET_DRIFT'):r.m.stage(r.package,r.meta)

def test_apply_requires_operator_root(rig,monkeypatch):
    r=rig;monkeypatch.setattr(r.m.os,'geteuid',lambda:1000)
    with pytest.raises(PermissionError,match='OPERATOR_SUDO_REQUIRED'):
        r.m.main(['--package',str(r.package),'--apply'])
    assert not r.calls
