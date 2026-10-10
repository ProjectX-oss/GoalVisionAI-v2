"""Offline typed quota correlation; disposable stores and fake transports only."""
from dataclasses import replace
from unittest.mock import patch

from test_monitor import Temporary, NOW, FakeTransport
from app.admin_alerts.correlation import groups
from app.admin_alerts.delivery import SenderConfig, dispatch
from app.admin_alerts.model import Event, DISCOVERY
from app.admin_alerts.store import Store

CODE = "QUOTA_DB_CONTENTION_EXHAUSTED"


class QuotaHealthCorrelationTests(Temporary):
    def setUp(self):
        super().setUp()
        self.store = Store(self.root)
        self.addCleanup(lambda: self.store.close())
        self.config = SenderConfig(True, "", 99, "AdminBot", 123, True)
        self.journal = Event(DISCOVERY, "QUOTA_DB_CONTENTION", "pipeline",
                             "journal-quota", NOW, "journal", invocation="a"*32,
                             facts={"code": CODE})
        self.health = replace(self.journal, occurrence="health-quota",
                              source="health-snapshot", invocation="UNKNOWN",
                              observed=NOW+0.004)

    def ingest(self, *events):
        now = max(event.observed for event in events) + 1
        self.store.ingest(list(events), {}, now)
        self.store.enqueue(now)

    def test_matching_typed_quota_groups_without_waiting_for_service_failure(self):
        self.ingest(self.journal, self.health)
        result = groups(self.store.db)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["associations"][self.health.signature],
                         "UNIQUE_TEMPORAL_SAME_SERVICE_QUOTA_CODE")
        self.assertEqual(self.store.db.execute(
            "SELECT invocation FROM incidents WHERE id=?", (self.health.signature,)
        ).fetchone()[0], "UNKNOWN")
        fake = FakeTransport()
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+60), 1)

    def test_four_realistic_executions_keep_sixteen_incidents_and_four_alerts(self):
        fake = FakeTransport()
        for index, offset in enumerate((0, 3600, 9000, 10800)):
            event = replace(self.journal, observed=NOW+offset,
                            invocation=f"{index+1:032x}", occurrence=f"journal-{index}")
            self.ingest(event,
                        replace(self.health, observed=event.observed+0.004,
                                occurrence=f"health-{index}"),
                        replace(event, rule="SERVICE_FAILURE", observed=event.observed+2.5),
                        replace(event, rule="MISSING_OUTPUT", observed=event.observed+213))
            self.assertEqual(dispatch(self.store, self.config, fake, event.observed+220), 1)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM incidents").fetchone()[0], 16)
        self.assertEqual(len(groups(self.store.db)), 4)
        self.assertEqual(dispatch(self.store, self.config, fake, NOW+11000), 0)
        self.assertEqual(len(fake.messages), 4)

    def test_arrival_order_and_late_health_do_not_repeat_acknowledged_alert(self):
        for first, second in ((self.journal, self.health), (self.health, self.journal)):
            with self.subTest(first=first.source):
                self.store.close()
                root = self.root/first.source
                root.mkdir()
                self.store = Store(root)
                self.ingest(first)
                fake = FakeTransport()
                self.assertEqual(dispatch(self.store, self.config, fake, NOW+60), 1)
                old = list(map(tuple, self.store.db.execute("SELECT * FROM outbox")))
                attempts = list(map(tuple, self.store.db.execute("SELECT * FROM attempts")))
                self.ingest(second)
                self.assertEqual(dispatch(self.store, self.config, fake, NOW+120), 0)
                self.assertEqual(old, list(map(tuple, self.store.db.execute("SELECT * FROM outbox"))))
                self.assertEqual(attempts, list(map(tuple, self.store.db.execute("SELECT * FROM attempts"))))

    def test_existing_duplicate_receipts_and_incident_identities_are_never_rewritten(self):
        # Disable only the new match during synthetic ingestion to model the
        # installed version's two already-acknowledged independent alerts.
        with patch("app.admin_alerts.correlation.QUOTA_HEALTH_CODE", "DISABLED", create=True):
            self.ingest(self.journal, self.health)
            self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+60), 2)
        originals = {table: list(map(tuple, self.store.db.execute(f"SELECT * FROM {table}")))
                     for table in ("incidents", "outbox", "attempts", "source_evidence")}
        self.store.enqueue(NOW+120)
        self.assertEqual(len(groups(self.store.db)), 1)
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+120), 0)
        for table, before in originals.items():
            self.assertEqual(before, list(map(tuple, self.store.db.execute(f"SELECT * FROM {table}"))))

    def test_uncertain_attempt_is_preserved_and_not_retried_via_other_source(self):
        self.ingest(self.health)
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET state='UNCERTAIN',attempts=1")
        old = list(map(tuple, self.store.db.execute("SELECT * FROM outbox")))
        self.ingest(self.journal)
        self.assertEqual(old, list(map(tuple, self.store.db.execute("SELECT * FROM outbox"))))
        self.assertEqual(dispatch(self.store, self.config, FakeTransport(), NOW+120), 0)

    def test_ambiguous_distinct_quota_invocations_stay_independent(self):
        self.ingest(self.journal, replace(self.journal, invocation="b"*32,
                                         observed=NOW+10), self.health)
        self.assertEqual(len(groups(self.store.db)), 3)

    def test_competing_service_failure_prevents_temporal_guess(self):
        self.ingest(self.journal, self.health, replace(self.journal,
                    rule="SERVICE_FAILURE", invocation="b"*32, observed=NOW+10))
        self.assertEqual(len(groups(self.store.db)), 3)

    def test_later_competitor_restores_independent_work_preserving_audit(self):
        self.ingest(self.journal, self.health)
        self.assertEqual(len(groups(self.store.db)), 1)
        audit = list(map(tuple, self.store.db.execute("SELECT * FROM correlation_audit")))
        self.ingest(replace(self.journal, invocation="b"*32, observed=NOW+10))
        self.assertEqual(len(groups(self.store.db)), 3)
        self.assertIsNotNone(self.store.db.execute(
            "SELECT 1 FROM outbox WHERE incident=? AND state='PENDING'",
            (self.health.signature,)).fetchone())
        after = list(map(tuple, self.store.db.execute("SELECT * FROM correlation_audit")))
        self.assertTrue(all(row in after for row in audit))

    def test_other_service_source_code_and_unattributed_quota_stay_independent(self):
        variants = (
            ("other-service", replace(self.journal, service="other.service"), self.health),
            ("not-journal", replace(self.journal, source="stdout"), self.health),
            ("not-health", self.journal, replace(self.health, source="stdout")),
            ("journal-code-missing", replace(self.journal, facts={}), self.health),
            ("health-code-missing", self.journal, replace(self.health, facts={})),
            ("other-code", self.journal, replace(self.health, facts={"code": "DATABASE_LOCK"})),
            ("unknown-journal", replace(self.journal, invocation="UNKNOWN"), self.health),
            ("service-only", replace(self.journal, rule="SERVICE_FAILURE"), self.health),
            ("outside-window", self.journal, replace(self.health, observed=NOW+30.001)),
        )
        for name, journal, health in variants:
            with self.subTest(name=name):
                self.store.close()
                root = self.root/name
                root.mkdir()
                self.store = Store(root)
                self.ingest(journal, health)
                self.assertEqual(len(groups(self.store.db)), 2)

    def test_exact_thirty_second_boundary_and_restart_are_deterministic(self):
        self.ingest(self.journal, replace(self.health, observed=NOW+30))
        self.assertEqual(len(groups(self.store.db)), 1)
        before = list(map(tuple, self.store.db.execute("SELECT * FROM correlation_audit")))
        self.store.close()
        self.store = Store(self.root)
        self.store.enqueue(NOW+120)
        self.assertEqual(len(groups(self.store.db)), 1)
        self.assertEqual(before, list(map(tuple, self.store.db.execute("SELECT * FROM correlation_audit"))))

    def test_same_invocation_repeated_journal_objects_are_one_match(self):
        self.ingest(self.journal, replace(self.journal, object_id="quota-reservation",
                                         observed=NOW+1), self.health)
        self.assertEqual(len(groups(self.store.db)), 1)


class QuotaReplayTests(Temporary):
    def module(self):
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[2]/"operations/admin-alerts/replay_quota_correlation.py"
        spec = importlib.util.spec_from_file_location("quota_readonly_replay", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_input_is_unchanged_and_output_contains_no_dispatch_claim(self):
        from copy import deepcopy
        event = Event(DISCOVERY, "QUOTA_DB_CONTENTION", "pipeline", "q", NOW,
                      "journal", invocation="a"*32, facts={"code": CODE})
        document = {"mode": "READ_ONLY", "truncated": False, "as_of_epoch": NOW+60,
                    "since_epoch": NOW-3600, "delivery_attempts_in_window": [],
                    "incidents": [{"id": event.signature, "rule": event.rule,
                        "service": event.service, "invocation": event.invocation,
                        "first_seen": NOW, "last_seen": NOW, "state": "OPEN",
                        "evidence": event.document(), "outbox_created_in_window": []}]}
        before = deepcopy(document)
        result = self.module().replay(document)
        self.assertEqual(document, before)
        self.assertEqual(result["recent_execution_groups"], 1)
        self.assertEqual(result["telegram_sends"], 0)
        self.assertEqual(result["source_writes"], 0)
        self.assertTrue(result["source_rows_unchanged"])

    def test_truncated_or_nonreadonly_input_is_rejected(self):
        for value in ({"mode": "READ_ONLY", "truncated": True},
                      {"mode": "MUTABLE", "truncated": False},
                      {"mode": "READ_ONLY"}):
            with self.subTest(value=value), self.assertRaisesRegex(
                    ValueError, "COMPLETE_READ_ONLY_EXPORT_REQUIRED"):
                self.module().replay(value)

    def test_replay_cli_refuses_source_overwrite(self):
        import json
        import sys
        path = self.root/"input.json"
        path.write_text(json.dumps({"mode": "READ_ONLY"}))
        before = path.read_bytes()
        with patch.object(sys, "argv", ["replay", "--input", str(path),
                                       "--output", str(path)]):
            with self.assertRaisesRegex(ValueError, "SOURCE_OVERWRITE_FORBIDDEN"):
                self.module().main()
        self.assertEqual(path.read_bytes(), before)
