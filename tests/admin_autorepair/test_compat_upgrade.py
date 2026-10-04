"""Synthetic ADMIN release routing; never call systemd, runuser or Codex."""
import importlib.util
import json
from pathlib import Path

import pytest


def exec_property(argv='/bin/python -m protected', *, live=False, ignore_errors='no'):
    stamp = 'Fri 2026-10-02 06:55:01 CEST' if live else 'n/a'
    return ('{ path='+argv.split()[0]+' ; argv[]='+argv+' ; ignore_errors='+ignore_errors+
            ' ; start_time=['+stamp+'] ; stop_time=['+stamp+'] ; pid='+('123' if live else '0')+
            ' ; code='+('exited' if live else '(null)')+' ; status='+('0' if live else '0/0')+' }')


@pytest.fixture
def installation(tmp_path, monkeypatch):
    source = Path(__file__).parents[2]/'operations/admin-autorepair/update_compat.py'
    spec = importlib.util.spec_from_file_location('admin_io_update', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    specs = {}
    package = tmp_path/'package'
    package.mkdir()
    (package/'update.py').write_bytes(source.read_bytes())
    for name, original in module.SPECS.items():
        base = tmp_path/name/'base'
        for name_module in original['modules']:
            module_path = base/name_module
            module_path.parent.mkdir(parents=True, exist_ok=True)
            module_path.write_text('old = True\n')
        (base/'run.py').write_text('pass\n')
        (base/'manifest.json').write_text(json.dumps(module.tree(base)))
        for name_module in original['modules']:
            overlay = package/'overlay'/name/name_module
            overlay.parent.mkdir(parents=True, exist_ok=True)
            overlay.write_text('new = True\n')
        specs[name] = dict(original, base=base, route_base=base,
                           override=tmp_path/'units'/name/'override.conf')
    monkeypatch.setattr(module, 'SPECS', specs)
    meta = {'source_commit':'a'*40, 'base_manifests':{n:module.tree(s['base']) for n,s in specs.items()},
            'files':{n:{p:module.sha(package/'overlay'/n/p) for p in s['modules']} for n,s in specs.items()},
            'updater_sha256':module.sha(package/'update.py')}
    (package/'metadata.json').write_text(json.dumps(meta))
    states = {s['timer']:'active' for s in specs.values()}
    states.update({s['service']:'inactive' for s in specs.values()})
    flags = {'reload':False, 'readback':False}
    calls, probes = [], []
    def control(*args):
        calls.append(args)
        if args[0] == 'show':
            unit, key = args[1], args[3]
            if key == 'ActiveState':
                return states[unit]
            for s in specs.values():
                if unit == s['service']:
                    target = s['route_base']
                    if s['override'].exists():
                        text = s['override'].read_text()
                        target = Path(next(line.split('=',1)[1] for line in text.splitlines()
                                           if line.startswith('WorkingDirectory=')))
                    if key == 'WorkingDirectory':
                        return str(target)
                    if key == 'ExecStart':
                        return exec_property('/usr/bin/python3 -I '+str(target/'run.py')+s['args'])
            if key == 'ExecStart':
                return exec_property()
            return 'protected-unchanged'
        if args[0] in ('start','stop'):
            assert args[1] in {s['timer'] for s in specs.values()}
            states[args[1]] = 'active' if args[0] == 'start' else 'inactive'
        if args[0] == 'daemon-reload' and flags['reload']:
            flags['reload'] = False
            raise RuntimeError('INJECTED_RELOAD')
        return ''
    def probe(target):
        probes.append(target)
        if flags['readback']:
            raise ValueError('ADMIN_STDOUT_READBACK_FAILED')
        return {'read_available':True}
    monkeypatch.setattr(module, 'control', control)
    monkeypatch.setattr(module, 'post_route', probe)
    return module, package, states, flags, calls, probes


def test_apply_replay_rollback_preserve_sources_and_inactive_timer(installation):
    m, package, states, flags, calls, probes = installation
    states[m.SPECS['worker']['timer']] = 'inactive'
    before = {n:m.tree(s['base']) for n,s in m.SPECS.items()}
    meta, targets = m.validate(package)
    assert not calls
    m.apply(package)
    for n,s in m.SPECS.items():
        assert s['override'].read_bytes() == m.dropin(s, targets[n])
        assert m.tree(s['base']) == before[n]
        assert m.tree(targets[n]) == dict(before[n], **meta['files'][n])
    m.apply(package)
    assert len(probes) == 1
    m.apply(package, rollback=True)
    assert all(not s['override'].exists() for s in m.SPECS.values())
    assert states[m.SPECS['monitor']['timer']] == 'active'
    assert states[m.SPECS['worker']['timer']] == 'inactive'
    assert all(call != ('start',m.SPECS['worker']['timer']) for call in calls)


def test_active_worker_refuses_without_kill_and_restores_timers(installation, monkeypatch):
    m, package, states, flags, calls, probes = installation
    states[m.SPECS['worker']['service']] = 'activating'
    ticks = iter([0,61])
    monkeypatch.setattr(m.time,'monotonic',lambda:next(ticks))
    with pytest.raises(TimeoutError, match='ADMIN_JOB_RUNNING'):
        m.apply(package)
    assert all(not s['override'].exists() for s in m.SPECS.values())
    assert all(states[s['timer']] == 'active' for s in m.SPECS.values())
    assert not probes


@pytest.mark.parametrize('failure',['reload','readback','second_dropin'])
def test_partial_apply_failure_restores_both_routes(installation, monkeypatch, failure):
    m, package, states, flags, calls, probes = installation
    if failure == 'second_dropin':
        atomic = m.atomic
        def fail(path,data):
            if path == m.SPECS['worker']['override']:
                raise OSError('INJECTED_SECOND_DROPIN')
            atomic(path,data)
        monkeypatch.setattr(m,'atomic',fail)
    else:
        flags[failure] = True
    with pytest.raises((RuntimeError, ValueError, OSError)):
        m.apply(package)
    assert all(not s['override'].exists() for s in m.SPECS.values())
    assert all(states[s['timer']] == 'active' for s in m.SPECS.values())


@pytest.mark.parametrize('where',['overlay','base','updater'])
def test_hash_drift_refused_before_controls(installation, where):
    m, package, states, flags, calls, probes = installation
    s = m.SPECS['worker']
    target = {'overlay':package/'overlay'/'worker'/s['modules'][0],
              'base':s['base']/s['modules'][0],'updater':package/'update.py'}[where]
    target.write_text('tampered\n')
    with pytest.raises(ValueError):
        m.apply(package)
    assert not calls


def test_partial_override_refuses_without_timer_changes(installation):
    m, package, states, flags, calls, probes = installation
    meta, targets = m.validate(package)
    s = m.SPECS['monitor']
    s['override'].parent.mkdir(parents=True)
    s['override'].write_bytes(m.dropin(s,targets['monitor']))
    with pytest.raises(ValueError, match='PARTIAL_OVERRIDE'):
        m.apply(package)
    assert not any(c[0] in ('start','stop') for c in calls)


def test_stage_symlink_refused(installation):
    m, package, states, flags, calls, probes = installation
    _, targets = m.validate(package)
    targets['monitor'].symlink_to(m.SPECS['monitor']['base'],target_is_directory=True)
    with pytest.raises(ValueError, match='STAGED_RELEASE_DRIFT'):
        m.apply(package)
    assert not any(c[0] in ('start','stop') for c in calls)


def test_worker_base_alias_drift_refused_before_controls(installation):
    m, package, states, flags, calls, probes = installation
    m.SPECS['worker']['route_base'] = m.SPECS['monitor']['base']
    with pytest.raises(ValueError, match='BASE_ROUTE_ALIAS_DRIFT'):
        m.apply(package)
    assert not calls

def test_both_monitor_modules_are_required(installation):
    m, package, states, flags, calls, probes = installation
    meta = json.loads((package/'metadata.json').read_text())
    del meta['files']['monitor']['app/admin_alerts/output_contracts.py']
    (package/'metadata.json').write_text(json.dumps(meta))
    with pytest.raises(ValueError, match='OVERLAY_MODULE_MISMATCH'):
        m.apply(package)
    assert not calls


def test_production_scope_has_only_admin_services(installation):
    m, *_ = installation
    assert {s['service'] for s in m.SPECS.values()} == {
        'goalvision-admin-alerts.service', 'goalvision-admin-autorepair.service'}
    assert len(m.PROTECTED) == 5
    assert all('admin' not in unit for unit in m.PROTECTED)

def test_read_only_transport_diagnostic_no_message_bodies(installation, tmp_path):
    import hashlib
    import sqlite3
    m, *_ = installation
    path = tmp_path/'admin.sqlite'
    db = sqlite3.connect(path)
    for table in ('attempts','operator_attempts'):
        db.execute(f'CREATE TABLE {table}(started REAL,result TEXT)')
        db.executemany(f'INSERT INTO {table} VALUES (?,?)',
                       [(1790910000,'RECEIPT_PERSISTED'),(1790910000,'RATE_LIMIT'),
                        (1790910000,'PRIVATE_SECRET'),(1,'RECEIPT_PERSISTED')])
    db.execute('CREATE TABLE incidents(rule TEXT,state TEXT,evidence TEXT,last_seen REAL)')
    db.execute('INSERT INTO incidents VALUES (?,?,?,?)', ('ADMIN_DELIVERY_DEGRADED','RECOVERED',
        json.dumps({'facts':{'code':'HEALTHY'},'body':'PRIVATE_SECRET'}),1790910000))
    db.commit(); db.close()
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    result=m.diagnostic(path)
    assert result['confirmed_messages_since_deploy']==2
    assert result['attempts']['RATE_LIMIT']==1
    assert 'PRIVATE_SECRET' not in json.dumps(result)
    assert result['admin_delivery']==[{'state':'RECOVERED','code':'HEALTHY'}]
    assert before==hashlib.sha256(path.read_bytes()).hexdigest()


def test_missing_diagnostic_database_never_created(installation,tmp_path):
    m,*_=installation
    path=tmp_path/'missing.sqlite'
    assert m.diagnostic(path)=={'status':'READ_UNAVAILABLE'}
    assert not path.exists()

def test_execstart_runtime_fields_do_not_change_route_identity(installation):
    m,*_=installation
    assert m.configured_exec(exec_property(live=True)) == m.configured_exec(exec_property(live=False))
    assert m.configured_exec(exec_property()) != m.configured_exec(exec_property('/bin/python -m changed'))
    assert m.configured_exec(exec_property()) != m.configured_exec(exec_property(ignore_errors='yes'))


@pytest.mark.parametrize('value',['', 'unexpected', exec_property()+' '+exec_property(),
    exec_property().replace(' ; ignore_errors=no','')])
def test_unknown_execstart_format_fails_closed(installation,value):
    m,*_=installation
    with pytest.raises(ValueError,match='UNSUPPORTED_EXECSTART'):
        m.configured_exec(value)


@pytest.mark.parametrize('actual_change',[False,True])
def test_daemon_reload_runtime_reset_vs_real_command_drift(installation,monkeypatch,actual_change):
    m,package,states,flags,calls,probes=installation
    original=m.control
    reloads=[]
    def control(*args):
        if args[0]=='daemon-reload':
            reloads.append(True)
        if args[0]=='show' and args[1] in m.PROTECTED and args[3]=='ExecStart':
            argv='/bin/python -m changed' if actual_change and reloads else '/bin/python -m protected'
            return exec_property(argv,live=not bool(reloads))
        return original(*args)
    monkeypatch.setattr(m,'control',control)
    if actual_change:
        with pytest.raises(ValueError,match='PREMATCH_ROUTE_CHANGED'):
            m.apply(package)
        assert all(not s['override'].exists() for s in m.SPECS.values())
    else:
        m.apply(package)
        assert all(s['override'].exists() for s in m.SPECS.values())
    assert all(states[s['timer']]=='active' for s in m.SPECS.values())


@pytest.fixture(params=["update_monitor_compat.py","update_rotation_alerts.py","update_health_projection.py"])
def monitor_installation(installation,tmp_path,monkeypatch,request):
    m,package,states,flags,calls,probes=installation
    source=Path(__file__).parents[2]/'operations/admin-autorepair'/request.param
    spec=importlib.util.spec_from_file_location('monitor_only_update',source)
    wrapper=importlib.util.module_from_spec(spec); spec.loader.exec_module(wrapper)
    monkeypatch.setattr(wrapper,'OVERRIDE',m.SPECS['monitor']['override'])
    config=tmp_path/'monitor.json'; config.write_text(json.dumps({'autorepair':{'enabled':False}}))
    marker=tmp_path/'DISABLED'; marker.touch()
    monkeypatch.setattr(wrapper,'CONFIG',config)
    monkeypatch.setattr(wrapper,'MARKER',marker)
    worker=m.SPECS['worker']
    states[worker['timer']]='inactive'
    original=m.control
    def control(*args):
        if args[0]=='show' and args[1]==wrapper.TIMER and args[3]=='UnitFileState':
            return 'disabled'
        if args[0]=='show' and args[1]==wrapper.WORKER and args[3]=='MainPID':
            return '0'
        return original(*args)
    monkeypatch.setattr(m,'control',control)
    if hasattr(wrapper,"BASE"):
        monkeypatch.setattr(wrapper,"BASE",m.SPECS["monitor"]["base"])
        base=m.SPECS["monitor"]["base"]
        for name in wrapper.MODULES:
            path=base/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("old = True\n")
            path=package/"overlay/monitor"/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text("new = True\n")
        (base/"manifest.json").write_text(json.dumps(m.tree(base)))
    wrapper.configure(m)
    meta=json.loads((package/'metadata.json').read_text())
    meta['base_manifests']["monitor"]=m.tree(m.SPECS["monitor"]["base"])
    meta['files']={'monitor':{name:m.sha(package/"overlay/monitor"/name) for name in m.SPECS["monitor"]["modules"]}}
    (package/'metadata.json').write_text(json.dumps(meta))
    return m,package,states,calls,wrapper,worker,config,marker


def test_monitor_only_apply_and_rollback_preserve_disabled_codex(monitor_installation):
    m,package,states,calls,w,worker,config,marker=monitor_installation
    before=config.read_bytes()
    source=m.tree(worker['base'])
    w.require_codex_disabled(m)
    m.apply(package)
    w.require_codex_disabled(m)
    m.apply(package,rollback=True)
    assert states[worker['timer']]=='inactive' and states[worker['service']]=='inactive'
    assert not worker['override'].exists()
    assert config.read_bytes()==before and marker.exists()
    assert m.tree(worker['base'])==source
    assert all(c[1] not in (worker['timer'],worker['service'])
               for c in calls if c[0] in ('start','stop','enable','disable'))
    assert len(m.SPECS)==1 and w.WORKER in m.PROTECTED


@pytest.mark.parametrize('condition',['enabled_config','missing_marker','active_timer','active_worker'])
def test_monitor_update_requires_disabled_codex(monitor_installation,condition):
    m,package,states,calls,w,worker,config,marker=monitor_installation
    if condition=='enabled_config': config.write_text(json.dumps({'autorepair':{'enabled':True}}))
    if condition=='missing_marker': marker.unlink()
    if condition=='active_timer': states[worker['timer']]='active'
    if condition=='active_worker': states[worker['service']]='active'
    with pytest.raises(ValueError,match='ADMIN_CODEX_NOT_DISABLED'):
        w.require_codex_disabled(m)
    assert not any(c[0] in ('start','stop') for c in calls)


def test_rotation_diagnostic_is_readonly_bounded_and_redacted(tmp_path):
    source=Path(__file__).parents[2]/"operations/admin-autorepair/update_rotation_alerts.py"
    spec=importlib.util.spec_from_file_location("rotation_diag",source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    from app.admin_alerts.store import Store
    from app.admin_alerts.model import coverage
    root=tmp_path/"admin";root.mkdir()
    store=Store(root)
    event=coverage("stdout",100,"ROTATED_INODE_LOST",object_id="stdout-rotation")
    store.ingest([event],{},100);store.enqueue(100)
    store.close()
    before=(root/"admin.sqlite").read_bytes()
    result=module.incident_diagnostic(root/"admin.sqlite")
    assert result["identity_verified"] and result["reason"]=="ROTATED_INODE_LOST"
    assert result["notification_counts"]=={"PENDING":{"rows":1,"acknowledged":0}}
    assert (root/"admin.sqlite").read_bytes()==before
    assert "evidence" not in result and "body" not in json.dumps(result)
    missing=tmp_path/"missing.sqlite"
    assert module.incident_diagnostic(missing)["status"]=="READ_UNAVAILABLE"
    assert not missing.exists()
