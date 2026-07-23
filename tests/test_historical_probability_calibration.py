import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.historical_dataset_split import (
    DatasetSplitCommand, Partition, RatioByChronology,
    SQLiteHistoricalDatasetSplitRepository, SplitStrategy,
    build_historical_dataset_split_service,
)
from app.historical_model_training import (
    FEATURE_NAMES, FEATURE_SCHEMA_FINGERPRINT,
    SQLiteHistoricalModelTrainingRepository,
    build_historical_model_training_service,
)
from app.historical_probability_calibration import (
    CalibrationMethod, CalibrationStatus, HistoricalCalibrationCommand,
    HistoricalCalibrationPolicy, SQLiteHistoricalProbabilityCalibrationRepository,
    build_historical_probability_calibration_service,
    inspect_calibration_artifact_set, inspect_target_calibration,
    inspect_validation_prediction, summarize_calibration_run,
    to_runtime_calibration_artifacts, verify_calibrated_probability_contract,
    verify_calibration_artifact_fingerprint, verify_raw_prediction_reproduction,
    verify_reliability_bins, verify_runtime_compatibility,
    verify_target_artifact_fingerprints, verify_validation_partition_only,
)
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository
from app.prediction_inference import OFFICIAL_TARGET_ORDER
from tests.test_historical_model_training import build_foundations, command as training_command


UTC = timezone.utc
CALIBRATED_AT = datetime(2026, 7, 22, 23, 0, tzinfo=UTC)


def low_support_policy(**changes):
    values = dict(
        minimum_validation_examples=6, minimum_positive_per_binary_target=1,
        minimum_negative_per_binary_target=1,
        minimum_examples_per_match_result_class=1,
        minimum_distinct_probabilities_for_isotonic=2,
    )
    values.update(changes)
    return HistoricalCalibrationPolicy(**values)


class HistoricalProbabilityCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        dataset, _, _ = build_foundations(self.database)
        split_outcome = build_historical_dataset_split_service(self.database, migrate=False).create(
            DatasetSplitCommand(
                split_request_id="calibration-source-split",
                split_name="Calibration source split",
                source_dataset_build_id=dataset.dataset_build_id,
                source_dataset_fingerprint=dataset.dataset_fingerprint,
                strategy=SplitStrategy.RATIO_BY_CHRONOLOGY_V1,
                ratios=RatioByChronology("0.45", "0.45", "0.10"),
                split_timestamp="2026-07-22T21:15:00Z",
            )
        )
        self.split_repository = SQLiteHistoricalDatasetSplitRepository(self.database, migrate=False)
        self.split = self.split_repository.load_dataset_split(split_outcome.split_id)
        self.fold = self.split.folds[0]
        training = build_historical_model_training_service(self.database, migrate=False).train(
            training_command(self.split, self.fold, "calibration-source-training")
        )
        self.model_repository = SQLiteHistoricalModelTrainingRepository(self.database, migrate=False)
        self.training_run = self.model_repository.load_training_run(training.training_run_id)
        self.artifact = self.model_repository.load_model_artifact(training.artifact_id)
        self.training_repository = SQLiteHistoricalTrainingDatasetRepository(self.database, migrate=False)
        self.policy = low_support_policy()
        self.service = build_historical_probability_calibration_service(
            self.database, policy=self.policy, migrate=False
        )
        self.repository = SQLiteHistoricalProbabilityCalibrationRepository(self.database, migrate=False)

    def tearDown(self):
        self.database.close()

    def command(self, request_id="historical-calibration-request", **changes):
        values = dict(
            calibration_request_id=request_id,
            calibration_run_name="Validation probability calibration",
            source_training_run_id=self.training_run.training_run_id,
            source_training_run_fingerprint=self.training_run.training_run_fingerprint,
            source_model_artifact_id=self.artifact.artifact_id,
            source_model_artifact_fingerprint=self.artifact.artifact_fingerprint,
            source_split_id=self.split.split_id,
            source_split_fingerprint=self.split.split_fingerprint,
            fold_id=self.fold.fold_id,
            fold_fingerprint=self.fold.fold_fingerprint,
            feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
            match_result_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
            totals_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
            btts_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
            calibration_timestamp=CALIBRATED_AT,
        )
        values.update(changes)
        return HistoricalCalibrationCommand(**values)

    def fit(self, **changes):
        return self.service.fit(self.command(**changes))

    def test_validation_only_fit_persists_complete_artifact_set(self):
        outcome = self.fit()
        self.assertEqual(outcome.status, CalibrationStatus.CALIBRATION_FITTED)
        self.assertEqual((outcome.fitted_target_count, outcome.derived_target_count), (7, 4))
        self.assertEqual(outcome.ordered_target_identities, tuple(item.value for item in OFFICIAL_TARGET_ORDER))
        run = self.repository.load_calibration_run(outcome.calibration_run_id)
        self.assertGreaterEqual(len(run.predictions), 6)
        self.assertEqual({item.partition for item in run.predictions}, {Partition.VALIDATION})
        self.assertEqual(len(run.artifact_set.target_artifacts), 11)
        self.assertTrue(run.metrics)
        self.assertEqual(len(run.reliability_bins), 11 * 2 * self.policy.reliability_bin_count)

    def test_probabilities_are_bounded_coherent_monotonic_and_complementary(self):
        outcome = self.fit()
        run = self.repository.load_calibration_run(outcome.calibration_run_id)
        for prediction in run.predictions:
            values = {item.target.value: item.probability for item in prediction.calibrated_probabilities.ordered_probabilities}
            self.assertEqual(values["HOME_WIN"] + values["DRAW"] + values["AWAY_WIN"], Decimal(1))
            self.assertGreaterEqual(values["OVER_1_5"], values["OVER_2_5"])
            self.assertGreaterEqual(values["OVER_2_5"], values["OVER_3_5"])
            self.assertEqual(values["OVER_1_5"] + values["UNDER_1_5"], Decimal(1))
            self.assertEqual(values["OVER_2_5"] + values["UNDER_2_5"], Decimal(1))
            self.assertEqual(values["OVER_3_5"] + values["UNDER_3_5"], Decimal(1))
            self.assertEqual(values["BTTS_YES"] + values["BTTS_NO"], Decimal(1))
            self.assertTrue(all(Decimal("0.001") <= value <= Decimal("0.999") for value in values.values()))

    def test_exact_replay_is_idempotent_and_changed_request_conflicts(self):
        first = self.fit()
        second = self.fit()
        changed = self.service.fit(self.command(calibration_run_name="Changed"))
        self.assertEqual(second.status, CalibrationStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(first.artifact_set_fingerprint, second.artifact_set_fingerprint)
        self.assertEqual(changed.status, CalibrationStatus.CONFLICT)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_probability_calibration_runs").fetchone()[0], 1)

    def test_uncontrolled_commands_and_non_validation_partition_reject(self):
        self.assertEqual(self.service.fit({}).status, CalibrationStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.service.fit(replace(self.command(), calibration_partition=Partition.TRAIN)).status, CalibrationStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.service.fit(replace(self.command(), calibration_partition=Partition.TEST)).status, CalibrationStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.service.fit(replace(self.command(), calibration_timestamp="")).status, CalibrationStatus.REJECTED_INVALID_REQUEST)

    def test_source_fingerprint_and_schema_mismatches_fail_closed(self):
        cases = (
            ("source_training_run_fingerprint", "a" * 64, CalibrationStatus.REJECTED_SOURCE_TRAINING_RUN),
            ("source_model_artifact_fingerprint", "b" * 64, CalibrationStatus.REJECTED_SOURCE_ARTIFACT),
            ("source_split_fingerprint", "c" * 64, CalibrationStatus.REJECTED_SOURCE_SPLIT),
            ("fold_fingerprint", "d" * 64, CalibrationStatus.REJECTED_SOURCE_SPLIT),
            ("feature_schema_fingerprint", "e" * 64, CalibrationStatus.REJECTED_INVALID_REQUEST),
        )
        for field, value, expected in cases:
            with self.subTest(field=field):
                outcome = self.service.fit(replace(self.command(request_id=f"bad-{field}"), **{field: value}))
                self.assertEqual(outcome.status, expected)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_probability_calibration_runs").fetchone()[0], 0)

    def test_sample_class_and_isotonic_support_fail_closed(self):
        insufficient_examples = build_historical_probability_calibration_service(
            self.database, policy=HistoricalCalibrationPolicy(), migrate=False
        ).fit(self.command())
        self.assertEqual(insufficient_examples.status, CalibrationStatus.REJECTED_INSUFFICIENT_EXAMPLES)
        insufficient_class = build_historical_probability_calibration_service(
            self.database, policy=low_support_policy(minimum_positive_per_binary_target=20), migrate=False
        ).fit(self.command(request_id="insufficient-class"))
        self.assertEqual(insufficient_class.status, CalibrationStatus.REJECTED_INSUFFICIENT_CLASS_SUPPORT)
        insufficient_distinct = build_historical_probability_calibration_service(
            self.database, policy=low_support_policy(minimum_distinct_probabilities_for_isotonic=100), migrate=False
        ).fit(self.command(request_id="insufficient-distinct"))
        self.assertEqual(insufficient_distinct.status, CalibrationStatus.REJECTED_INSUFFICIENT_CLASS_SUPPORT)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_probability_calibration_runs").fetchone()[0], 0)

    def test_raw_prediction_order_provenance_and_reproduction_are_deterministic(self):
        first = self.fit()
        predictions = self.repository.list_validation_predictions(first.calibration_run_id)
        self.assertEqual(tuple(item.deterministic_order for item in predictions), tuple(range(len(predictions))))
        self.assertTrue(all(item.artifact_id == self.artifact.artifact_id for item in predictions))
        self.assertTrue(all(item.training_run_id == self.training_run.training_run_id for item in predictions))
        self.assertEqual(len({item.raw_prediction_fingerprint for item in predictions}), len(predictions))
        self.assertEqual(verify_raw_prediction_reproduction(
            self.repository, self.model_repository, self.training_repository, first.calibration_run_id
        ), ())

    def test_runtime_adapter_rejects_tampered_artifact_set_identity(self):
        outcome = self.fit()
        artifact = self.repository.load_calibration_artifact_set(outcome.calibration_artifact_set_id)
        predictions = self.repository.list_validation_predictions(outcome.calibration_run_id)
        from app.historical_probability_calibration.exceptions import SchemaCompatibilityError
        with self.assertRaises(SchemaCompatibilityError):
            to_runtime_calibration_artifacts(
                replace(artifact, artifact_set_fingerprint="f" * 64), predictions, self.training_repository
            )

    def test_streaming_predictions_matches_ordered_repository_view(self):
        outcome = self.fit()
        expected = self.repository.list_validation_predictions(outcome.calibration_run_id)
        self.assertEqual(tuple(self.repository.stream_calibrated_predictions(outcome.calibration_run_id)), expected)

    def test_test_and_train_examples_are_never_materialized(self):
        loaded = []
        underlying = self.training_repository

        class SpyRepository:
            def load_dataset_identity(self, dataset_build_id):
                return underlying.load_dataset_identity(dataset_build_id)

            def load_training_example(self, training_example_id):
                loaded.append(training_example_id)
                return underlying.load_training_example(training_example_id)

        forbidden = {
            item.training_example_id
            for partition in (Partition.TRAIN, Partition.TEST)
            for item in self.split_repository.list_assignments_by_partition(self.fold.fold_id, partition)
        }
        from app.historical_probability_calibration.service import HistoricalProbabilityCalibrationService
        service = HistoricalProbabilityCalibrationService(
            self.model_repository, self.split_repository, SpyRepository(), self.repository, self.policy
        )
        self.assertEqual(service.fit(self.command()).status, CalibrationStatus.CALIBRATION_FITTED)
        self.assertTrue(forbidden)
        self.assertTrue(forbidden.isdisjoint(loaded))

    def test_identity_requires_explicit_policy_and_all_methods_are_supported(self):
        rejected = self.service.fit(self.command(match_result_method=CalibrationMethod.IDENTITY_V1))
        self.assertEqual(rejected.status, CalibrationStatus.REJECTED_CALIBRATION_FIT)
        identity_service = build_historical_probability_calibration_service(
            self.database, policy=low_support_policy(allow_identity_calibration=True), migrate=False
        )
        identity = identity_service.fit(self.command(
            request_id="identity-calibration", match_result_method=CalibrationMethod.IDENTITY_V1,
            totals_method=CalibrationMethod.IDENTITY_V1, btts_method=CalibrationMethod.IDENTITY_V1,
        ))
        self.assertEqual(identity.status, CalibrationStatus.CALIBRATION_FITTED)
        platt = self.service.fit(self.command(
            request_id="platt-calibration", match_result_method=CalibrationMethod.PLATT_SCALING_V1,
            totals_method=CalibrationMethod.PLATT_SCALING_V1,
            btts_method=CalibrationMethod.PLATT_SCALING_V1,
        ))
        self.assertIn(platt.status, {CalibrationStatus.CALIBRATION_FITTED, CalibrationStatus.REJECTED_CONVERGENCE})

    def test_inspection_reproduction_and_runtime_adapter_are_read_only(self):
        outcome = self.fit()
        before = self.database.connection.total_changes
        self.assertEqual(summarize_calibration_run(self.repository, outcome.calibration_run_id)["validation_rows"], outcome.validation_row_count)
        artifact = inspect_calibration_artifact_set(self.repository, outcome.calibration_artifact_set_id)
        self.assertIsNotNone(inspect_target_calibration(self.repository, artifact.artifact_set_id, "HOME_WIN"))
        self.assertIsNotNone(inspect_validation_prediction(self.repository, outcome.calibration_run_id, artifact and self.repository.list_validation_predictions(outcome.calibration_run_id)[0].training_example_id))
        self.assertEqual(verify_validation_partition_only(self.repository, outcome.calibration_run_id), ())
        self.assertEqual(verify_raw_prediction_reproduction(self.repository, self.model_repository, self.training_repository, outcome.calibration_run_id), ())
        self.assertEqual(verify_calibration_artifact_fingerprint(self.repository, artifact.artifact_set_id), ())
        self.assertEqual(verify_target_artifact_fingerprints(self.repository, artifact.artifact_set_id), ())
        self.assertEqual(verify_calibrated_probability_contract(self.repository, outcome.calibration_run_id), ())
        self.assertEqual(verify_reliability_bins(self.repository, outcome.calibration_run_id), ())
        self.assertEqual(verify_runtime_compatibility(self.repository, self.training_repository, artifact.artifact_set_id), ())
        runtime = to_runtime_calibration_artifacts(artifact, self.repository.list_validation_predictions(outcome.calibration_run_id), self.training_repository)
        self.assertEqual((len(runtime), {item.active for item in runtime}), (11, {False}))
        self.assertEqual(before, self.database.connection.total_changes)

    def test_append_only_triggers_and_atomic_rollback(self):
        outcome = self.fit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "UPDATE historical_probability_calibration_runs SET outcome='changed' WHERE calibration_run_id=?",
                (outcome.calibration_run_id,),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "DELETE FROM historical_probability_calibration_artifact_sets WHERE artifact_set_id=?",
                (outcome.calibration_artifact_set_id,),
            )
        original = self.repository._insert_metrics
        self.repository._insert_metrics = lambda *_: (_ for _ in ()).throw(sqlite3.IntegrityError("forced"))
        failed = self.service.fit(self.command(request_id="atomic-failure"))
        self.repository._insert_metrics = original
        self.assertEqual(failed.status, CalibrationStatus.PERSISTENCE_FAILURE)
        self.assertEqual(self.database.connection.execute(
            "SELECT COUNT(*) FROM historical_probability_calibration_runs WHERE calibration_request_id='atomic-failure'"
        ).fetchone()[0], 0)


class HistoricalCalibrationMigrationAndStartupTests(unittest.TestCase):
    def test_calibration_schema_survives_current_migration_and_v26_upgrade(self):
        fresh = Database(":memory:")
        SQLiteHistoricalProbabilityCalibrationRepository(fresh)
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 30)
        self.assertEqual(len(fresh.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'historical_probability_calibration_%'").fetchall()), 6)
        fresh.close()

        connection = sqlite3.connect(":memory:")
        with patch("app.database.migrations.MIGRATIONS", MIGRATIONS[:26]):
            MigrationManager(connection).migrate()
        MigrationManager(connection).migrate()
        self.assertEqual(connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 30)
        connection.close()

    def test_import_and_service_composition_have_zero_startup_side_effects(self):
        database = Database(":memory:")
        SQLiteHistoricalProbabilityCalibrationRepository(database)
        before = database.connection.total_changes
        service = build_historical_probability_calibration_service(database, migrate=False)
        self.assertIsNotNone(service)
        self.assertEqual(before, database.connection.total_changes)
        self.assertEqual(database.connection.execute("SELECT COUNT(*) FROM historical_probability_calibration_runs").fetchone()[0], 0)
        database.close()


if __name__ == "__main__":
    unittest.main()
