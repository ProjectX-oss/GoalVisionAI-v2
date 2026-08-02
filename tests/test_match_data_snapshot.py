import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Thread
from uuid import uuid4

from app.database import Database
from app.database.migrations import MIGRATIONS, MigrationManager
from app.match_data_snapshot import (
    FormRecord, HeadToHeadRecord, MatchContextRecord,
    MatchDataSnapshotFingerprint, MatchDataSnapshotRegistrationCommand,
    MatchSnapshotStatus, OddsContextRecord, SeasonAggregateRecord,
    SnapshotLifecycleResultStatus, SnapshotLifecycleState,
    SnapshotRegistrationStatus, TeamAvailabilityRecord, VenueSplitRecord,
    build_match_data_snapshot_service,
)


UTC = timezone.utc
EFFECTIVE = datetime(2026, 8, 1, 12, tzinfo=UTC)
KICKOFF = EFFECTIVE + timedelta(hours=3)


def form(*, matches: int = 5, wins: int = 3, possession=Decimal("54.2")) -> FormRecord:
    return FormRecord(
        matches, wins, 1, 1, 9, 5, 2, 1,
        Decimal("8.4"), Decimal("5.7"), 60, 25, possession,
    )


def command(**changes) -> MatchDataSnapshotRegistrationCommand:
    value = MatchDataSnapshotRegistrationCommand(
        source_provider=" Provider-A ", source_event_id=" Event-100 ",
        source_snapshot_id=" Snapshot-1 ", match_id=" Match-100 ",
        competition_id=" League-1 ", competition_name="  Premier   League ",
        season_identifier="2026-27", home_team_id="Team-1", home_team_name="Café United",
        away_team_id="Team-2", away_team_name="Rovers", kickoff_timestamp=KICKOFF,
        snapshot_effective_timestamp=EFFECTIVE,
        source_updated_timestamp=EFFECTIVE - timedelta(minutes=2),
        registration_timestamp=EFFECTIVE + timedelta(minutes=1),
        scheduled_status=MatchSnapshotStatus.SCHEDULED, postponed_indicator=False,
        cancelled_indicator=False, neutral_venue_indicator=False, venue=" Main  Ground ",
        home_recent_form=form(), away_recent_form=replace(form(), wins=2, draws=2),
        home_venue_split=VenueSplitRecord(6, 4, 1, 1, 12, 5, 3, 1, Decimal("10.2"), Decimal("5.1")),
        away_venue_split=VenueSplitRecord(6, 2, 2, 2, 8, 8, 2, 2, Decimal("7.5"), Decimal("8.2")),
        home_season_aggregate=SeasonAggregateRecord(10, 22, 20, 9, 2, Decimal("18.2"), Decimal("10.1")),
        away_season_aggregate=SeasonAggregateRecord(10, 16, 14, 13, 7, Decimal("13.5"), Decimal("14.2")),
        head_to_head=HeadToHeadRecord(4, 2, 1, 1, 11, 3, 2, EFFECTIVE - timedelta(days=90)),
        home_availability=TeamAvailabilityRecord(True, False, 2, 0, 1, "available", EFFECTIVE - timedelta(minutes=10), EFFECTIVE - timedelta(hours=1)),
        away_availability=TeamAvailabilityRecord(False, True, 3, 1, 2, "doubtful", EFFECTIVE - timedelta(minutes=10), EFFECTIVE - timedelta(hours=1)),
        context=MatchContextRecord(6, 4, Decimal("20.5"), Decimal("350.2"), 1, 2, "Regular Season", True, "Dry", "Good"),
        odds_snapshot=OddsContextRecord("book-a", "match winner", "home", None, Decimal("1.80"), EFFECTIVE - timedelta(minutes=5)),
    )
    return replace(value, **changes)


class MatchDataSnapshotValidationTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.service = build_match_data_snapshot_service(self.database)

    def tearDown(self):
        self.database.close()

    def assert_rejected(self, value, reason):
        result = self.service.register_match_data_snapshot(value)
        self.assertEqual(result.status, SnapshotRegistrationStatus.REJECTED_INVALID)
        self.assertEqual(result.ordered_reason_codes, (reason,))

    def test_complete_and_partial_snapshots_are_valid(self):
        complete = self.service.register_match_data_snapshot(command())
        partial = self.service.register_match_data_snapshot(command(
            source_event_id="event-101", source_snapshot_id="snapshot-partial",
            match_id="match-101", home_recent_form=None, away_recent_form=None,
            home_venue_split=None, away_venue_split=None,
            home_season_aggregate=None, away_season_aggregate=None,
            head_to_head=None, home_availability=None, away_availability=None,
            context=None, odds_snapshot=None,
        ))
        self.assertEqual(complete.status, SnapshotRegistrationStatus.REGISTERED)
        self.assertEqual(partial.status, SnapshotRegistrationStatus.REGISTERED)

    def test_identity_and_status_rejections(self):
        cases = (
            (command(away_team_id="team-1"), "IDENTICAL_TEAMS"),
            (command(away_team_name="café united"), "IDENTICAL_TEAMS"),
            (command(kickoff_timestamp=EFFECTIVE), "NOT_PREMATCH"),
            (command(registration_timestamp=EFFECTIVE - timedelta(minutes=3)), "REGISTRATION_BEFORE_SOURCE_UPDATE"),
            (command(is_live=True), "LIVE_DATA_FORBIDDEN"),
            (command(cancelled_indicator=True), "CANCELLED_MATCH"),
            (command(scheduled_status=MatchSnapshotStatus.COMPLETED), "COMPLETED_MATCH"),
            (command(source_snapshot_id=" "), "INVALID_TEXT"),
        )
        for value, reason in cases:
            with self.subTest(reason=reason):
                self.assert_rejected(value, reason)

    def test_numeric_rejections(self):
        cases = (
            (command(home_recent_form=replace(form(), goals_scored=-1)), "NEGATIVE_COUNT"),
            (command(home_recent_form=replace(form(), wins=5, draws=1)), "INCONSISTENT_RESULTS"),
            (command(home_recent_form=replace(form(), clean_sheets=6)), "INVALID_CLEAN_SHEETS"),
            (command(home_recent_form=replace(form(), failed_to_score=6)), "INVALID_FAILED_TO_SCORE"),
            (command(home_recent_form=form(possession=Decimal("100.1"))), "INVALID_POSSESSION"),
            (command(home_recent_form=form(possession=Decimal("NaN"))), "INVALID_DECIMAL"),
        )
        for value, reason in cases:
            with self.subTest(reason=reason):
                self.assert_rejected(value, reason)

    def test_optional_odds_are_accepted_and_invalid_odds_rejected(self):
        accepted = self.service.register_match_data_snapshot(command(odds_snapshot=None))
        self.assertEqual(accepted.status, SnapshotRegistrationStatus.REGISTERED)
        invalid = command(
            source_snapshot_id="snapshot-bad-odds",
            odds_snapshot=replace(command().odds_snapshot, decimal_odds=Decimal("1")),
        )
        self.assert_rejected(invalid, "INVALID_DECIMAL_ODDS")

    def test_normalization_and_fingerprints_are_stable(self):
        first = self.service._validator.prepare(command())
        equivalent = self.service._validator.prepare(command(
            source_provider="provider-a", competition_name="Premier League",
            registration_timestamp=EFFECTIVE + timedelta(minutes=30),
            home_team_name="Cafe\u0301 United",
        ))
        self.assertEqual(first.command.home_team_name, "Café United")
        self.assertEqual(first.command.kickoff_timestamp.utcoffset(), timedelta(0))
        self.assertIn('"decimal_odds":"1.8"', first.deterministic_snapshot)
        self.assertEqual(first.logical_identity_fingerprint, equivalent.logical_identity_fingerprint)
        self.assertEqual(first.content_fingerprint, equivalent.content_fingerprint)
        changed = self.service._validator.prepare(command(source_snapshot_id="snapshot-2"))
        self.assertNotEqual(first.content_fingerprint, changed.content_fingerprint)


class MatchDataSnapshotLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.service = build_match_data_snapshot_service(self.database)

    def tearDown(self):
        self.database.close()

    def test_registration_idempotency_supersession_and_history(self):
        first = self.service.register_match_data_snapshot(command())
        again = self.service.register_match_data_snapshot(command(registration_timestamp=EFFECTIVE + timedelta(minutes=20)))
        second = self.service.register_match_data_snapshot(command(
            source_snapshot_id="snapshot-2",
            source_updated_timestamp=EFFECTIVE,
            registration_timestamp=EFFECTIVE + timedelta(minutes=30),
            home_recent_form=replace(form(), goals_scored=10),
        ))
        self.assertEqual(first.version, 1)
        self.assertEqual(again.status, SnapshotRegistrationStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(again.snapshot_id, first.snapshot_id)
        self.assertEqual(second.status, SnapshotRegistrationStatus.SUPERSEDED_PREVIOUS)
        self.assertEqual(second.version, 2)
        versions = self.service.repository.list_snapshot_versions(first.logical_identity_fingerprint)
        self.assertEqual([item.snapshot_version for item in versions], [1, 2])
        self.assertEqual(self.service.repository.current_state(first.snapshot_id), SnapshotLifecycleState.SUPERSEDED)
        self.assertEqual(self.service.repository.find_latest_active_snapshot(first.logical_identity_fingerprint).snapshot_id, second.snapshot_id)

    def test_withdrawal_invalidation_and_window_lookup(self):
        first = self.service.register_match_data_snapshot(command())
        withdrawn = self.service.withdraw_snapshot(first.snapshot_id, reason_code=" provider withdrawal ", event_timestamp=EFFECTIVE + timedelta(hours=1))
        repeated = self.service.withdraw_snapshot(first.snapshot_id, reason_code="PROVIDER_WITHDRAWAL", event_timestamp=EFFECTIVE + timedelta(hours=1))
        self.assertEqual(withdrawn.status, SnapshotLifecycleResultStatus.APPLIED)
        self.assertEqual(repeated.status, SnapshotLifecycleResultStatus.IDEMPOTENT_EXISTING)
        other = self.service.register_match_data_snapshot(command(
            match_id="match-200", source_event_id="event-200", source_snapshot_id="snapshot-200"
        ))
        active = self.service.repository.list_active_snapshots_by_kickoff_window(EFFECTIVE, KICKOFF)
        self.assertEqual(tuple(item.snapshot_id for item in active), (other.snapshot_id,))
        invalidated = self.service.invalidate_snapshot(other.snapshot_id, reason_code="BAD_SOURCE", event_timestamp=EFFECTIVE + timedelta(hours=1))
        self.assertEqual(invalidated.state, SnapshotLifecycleState.INVALIDATED)

    def test_append_only_triggers_and_atomic_rollback(self):
        result = self.service.register_match_data_snapshot(command())
        for statement in (
            "UPDATE match_data_snapshot_versions SET match_id='changed'",
            "DELETE FROM match_data_snapshot_versions",
            "UPDATE match_data_snapshot_lifecycle_events SET reason_code='changed'",
            "DELETE FROM match_data_snapshot_lifecycle_events",
        ):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(statement)
        self.assertIsNotNone(self.service.repository.find_snapshot_by_id(result.snapshot_id))


class MatchDataSnapshotMigrationAndConcurrencyTests(unittest.TestCase):
    def test_fresh_v15_and_v14_upgrade(self):
        fresh = Database(":memory:")
        MigrationManager(fresh.connection).migrate()
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 40)
        fresh.close()
        upgrade = Database(":memory:")
        upgrade.connection.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
        for migration in MIGRATIONS[:14]:
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute("INSERT INTO schema_migrations VALUES (?, 'existing')", (migration.version,))
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 40)
        tables = {row[0] for row in upgrade.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"match_data_snapshot_versions", "match_data_snapshot_lifecycle_events", "match_feature_sets"} <= tables)
        upgrade.close()

    def test_concurrent_identical_registration_is_idempotent(self):
        path = Path("tests") / f".match-snapshots-{uuid4().hex}.db"
        try:
            seed = Database(path)
            MigrationManager(seed.connection).migrate()
            seed.close()
            statuses = []

            def worker():
                database = Database(path)
                statuses.append(build_match_data_snapshot_service(database).register_match_data_snapshot(command()).status)
                database.close()

            threads = [Thread(target=worker) for _ in range(2)]
            for thread in threads: thread.start()
            for thread in threads: thread.join()
            check = Database(path)
            self.assertEqual(check.connection.execute("SELECT COUNT(*) FROM match_data_snapshot_versions").fetchone()[0], 1)
            self.assertIn(SnapshotRegistrationStatus.REGISTERED, statuses)
            self.assertIn(SnapshotRegistrationStatus.IDEMPOTENT_EXISTING, statuses)
            check.close()
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
