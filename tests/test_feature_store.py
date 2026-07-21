import sqlite3
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from app.database import Database
from app.feature_store import (
    FEATURE_DEFINITIONS, FeatureGenerationStatus, FeatureStorePolicy,
    SCHEMA_IDENTIFIER, build_feature_store_service, generate_match_feature_set,
)
from app.match_data_snapshot import (
    SnapshotLifecycleState, build_match_data_snapshot_service,
)
from tests.test_match_data_snapshot import EFFECTIVE, command, form


class FeatureStoreTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.snapshots = build_match_data_snapshot_service(self.database)
        self.features = build_feature_store_service(self.database)
        registered = self.snapshots.register_match_data_snapshot(command())
        self.snapshot = self.snapshots.repository.find_snapshot_by_id(registered.snapshot_id)

    def tearDown(self):
        self.database.close()

    def generate(self, snapshot=None, **changes):
        arguments = {
            "schema_version": SCHEMA_IDENTIFIER,
            "feature_timestamp": (snapshot or self.snapshot).prepared.command.snapshot_effective_timestamp,
        }
        arguments.update(changes)
        return generate_match_feature_set(self.features, snapshot or self.snapshot, **arguments)

    def values(self, outcome):
        return {item.name: item.value for item in outcome.feature_set.ordered_feature_values}

    def test_complete_feature_calculations(self):
        outcome = self.generate()
        self.assertEqual(outcome.status, FeatureGenerationStatus.GENERATED)
        values = self.values(outcome)
        self.assertEqual(values["home_recent_points_per_match"], Decimal("2.000000"))
        self.assertEqual(values["away_recent_points_per_match"], Decimal("1.600000"))
        self.assertEqual(values["home_recent_goals_scored_per_match"], Decimal("1.800000"))
        self.assertEqual(values["home_recent_clean_sheet_rate"], Decimal("0.400000"))
        self.assertEqual(values["home_recent_failed_to_score_rate"], Decimal("0.200000"))
        self.assertEqual(values["home_team_home_points_per_match"], Decimal("2.166667"))
        self.assertEqual(values["home_season_goal_difference_per_match"], Decimal("1.100000"))
        self.assertEqual(values["rest_days_difference"], Decimal("2.000000"))
        self.assertEqual(values["missing_player_difference"], Decimal("1.000000"))
        self.assertEqual(values["head_to_head_btts_rate"], Decimal("0.750000"))
        self.assertEqual(values["combined_recent_goals_per_match"], Decimal("3.600000"))
        self.assertEqual(values["competition_stage_encoding"], 1)

    def test_feature_order_registry_documentation_and_no_odds(self):
        outcome = self.generate()
        names = tuple(item.name for item in outcome.feature_set.ordered_feature_values)
        self.assertEqual(names, tuple(item.name for item in FEATURE_DEFINITIONS))
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(item.source_fields and item.missing_data_behavior for item in FEATURE_DEFINITIONS))
        self.assertFalse(any("odds" in name or "market" in name for name in names))

    def test_missing_optional_data_uses_indicators_not_zero_imputation(self):
        registered = self.snapshots.register_match_data_snapshot(command(
            match_id="match-partial", source_event_id="event-partial",
            source_snapshot_id="snapshot-partial", home_venue_split=None,
            away_venue_split=None, home_season_aggregate=None,
            away_season_aggregate=None, head_to_head=None,
            home_availability=None, away_availability=None, context=None,
            odds_snapshot=None,
        ))
        snapshot = self.snapshots.repository.find_snapshot_by_id(registered.snapshot_id)
        outcome = self.generate(snapshot)
        values = self.values(outcome)
        missing = dict(outcome.feature_set.missingness_indicators)
        self.assertIsNone(values["home_team_home_points_per_match"])
        self.assertTrue(missing["home_team_home_points_per_match"])
        self.assertEqual(values["home_venue_sample_size"], 0)
        self.assertFalse(missing["home_venue_sample_size"])
        self.assertFalse(values["head_to_head_availability_indicator"])

    def test_zero_denominator_is_missing_and_quantization_is_deterministic(self):
        zero = replace(form(), match_count=0, wins=0, draws=0, losses=0,
                       goals_scored=0, goals_conceded=0, clean_sheets=0,
                       failed_to_score=0)
        registered = self.snapshots.register_match_data_snapshot(command(
            match_id="match-zero", source_event_id="event-zero",
            source_snapshot_id="snapshot-zero", home_recent_form=zero,
            away_recent_form=zero,
        ))
        snapshot = self.snapshots.repository.find_snapshot_by_id(registered.snapshot_id)
        values = self.values(self.generate(snapshot))
        self.assertIsNone(values["home_recent_points_per_match"])
        self.assertIsNone(values["combined_recent_goals_per_match"])

    def test_idempotency_and_fingerprint_repeatability(self):
        first = self.generate()
        second = self.generate()
        self.assertEqual(second.status, FeatureGenerationStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(first.feature_set.feature_set_id, second.feature_set.feature_set_id)
        self.assertEqual(first.feature_set.feature_fingerprint, second.feature_set.feature_fingerprint)
        self.assertEqual(
            self.database.connection.execute("SELECT COUNT(*) FROM match_feature_sets").fetchone()[0], 1
        )

    def test_changed_snapshot_version_creates_new_feature_set(self):
        first = self.generate()
        updated = self.snapshots.register_match_data_snapshot(command(
            source_snapshot_id="snapshot-2",
            source_updated_timestamp=EFFECTIVE,
            registration_timestamp=EFFECTIVE + timedelta(minutes=20),
            home_recent_form=replace(form(), goals_scored=10),
        ))
        snapshot = self.snapshots.repository.find_snapshot_by_id(updated.snapshot_id)
        second = self.generate(snapshot)
        self.assertEqual(second.status, FeatureGenerationStatus.GENERATED)
        self.assertNotEqual(first.feature_set.feature_fingerprint, second.feature_set.feature_fingerprint)
        self.assertEqual(len(self.features.repository.list_feature_sets_for_snapshot(snapshot.snapshot_id)), 1)
        self.assertEqual(self.features.repository.find_latest_for_match(snapshot.match_id).feature_set_id, second.feature_set.feature_set_id)

    def test_inactive_rejection_and_explicit_historical_replay(self):
        self.snapshots.withdraw_snapshot(
            self.snapshot.snapshot_id, reason_code="STALE", event_timestamp=EFFECTIVE + timedelta(minutes=30)
        )
        rejected = self.generate()
        replay = self.generate(historical_replay=True)
        self.assertEqual(rejected.status, FeatureGenerationStatus.REJECTED_INVALID_SNAPSHOT)
        self.assertEqual(replay.status, FeatureGenerationStatus.GENERATED)

    def test_unsupported_schema_timestamp_and_baseline_rejections(self):
        unsupported = self.generate(schema_version="v2")
        future = self.generate(feature_timestamp=EFFECTIVE + timedelta(seconds=1))
        partial = self.snapshots.register_match_data_snapshot(command(
            match_id="match-no-baseline", source_event_id="event-no-baseline",
            source_snapshot_id="snapshot-no-baseline", home_recent_form=None,
        ))
        partial_snapshot = self.snapshots.repository.find_snapshot_by_id(partial.snapshot_id)
        no_baseline = self.generate(partial_snapshot)
        self.assertEqual(unsupported.status, FeatureGenerationStatus.REJECTED_UNSUPPORTED_SCHEMA)
        self.assertEqual(future.status, FeatureGenerationStatus.REJECTED_INVALID_SNAPSHOT)
        self.assertEqual(no_baseline.status, FeatureGenerationStatus.REJECTED_INVALID_SNAPSHOT)

    def test_source_snapshot_fingerprint_mismatch_rejected(self):
        corrupted = replace(
            self.snapshot,
            prepared=replace(self.snapshot.prepared, content_fingerprint="0" * 64),
        )
        outcome = self.generate(corrupted)
        self.assertEqual(outcome.status, FeatureGenerationStatus.REJECTED_INVALID_SNAPSHOT)

    def test_repository_round_trip_and_foreign_key(self):
        generated = self.generate().feature_set
        loaded = self.features.repository.find_by_feature_fingerprint(generated.feature_fingerprint)
        self.assertEqual(loaded, generated)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                """
                INSERT INTO match_feature_sets VALUES (
                    'bad', 'missing', 'm', 's', 'v', 'model', 'f', 'ff',
                    '[]', '[]', '{}', ?, ?
                )
                """,
                (EFFECTIVE.isoformat(), EFFECTIVE.isoformat()),
            )

    def test_feature_rows_are_immutable(self):
        self.generate()
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("UPDATE match_feature_sets SET match_id='changed'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("DELETE FROM match_feature_sets")

    def test_changed_supported_schema_policy_creates_new_schema_record(self):
        first = self.generate()
        policy = FeatureStorePolicy(
            schema_name="official_prematch_features", schema_version="v1.1",
            schema_identifier="official_prematch_features_v1.1",
            model_compatibility_version="official_prediction_model_input_v1",
        )
        alternate = build_feature_store_service(self.database, policy=policy)
        second = generate_match_feature_set(
            alternate, self.snapshot, schema_version=policy.schema_identifier,
            feature_timestamp=EFFECTIVE,
        )
        self.assertEqual(second.status, FeatureGenerationStatus.GENERATED)
        self.assertNotEqual(first.feature_set.feature_fingerprint, second.feature_set.feature_fingerprint)


if __name__ == "__main__":
    unittest.main()
