"""V1.3.1 idle, conservative invalidation and immutable existing epoch regressions."""
from dataclasses import replace
import json
import time
from unittest.mock import Mock, patch

from test_monitor import Temporary, NOW, FakeTransport
from app.admin_alerts.activation import prepare_epoch, resume_projection, resume
from app.admin_alerts.delivery import SenderConfig, DeliveryError, dispatch, run_delivery
from app.admin_alerts.model import Event, DISCOVERY
from app.admin_alerts.store import Store


class IdleTests(Temporary):
    def setUp(self):
        super().setUp()
        self.store = Store(self.root)
        self.addCleanup(lambda: self.store.close())
        self.sender = SenderConfig(True, '', 99, 'AdminBot', 123, True)
        prepare_epoch(self.store.db, NOW-10)
        self.old = Event('monitor', 'ADMIN_DELIVERY_DEGRADED', 'admin', 'UNKNOWN', NOW,
                         'admin-transport', facts={'code': 'UNKNOWN'})
        self.transport = Mock()
        self.transport.validate.side_effect = AssertionError('NO VALIDATION')
        self.transport.send.side_effect = AssertionError('NO SEND')
        self.factory = Mock(return_value=self.transport)
        self.network = patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('NO NETWORK'))
        self.network.start(); self.addCleanup(self.network.stop)

    def run_idle(self):
        return run_delivery(self.store, self.sender, NOW+1, deadline=time.monotonic()+30, factory=self.factory)

    def seed(self, event=None):
        self.store.ingest([event or self.old], {}, NOW)
        self.store.enqueue(NOW)

    def tables(self, names):
        return {name: list(map(tuple, self.store.db.execute('SELECT * FROM '+name))) for name in names}

    def test_idle_report_no_incident_outbox_attempt_or_transport(self):
        before = self.tables(('incidents','outbox','attempts','source_evidence'))
        self.assertEqual(self.run_idle(), (0, {'code':'IDLE_NO_DELIVERY_WORK','transport_verified_this_scan':False}))
        self.assertEqual(before, self.tables(before))
        self.transport.validate.assert_not_called()
        self.transport.send.assert_not_called()
        self.assertIsNone(self.store.get('delivery'))

    def test_scan_reports_idle_and_does_not_create_delivery_incident(self):
        from app.admin_alerts.cli import scan
        mocks = {'systemd': {}, 'service_rules': ([], {}), 'tail': ([], [], {}, 0),
                 'journal': ([], {}), 'health_rows': ([], {}), 'unresolved': ([], {}),
                 'weekly_unresolved': ([], {}), 'configured_release': 'UNKNOWN'}
        with patch.multiple('app.admin_alerts.cli', **{k:Mock(return_value=v) for k,v in mocks.items()}), patch('app.admin_alerts.cli.Telegram', self.factory):
            scan({'stdout':'unused','health_database':'unused','ledger_database':'unused','release_environment':'unused',
                  'sender':self.sender.__dict__}, self.root, no_send=False)
        report = json.loads((self.root/'incident-report.json').read_text())
        self.assertEqual(report['admin_delivery']['code'], 'IDLE_NO_DELIVERY_WORK')
        self.assertFalse(report['incidents'])
        self.transport.validate.assert_not_called()
        self.transport.send.assert_not_called()
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0], 0)

    def test_idle_preserves_every_real_failure(self):
        for code in ('TOKEN_INVALID','BOT_IDENTITY_MISMATCH','PRIVATE_DESTINATION_MISMATCH',
                     'TRANSPORT_UNCERTAIN','INVALID_RECEIPT','SECRET_UNAVAILABLE'):
            with self.subTest(code=code):
                with self.store.db:
                    self.store.put('delivery', {'code':code,'permanent':True,'next':0})
                self.assertEqual(self.run_idle()[1]['code'], code)
                row = self.store.db.execute("SELECT * FROM incidents WHERE rule='ADMIN_DELIVERY_DEGRADED'").fetchone()
                self.assertNotEqual(row['state'], 'RECOVERED')
        self.transport.validate.assert_not_called()
        self.transport.send.assert_not_called()

    def test_no_state_does_not_hide_retained_real_error(self):
        self.seed(replace(self.old, occurrence='TRANSPORT_UNCERTAIN', facts={'code':'TRANSPORT_UNCERTAIN'}))
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET state='EXHAUSTED',attempts=5")
        self.assertEqual(self.run_idle()[1]['code'],'TRANSPORT_UNCERTAIN')
        self.assertEqual(self.store.invalidate_idle_delivery(NOW+1),0)

    def test_real_receipt_health_then_idle_does_not_claim_new_verification(self):
        self.seed(Event(DISCOVERY, 'TIMER_INACTIVE','timer','fault',NOW,'systemd'))
        fake=FakeTransport()
        sent,state=run_delivery(self.store,self.sender,NOW+1,deadline=time.monotonic()+30,factory=lambda c:fake)
        self.assertEqual((sent,state['code']),(1,'HEALTHY'))
        self.assertEqual(self.run_idle()[1]['code'],'IDLE_NO_DELIVERY_WORK')
        self.assertEqual(self.store.get('delivery')['code'],'HEALTHY')

    def test_validation_and_constructor_errors_still_degrade(self):
        self.seed(Event(DISCOVERY, 'TIMER_INACTIVE','timer','fault',NOW,'systemd'))
        for code in ('TOKEN_INVALID','BOT_IDENTITY_MISMATCH','PRIVATE_DESTINATION_MISMATCH','TRANSPORT_UNCERTAIN'):
            with self.subTest(code=code):
                with self.store.db:
                    self.store.db.execute("DELETE FROM metadata WHERE key='delivery'")
                transport=Mock();transport.validate.side_effect=DeliveryError(code)
                sent,state=run_delivery(self.store,self.sender,NOW+1,deadline=time.monotonic()+30,factory=lambda c:transport)
                self.assertEqual((sent,state['code']),(0,code))
                transport.send.assert_not_called()
                self.assertTrue(self.store.db.execute("SELECT 1 FROM incidents WHERE rule='ADMIN_DELIVERY_DEGRADED' AND state!='RECOVERED'").fetchone())
        factory=Mock(side_effect=OSError())
        self.assertEqual(run_delivery(self.store,self.sender,NOW+1,deadline=time.monotonic()+30,factory=factory)[1]['code'],'SECRET_UNAVAILABLE')

    def test_cleanup_preserves_evidence_epoch_and_audits_original_outbox(self):
        self.seed()
        before = self.tables(('notification_epochs','epoch_incidents','occurrences','source_evidence','attempts'))
        incident=dict(self.store.db.execute('SELECT * FROM incidents').fetchone())
        outbox=[dict(r) for r in self.store.db.execute('SELECT * FROM outbox')]
        self.assertEqual(self.store.invalidate_idle_delivery(NOW+1),1)
        self.assertEqual(before,self.tables(before))
        row=dict(self.store.db.execute('SELECT * FROM incidents').fetchone())
        self.assertEqual(row,{**incident,'state':'INVALIDATED'})
        audit=self.store.db.execute('SELECT * FROM invalidations').fetchone()
        self.assertEqual(json.loads(audit['original_incident']),incident)
        self.assertEqual(json.loads(audit['original_outbox']),outbox)
        self.assertEqual(json.loads(audit['evidence'])['reason'],'IDLE_NO_DELIVERY_WORK_NOT_TRANSPORT_FAILURE')
        self.assertEqual(self.store.db.execute('SELECT state FROM outbox').fetchone()[0],'SUPERSEDED')
        self.assertEqual(json.loads(self.store.db.execute('SELECT original_outbox FROM notification_audit').fetchone()[0]),outbox[0])
        self.assertEqual(self.store.invalidate_idle_delivery(NOW+2),0)
        self.assertEqual(self.run_idle()[1]['code'],'IDLE_NO_DELIVERY_WORK')

    def test_real_fault_and_recovery_after_tombstone(self):
        self.seed(); self.store.invalidate_idle_delivery(NOW+1)
        with self.store.db:
            self.store.put('delivery',{'code':'TRANSPORT_UNCERTAIN','next':0})
        self.run_idle()
        self.store.enqueue(NOW+2)
        sent,state=run_delivery(self.store,self.sender,NOW+3,deadline=time.monotonic()+30,factory=lambda c:FakeTransport())
        self.assertEqual((sent,state['code']),(1,'HEALTHY'))
        self.assertEqual(sorted(r[0] for r in self.store.db.execute('SELECT state FROM incidents')),['INVALIDATED','RECOVERED'])

    def test_attempted_uncertain_receipt_or_contradiction_never_invalidated(self):
        self.seed()
        mutations = ["UPDATE outbox SET attempts=1", "UPDATE outbox SET state='UNCERTAIN'",
                     "UPDATE outbox SET acknowledged=1", "UPDATE outbox SET receipt='{}'",
                     "UPDATE outbox SET error='TRANSPORT_UNCERTAIN'",
                     "INSERT INTO attempts(outbox,started,result) SELECT id,1,'ATTEMPTED' FROM outbox",
                     "UPDATE incidents SET evidence=replace(evidence,'UNKNOWN','TRANSPORT_UNCERTAIN')",
                     "UPDATE occurrences SET source='other'",
                     "INSERT INTO metadata VALUES ('delivery','{}')"]
        for sql in mutations:
            with self.subTest(sql=sql):
                self.store.db.execute('SAVEPOINT fixture')
                self.store.db.execute(sql)
                from app.admin_alerts.invalidation import idle_eligible
                row=self.store.db.execute('SELECT * FROM incidents').fetchone()
                self.assertFalse(idle_eligible(self.store.db,row))
                self.store.db.execute('ROLLBACK TO fixture');self.store.db.execute('RELEASE fixture')
        self.assertEqual(self.store.invalidate_idle_delivery(NOW+1),1)

    def test_epoch_suppressed_work_does_not_validate(self):
        # A pending row from the activation episode must be filtered before validate.
        self.store.close()
        sub=self.root/'old';sub.mkdir();self.store=Store(sub)
        self.seed(Event(DISCOVERY,'TIMER_INACTIVE','timer','old',NOW,'systemd'))
        prepare_epoch(self.store.db,NOW+1)
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET state='PENDING'")
        transport=Mock();transport.validate.side_effect=AssertionError('NO VALIDATION')
        self.assertEqual(dispatch(self.store,self.sender,transport,NOW+2),0)
        transport.validate.assert_not_called()

    def test_missing_token_is_real_configuration_failure_even_without_work(self):
        sender=replace(self.sender,token_file=str(self.root/'missing-token'))
        sent,state=run_delivery(self.store,sender,NOW+1,deadline=time.monotonic()+30)
        self.assertEqual(sent,0)
        self.assertEqual(state['code'],'SECRET_FILE_PERMISSIONS')
        self.assertTrue(self.store.db.execute("SELECT 1 FROM incidents WHERE rule='ADMIN_DELIVERY_DEGRADED' AND state='OPEN'").fetchone())
