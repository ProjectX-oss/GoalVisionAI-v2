import sqlite3
import unittest
from dataclasses import replace
from decimal import Decimal

from app.database import Database
from app.database.migrations import MIGRATIONS, MigrationManager
from app.feature_store import (
    FEATURE_DEFINITIONS,
    FeatureValue,
    SCHEMA_IDENTIFIER,
    build_feature_store_service,
    generate_match_feature_set,
)
from app.match_data_snapshot import build_match_data_snapshot_service
from app.model_input_builder import (
    GOALVISION_MODEL_INPUT_V1,
    ModelInputGenerationStatus,
    REQUIRED_BASELINE_FEATURES,
    build_model_input_builder,
    generate_model_input,
)
from tests.test_match_data_snapshot import EFFECTIVE, command


class ModelInputBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = Database(":memory:")
        snapshots = build_match_data_snapshot_service(self.database)
        registered = snapshots.register_match_data_snapshot(command())
        snapshot = snapshots.repository.find_snapshot_by_id(registered.snapshot_id)
        features = build_feature_store_service(self.database)
        generated = generate_match_feature_set(
            features,
            snapshot,
            schema_version=SCHEMA_IDENTIFIER,
            feature_timestamp=EFFECTIVE,
        )
        self.feature_set = generated.feature_set
        self.service = build_model_input_builder(self.database)

    def tearDown(self) -> None:
        self.database.close()

    def test_schema_has_fixed_feature_store_order_and_metadata(self) -> None:
        schema = GOALVISION_MODEL_INPUT_V1
        expected = tuple(item.name for item in FEATURE_DEFINITIONS)
        self.assertEqual(schema.identifier, "goalvision_model_input_v1")
        self.assertEqual(schema.ordered_feature_names, expected)
        self.assertEqual(
            tuple(item.index for item in schema.ordered_feature_metadata),
            tuple(range(len(expected))),
        )
        required = {
            item.name
            for item in schema.ordered_feature_metadata
            if item.required_baseline
        }
        self.assertEqual(required, REQUIRED_BASELINE_FEATURES)

    def test_successful_generation_preserves_order_values_and_provenance(self) -> None:
        result = generate_model_input(self.service, self.feature_set)
        self.assertEqual(result.status, ModelInputGenerationStatus.GENERATED)
        vector = result.model_input
        self.assertEqual(
            vector.ordered_feature_names,
            tuple(item.name for item in self.feature_set.ordered_feature_values),
        )
        self.assertEqual(
            vector.ordered_feature_values,
            tuple(item.value for item in self.feature_set.ordered_feature_values),
        )
        self.assertEqual(vector.feature_fingerprint, self.feature_set.feature_fingerprint)
        self.assertEqual(
            vector.source_snapshot_fingerprint,
            self.feature_set.source_snapshot_fingerprint,
        )
        self.assertEqual(vector.source_feature_fingerprint, self.feature_set.feature_fingerprint)

    def test_missing_values_are_not_imputed_and_mask_is_ordered(self) -> None:
        snapshots = build_match_data_snapshot_service(self.database)
        registered = snapshots.register_match_data_snapshot(command(
            match_id="model-input-partial",
            source_event_id="model-input-partial",
            source_snapshot_id="model-input-partial",
            home_venue_split=None,
            away_venue_split=None,
            home_season_aggregate=None,
            away_season_aggregate=None,
            head_to_head=None,
            home_availability=None,
            away_availability=None,
            context=None,
            odds_snapshot=None,
        ))
        snapshot = snapshots.repository.find_snapshot_by_id(registered.snapshot_id)
        features = build_feature_store_service(self.database)
        feature_result = generate_match_feature_set(
            features,
            snapshot,
            schema_version=SCHEMA_IDENTIFIER,
            feature_timestamp=EFFECTIVE,
        )
        result = generate_model_input(self.service, feature_result.feature_set)
        vector = result.model_input
        index = vector.ordered_feature_names.index("home_team_home_points_per_match")
        self.assertIsNone(vector.ordered_feature_values[index])
        self.assertTrue(vector.missingness_mask[index])
        self.assertIn("home_team_home_points_per_match", vector.missing_feature_names)
        expected = Decimal(
            len(vector.ordered_feature_names) - len(vector.missing_feature_names)
        ) / Decimal(len(vector.ordered_feature_names))
        self.assertEqual(vector.completeness_score, expected.quantize(Decimal("0.000001")))

    def test_identical_generation_is_idempotent_and_fingerprint_stable(self) -> None:
        first = generate_model_input(self.service, self.feature_set)
        second = generate_model_input(self.service, self.feature_set)
        self.assertEqual(second.status, ModelInputGenerationStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(first.model_input, second.model_input)
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM model_input_vectors"
            ).fetchone()[0],
            1,
        )

    def test_execution_timestamp_is_excluded_from_fingerprint(self) -> None:
        identity = self.service.repository.load_source_feature_identity(
            self.feature_set.feature_set_id
        )
        first = self.service._builder.build(self.feature_set, identity)
        second = self.service._builder.build(self.feature_set, identity)
        self.assertEqual(first.model_input_fingerprint, second.model_input_fingerprint)

    def test_schema_and_compatibility_rejections(self) -> None:
        cases = (
            (
                replace(self.feature_set, feature_schema_name="unknown_features"),
                "UNSUPPORTED_FEATURE_SCHEMA",
            ),
            (
                replace(self.feature_set, feature_schema_version="v2"),
                "INCOMPATIBLE_FEATURE_SCHEMA_VERSION",
            ),
            (
                replace(self.feature_set, model_compatibility_version="model-v2"),
                "INCOMPATIBLE_COMPATIBILITY_VERSION",
            ),
        )
        for feature_set, reason in cases:
            with self.subTest(reason=reason):
                result = generate_model_input(self.service, feature_set)
                self.assertEqual(result.status, ModelInputGenerationStatus.REJECTED_INVALID)
                self.assertEqual(result.ordered_reason_codes, (reason,))

    def test_snapshot_and_feature_fingerprint_mismatch_rejections(self) -> None:
        cases = (
            (
                replace(self.feature_set, source_snapshot_fingerprint="1" * 64),
                "SNAPSHOT_FINGERPRINT_MISMATCH",
            ),
            (
                replace(self.feature_set, feature_fingerprint="2" * 64),
                "FEATURE_FINGERPRINT_MISMATCH",
            ),
        )
        for feature_set, reason in cases:
            with self.subTest(reason=reason):
                result = generate_model_input(self.service, feature_set)
                self.assertEqual(result.status, ModelInputGenerationStatus.REJECTED_INVALID)
                self.assertEqual(result.ordered_reason_codes, (reason,))

    def test_duplicate_unknown_and_reordered_features_are_rejected(self) -> None:
        values = self.feature_set.ordered_feature_values
        duplicate = (replace(values[0], name=values[1].name),) + values[1:]
        unknown = (replace(values[0], name="future_unknown_feature"),) + values[1:]
        reordered = (values[1], values[0]) + values[2:]
        cases = (
            (duplicate, "DUPLICATE_FEATURE_NAME"),
            (unknown, "UNKNOWN_FEATURE"),
            (reordered, "INVALID_FEATURE_ORDER"),
        )
        for changed, reason in cases:
            with self.subTest(reason=reason):
                result = generate_model_input(
                    self.service,
                    replace(self.feature_set, ordered_feature_values=changed),
                )
                self.assertEqual(result.status, ModelInputGenerationStatus.REJECTED_INVALID)
                self.assertEqual(result.ordered_reason_codes, (reason,))

    def test_invalid_missingness_and_required_baseline_are_rejected(self) -> None:
        mask = self.feature_set.missingness_indicators
        unsupported = ((mask[0][0], 1),) + mask[1:]
        result = generate_model_input(
            self.service,
            replace(self.feature_set, missingness_indicators=unsupported),
        )
        self.assertEqual(
            result.ordered_reason_codes,
            ("UNSUPPORTED_MISSINGNESS_STATE",),
        )
        values = self.feature_set.ordered_feature_values
        missing_value = (FeatureValue(values[0].name, None),) + values[1:]
        missing_mask = ((mask[0][0], True),) + mask[1:]
        baseline = generate_model_input(
            self.service,
            replace(
                self.feature_set,
                ordered_feature_values=missing_value,
                missingness_indicators=missing_mask,
            ),
        )
        self.assertEqual(
            baseline.ordered_reason_codes,
            ("REQUIRED_BASELINE_FEATURE_MISSING",),
        )

    def test_nan_and_non_decimal_values_are_rejected(self) -> None:
        values = self.feature_set.ordered_feature_values
        for invalid in (Decimal("NaN"), Decimal("Infinity"), 1.5):
            with self.subTest(invalid=invalid):
                changed = (FeatureValue(values[0].name, invalid),) + values[1:]
                result = generate_model_input(
                    self.service,
                    replace(self.feature_set, ordered_feature_values=changed),
                )
                self.assertEqual(
                    result.ordered_reason_codes,
                    ("MALFORMED_DECIMAL_VALUE",),
                )

    def test_repository_round_trip_unique_identity_and_immutability(self) -> None:
        vector = generate_model_input(self.service, self.feature_set).model_input
        loaded = self.service.repository.find_by_fingerprint(
            vector.model_input_fingerprint
        )
        self.assertEqual(loaded, vector)
        self.assertEqual(
            self.service.repository.find_for_feature_set(
                vector.feature_set_id,
                vector.schema_name,
                vector.schema_version,
                vector.compatibility_version,
            ),
            vector,
        )
        self.assertEqual(
            self.service.repository.list_for_feature_set(vector.feature_set_id),
            (vector,),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "UPDATE model_input_vectors SET match_id='changed'"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute("DELETE FROM model_input_vectors")

    def test_unpersisted_feature_set_is_rejected(self) -> None:
        result = generate_model_input(
            self.service,
            replace(self.feature_set, feature_set_id="missing-feature-set"),
        )
        self.assertEqual(result.status, ModelInputGenerationStatus.REJECTED_INVALID)
        self.assertEqual(
            result.ordered_reason_codes,
            ("SOURCE_FEATURE_NOT_PERSISTED",),
        )


class ModelInputMigrationTests(unittest.TestCase):
    def test_fresh_v16_and_v15_upgrade(self) -> None:
        fresh = Database(":memory:")
        MigrationManager(fresh.connection).migrate()
        self.assertEqual(
            fresh.connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0],
            30,
        )
        fresh.close()

        upgrade = Database(":memory:")
        upgrade.connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL
            )
            """
        )
        for migration in MIGRATIONS[:15]:
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute(
                "INSERT INTO schema_migrations VALUES (?, 'existing')",
                (migration.version,),
            )
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(
            upgrade.connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0],
            30,
        )
        columns = {
            row[1]
            for row in upgrade.connection.execute(
                "PRAGMA table_info(model_input_vectors)"
            )
        }
        self.assertIn("model_input_fingerprint", columns)
        upgrade.close()


if __name__ == "__main__":
    unittest.main()
