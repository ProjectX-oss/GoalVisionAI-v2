"""Offline controller tests: fake systemd, real disposable SQLite/filesystem only."""
from __future__ import annotations

import copy
import base64
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('quota_controller', Path(__file__).with_name('controller.py'))
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class FakeSystemd:
    def __init__(self, root: Path, contract: dict) -> None:
        self.root, self.contract = root, contract
        self.commands = []
        self.loaded = {}
        self.now = 0.0
        self.active_until = 0.0
        self.reloads = 0
        self.fail_reload = set()
        self.always_fail_reload = False
        self.bad_loaded_reload = set()
        self.drift = False
        self.history = []
        self.load()

    def load(self) -> None:
        for service, before in self.contract['services'].items():
            actual = copy.deepcopy(before)
            row = next(r for r in self.contract['routes'] if r['service'] == service)
            path = self.root / row['target'].lstrip('/')
            if path.exists() and str(m.RELEASE) in path.read_text():
                env = 'research.env' if service == m.SERVICES[-1] else 'release.env'
                actual['EnvironmentFiles'] = str(m.RELEASE / env) + ' (ignore_errors=no)'
                actual['DropInPaths'] = row['target']
            gate = path.parent / m.GATE_NAME
            if gate.exists():
                actual['DropInPaths'] = ' '.join(filter(None, [actual['DropInPaths'], '/' + str(gate.relative_to(self.root))]))
            actual.update(NeedDaemonReload='no', LoadState='loaded')
            self.loaded[service] = actual
        self.history.append(copy.deepcopy(self.loaded))

    def run(self, args: list[str], timeout: float = 5) -> str:
        self.commands.append(args)
        if Path(args[0]).name == 'git':
            root = args[args.index('-C') + 1]
            return next(v['commit'] for v in self.contract['releases'].values()
                        if str(self.root / v['before'].lstrip('/')) == root)
        if Path(args[0]).name == 'journalctl':
            return json.dumps({'MESSAGE': 'QUOTA_DB_CONTENTION_RETRY'})
        assert Path(args[0]).name == 'systemctl', args
        if args[1] == 'list-units':
            return '\n'.join(m.SERVICES)
        if args[1] == 'daemon-reload':
            self.reloads += 1
            if self.always_fail_reload or self.reloads in self.fail_reload:
                raise m.Blocked('FAKE_RELOAD_FAILURE')
            self.load()
            if self.reloads in self.bad_loaded_reload:
                self.loaded[m.SERVICES[0]]['EnvironmentFiles'] = 'wrong'
            return ''
        assert args[1] == 'show', args
        props = next(a for a in args if a.startswith('--property=')).split('=', 1)[1].split(',')
        if props == ['Id', 'NeedDaemonReload']:
            return 'NeedDaemonReload=' + ('yes' if self.drift else 'no')
        service = args[2]
        if service.endswith('.timer'):
            values = {**self.contract['timers'][service], 'NeedDaemonReload': 'no'}
        elif 'MainPID' in props:
            active = self.now < self.active_until
            values = {'ActiveState': 'activating' if active else 'inactive', 'SubState': 'start' if active else 'dead',
                      'MainPID': '12' if active else '0', 'ControlPID': '0', 'Job': ''}
        else:
            values = self.loaded[service]
        result = []
        for k in props:
            v = values.get(k, '')
            if k == 'ExecStart':
                v = '{ path=/python ; argv[]=' + v + ' ; ignore_errors=no ; pid=0 ; status=0/0 }'
            if k == 'Environment':
                v = ''
            result.append(k + '=' + v)
        return '\n'.join(result)

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.package = self.root / 'package'
        self.package.mkdir()
        self.contract = {'package_manifest_sha256': '', 'route_relocation_approved': True,
                         'release_root': str(m.RELEASE), 'relocated_files': {}, 'static_files': {}, 'services': {}, 'timers': {}, 'releases': {},
                         'configuration_directories': {}, 'routes': [], 'databases': {}}
        files = {}
        for label, env in [('application', '/old/release.env'), ('research', '/old/research.env')]:
            before = '/old/' + label
            source = b'# frozen test source\n'
            self.write(before + '/app/__init__.py', b'# old source\n')
            self.write(before + '/requirements.txt', b'')
            self.write(env, ('PYTHONPATH=' + before + '\nSECRET=do-not-print\n').encode())
            self.contract['releases'][label] = {'before': before, 'commit': label + '-commit',
                'environment': env, 'environment_sha256': m.digest(self.path(env).read_bytes()),
                'files': {'app/__init__.py': m.digest(b'# old source\n'), 'requirements.txt': m.digest(b'')}}
            frozen_env = ('PYTHONPATH=' + str(m.PACKAGE / label) + '\nSECRET=do-not-print\n').encode()
            env_name = 'research.env' if label == 'research' else 'release.env'
            (self.package / env_name).write_bytes(frozen_env)
            files[env_name] = m.digest(frozen_env)
            self.contract['static_files'][env] = m.digest(self.path(env).read_bytes())
            self.write(before + '/app/lab_v2_shadow/repository.py', source)
            self.contract['releases'][label]['files']['app/lab_v2_shadow/repository.py'] = m.digest(source)
            for name, content in [('app/__init__.py', source), ('app/lab_v2_shadow/repository.py', source), ('requirements.txt', b'')]:
                p = self.package / label / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(content)
                files[label + '/' + name] = m.digest(content)
        for index, service in enumerate(m.SERVICES):
            target = '/etc/systemd/system/' + service + '.d/90-' + ('research' if index == 4 else 'operational') + '.conf'
            env = '/old/research.env' if index == 4 else '/old/release.env'
            before = ('[Service]\nEnvironmentFile=\nEnvironmentFile=' + env + '\n').encode() if index < 4 else None
            after = ('[Service]\nEnvironmentFile=\nEnvironmentFile=' + str(m.PACKAGE / ('research.env' if index == 4 else 'release.env')) + '\n').encode()
            row = {'service': service, 'target': target, 'before': None, 'before_sha256': None,
                   'after': 'configuration/' + service + '.proposed', 'after_sha256': m.digest(after)}
            if before is not None:
                row.update(before='configuration/' + service + '.before', before_sha256=m.digest(before))
                self.write(target, before)
            for field, data in [('before', before), ('after', after)]:
                if data is not None:
                    p = self.package / row[field];p.parent.mkdir(exist_ok=True);p.write_bytes(data)
                    files[row[field]] = m.digest(data)
            self.contract['routes'].append(row)
            self.contract['configuration_directories'][str(Path(target).parent)] = [Path(target).name] if before else []
            unit = '/etc/systemd/system/' + service
            self.write(unit, b'unit\n')
            self.contract['static_files'][unit] = m.digest(b'unit\n')
            self.contract['services'][service] = {'FragmentPath': unit, 'DropInPaths': target if before else '',
                'EnvironmentFiles': env + ' (ignore_errors=no)', 'ExecStart': '/python -P -m frozen --send',
                'Environment': m.digest(b''), 'Type': 'oneshot'}
            timer = service.replace('.service', '.timer')
            self.contract['timers'][timer] = {'ActiveState': 'active', 'UnitFileState': 'enabled',
                'TimersCalendar': '*:00/30', 'FragmentPath': '/etc/systemd/system/' + timer, 'DropInPaths': ''}
        for label in ('audit', 'ledger', 'shadow'):
            name = m.SHADOW_PATH if label == 'shadow' else '/data/' + label + '.db';self.path(name).parent.mkdir(parents=True, exist_ok=True)
            db = sqlite3.connect(self.path(name))
            db.executescript('CREATE TABLE adaptive_schema(version INTEGER); INSERT INTO adaptive_schema VALUES(5); '
                             'CREATE TABLE history(value TEXT); INSERT INTO history VALUES("KEEP"); '
                             'CREATE TABLE cycle_health(document TEXT); CREATE TABLE evidence(kind TEXT,identity TEXT);')
            db.execute('INSERT INTO cycle_health VALUES(?)', (json.dumps({'started_at': '2026-09-27T09:00:00+00:00',
                'completed_at': '2026-09-27T09:01:00+00:00', 'result': 'HEALTHY', 'provider_calls': 7, 'published': 1}),))
            db.execute("INSERT INTO evidence VALUES('receipt','synthetic')");db.commit()
            db.close()
            if label == 'shadow':
                self.path(name).unlink()
                with sqlite3.connect(self.path(name)) as db:
                    db.executescript(Path(__file__).with_name('shadow-schema.sql').read_text())
                    db.execute("INSERT INTO lab_v2_shadow_evidence VALUES('candidate','x','now','fp',?)", ('{"stage":"EARLY_CANDIDATE","kickoff_utc":"2026"}',))
                    db.execute("INSERT INTO lab_v2_provider_cache VALUES('cache','fixtures','query','{}','2026','2027','fp','{}')")
                    db.execute("INSERT INTO lab_v2_final_review_pending VALUES(1,'home','PENDING','2026','{}')")
            with sqlite3.connect(self.path(name)) as db:
                schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
            self.contract['databases'][label] = {'path': name, 'schema_sha256': m.digest(json.dumps(schema, separators=(',', ':')).encode())}
        self.contract['databases']['shadow'].update(check_version=m.SHADOW_CHECK, user_version=0)
        self.contract['shadow_migration_proof'] = {'migration_required': False,
            'repository_sha256': {name: value for name, value in files.items() if name.endswith('lab_v2_shadow/repository.py')},
            'ddl_schema_sha256': self.contract['databases']['shadow']['schema_sha256']}
        for name in [row['after'] for row in self.contract['routes']] + ['release.env', 'research.env']:
            data = (self.package / name).read_bytes().replace(str(m.PACKAGE).encode(), str(m.RELEASE).encode())
            self.contract['relocated_files'][name] = {'sha256': m.digest(data), 'bytes_b64': base64.b64encode(data).decode()}
        self.write(str(m.ADMIN_CONFIG), b'{"sender":{"enabled":false}}')
        self.path(m.ADMIN_DB).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path(m.ADMIN_DB)) as db:
            db.executescript('CREATE TABLE attempts(id INTEGER); CREATE TABLE outbox(attempts INTEGER,acknowledged INTEGER,receipt TEXT,state TEXT);')
        manifest = {'files': files, 'application_commit': m.SOURCE, 'configuration': self.contract['routes']}
        self.manifest_path = self.package / 'manifest.json'
        self.manifest_path.write_text(json.dumps(manifest))
        self.sha_patch = patch.object(m, 'MANIFEST_SHA', m.digest(self.manifest_path.read_bytes()))
        self.sha_patch.start(); self.addCleanup(self.sha_patch.stop)
        self.contract['package_manifest_sha256'] = m.MANIFEST_SHA
        self.systemd = FakeSystemd(self.root, self.contract)
        self.host = m.Host(self.root, self.systemd.run, lambda: self.systemd.now, self.systemd.sleep)
        self.controller = m.Controller(self.host, self.package, self.contract)
        self.before = {r['target']: self.path(r['target']).read_bytes() if r['before'] else None for r in self.contract['routes']}
        self.db_before = {p: p.read_bytes() for p in [*(self.path(v['path']) for v in self.contract['databases'].values()), self.path(m.ADMIN_DB)]}

    def tearDown(self) -> None:
        # Immutable release directories are deliberately not writable, even in tests.
        for p in self.root.rglob('*'):
            if p.is_dir():
                p.chmod(0o700)

    def path(self, name: str | Path) -> Path:
        return self.root / str(name).lstrip('/')

    def write(self, name: str, content: bytes) -> None:
        p = self.path(name);p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(content)

    def assert_before(self) -> None:
        for name, expected in self.before.items():
            self.assertEqual(self.path(name).read_bytes() if self.path(name).exists() else None, expected)

    def assert_no_fence(self) -> None:
        self.assertFalse(self.path(m.STATE / 'blocked').exists())
        self.assertTrue(all(not self.controller.gate(s).exists() for s in m.SERVICES))

    def assert_databases(self) -> None:
        for path, before in self.db_before.items():
            self.assertEqual(path.read_bytes(), before)

    def test_check_read_only(self) -> None:
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.controller.check()['status'], 'CHECK_PASSED')
        after = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(any(c[1] == 'daemon-reload' for c in self.systemd.commands))

    def test_tamper(self) -> None:
        (self.package / 'application/app/__init__.py').write_text('tamper')
        with self.assertRaisesRegex(m.Blocked, 'HASH_MISMATCH'):
            self.controller.check()

    def test_manifest_tamper(self) -> None:
        self.manifest_path.write_text('{}')
        with self.assertRaisesRegex(m.Blocked, 'MANIFEST_MISMATCH'):
            self.controller.check()

    def test_unexpected_package_file(self) -> None:
        (self.package / 'extra').write_text('no')
        with self.assertRaisesRegex(m.Blocked, 'FILE_SET'):
            self.controller.check()

    def test_symlink(self) -> None:
        p = self.package / 'application/app/__init__.py';p.unlink();p.symlink_to('/etc/passwd')
        with self.assertRaisesRegex(m.Blocked, 'SYMLINK'):
            self.controller.check()

    def test_route_drift(self) -> None:
        self.path(self.contract['routes'][0]['target']).write_text('drift')
        with self.assertRaisesRegex(m.Blocked, 'ROUTE_DRIFT'):
            self.controller.execute('install')
        self.assertEqual(self.systemd.reloads, 0)

    def test_admin_enabled(self) -> None:
        self.path(m.ADMIN_CONFIG).write_text('{"sender":{"enabled":true}}')
        with self.assertRaisesRegex(m.Blocked, 'ADMIN_SENDER_ENABLED'):
            self.controller.execute('install')
        self.assertEqual(self.systemd.reloads, 0)

    def test_admin_attempt(self) -> None:
        with sqlite3.connect(self.path(m.ADMIN_DB)) as db:
            db.execute('INSERT INTO attempts VALUES(1)')
        self.assertEqual(self.controller.check()['admin']['delivery_attempt_rows'], 1)

    def test_need_reload(self) -> None:
        self.systemd.drift = True
        with self.assertRaisesRegex(m.Blocked, 'DAEMON_RELOAD_DRIFT'):
            self.controller.check()

    def test_unexpected_dropin(self) -> None:
        self.write(str(Path(self.contract['routes'][0]['target']).parent / '99-evil.conf'), b'drift')
        with self.assertRaisesRegex(m.Blocked, 'UNEXPECTED_DROPIN'):
            self.controller.check()

    def test_active_drains(self) -> None:
        self.systemd.active_until = 4.0
        self.assertEqual(self.controller.execute('install')['status'], 'INSTALLED_WAITING_FOR_SCHEDULED_EVIDENCE')
        self.assertEqual(self.systemd.now, 4)
        self.assertEqual(self.systemd.reloads, 3)
        self.assert_no_fence(); self.assert_databases()
        self.assertTrue(all(c[1] in {'show', 'list-units', 'daemon-reload', '-c'} for c in self.systemd.commands))

    def test_drain_timeout(self) -> None:
        self.systemd.active_until = 1000
        with self.assertRaisesRegex(m.Blocked, 'DRAIN_TIMEOUT'):
            self.controller.execute('install')
        self.assertEqual(self.systemd.now, 60)
        self.assert_before(); self.assert_no_fence(); self.assert_databases()

    def test_fail_each_route(self) -> None:
        for index in range(1, 6):
            with self.subTest(index=index):
                fired = []
                def fail(name: str) -> None:
                    if name == 'route:' + str(index) and not fired:
                        fired.append(True);raise RuntimeError('injected')
                self.controller.hook = fail
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    self.controller.execute('install')
                self.assert_before(); self.assert_no_fence(); self.assert_databases()

    def test_crash_before_mutation(self) -> None:
        fired = []
        def fail(name: str) -> None:
            if name == 'journal:PREPARED' and not fired:
                fired.append(True); raise KeyboardInterrupt()
        self.controller.hook = fail
        with self.assertRaises(KeyboardInterrupt):
            self.controller.execute('install')
        self.assert_before(); self.assert_no_fence()

    def test_external_recovery_after_kill(self) -> None:
        self.controller.verify_package(); self.controller.stage()
        tx = {'manifest': m.MANIFEST_SHA, 'origin': 'before', 'target': 'after', 'events': []}
        self.controller.record(tx, 'PREPARED');self.controller.fence();self.controller.record(tx, 'CHANGING')
        row = self.contract['routes'][0]
        m.atomic(self.path(row['target']), self.controller.route_bytes(row, 'after'))
        # A fresh instance simulates ExecStopPost after a killed controller.
        m.Controller(self.host, self.package, self.contract).recover()
        self.assert_before(); self.assert_no_fence()

    def test_rollback_exact_and_research_absence(self) -> None:
        self.controller.execute('install')
        with sqlite3.connect(self.path('/data/audit.db')) as db:
            db.execute('INSERT INTO history VALUES("NEW_AFTER_INSTALL")')
        updated = self.path('/data/audit.db').read_bytes()
        self.assertEqual(self.controller.execute('rollback')['status'], 'ROLLED_BACK')
        self.assert_before(); self.assert_no_fence()
        self.assertEqual(self.path('/data/audit.db').read_bytes(), updated)
        self.assertFalse(self.path(self.contract['routes'][-1]['target']).exists())

    def test_daemon_reload_failure(self) -> None:
        self.systemd.fail_reload = {2}
        with self.assertRaisesRegex(m.Blocked, 'RELOAD_FAILURE'):
            self.controller.execute('install')
        self.assert_before();self.assert_no_fence()

    def test_loaded_route_mismatch(self) -> None:
        self.systemd.bad_loaded_reload = {2}
        with self.assertRaisesRegex(m.Blocked, 'LOADED_ROUTE_MISMATCH'):
            self.controller.execute('install')
        self.assert_before();self.assert_no_fence()

    def test_timer_capabilities_preserved(self) -> None:
        timers = copy.deepcopy(self.contract['timers'])
        before = self.controller.check()['capabilities']
        self.controller.execute('install')
        self.assertEqual(self.controller.check()['capabilities'], before)
        self.assertEqual(self.controller.timers(), timers)
        for name in ['release.env', 'research.env']:
            self.assertIn(b'SECRET=do-not-print\n', self.path(m.RELEASE / name).read_bytes())
        self.assert_databases()

    def test_replay_safely_rejected(self) -> None:
        self.controller.execute('install')
        with self.assertRaisesRegex(m.Blocked, 'UNEXPECTED_ROUTE_STATE'):
            self.controller.execute('install')
        self.controller.execute('rollback')
        with self.assertRaisesRegex(m.Blocked, 'UNEXPECTED_ROUTE_STATE'):
            self.controller.execute('rollback')

    def test_lock_contention(self) -> None:
        with self.host.lock():
            with self.assertRaisesRegex(m.Blocked, 'LOCK_BUSY'):
                self.controller.execute('install')
        self.assertEqual(self.systemd.reloads, 0)

    def test_unresolved_mixed_routes_stay_fenced(self) -> None:
        def fail(name: str) -> None:
            if name == 'route:2':
                self.systemd.always_fail_reload = True
                raise RuntimeError('route failure')
        self.controller.hook = fail
        with self.assertRaisesRegex(m.Blocked, 'RECOVERY_UNPROVEN'):
            self.controller.execute('install')
        self.assertTrue(self.path(m.STATE / 'blocked').exists())
        self.assertTrue(all(self.controller.gate(s).exists() for s in m.SERVICES))
        self.assertTrue(all(m.GATE_NAME in self.systemd.loaded[s]['DropInPaths'] for s in m.SERVICES))
        # No reload exposing mixed routes ever had an open condition.
        self.assertEqual(self.controller.journal()['phase'], 'CHANGING')
        self.assert_databases()

    def test_absent_before_file_drift_not_deleted(self) -> None:
        self.controller.execute('install')
        research = self.path(self.contract['routes'][-1]['target']);research.write_text('foreign')
        with self.assertRaisesRegex(m.Blocked, 'ROUTE_DRIFT'):
            self.controller.execute('rollback')
        self.assertEqual(research.read_text(), 'foreign')

    def test_existing_release_mismatch(self) -> None:
        self.write(str(m.RELEASE / 'unreviewed'), b'bad')
        with self.assertRaisesRegex(m.Blocked, 'FILE_SET'):
            self.controller.execute('install')
        self.assertEqual(self.systemd.reloads, 0)

    def test_schema_drift(self) -> None:
        with sqlite3.connect(self.path('/data/audit.db')) as db:
            db.execute('CREATE TABLE unexpected(x)')
        with self.assertRaisesRegex(m.Blocked, 'MIGRATION_REQUIRED'):
            self.controller.check()

    def test_crash_every_fence_boundary(self) -> None:
        for service in m.SERVICES:
            with self.subTest(service=service):
                fired = []
                def fail(name: str) -> None:
                    if name == 'fence:' + service and not fired:
                        fired.append(True); raise KeyboardInterrupt()
                self.controller.hook = fail
                with self.assertRaises(KeyboardInterrupt):
                    self.controller.execute('install')
                self.assert_before(); self.assert_no_fence()

    def test_rollback_failure_each_route_restores_installed(self) -> None:
        self.controller.execute('install')
        for index in range(1, 6):
            with self.subTest(index=index):
                fired = []
                def fail(name: str) -> None:
                    if name == 'route:' + str(index) and not fired:
                        fired.append(True); raise RuntimeError('rollback failure')
                self.controller.hook = fail
                with self.assertRaisesRegex(RuntimeError, 'rollback failure'):
                    self.controller.execute('rollback')
                self.assertEqual(self.controller.route_state(), 'after')
                self.assert_no_fence(); self.assert_databases()

    def test_crash_after_unfence_keeps_committed_release(self) -> None:
        fired = []
        def fail(name: str) -> None:
            if name == 'unfence:marker' and not fired:
                fired.append(True); raise KeyboardInterrupt()
        self.controller.hook = fail
        with self.assertRaises(KeyboardInterrupt):
            self.controller.execute('install')
        self.assertEqual(self.controller.route_state(), 'after')
        self.assert_no_fence()

    def test_unfence_reload_failure_does_not_restore_old_code(self) -> None:
        self.systemd.fail_reload = {3}
        with self.assertRaisesRegex(m.Blocked, 'RELOAD_FAILURE'):
            self.controller.execute('install')
        self.assertEqual(self.controller.route_state(), 'after')
        self.assert_no_fence()

    def test_release_write_permission_rejected(self) -> None:
        self.controller.verify_package();self.controller.stage()
        self.path(m.RELEASE / 'application/app/__init__.py').chmod(0o644)
        with self.assertRaisesRegex(m.Blocked, 'WRITABLE_RELEASE'):
            self.controller.execute('install')
        self.assert_before()

    def test_foreign_research_route_during_recovery_not_removed(self) -> None:
        self.controller.verify_package();self.controller.stage()
        tx = {'manifest': m.MANIFEST_SHA, 'origin': 'before', 'target': 'after', 'events': []}
        self.controller.record(tx, 'PREPARED');self.controller.fence();self.controller.record(tx, 'CHANGING')
        path = self.path(self.contract['routes'][-1]['target']);path.write_text('foreign')
        with self.assertRaisesRegex(m.Blocked, 'OVERWRITE_ROUTE_DRIFT'):
            self.controller.recover()
        self.assertEqual(path.read_text(), 'foreign')
        self.assertTrue(self.path(m.STATE / 'blocked').exists())

    def test_timer_drift_blocks(self) -> None:
        key = next(iter(self.contract['timers']))
        original = self.systemd.run
        def changed(args: list[str], timeout: float = 5) -> str:
            output = original(args, timeout)
            return output.replace('ActiveState=active', 'ActiveState=inactive') if key in args else output
        self.host.command = changed
        with self.assertRaisesRegex(m.Blocked, 'TIMER_STATE_OR_SCHEDULE_DRIFT'):
            self.controller.execute('install')
        self.assertEqual(self.systemd.reloads, 0)

    def test_capability_drift_blocks(self) -> None:
        self.systemd.loaded[m.SERVICES[0]]['ExecStart'] = '/python -P -m frozen'
        with self.assertRaisesRegex(m.Blocked, 'LOADED_ROUTE_MISMATCH'):
            self.controller.execute('install')
        self.assertEqual(self.systemd.reloads, 0)

    def test_disk_space(self) -> None:
        with patch.object(m.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(100, 100, 0)):
            with self.assertRaisesRegex(m.Blocked, 'DISK_SPACE'):
                self.controller.execute('install')
        self.assertEqual(self.systemd.reloads, 0)

    def test_database_inodes_preserved(self) -> None:
        before = {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in self.db_before}
        self.controller.execute('install');self.controller.execute('rollback')
        self.assertEqual(before, {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in self.db_before})

    def test_confirmation_contract_binds_code(self) -> None:
        root = self.root / 'cli';root.mkdir()
        (root / 'controller.py').write_bytes(b'reviewed')
        contract = {'controller_sha256': m.digest(b'reviewed')}
        (root / 'host-contract.json').write_text(json.dumps(contract))
        sums = {p.name: m.digest(p.read_bytes()) for p in root.iterdir()}
        (root / 'controller-checksums.json').write_text(json.dumps(sums))
        sha = m.digest((root / 'host-contract.json').read_bytes())
        self.assertEqual(m.load_contract(root, sha), contract)
        (root / 'controller.py').write_bytes(b'tampered')
        sums['controller.py'] = m.digest(b'tampered')
        (root / 'controller-checksums.json').write_text(json.dumps(sums))
        with self.assertRaisesRegex(m.Blocked, 'PINNED_CONTROLLER'):
            m.load_contract(root, sha)

    def test_status_read_only_and_no_production_validation_claim(self) -> None:
        before = {p: p.read_bytes() for p in self.db_before}
        result = self.controller.status()
        self.assertEqual(result['latest_discovery_health']['provider_calls'], 7)
        self.assertEqual(result['latest_discovery_health']['result'], 'HEALTHY')
        self.assertEqual(result['latest_delivery'], {'kind': 'receipt', 'identity': 'synthetic'})
        self.assertEqual(result['production_validation'], 'NOT_ASSERTED')
        self.assertEqual(result['admin']['sender_enabled'], False)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(self.systemd.reloads, 0)

    def test_approved_relocation_exact_bytes(self) -> None:
        self.controller.verify_package()
        for row in self.contract['routes']:
            before = (self.package / row['after']).read_bytes()
            self.assertEqual(self.controller.route_bytes(row, 'after'),
                             before.replace(str(m.PACKAGE).encode(), str(m.RELEASE).encode()))
        data = self.controller.stage_contents()
        for name in ('release.env', 'research.env'):
            self.assertEqual(data[name], (self.package / name).read_bytes().replace(
                str(m.PACKAGE).encode(), str(m.RELEASE).encode()))

    def test_other_release_and_dev_paths_block(self) -> None:
        for path in ('/opt/other', '/home/arvis/development', '/tmp/release'):
            self.contract['release_root'] = path
            with self.assertRaisesRegex(m.Blocked, 'UNAPPROVED_RELEASE_ROOT'):
                self.controller.execute('install')
            self.assert_before()
        self.assertEqual(self.systemd.reloads, 0)

    def test_approval_missing_blocks(self) -> None:
        self.contract['route_relocation_approved'] = False
        with self.assertRaisesRegex(m.Blocked, 'REVIEW_REQUIRED'):
            self.controller.check()

    def test_relocated_bytes_tamper_blocks(self) -> None:
        name = self.contract['routes'][0]['after']
        self.contract['relocated_files'][name]['bytes_b64'] = base64.b64encode(b'/home/dev').decode()
        with self.assertRaisesRegex(m.Blocked, 'RELOCATED_BYTES_MISMATCH'):
            self.controller.execute('install')
        self.assert_before()

    def test_existing_exact_release_reused(self) -> None:
        self.controller.verify_package(); self.controller.stage()
        before = {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in self.path(m.RELEASE).rglob('*')}
        self.controller.stage()
        self.assertEqual(before, {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in before})
        self.controller.verify_staged()
        self.assertTrue(all(p.stat().st_mode & 0o222 == 0 for p in before))

    def test_staging_hash_verified_before_sealing_and_rename(self) -> None:
        original = m.verify_tree
        calls = []
        def verify(root: Path, expected: dict, **kwargs: object) -> None:
            if root.name.startswith('.quota-stage-'):
                calls.append(root)
                self.assertFalse(self.path(m.RELEASE).exists())
                self.assertTrue((root / 'application/app/__init__.py').stat().st_mode & 0o200)
            original(root, expected, **kwargs)
        self.controller.verify_package()
        with patch.object(m, 'verify_tree', side_effect=verify):
            self.controller.stage()
        self.assertEqual(len(calls), 1)
        self.controller.verify_staged()

    def test_existing_same_files_wrong_bytes_blocks(self) -> None:
        self.controller.verify_package(); self.controller.stage()
        p = self.path(m.RELEASE / 'application/app/__init__.py')
        p.chmod(0o644); p.write_bytes(b'wrong'); p.chmod(0o444)
        with self.assertRaisesRegex(m.Blocked, 'HASH_MISMATCH'):
            self.controller.stage()

    def test_shadow_large_size_never_scans(self) -> None:
        path = self.path(m.SHADOW_PATH)
        original_stat = Path.stat
        queries = []
        original_connect = sqlite3.connect
        def connect(*args: object, **kwargs: object) -> sqlite3.Connection:
            db = original_connect(*args, **kwargs)
            db.set_trace_callback(queries.append)
            return db
        def large_stat(p: Path, *args: object, **kwargs: object) -> os.stat_result:
            result = original_stat(p, *args, **kwargs)
            if p == path:
                values = list(result); values[6] = 11 * 1024**3
                return os.stat_result(values)
            return result
        before = path.read_bytes()
        with patch.object(Path, 'stat', large_stat), patch.object(m.sqlite3, 'connect', side_effect=connect):
            result = self.controller.shadow_compatibility(self.contract['databases']['shadow'])
        self.assertEqual(result['size_bytes'], 11 * 1024**3)
        self.assertEqual(result['status'], 'COMPATIBLE')
        self.assertEqual(result['FULL_SHADOW_INTEGRITY'], 'NOT_COMPLETED_DUE_TO_SIZE_AND_BOUND')
        self.assertEqual(result['physical_integrity_notice'], m.SHADOW_NOTICE)
        self.assertFalse(any(word in q.lower() for q in queries for word in
                             ('integrity_check', 'quick_check', 'foreign_key_check', 'count(', 'insert ', 'update ', 'delete ')))
        self.assertTrue(all('SEARCH ' in plan for plan in result['indexed_read_plans']))
        self.assertEqual(before, path.read_bytes())
        self.assertFalse(list(path.parent.glob(path.name + '-*')))

    def test_shadow_bad_header_blocks(self) -> None:
        path = self.path(m.SHADOW_PATH)
        data = path.read_bytes(); path.write_bytes(b'X' + data[1:])
        with self.assertRaisesRegex(m.Blocked, 'INVALID_HEADER'):
            self.controller.databases()

    def test_shadow_missing_table_index_column_constraint_blocks(self) -> None:
        path = self.path(m.SHADOW_PATH); original = path.read_bytes()
        for sql in ('DROP TABLE lab_v2_final_review_pending',
                    'DROP INDEX lab_v2_provider_cache_lookup',
                    'ALTER TABLE lab_v2_provider_cache RENAME COLUMN endpoint TO missing',
                    'DROP TRIGGER lab_v2_shadow_no_update',
                    'CREATE TABLE unknown(x)'):
            with self.subTest(sql=sql):
                path.write_bytes(original)
                with sqlite3.connect(path) as db:
                    db.execute(sql)
                with self.assertRaisesRegex(m.Blocked, 'SCHEMA_OR_MIGRATION_REQUIRED'):
                    self.controller.shadow_compatibility(self.contract['databases']['shadow'])

    def test_shadow_unknown_version_blocks(self) -> None:
        with sqlite3.connect(self.path(m.SHADOW_PATH)) as db:
            db.execute('PRAGMA user_version=1')
        with self.assertRaisesRegex(m.Blocked, 'UNKNOWN_SCHEMA_VERSION'):
            self.controller.shadow_compatibility(self.contract['databases']['shadow'])

    def test_shadow_read_failure_blocks(self) -> None:
        original = sqlite3.connect
        def connect(*args: object, **kwargs: object) -> sqlite3.Connection:
            db = original(*args, **kwargs)
            db.set_authorizer(lambda op, a, b, c, d: sqlite3.SQLITE_DENY
                              if op == sqlite3.SQLITE_READ and a == 'lab_v2_shadow_evidence' else sqlite3.SQLITE_OK)
            return db
        with patch.object(m.sqlite3, 'connect', side_effect=connect):
            with self.assertRaises(sqlite3.DatabaseError):
                self.controller.check()

    def test_shadow_timeout_is_failure_only_for_required_reads(self) -> None:
        clock = iter((0, 0, 4))
        self.host.monotonic = lambda: next(clock, 4)
        with self.assertRaisesRegex(m.Blocked, 'READ_DEADLINE'):
            self.controller.shadow_compatibility(self.contract['databases']['shadow'])

    def test_shadow_unsafe_modes_sidecars_symlinks_block(self) -> None:
        path = self.path(m.SHADOW_PATH); data = path.read_bytes()
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = Path(str(path) + suffix); sidecar.touch()
            with self.assertRaisesRegex(m.Blocked, 'SIDECAR'):
                self.controller.shadow_compatibility(self.contract['databases']['shadow'])
            sidecar.unlink()
        path.write_bytes(data[:18] + b'\x02\x02' + data[20:])
        with self.assertRaisesRegex(m.Blocked, 'MODE_REQUIRES_REVIEW'):
            self.controller.shadow_compatibility(self.contract['databases']['shadow'])
        path.unlink(); path.symlink_to(self.path('/data/audit.db'))
        with self.assertRaisesRegex(m.Blocked, 'DATABASE_UNREADABLE'):
            self.controller.shadow_compatibility(self.contract['databases']['shadow'])

    def test_pending_admin_allowed_fresh_and_unchanged(self) -> None:
        with sqlite3.connect(self.path(m.ADMIN_DB)) as db:
            db.execute("INSERT INTO outbox VALUES(0,0,NULL,'PENDING')")
        before = {p: p.read_bytes() for p in (self.path(m.ADMIN_DB), self.path(m.ADMIN_CONFIG))}
        result = self.controller.check()['admin']
        self.assertEqual(result['pending_outbox'], 1)
        self.assertFalse(result['sender_enabled'])
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.path(m.ADMIN_CONFIG).write_text('{"sender":{"enabled":true}}')
        with self.assertRaisesRegex(m.Blocked, 'ADMIN_SENDER_ENABLED'):
            self.controller.check()

    def test_admin_fresh_read_failure_blocks(self) -> None:
        self.path(m.ADMIN_CONFIG).unlink()
        with self.assertRaises(m.Blocked):
            self.controller.check()
        self.assertEqual(self.systemd.reloads, 0)

    def test_admin_permission_failure_requires_operator(self) -> None:
        original = m.read
        def denied(path: Path) -> bytes:
            if path == self.path(m.ADMIN_CONFIG):
                raise PermissionError()
            return original(path)
        with patch.object(m, 'read', side_effect=denied):
            with self.assertRaisesRegex(m.Blocked, 'ADMIN_PRIVILEGED_CHECK_REQUIRES_OPERATOR'):
                self.controller.check()

    def test_reviewed_real_contract_and_ddl(self) -> None:
        root = Path(__file__).parent
        contract = json.loads((root / 'host-contract.json').read_text())
        self.assertTrue(contract['route_relocation_approved'])
        self.assertEqual(contract['release_root'], '/opt/goalvision-prematch-quota-557d5af2-f24738b05fef')
        with sqlite3.connect(':memory:') as db:
            db.executescript((root / 'shadow-schema.sql').read_text())
            self.assertEqual(m.schema_fingerprint(db), contract['databases']['shadow']['schema_sha256'])
        frozen = root / 'frozen' if (root / 'frozen').exists() else m.PACKAGE
        for name, expected in contract['relocated_files'].items():
            original = (frozen / name).read_bytes()
            derived = original.replace(str(m.PACKAGE).encode(), str(m.RELEASE).encode())
            self.assertEqual(derived, base64.b64decode(expected['bytes_b64']))
            self.assertEqual(m.digest(derived), expected['sha256'])
        self.assertEqual(contract['package_manifest_sha256'],
                         'f24738b05fef5f71f3ebcaead3c791233d94fcc38cee21e96a59f2f23493fff2')

    def test_shadow_migration_proof_mismatch_blocks(self) -> None:
        self.contract['shadow_migration_proof']['migration_required'] = True
        with self.assertRaisesRegex(m.Blocked, 'SHADOW_MIGRATION_REQUIRED'):
            self.controller.execute('install')
        self.assertEqual(self.systemd.reloads, 0)

    def test_shadow_unindexed_plan_blocks(self) -> None:
        with patch.object(m, 'SHADOW_READS', (("SELECT identity FROM lab_v2_shadow_evidence LIMIT 1", ()),)):
            with self.assertRaisesRegex(m.Blocked, 'UNBOUNDED_READ_PLAN'):
                self.controller.shadow_compatibility(self.contract['databases']['shadow'])

    def test_small_databases_keep_full_checks(self) -> None:
        original = sqlite3.connect
        queries = []
        def connect(*args: object, **kwargs: object) -> sqlite3.Connection:
            db = original(*args, **kwargs); db.set_trace_callback(queries.append); return db
        with patch.object(m.sqlite3, 'connect', side_effect=connect):
            self.controller.databases()
        self.assertEqual(queries.count('PRAGMA integrity_check'), 2)
        self.assertEqual(queries.count('PRAGMA foreign_key_check'), 2)

    def test_no_network_or_worker_control_source(self) -> None:
        source = Path(m.__file__).read_text()
        for value in ['import requests', 'import socket', 'import app', "'kill'", "'stop'", "'restart'", "'start'", "'disable'", "'enable'"]:
            self.assertNotIn(value, source)


if __name__ == '__main__':
    unittest.main()
