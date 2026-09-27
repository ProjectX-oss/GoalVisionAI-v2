"""Full disposable direct-upgrade/activation/rollback workflow; no host control."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from test_monitor import Temporary, NOW
from test_upgrade_v1_2 import manifest
from app.admin_alerts.model import Event, DISCOVERY
from app.admin_alerts.store import Store

spec = importlib.util.spec_from_file_location('admin_control_v13', 'operations/admin-alerts/control_v1_3.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class OperationsTests(Temporary):
    def setUp(self):
        super().setUp()
        for name in ('TARGET', 'STATE', 'UNIT_ROOT'):
            path = self.root/name; path.mkdir()
            p = patch.object(control, name, path); p.start(); self.addCleanup(p.stop)
        for name in ('BACKUP','STAGE','TRANSACTION','CONFIG'):
            p = patch.object(control, name, self.root/name); p.start(); self.addCleanup(p.stop)
        self.token = self.root/'token'; self.token.write_text('99:'+'x'*30); self.token.chmod(0o600)
        control.CONFIG.write_text(json.dumps({'sender': {'enabled':False,'token_file':str(self.token),
            'bot_id':99,'bot_username':'AdminBot','private_chat_id':123,'operator_confirmed_start':True}}))
        control.CONFIG.chmod(0o640)
        (control.STATE/'scan.lock').touch()
        store = Store(control.STATE)
        store.ingest([Event(DISCOVERY, 'SERVICE_FAILURE', 'pipeline', 'a', NOW, 'journal', invocation='a'*32)],
                     {'ledger':{'after':'old-cursor'},'journal':{'cursor':'s=old'}}, NOW)
        store.enqueue(NOW)
        # Drop v1.3-only tables: exact v1.2 schema shape, including retained audits.
        with store.db:
            for table in ('source_evidence','correlation_audit','notification_audit','notification_epochs','epoch_incidents'):
                store.db.execute('DROP TABLE '+table)
        store.close()
        (control.TARGET/'run.py').write_text('v1.2')
        old = manifest(control.TARGET)
        self.package = self.root/'package'; self.package.mkdir()
        (self.package/'run.py').write_text('v1.3')
        (self.package/'v1-2-SHA256SUMS').write_text(old)
        units = {}
        for name in control.ADMIN:
            (control.UNIT_ROOT/name).write_text(name)
            units[name] = control.sha(control.UNIT_ROOT/name)
        (self.package/'upgrade-baseline.json').write_text(json.dumps({'admin_units':units}))
        manifest(self.package)
        self.commands=[]; self.active=True
        def systemctl(action,*units):
            self.commands.append((action,*units))
            self.assertIn(action, ('show','stop','start'))
            self.assertTrue(all(u in control.ADMIN for u in units))
            if action=='show': return 'active' if self.active else 'inactive'
            if control.ADMIN[0] in units: self.active=action=='start'
            return ''
        for p in (patch.object(control,'systemctl',side_effect=systemctl),patch('os.geteuid',return_value=0)):
            p.start();self.addCleanup(p.stop)

    def snapshot(self):
        return {str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}

    def test_readonly_check_upgrade_preserves_v12_db_config_token_and_cursors(self):
        before=self.snapshot()
        result=control.inspect(self.package,installed='v1.2')
        self.assertEqual(before,self.snapshot())
        self.assertFalse(result['sender_enabled'])
        db_before=(control.STATE/'admin.sqlite').read_bytes()
        config_before=control.CONFIG.read_bytes(); token_before=self.token.read_bytes()
        control.change(self.package,'upgrade')
        self.assertEqual((control.TARGET/'run.py').read_text(),'v1.3')
        self.assertEqual(db_before,(control.STATE/'admin.sqlite').read_bytes())
        self.assertEqual(config_before,control.CONFIG.read_bytes())
        self.assertEqual(token_before,self.token.read_bytes())
        self.assertTrue(self.active)
        self.assertFalse((control.STATE/'DISABLED').exists())
        before=self.snapshot()
        control.inspect(self.package,installed='v1.3')
        self.assertEqual(before,self.snapshot())
        self.assertTrue(all(u in control.ADMIN for cmd in self.commands for u in cmd[1:]))

    def test_activation_separate_confirmation_epoch_disable_and_safe_rollback(self):
        control.change(self.package,'upgrade')
        with self.assertRaises(ValueError):
            control.change(self.package,'enable-sender')
        self.assertFalse(json.loads(control.CONFIG.read_text())['sender']['enabled'])
        result=control.change(self.package,'enable-sender',control.CONFIRM)
        self.assertTrue(result['sender_enabled'])
        self.assertTrue(json.loads(control.CONFIG.read_text())['sender']['enabled'])
        with self.assertRaises(ValueError):
            control.change(self.package,'enable-sender',control.CONFIRM)
        store=Store(control.STATE)
        self.assertEqual(store.db.execute('SELECT count(*) FROM notification_epochs').fetchone()[0],1)
        self.assertEqual(store.db.execute('SELECT state FROM outbox').fetchone()[0],'SUPERSEDED')
        self.assertEqual(store.get('ledger'),{'after':'old-cursor'})
        store.close()
        control.change(self.package,'disable-sender')
        self.assertFalse(json.loads(control.CONFIG.read_text())['sender']['enabled'])
        self.assertTrue(self.active)
        before=(control.STATE/'admin.sqlite').read_bytes()
        control.change(self.package,'rollback')
        self.assertEqual((control.TARGET/'run.py').read_text(),'v1.2')
        self.assertEqual(before,(control.STATE/'admin.sqlite').read_bytes())
        self.assertTrue((control.STATE/'DISABLED').exists())
        self.assertFalse(self.active)

    def test_epoch_audit_failure_keeps_sender_false_and_admin_fenced(self):
        control.change(self.package,'upgrade')
        with patch('app.admin_alerts.activation.prepare_epoch',side_effect=OSError('secret failure')):
            with self.assertRaises(OSError):
                control.change(self.package,'enable-sender',control.CONFIRM)
        self.assertFalse(json.loads(control.CONFIG.read_text())['sender']['enabled'])
        self.assertTrue((control.STATE/'DISABLED').exists())
        self.assertFalse(self.active)

    def test_config_failure_after_replace_restores_false_and_leaves_fence(self):
        control.change(self.package,'upgrade')
        from app.admin_alerts.activation import write_config
        def broken(path,config):
            write_config(path,config)
            if config['sender']['enabled']:
                raise OSError('synthetic fsync failure after replace')
        with patch('app.admin_alerts.activation.write_config',side_effect=broken):
            with self.assertRaises(OSError):
                control.change(self.package,'enable-sender',control.CONFIRM)
        self.assertFalse(json.loads(control.CONFIG.read_text())['sender']['enabled'])
        self.assertTrue((control.STATE/'DISABLED').exists())

    def test_tamper_enabled_sender_sidecar_and_lock_block_before_control(self):
        config=control.CONFIG.read_text()
        value=json.loads(config);value['sender']['enabled']=True
        control.CONFIG.write_text(json.dumps(value))
        with self.assertRaises(ValueError): control.change(self.package,'upgrade')
        control.CONFIG.write_text(config)
        sidecar=control.STATE/'admin.sqlite-wal';sidecar.touch()
        with self.assertRaises(ValueError): control.inspect(self.package,installed='v1.2')
        sidecar.unlink()
        with control.scan_lock():
            with self.assertRaises(BlockingIOError): control.inspect(self.package,installed='v1.2')
        (control.TARGET/'run.py').write_text('tampered')
        with self.assertRaises(ValueError): control.change(self.package,'upgrade')
        self.assertFalse(any(c[0] in ('start','stop') for c in self.commands))

    def test_control_allowlist_and_sanitized_failure_output(self):
        # Reach the real wrapper, not the fake injected by setUp.
        wrapper_spec=importlib.util.spec_from_file_location('admin_control_wrapper_v13', 'operations/admin-alerts/control_v1_3.py')
        wrapper=importlib.util.module_from_spec(wrapper_spec)
        wrapper_spec.loader.exec_module(wrapper)
        with self.assertRaises(ValueError): wrapper.systemctl('stop','goalvision-lab-v2-discover.service')
        with self.assertRaises(ValueError): wrapper.systemctl('daemon-reload')
        with patch('sys.argv',['control_v1_3.py','prepare-enable']), patch.object(control,'inspect',side_effect=OSError('secret-token-private-config')), patch('builtins.print') as output:
            self.assertEqual(control.main(),1)
        rendered=str(output.call_args)
        self.assertNotIn('secret-token',rendered)
        self.assertNotIn('private-config',rendered)

    def test_disable_works_with_missing_token_and_keeps_existing_fence(self):
        control.change(self.package,'upgrade')
        self.token.unlink()
        (control.STATE/'DISABLED').touch()
        control.change(self.package,'disable-sender')
        self.assertFalse(json.loads(control.CONFIG.read_text())['sender']['enabled'])
        self.assertTrue((control.STATE/'DISABLED').exists())

    def test_activation_timer_start_failure_restores_disabled_configuration(self):
        control.change(self.package,'upgrade')
        real=control.systemctl
        def fail_start(action,*units):
            if action=='start':
                raise OSError('timer unavailable')
            return real(action,*units)
        with patch.object(control,'systemctl',side_effect=fail_start):
            with self.assertRaises(OSError):
                control.change(self.package,'enable-sender',control.CONFIRM)
        self.assertFalse(json.loads(control.CONFIG.read_text())['sender']['enabled'])
        self.assertTrue((control.STATE/'DISABLED').exists())
        self.assertFalse(self.active)
