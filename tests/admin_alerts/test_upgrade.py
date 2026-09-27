"""Exercise atomic ADMIN replacement and rollback on temporary directories only."""
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from test_monitor import Temporary

spec = importlib.util.spec_from_file_location('admin_upgrade', 'operations/admin-alerts/upgrade_v1_1.py')
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


def manifest(root):
    value = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}\n'
                    for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS')
    (root/'SHA256SUMS').write_text(value)
    return value


class UpgradeTests(Temporary):
    def setUp(self):
        super().setUp()
        for name in ('TARGET', 'STATE', 'UNIT_ROOT'):
            path = self.root/name; path.mkdir()
            patcher = patch.object(upgrade, name, path); patcher.start(); self.addCleanup(patcher.stop)
        for name in ('BACKUP', 'STAGE', 'TRANSACTION', 'CONFIG'):
            patcher = patch.object(upgrade, name, self.root/name); patcher.start(); self.addCleanup(patcher.stop)
        upgrade.CONFIG.write_text('{"sender":{"enabled":false}}')
        (upgrade.STATE/'admin.sqlite').write_bytes(b'existing incident outbox cursors')
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
            'admin_units': units, 'protected_sha256': {str(self.protected): upgrade.sha(self.protected)}}))
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
        self.assertTrue(self.active)
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
        self.assertTrue(self.active)

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
