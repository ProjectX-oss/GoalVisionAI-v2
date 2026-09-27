"""Disposable direct upgrade, resume, failures and rollback; ADMIN control is fake."""
import importlib.util
import json
from unittest.mock import patch
from test_monitor import Temporary, NOW, FakeTransport
from test_upgrade_v1_2 import manifest
from app.admin_alerts.activation import prepare_epoch, resume_projection
from app.admin_alerts.delivery import SenderConfig, dispatch
from app.admin_alerts.model import Event, DISCOVERY
from app.admin_alerts.store import Store

spec=importlib.util.spec_from_file_location('admin_control_v131','operations/admin-alerts/control_v1_3_1.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)


class ResumeOperationsTests(Temporary):
    def setUp(self):
        super().setUp()
        for name in ('TARGET','STATE','UNIT_ROOT'):
            path=self.root/name;path.mkdir()
            p=patch.object(control,name,path);p.start();self.addCleanup(p.stop)
        for name in ('BACKUP','STAGE','TRANSACTION','CONFIG'):
            p=patch.object(control,name,self.root/name);p.start();self.addCleanup(p.stop)
        token=self.root/'token';token.write_text('99:'+'x'*30);token.chmod(0o600)
        control.CONFIG.write_text(json.dumps({'sender':{'enabled':False,'token_file':str(token),
            'bot_id':99,'bot_username':'AdminBot','private_chat_id':123,'operator_confirmed_start':True}}))
        (control.STATE/'scan.lock').touch()
        store=Store(control.STATE)
        store.ingest([Event(DISCOVERY,'TIMER_INACTIVE','timer','old',NOW-20,'systemd')],{},NOW-20)
        store.enqueue(NOW-20);prepare_epoch(store.db,NOW-10)
        store.ingest([Event('monitor','ADMIN_DELIVERY_DEGRADED','admin','UNKNOWN',NOW,
                           'admin-transport',facts={'code':'UNKNOWN'})],{},NOW)
        store.enqueue(NOW);store.close()
        (control.TARGET/'run.py').write_text('v1.3')
        old=manifest(control.TARGET)
        self.package=self.root/'package';self.package.mkdir()
        (self.package/'run.py').write_text('v1.3.1')
        (self.package/'v1-3-SHA256SUMS').write_text(old)
        units={}
        for name in control.ADMIN:
            (control.UNIT_ROOT/name).write_text(name);units[name]=control.sha(control.UNIT_ROOT/name)
        (self.package/'upgrade-baseline.json').write_text(json.dumps({'admin_units':units}))
        manifest(self.package)
        self.active=True;self.commands=[]
        def systemctl(action,*units):
            self.commands.append((action,*units))
            self.assertTrue(units and all(u in control.ADMIN for u in units))
            if action=='show':return 'active' if self.active else 'inactive'
            if control.ADMIN[0] in units:self.active=action=='start'
            return ''
        for p in (patch.object(control,'systemctl',side_effect=systemctl),patch('os.geteuid',return_value=0),
                  patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('NO NETWORK'))):
            p.start();self.addCleanup(p.stop)

    def snapshot(self):
        return {str(p):(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}

    def ready(self):
        control.change(self.package,'upgrade')
        store=Store(control.STATE)
        self.assertEqual(store.invalidate_idle_delivery(NOW+1),1)
        store.close()

    def sender(self):return json.loads(control.CONFIG.read_text())['sender']['enabled']

    def test_direct_upgrade_preserves_every_db_byte_config_token(self):
        before=self.snapshot()
        review=control.inspect(self.package,installed='v1.3')
        self.assertFalse(review['resume_ready'])
        self.assertEqual(before,self.snapshot())
        raw=(control.STATE/'admin.sqlite').read_bytes();config=control.CONFIG.read_bytes()
        control.change(self.package,'upgrade')
        self.assertEqual(raw,(control.STATE/'admin.sqlite').read_bytes())
        self.assertEqual(config,control.CONFIG.read_bytes())
        self.assertEqual((control.TARGET/'run.py').read_text(),'v1.3.1')
        self.assertFalse(self.sender());self.assertTrue(self.active)
        self.assertFalse((control.STATE/'DISABLED').exists())

    def test_prepare_resume_readonly_requires_cleanup_then_reports_ready(self):
        control.change(self.package,'upgrade')
        before=self.snapshot();review=control.inspect(self.package,installed='v1.3.1')
        self.assertEqual(before,self.snapshot());self.assertFalse(review['resume_ready'])
        with self.assertRaises(ValueError):control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        store=Store(control.STATE);store.invalidate_idle_delivery(NOW+1);store.close()
        before=self.snapshot();review=control.inspect(self.package,installed='v1.3.1')
        self.assertEqual(before,self.snapshot());self.assertTrue(review['resume_ready'])
        self.assertEqual(review['attempted_notifications'],0)
        self.assertEqual(review['superseded_notifications'],2)
        self.assertEqual(review['active_actionable_post_epoch_incidents'],[])
        self.assertEqual(review['activation_review_required'],[])

    def test_resume_exact_confirmation_no_db_changes_restart_and_real_future_send(self):
        self.ready()
        for confirm in (None,'',control.CONFIRM,control.RESUME_CONFIRM+' '):
            with self.assertRaises(ValueError):control.change(self.package,'resume-sender',confirm)
            self.assertFalse(self.sender())
        raw=(control.STATE/'admin.sqlite').read_bytes()
        with patch('app.admin_alerts.activation.prepare_epoch',side_effect=AssertionError('NO NEW EPOCH')):
            result=control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        self.assertTrue(result['sender_enabled']);self.assertTrue(self.sender());self.assertTrue(self.active)
        self.assertEqual(raw,(control.STATE/'admin.sqlite').read_bytes())
        store=Store(control.STATE)
        store.enqueue(NOW+3)
        sender=SenderConfig(**json.loads(control.CONFIG.read_text())['sender']);fake=FakeTransport()
        self.assertEqual(dispatch(store,sender,fake,NOW+3),0)
        store.ingest([Event(DISCOVERY,'PROVIDER_FAILURE','new','new',NOW+4,'health')],{},NOW+4)
        store.enqueue(NOW+4)
        self.assertEqual(dispatch(store,sender,fake,NOW+4),1)
        store.close()
        self.assertTrue(all(u in control.ADMIN for cmd in self.commands for u in cmd[1:]))

    def test_enable_replay_refused_and_resume_enabled_refused(self):
        self.ready()
        with self.assertRaisesRegex(ValueError,'ACTIVATION_REPLAY'):
            control.change(self.package,'enable-sender',control.CONFIRM)
        control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        with self.assertRaises(ValueError):control.change(self.package,'resume-sender',control.RESUME_CONFIRM)

    def test_resume_config_failure_restores_false_and_fences(self):
        self.ready();raw=(control.STATE/'admin.sqlite').read_bytes()
        from app.admin_alerts.activation import write_config
        def fail(path,value):
            write_config(path,value)
            if value['sender']['enabled']:raise OSError('after replace')
        with patch('app.admin_alerts.activation.write_config',side_effect=fail):
            with self.assertRaises(OSError):control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        self.assertFalse(self.sender());self.assertFalse(self.active)
        self.assertTrue((control.STATE/'DISABLED').exists())
        self.assertEqual(raw,(control.STATE/'admin.sqlite').read_bytes())

    def test_timer_restore_failure_restores_false_and_fences(self):
        self.ready();real=control.systemctl
        def fail(action,*units):
            if action=='start':raise OSError('timer start')
            return real(action,*units)
        with patch.object(control,'systemctl',side_effect=fail):
            with self.assertRaises(OSError):control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        self.assertFalse(self.sender());self.assertFalse(self.active)
        self.assertTrue((control.STATE/'DISABLED').exists())

    def test_error_cleanup_disables_even_when_stop_fails(self):
        self.ready();real=control.systemctl;starts=[]
        def fail(action,*units):
            if action=='start':starts.append(True);raise OSError('start')
            if action=='stop' and starts:raise OSError('stop')
            return real(action,*units)
        with patch.object(control,'systemctl',side_effect=fail):
            with self.assertRaises(OSError):control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        self.assertFalse(self.sender());self.assertTrue((control.STATE/'DISABLED').exists())

    def test_inactive_timer_stays_inactive_and_rollback_preserves_db_fences_disables(self):
        self.ready();self.active=False
        control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        self.assertTrue(self.sender());self.assertFalse(self.active)
        raw=(control.STATE/'admin.sqlite').read_bytes()
        control.change(self.package,'rollback')
        self.assertEqual(raw,(control.STATE/'admin.sqlite').read_bytes())
        self.assertEqual((control.TARGET/'run.py').read_text(),'v1.3')
        self.assertFalse(self.sender());self.assertTrue((control.STATE/'DISABLED').exists())

    def test_malformed_epoch_and_config_fence_or_tamper_block_resume(self):
        self.ready()
        config=json.loads(control.CONFIG.read_text())
        for key,value in (('enabled',True),('operator_confirmed_start',False),('operator_confirmed_start','true'),('private_chat_id',-123),('bot_id',100)):
            with self.subTest(key=key):
                altered=json.loads(json.dumps(config));altered['sender'][key]=value
                control.CONFIG.write_text(json.dumps(altered))
                self.assertFalse(control.inspect(self.package,installed='v1.3.1')['resume_ready'])
        control.CONFIG.write_text(json.dumps(config))
        (control.STATE/'DISABLED').touch()
        self.assertFalse(control.inspect(self.package,installed='v1.3.1')['resume_ready'])
        (control.STATE/'DISABLED').unlink()
        with control.snapshot() as db:
            raw=db.serialize()
        import sqlite3
        for sql in ("UPDATE notification_epochs SET id='wrong'", "UPDATE notification_epochs SET policy='wrong'",
                    "INSERT INTO notification_epochs VALUES ('extra',1,'wrong')",
                    "UPDATE epoch_incidents SET episode_at_activation=NULL",
                    "UPDATE epoch_incidents SET epoch='wrong'",
                    "INSERT INTO epoch_incidents VALUES ('missing','ADMIN_NOTIFICATION_EPOCH_V1',1,1)",
                    "DELETE FROM notification_epochs"):
            with self.subTest(sql=sql):
                db=sqlite3.connect(':memory:');db.deserialize(raw);db.row_factory=sqlite3.Row
                for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall():db.execute('DROP TRIGGER '+row[0])
                db.execute(sql)
                self.assertFalse(resume_projection(db,config)['resume_ready']);db.close()
        (control.TARGET/'run.py').write_text('tampered')
        with self.assertRaises(ValueError):control.change(self.package,'resume-sender',control.RESUME_CONFIRM)

    def test_control_rejects_prematch_and_daemon_reload(self):
        spec=importlib.util.spec_from_file_location('raw_control131','operations/admin-alerts/control_v1_3_1.py')
        raw=importlib.util.module_from_spec(spec);spec.loader.exec_module(raw)
        with self.assertRaises(ValueError):raw.systemctl('stop',DISCOVERY)
        with self.assertRaises(ValueError):raw.systemctl('daemon-reload')

    def test_disable_then_resume_and_readonly_cli(self):
        self.ready()
        with patch('sys.argv',['control','prepare-resume']),patch.object(control,'inspect',wraps=lambda *a,**k: {'resume_ready':True}),patch('builtins.print'):
            self.assertEqual(control.main(),0)
        control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        control.change(self.package,'disable-sender')
        self.assertFalse(self.sender());self.assertTrue(self.active)
        control.change(self.package,'resume-sender',control.RESUME_CONFIRM)
        self.assertTrue(self.sender())
