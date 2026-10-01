"""Monitor composition and deployment preparation, entirely offline."""
import importlib.util
from contextlib import closing
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.admin_alerts.autorepair import enqueue
from app.admin_alerts.cli import scan
from app.admin_alerts.model import DISCOVERY, Event
from app.admin_alerts.store import Store


def test_scan_first_enabled_baseline_and_new_job(tmp_path, spool, monkeypatch):
    from app.admin_alerts import cli
    root=tmp_path/'admin-alerts'
    config={'stdout':'unused','health_database':'unused','ledger_database':'unused',
            'release_environment':'unused','autorepair':{'enabled':True,'spool':str(spool)}}
    old=Event(DISCOVERY,'DATABASE_LOCK','old','old',1000,'fixture')
    current=[old]
    monkeypatch.setattr(cli,'systemd',lambda: {})
    monkeypatch.setattr(cli,'service_rules',lambda *args: ([],{}))
    monkeypatch.setattr(cli,'tail',lambda *args, **kw: ([],[],{},0))
    monkeypatch.setattr(cli,'journal',lambda *args: (current,{}))
    monkeypatch.setattr(cli,'health_rows',lambda *args: ([],{}))
    monkeypatch.setattr(cli,'unresolved',lambda *args: ([],{}))
    monkeypatch.setattr(cli,'weekly_unresolved',lambda *args: ([],{}))
    monkeypatch.setattr(cli,'configured_release',lambda *args: 'UNKNOWN')
    assert scan(config,root)['telegram_sends']==0
    assert not list((spool/'queue').iterdir())
    current.append(Event(DISCOVERY,'DATABASE_LOCK','new','new',1001,'fixture'))
    assert scan(config,root)['telegram_sends']==0
    assert len(list((spool/'queue').iterdir()))==1
    assert scan(config,root)['telegram_sends']==0
    assert len(list((spool/'queue').iterdir()))==1
    config['autorepair']['enabled']=False
    current.append(Event(DISCOVERY,'DATABASE_LOCK','later','later',1002,'fixture'))
    scan(config,root)
    assert len(list((spool/'queue').iterdir()))==1


def installer():
    spec=importlib.util.spec_from_file_location('autorepair_install', 'operations/admin-autorepair/install_v1.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installer_preview_never_mutates_or_controls_services(monkeypatch):
    module=installer()
    monkeypatch.setattr('sys.argv',['install_v1.py'])
    with patch.object(module,'install',side_effect=AssertionError('MUTATION')), \
         patch.object(module,'systemctl',side_effect=AssertionError('SERVICE')):
        assert module.main()==0


def test_installer_service_allowlist():
    import pytest
    with pytest.raises(ValueError):
        installer().systemctl('stop',DISCOVERY)


@pytest.mark.parametrize('foreign_owner', [False, True])
def test_snapshot_supports_linked_worktree_and_pins_exact_head(tmp_path, monkeypatch, foreign_owner):
    module = installer()
    repo = tmp_path/"repo with spaces ' ; $literal"
    review = tmp_path/'review'
    snapshot = tmp_path/'snapshot.git'
    repo.mkdir()
    subprocess.run(['git','-C',str(repo),'init','-q'],check=True)
    (repo/'code.py').write_text('BASE = 1\n')
    subprocess.run(['git','-C',str(repo),'add','code.py'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@invalid',
                    'commit','-qm','base'],check=True)
    main_head = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip()
    subprocess.run(['git','-C',str(repo),'worktree','add','-q','-b','review',str(review),'HEAD'],check=True)
    (review/'code.py').write_text('BASE = 2\n')
    (review/'untracked-secret.env').write_text('MUST_NOT_BE_SNAPSHOTTED\n')
    subprocess.run(['git','-C',str(review),'add','code.py'],check=True)
    subprocess.run(['git','-C',str(review),'-c','user.name=Test','-c','user.email=test@invalid',
                    'commit','-qm','reviewed'],check=True)
    reviewed_head = subprocess.check_output(['git','-C',str(review),'rev-parse','HEAD']).decode().strip()
    assert reviewed_head != main_head
    assert (review/'.git').is_file()
    if foreign_owner:
        common = repo/'.git'
        env = {'PATH':'/usr/bin:/bin', 'GIT_CONFIG_NOSYSTEM':'1',
               'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_TEST_ASSUME_DIFFERENT_OWNER':'1'}
        # Parent -c cannot authorize the child upload-pack process: reproduce
        # the production failure using real Git before exercising the fix.
        result = subprocess.run(['git','-c','safe.directory='+str(common),
                                 'clone','--bare','--no-local',str(common),
                                 str(tmp_path/'negative.git')], env=env,
                                capture_output=True, text=True)
        assert result.returncode == 128
        assert 'dubious ownership' in result.stderr
        real_run = subprocess.run

        def foreign_owner_clone(argv, **kwargs):
            if 'clone' in argv:
                import shlex
                upload_pack = next(arg.split('=',1)[1] for arg in argv
                                   if arg.startswith('--upload-pack='))
                assert shlex.split(upload_pack) == ['/usr/bin/git','-c',
                    'safe.directory='+str(common),'-c','core.hooksPath=/dev/null','upload-pack']
                kwargs['env'] = {**kwargs['env'], 'GIT_TEST_ASSUME_DIFFERENT_OWNER':'1'}
            return real_run(argv, **kwargs)

        monkeypatch.setattr(module.subprocess, 'run', foreign_owner_clone)
    module.snapshot(review.resolve(), snapshot)
    assert subprocess.check_output(['git','--git-dir='+str(snapshot),'rev-parse','HEAD']).decode().strip() == reviewed_head
    assert subprocess.check_output(['git','--git-dir='+str(snapshot),'symbolic-ref','HEAD']).decode().strip() == (
        'refs/heads/goalvision-reviewed-source')
    tree = subprocess.check_output(['git','--git-dir='+str(snapshot),'ls-tree','-r','--name-only','HEAD']).decode()
    assert 'code.py' in tree
    assert 'untracked-secret.env' not in tree
    assert not subprocess.check_output(['git','--git-dir='+str(snapshot),'remote']).strip()


def test_snapshot_clone_failure_is_diagnostic_and_cleans_destination(tmp_path, monkeypatch):
    module = installer()
    repo = tmp_path/'repo'
    snapshot = tmp_path/'snapshot.git'
    repo.mkdir()
    subprocess.run(['git','-C',str(repo),'init','-q'],check=True)
    (repo/'code.py').write_text('VALUE = 1\n')
    subprocess.run(['git','-C',str(repo),'add','code.py'],check=True)
    subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@invalid',
                    'commit','-qm','base'],check=True)
    real_run = subprocess.run

    def fail_clone(argv, **kwargs):
        if 'clone' in argv:
            assert '--no-local' in argv
            snapshot.mkdir()
            return subprocess.CompletedProcess(argv, 128, stderr='fatal: simulated snapshot race\n')
        return real_run(argv, **kwargs)

    monkeypatch.setattr(module.subprocess, 'run', fail_clone)
    with pytest.raises(ValueError, match='SOURCE_SNAPSHOT_CLONE_FAILED:fatal: simulated snapshot race'):
        module.snapshot(repo.resolve(), snapshot)
    assert not snapshot.exists()


def test_pretransaction_failure_cleans_only_attempt_releases(tmp_path, monkeypatch):
    module = installer()
    for name in ('TRANSACTION','WORKER_CONFIG','OVERRIDE','WORKER_LINK','ADMIN_RELEASES',
                 'WORKER_RELEASES','SOURCE_RELEASES','UNIT_ROOT','SPOOL'):
        monkeypatch.setattr(module, name, tmp_path/name)
    module.UNIT_ROOT.mkdir()
    monkeypatch.setattr(module, 'ADMIN_CONFIG', tmp_path/'admin.json')
    module.ADMIN_CONFIG.write_text('{}')
    monkeypatch.setattr(module.pwd, 'getpwnam', lambda _: SimpleNamespace(pw_uid=123))
    monkeypatch.setattr(module.grp, 'getgrnam', lambda _: SimpleNamespace(gr_gid=123))
    monkeypatch.setattr(module.subprocess, 'run',
                        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0))
    monkeypatch.setattr(module, 'stage',
                        lambda source, destination, runner: destination.mkdir(parents=True))

    def fail_snapshot(source, destination):
        destination.mkdir(parents=True)
        raise ValueError('SNAPSHOT_PREP_FAILURE')

    monkeypatch.setattr(module, 'snapshot', fail_snapshot)
    source = tmp_path/'source'
    source.mkdir()
    args = SimpleNamespace(source=source, release='r3-fixture',
                           admin_source=tmp_path/'admin-source',
                           prematch_source=tmp_path/'prematch-source',
                           enable_autorepair=False)
    with pytest.raises(ValueError, match='SNAPSHOT_PREP_FAILURE'):
        module.install(args)
    assert not (module.ADMIN_RELEASES/'r3-fixture').exists()
    assert not (module.WORKER_RELEASES/'r3-fixture').exists()
    assert not (module.SOURCE_RELEASES/'r3-fixture').exists()
    assert not module.TRANSACTION.exists()


def test_units_have_readonly_sources_hidden_credentials_and_singleton():
    service=Path('operations/admin-autorepair/goalvision-admin-autorepair.service').read_text()
    timer=Path('operations/admin-autorepair/goalvision-admin-autorepair.timer').read_text()
    for required in ('User=arvis','Group=goalvision-admin-alerts','ProtectSystem=strict',
                     'ProtectHome=tmpfs','NoNewPrivileges=yes','KillMode=control-group',
                     'TemporaryFileSystem=/etc:ro /run:ro /var:ro'):
        assert required in service
    directives = [line.split('=', 1)[0] for line in service.splitlines()
                  if '=' in line and not line.startswith('#')]
    for name in ('TemporaryFileSystem', 'BindReadOnlyPaths', 'BindPaths', 'ReadWritePaths'):
        assert directives.count(name) == 1
    mounts = dict(line.split('=', 1) for line in service.splitlines()
                  if '=' in line and not line.startswith('#'))
    readonly = set(mounts['BindReadOnlyPaths'].split())
    assert readonly == {
        '/opt/goalvision-admin-autorepair-sources', '/home/arvis/.codex',
        '/home/arvis/.local/bin/codex', '/etc/ssl', '/etc/resolv.conf',
        '/etc/hosts', '/etc/nsswitch.conf', '/etc/passwd', '/etc/group',
        '-/etc/gai.conf', '-/etc/host.conf', '-/run/systemd/resolve/stub-resolv.conf',
        '-/run/systemd/resolve/resolv.conf', '/etc/goalvision-admin-autorepair.json'}
    assert mounts['BindPaths'] == '/var/lib/goalvision-admin-autorepair'
    assert mounts['ReadWritePaths'] == '/var/lib/goalvision-admin-autorepair'
    assert mounts['CapabilityBoundingSet'] == mounts['AmbientCapabilities'] == ''
    for name in ('CPUQuota', 'MemoryMax', 'MemorySwapMax', 'TasksMax', 'LimitFSIZE',
                 'TimeoutStartSec', 'TimeoutStopSec', 'KillMode', 'SendSIGKILL'):
        assert name in mounts
    assert 'OnUnitInactiveSec=30s' in timer
    assert 'admin-token' not in service


def test_rollback_preserves_history_and_only_restores_owned_files(tmp_path, monkeypatch):
    from types import SimpleNamespace
    module=installer()
    for name in ('TRANSACTION','ADMIN_CONFIG','WORKER_CONFIG','OVERRIDE','WORKER_LINK'):
        monkeypatch.setattr(module,name,tmp_path/name)
    monkeypatch.setattr(module,'UNIT_ROOT',tmp_path/'units')
    module.UNIT_ROOT.mkdir()
    release=tmp_path/'worker-release'; release.mkdir()
    module.WORKER_LINK.symlink_to(release)
    for path in (module.WORKER_CONFIG,module.OVERRIDE,*(module.UNIT_ROOT/n for n in module.UNITS)):
        path.write_text('new')
    history=tmp_path/'admin.sqlite'; history.write_bytes(b'preserved incident and job history')
    module.ADMIN_CONFIG.write_text('new config')
    module.TRANSACTION.write_text(json.dumps({'admin_config':'original config','admin_timer_active':True,
                                            'worker_release':str(release)}))
    commands=[]
    monkeypatch.setattr(module,'systemctl',lambda *args: commands.append(args))
    monkeypatch.setattr(module,'drain_admin',lambda:None)
    monkeypatch.setattr(module.grp,'getgrnam',lambda _:SimpleNamespace(gr_gid=123))
    monkeypatch.setattr(module,'write',lambda path,content,*args:path.write_text(content))
    module.rollback()
    module.rollback()  # Idempotent; no second service sequence.
    assert module.ADMIN_CONFIG.read_text()=='original config'
    assert history.read_bytes()==b'preserved incident and job history'
    assert release.exists()
    assert not module.WORKER_LINK.is_symlink()
    assert not module.WORKER_CONFIG.exists()
    assert commands==[
        ('disable','--now','goalvision-admin-autorepair.timer'),
        ('stop','goalvision-admin-autorepair.service'),
        ('stop','goalvision-admin-alerts.timer'),('daemon-reload',),('start','goalvision-admin-alerts.timer')]


@pytest.fixture
def activation_install(tmp_path, monkeypatch, spool):
    """Real staged files and SQLite; all identity/service/source operations fake."""
    from app.admin_alerts import cli
    module = installer()
    for name in ('TRANSACTION', 'ADMIN_CONFIG', 'WORKER_CONFIG', 'OVERRIDE',
                 'WORKER_LINK', 'UNIT_ROOT', 'ADMIN_RELEASES', 'WORKER_RELEASES',
                 'SOURCE_RELEASES'):
        monkeypatch.setattr(module, name, tmp_path/name)
    monkeypatch.setattr(module, 'SPOOL', spool)
    state = tmp_path/'admin-alerts'
    state.mkdir()
    monkeypatch.setattr(module, 'ADMIN_STATE', state)
    events = [Event(DISCOVERY, 'DATABASE_LOCK', str(i), str(i), 1000, 'fixture')
              for i in range(4)]
    store = Store(state)
    store.ingest(events, {}, 1000)
    for row, status in zip(store.db.execute('SELECT id FROM incidents ORDER BY id').fetchall(),
                           ('OPEN', 'REPEATED', 'ESCALATED', 'PENDING')):
        store.db.execute('UPDATE incidents SET state=? WHERE id=?', (status, row['id']))
    store.db.commit()
    store.close()
    config = {'stdout': 'unused', 'health_database': 'unused', 'ledger_database': 'unused',
              'release_environment': 'unused', 'autorepair': {'enabled': False}}
    module.ADMIN_CONFIG.write_text(json.dumps(config))
    calls = []
    mode = {'failure': None, 'active': True}
    monkeypatch.setattr(module.pwd, 'getpwnam', lambda _: SimpleNamespace(pw_uid=123))
    monkeypatch.setattr(module.grp, 'getgrnam', lambda _: SimpleNamespace(gr_gid=123))
    monkeypatch.setattr(module.os, 'chown', lambda *args: None)
    def write(path, content, *args):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setattr(module, 'write', write)
    monkeypatch.setattr(module, 'snapshot', lambda source, target: target.mkdir())
    monkeypatch.setattr(module, 'drain_admin', lambda: calls.append(('drain',)))
    def control(*args):
        calls.append(args)
        if args == ('enable', '--now', 'goalvision-admin-autorepair.timer'):
            if mode['failure'] == 'enable':
                raise subprocess.CalledProcessError(1, args)
            # Simulate the earliest possible timer dispatch. All old episodes
            # must already be excluded, including a PENDING episode opening.
            with closing(Store(state)) as db:
                assert db.db.execute('SELECT 1 FROM repair_activation').fetchone()
                assert db.db.execute('SELECT count(*) FROM repair_exclusions').fetchone()[0] == 4
                db.db.execute("UPDATE incidents SET state='OPEN' WHERE state='PENDING'")
                db.db.commit()
                assert enqueue(db, spool, 1002) is None
                assert db.db.execute('SELECT count(*) FROM repair_jobs').fetchone()[0] == 0
            assert not list((spool/'queue').iterdir())
            assert not list((spool/'running').iterdir())
    monkeypatch.setattr(module, 'systemctl', control)
    monkeypatch.setattr(cli, 'systemd', lambda: {})
    monkeypatch.setattr(cli, 'service_rules', lambda *args: ([], {}))
    monkeypatch.setattr(cli, 'tail', lambda *args, **kw: ([], [], {}, 0))
    monkeypatch.setattr(cli, 'journal', lambda *args: ([], {}))
    monkeypatch.setattr(cli, 'health_rows', lambda *args: ([], {}))
    monkeypatch.setattr(cli, 'unresolved', lambda *args: ([], {}))
    monkeypatch.setattr(cli, 'weekly_unresolved', lambda *args: ([], {}))
    monkeypatch.setattr(cli, 'configured_release', lambda *args: 'UNKNOWN')
    def run(argv, **kwargs):
        if argv == ['/usr/bin/systemctl', 'is-active', '--quiet', 'goalvision-admin-alerts.timer']:
            return subprocess.CompletedProcess(argv, 0 if mode['active'] else 3)
        release = module.ADMIN_RELEASES/'fixture'
        assert argv == ['/usr/sbin/runuser', '-u', 'goalvision-admin-alerts', '--',
                        '/usr/bin/python3', '-I', str(release/'run.py'),
                        '--config', str(module.ADMIN_CONFIG), '--state', str(state), '--no-send']
        assert kwargs['check'] is True and kwargs['timeout'] == 60
        assert kwargs['cwd'] == release
        assert kwargs['env'] == {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
        assert (release/'app/admin_alerts/cli.py').is_file()
        assert str(release/'run.py') in module.OVERRIDE.read_text()
        assert calls == [('stop', 'goalvision-admin-alerts.timer'), ('drain',),
                         ('daemon-reload',), ('disable', '--now', 'goalvision-admin-autorepair.timer'),
                         ('stop', 'goalvision-admin-autorepair.service')]
        calls.append(('baseline',))
        failure = mode['failure']
        if failure == 'exit':
            raise subprocess.CalledProcessError(1, argv)
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(argv, 60)
        if failure in ('missing_baseline', 'disabled'):
            report = {'no_send': True, 'telegram_sends': 0} if failure == 'missing_baseline' else {'status': 'DISABLED'}
        elif failure == 'missing_exclusions':
            with closing(Store(state)) as db:
                db.db.execute('INSERT INTO repair_activation VALUES (1,1001)')
                db.db.commit()
            report = {'no_send': True, 'telegram_sends': 0}
        else:
            assert json.loads(module.ADMIN_CONFIG.read_text())['autorepair']['enabled'] is True
            report = scan({}, state, no_send=True, config_path=module.ADMIN_CONFIG)
        if failure in ('queue', 'running'):
            (spool/failure/'unexpected.partial').write_text('unexpected')
        if failure == 'reservation':
            with closing(Store(state)) as db:
                db.ingest([Event(DISCOVERY, 'DATABASE_LOCK', 'new', 'new', 1001, 'fixture')], {}, 1001)
                key = enqueue(db, spool, 1001)
                (spool/'queue'/f'{key}.json').unlink()  # SQLite alone must catch it.
        return subprocess.CompletedProcess(argv, 0, json.dumps(report).encode())
    monkeypatch.setattr(module.subprocess, 'run', run)
    args = SimpleNamespace(source=Path.cwd(), release='fixture', admin_source=tmp_path,
                           prematch_source=tmp_path, enable_autorepair=True)
    return module, args, calls, mode


@pytest.mark.parametrize('active', [True, False])
def test_installer_baseline_precedes_immediate_worker_start(activation_install, active):
    module, args, calls, mode = activation_install
    mode['active'] = active
    module.install(args)
    assert calls.count(('baseline',)) == 1
    assert calls.index(('baseline',)) < calls.index(('enable', '--now', 'goalvision-admin-autorepair.timer'))
    assert (('start', 'goalvision-admin-alerts.timer') in calls) is active


@pytest.mark.parametrize('failure', ['exit', 'timeout', 'disabled', 'missing_baseline',
                                    'missing_exclusions', 'queue', 'running', 'reservation',
                                    'baseline_job', 'enable'])
def test_installer_activation_failure_leaves_worker_disabled_and_rollback_available(activation_install, failure):
    module, args, calls, mode = activation_install
    original = module.ADMIN_CONFIG.read_text()
    mode['failure'] = failure
    if failure == 'baseline_job':
        with closing(Store(module.ADMIN_STATE)) as db:
            row = db.db.execute('SELECT id,episode FROM incidents LIMIT 1').fetchone()
            db.db.execute('INSERT INTO repair_jobs VALUES (?,?,?,?,?)',
                          ('existing-invalid-job', row['id'], row['episode'], 1000, '{}'))
            db.db.commit()
    with pytest.raises((ValueError, subprocess.SubprocessError)):
        module.install(args)
    assert calls[-2:] == [('disable', '--now', 'goalvision-admin-autorepair.timer'),
                         ('stop', 'goalvision-admin-autorepair.service')]
    assert ('start', 'goalvision-admin-alerts.timer') not in calls
    if failure != 'enable':
        assert ('enable', '--now', 'goalvision-admin-autorepair.timer') not in calls
    assert module.TRANSACTION.exists()
    before = (module.ADMIN_STATE/'admin.sqlite').read_bytes()
    module.rollback()
    assert module.ADMIN_CONFIG.read_text() == original
    assert (module.ADMIN_STATE/'admin.sqlite').read_bytes() == before
    assert json.loads(module.TRANSACTION.read_text())['rolled_back'] is True


def test_disabled_install_never_scans_or_enables_worker(activation_install):
    module, args, calls, mode = activation_install
    args.enable_autorepair = False
    module.install(args)
    assert ('baseline',) not in calls
    assert not any('goalvision-admin-autorepair.timer' in command for command in calls)
    assert json.loads(module.ADMIN_CONFIG.read_text())['autorepair']['enabled'] is False


@pytest.mark.parametrize('directory', ['queue', 'running'])
def test_installer_rejects_preexisting_spool_before_scanning(activation_install, directory):
    module, args, calls, mode = activation_install
    pending = module.SPOOL/directory/'old.partial'
    pending.write_text('retained')
    with pytest.raises(ValueError, match='ACTIVATION_SPOOL_NOT_EMPTY'):
        module.install(args)
    assert ('baseline',) not in calls
    assert ('enable', '--now', 'goalvision-admin-autorepair.timer') not in calls
    assert pending.read_text() == 'retained'
