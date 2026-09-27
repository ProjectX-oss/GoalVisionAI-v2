"""Exercise atomic ADMIN replacement and rollback on temporary directories only."""
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from test_monitor import Temporary, NOW
from app.admin_alerts.store import Store
from app.admin_alerts.model import Event, UNITS
import sqlite3

spec = importlib.util.spec_from_file_location('admin_upgrade_v1_2', 'operations/admin-alerts/upgrade_v1_2.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


def manifest(root):
    value = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n'
                    for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS')
    (root/'SHA256SUMS').write_text(value)
    return value


class UpgradeV12Tests(Temporary):
    def setUp(self):
        super().setUp()
        for name in ('TARGET', 'STATE', 'UNIT_ROOT'):
            path = self.root/name; path.mkdir()
            patcher = patch.object(upgrade, name, path); patcher.start(); self.addCleanup(patcher.stop)
        for name in ('BACKUP', 'STAGE', 'TRANSACTION', 'CONFIG'):
            patcher = patch.object(upgrade, name, self.root/name); patcher.start(); self.addCleanup(patcher.stop)
        upgrade.CONFIG.write_text('{"sender":{"enabled":false}}')
        (upgrade.STATE/'scan.lock').touch()
        store = Store(upgrade.STATE)
        store.ingest([Event(UNITS[1], 'MISSING_OUTPUT', inv, inv, NOW, 'journal-output', invocation=inv)
                      for inv in ('a'*32, 'b'*32)], {'journal': {'cursor': 'v1-cursor'}}, NOW)
        store.enqueue(NOW)
        # A v1 database has no invalidation audit table/triggers.
        with store.db:
            store.db.execute('DROP TABLE invalidations')
        store.close()
        (upgrade.TARGET/'run.py').write_text('old')
        old = manifest(upgrade.TARGET)
        self.package = self.root/'package'; self.package.mkdir()
        (self.package/'run.py').write_text('new')
        (self.package/'v1-SHA256SUMS').write_text(old)
        units = {}
        for name in upgrade.ADMIN:
            (upgrade.UNIT_ROOT/name).write_text(name)
            units[name] = upgrade.sha(upgrade.UNIT_ROOT/name)
        self.protected = self.root/'prematch'; self.protected.write_text('PREMATCH unchanged')
        (self.package/'upgrade-baseline.json').write_text(json.dumps({
            'operator_observed_incidents': [Event(UNITS[1], 'MISSING_OUTPUT', inv, inv, NOW, 'journal-output', invocation=inv).signature for inv in ('a'*32, 'b'*32)], 'admin_units': units, 'protected_sha256': {str(self.protected): upgrade.sha(self.protected)}}))
        manifest(self.package)
        self.commands = []
        self.active = True
        def systemctl(*args):
            self.commands.append(args)
            if args[0] in ('stop', 'start'):
                self.assertIn(args[1], upgrade.ADMIN)
                if args[1] == upgrade.ADMIN[0]:
                    self.active = args[0] == 'start'
                return ''
            if args[0] == 'list-units':
                return 'goalvision-admin-alerts.timer loaded active waiting'
            if '--property=StandardOutput' in args:
                return 'null'
            if '--property=ActiveState' in args:
                return 'active' if self.active else 'inactive'
            return ''
        for patcher in (patch.object(upgrade, 'systemctl', side_effect=systemctl), patch('os.geteuid', return_value=0)):
            patcher.start(); self.addCleanup(patcher.stop)

    def test_upgrade_rollback_preserves_database_config_and_prematch(self):
        paths = [upgrade.STATE/'admin.sqlite', upgrade.CONFIG, self.protected]
        before = [upgrade.sha(p) for p in paths]
        upgrade.preflight(self.package)
        self.assertFalse(upgrade.TRANSACTION.exists())
        upgrade.apply(self.package)
        self.assertEqual((upgrade.TARGET/'run.py').read_text(), 'new')
        self.assertEqual((upgrade.BACKUP/'run.py').read_text(), 'old')
        self.assertTrue(self.active)
        upgrade.apply(self.package, rollback=True)
        self.assertEqual((upgrade.TARGET/'run.py').read_text(), 'old')
        self.assertEqual(before, [upgrade.sha(p) for p in paths])
        self.assertFalse(self.active)
        self.assertFalse(any(c[0] == 'daemon-reload' for c in self.commands))

    def test_enabled_sender_and_changed_installed_file_fail_before_stop(self):
        upgrade.CONFIG.write_text('{"sender":{"enabled":true}}')
        with self.assertRaises(ValueError):
            upgrade.apply(self.package)
        upgrade.CONFIG.write_text('{"sender":{"enabled":false}}')
        (upgrade.TARGET/'run.py').write_text('unexpected')
        with self.assertRaises(ValueError):
            upgrade.apply(self.package)
        self.assertFalse(any(c[0] == 'stop' for c in self.commands))

    def test_failure_after_exchange_restores_original_files_and_leaves_admin_stopped(self):
        real_verify = upgrade.verify
        def verify(root, values):
            if root == upgrade.TARGET and (root/'run.py').read_text() == 'new':
                raise ValueError('injected verification failure')
            real_verify(root, values)
        with patch.object(upgrade, 'verify', side_effect=verify):
            with self.assertRaises(ValueError):
                upgrade.apply(self.package)
        self.assertEqual((upgrade.TARGET/'run.py').read_text(), 'old')
        self.assertFalse(self.active)
        upgrade.apply(self.package, rollback=True)
        self.assertFalse(self.active)

    def test_package_tampering_fails_check(self):
        (self.package/'run.py').write_text('tamper')
        with self.assertRaises(ValueError):
            upgrade.preflight(self.package)
        self.assertEqual(self.commands, [])

    def test_loaded_drift_blocks_before_any_control(self):
        original = upgrade.systemctl
        def drift(*args):
            if '--property=Id,NeedDaemonReload' in args:
                return 'NeedDaemonReload=yes'
            return original(*args)
        with patch.object(upgrade, 'systemctl', side_effect=drift):
            with self.assertRaises(ValueError):
                upgrade.apply(self.package)
        self.assertFalse(any(c[0] == 'stop' for c in self.commands))

    def test_check_is_read_only_no_files_or_metadata_changed(self):
        def snapshot():
            return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        before = snapshot()
        result = upgrade.preflight(self.package)
        self.assertEqual(len(result['eligible_incidents']), 2)
        self.assertEqual(result['admin_delivery_attempts'], 0)
        self.assertEqual(before, snapshot())
        self.assertFalse(any(c[0] in ('stop', 'start', 'daemon-reload') for c in self.commands))

    def test_live_database_failure_or_attempts_refuse_before_control(self):
        for sql in ("UPDATE outbox SET attempts=1", "INSERT INTO attempts(outbox,started,result) SELECT id,1,'ATTEMPTED' FROM outbox LIMIT 1",
                    "UPDATE incidents SET evidence='{}'", "UPDATE outbox SET acknowledged=1",
                    "UPDATE incidents SET last_sent=1"):
            with self.subTest(sql=sql):
                path = upgrade.STATE/'admin.sqlite'; original = path.read_bytes()
                db = sqlite3.connect(path)
                db.execute(sql); db.commit(); db.close()
                with self.assertRaises(ValueError):
                    upgrade.apply(self.package)
                path.write_bytes(original)
        self.assertFalse(any(c[0] in ('stop', 'start') for c in self.commands))

    def test_scan_locked_or_sidecar_refuses_read_only_check(self):
        import fcntl
        with (upgrade.STATE/'scan.lock').open('rb') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                upgrade.preflight(self.package)
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = upgrade.STATE/('admin.sqlite'+suffix); sidecar.touch()
            with self.assertRaises(ValueError):
                upgrade.preflight(self.package)
            sidecar.unlink()

    def test_output_route_drift_refuses(self):
        original = upgrade.systemctl
        def drift(*args):
            return 'journal' if '--property=StandardOutput' in args else original(*args)
        with patch.object(upgrade, 'systemctl', side_effect=drift):
            with self.assertRaises(ValueError):
                upgrade.apply(self.package)
        self.assertFalse(any(c[0] == 'stop' for c in self.commands))

    def test_direct_v1_migration_keeps_history_and_rollback_keeps_migrated_db(self):
        review = upgrade.preflight(self.package)
        upgrade.apply(self.package)
        store = Store(upgrade.STATE)
        before = {name: [tuple(r) for r in store.db.execute('SELECT * FROM '+name)]
                  for name in ('metadata', 'occurrences', 'attempts')}
        self.assertEqual(store.invalidate_legacy_output(NOW+1), 2)
        self.assertEqual(before, {name: [tuple(r) for r in store.db.execute('SELECT * FROM '+name)] for name in before})
        self.assertEqual(set(review['eligible_incidents']), {r[0] for r in store.db.execute('SELECT incident FROM invalidations')})
        self.assertEqual({r[0] for r in store.db.execute('SELECT state FROM outbox')}, {'SUPERSEDED'})
        store.close()
        digest = upgrade.sha(upgrade.STATE/'admin.sqlite')
        upgrade.apply(self.package, rollback=True)
        self.assertEqual(digest, upgrade.sha(upgrade.STATE/'admin.sqlite'))
        self.assertFalse(self.active)  # Old lifecycle code cannot safely run on invalidations.
        self.assertTrue((upgrade.STATE/'DISABLED').is_file())
