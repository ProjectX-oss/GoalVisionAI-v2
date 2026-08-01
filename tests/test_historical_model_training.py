import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.historical_data_import import (
    HISTORICAL_DATASET_SCHEMA, HistoricalDataset, HistoricalMatchInput,
    HistoricalTeamStatisticsInput, build_historical_match_importer,
)
from app.historical_dataset_split import (
    DatasetSplitCommand, DatasetSplitStatus, Partition, RatioByChronology,
    SplitStrategy, SQLiteHistoricalDatasetSplitRepository,
    build_historical_dataset_split_service,
)
from app.historical_model_training import (
    FEATURE_NAMES, FEATURE_SCHEMA_FINGERPRINT, EstimatorConfiguration,
    HistoricalModelTrainer, HistoricalModelTrainingCommand, SQLiteHistoricalModelTrainingRepository,
    TrainingStatus, build_historical_model_training_service,
    compare_reproduced_predictions, inspect_model_artifact,
    inspect_target_estimator, predict_raw_probabilities,
    reproduce_training_metrics, summarize_training_run,
    verify_artifact_fingerprint, verify_estimator_fingerprints,
    verify_feature_compatibility, verify_preprocessing_train_only,
    verify_probability_contract, verify_training_partition_only,
)
from app.historical_model_training.preprocessing import fit_preprocessing, transform_examples
from app.historical_model_training.estimators import fit_estimators, validate_class_support
from app.historical_model_training.exceptions import (
    EstimatorConvergenceError, InsufficientClassSupportError, PreprocessingError,
)
from app.historical_model_training.policy import ModelTrainingPolicy, PreprocessingPolicy
from app.historical_model_training.validation import normalize_training_command
from app.historical_training_dataset import (
    DatasetBuildCommand, DatasetBuildStatus, SQLiteHistoricalTrainingDatasetRepository,
    build_historical_training_dataset_service,
)


UTC = timezone.utc
BASE = datetime(2025, 1, 1, 12, 0, tzinfo=UTC)
TRAINED_AT = datetime(2026, 7, 22, 22, 0, tzinfo=UTC)


def statistics(seed, possession):
    return HistoricalTeamStatisticsInput(
        possession=str(possession), shots=7 + seed % 8,
        shots_on_target=2 + seed % 5, expected_goals=str(Decimal("0.5") + Decimal(seed % 15) / 10),
        corners=2 + seed % 7, yellow_cards=seed % 4, red_cards=0,
        fouls=7 + seed % 8, offsides=seed % 4,
    )


def source_history():
    scores = ((0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (1, 2), (3, 1), (2, 2), (4, 1), (2, 3))
    games = []
    for day in range(20):
        pairs = (("Alpha", "Charlie"), ("Bravo", "Delta")) if day % 2 == 0 else (("Charlie", "Alpha"), ("Delta", "Bravo"))
        for game, (home, away) in enumerate(pairs):
            score = scores[(day * 2 + game) % len(scores)]
            home_possession = 45 + (day * 2 + game) % 11
            games.append(HistoricalMatchInput(
                source_match_id=f"training-match-{day}-{game}", competition="Training League",
                season="2025/26", round=f"Round {day + 1}", kickoff_utc=BASE + timedelta(days=day),
                home_team=home, away_team=away, full_time_home_score=score[0],
                full_time_away_score=score[1],
                full_time_result="H" if score[0] > score[1] else "D" if score[0] == score[1] else "A",
                venue=f"{home} Ground", home_statistics=statistics(day * 2 + game, home_possession),
                away_statistics=statistics(day * 2 + game + 1, 100 - home_possession),
            ))
    return tuple(games)


def build_foundations(database):
    imported = build_historical_match_importer(database).import_dataset(
        HistoricalDataset(
            schema_version=HISTORICAL_DATASET_SCHEMA, provider="Training Test Provider",
            dataset_id="model-training-history", dataset_version="v1", matches=source_history(),
        ), import_timestamp="2026-07-22T19:00:00Z",
    )
    dataset = build_historical_training_dataset_service(database, migrate=False).build(DatasetBuildCommand(
        request_id="model-training-dataset", dataset_name="Model training source",
        source_import_ids=(imported.import_id,), competition_filters=("Training League",),
        season_filters=("2025/26",), kickoff_lower_bound=BASE + timedelta(days=6),
        kickoff_upper_bound=BASE + timedelta(days=20), build_timestamp="2026-07-22T20:00:00Z",
    ))
    assert dataset.status is DatasetBuildStatus.DATASET_BUILT
    split = build_historical_dataset_split_service(database, migrate=False).create(DatasetSplitCommand(
        split_request_id="model-training-split", split_name="Model training split",
        source_dataset_build_id=dataset.dataset_build_id,
        source_dataset_fingerprint=dataset.dataset_fingerprint,
        strategy=SplitStrategy.RATIO_BY_CHRONOLOGY_V1,
        ratios=RatioByChronology("0.70", "0.15", "0.15"),
        split_timestamp="2026-07-22T21:00:00Z",
    ))
    assert split.status is DatasetSplitStatus.SPLIT_CREATED
    split_repository = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    fold = split_repository.load_dataset_split(split.split_id).folds[0]
    return dataset, split, fold


def command(split, fold, request_id="model-training-request"):
    return HistoricalModelTrainingCommand(
        training_request_id=request_id, training_run_name="Deterministic baseline",
        source_split_id=split.split_id, source_split_fingerprint=split.split_fingerprint,
        fold_id=fold.fold_id, fold_fingerprint=fold.fold_fingerprint,
        feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
        ordered_feature_names=FEATURE_NAMES, training_timestamp=TRAINED_AT,
        estimator=EstimatorConfiguration(convergence_tolerance=Decimal("0.0004")),
    )


class TrainingFoundationTests(unittest.TestCase):
    def setUp(self):
        self.database = Database(":memory:")
        self.dataset, self.split, self.fold = build_foundations(self.database)
        self.service = build_historical_model_training_service(self.database, migrate=False)
        self.repository = SQLiteHistoricalModelTrainingRepository(self.database, migrate=False)
        self.training_repository = SQLiteHistoricalTrainingDatasetRepository(self.database, migrate=False)

    def tearDown(self):
        self.database.close()

    def train(self):
        return self.service.train(command(self.split, self.fold))

    def test_valid_command_is_normalized_and_uncontrolled_values_reject(self):
        normalized = normalize_training_command(command(self.split, self.fold))
        self.assertEqual((normalized.training_partition, len(normalized.ordered_feature_names)), (Partition.TRAIN, 145))
        self.assertEqual(self.service.train({}).status, TrainingStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.service.train(replace(command(self.split, self.fold), training_partition=Partition.TEST)).status, TrainingStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.service.train(replace(command(self.split, self.fold), training_timestamp="")).status, TrainingStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.service.train(replace(command(self.split, self.fold), ordered_feature_names=())).status, TrainingStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.service.train(replace(command(self.split, self.fold), estimator={})).status, TrainingStatus.REJECTED_INVALID_REQUEST)

    def test_training_persists_safe_complete_artifact_and_metrics(self):
        outcome = self.train()
        self.assertEqual(outcome.status, TrainingStatus.MODEL_TRAINED)
        self.assertEqual((outcome.original_feature_count, outcome.transformed_feature_count, outcome.target_count), (145, 145, 11))
        artifact = self.repository.load_model_artifact(outcome.artifact_id)
        self.assertEqual(len(artifact.estimators), 3)
        self.assertEqual(len(self.repository.list_artifact_targets(outcome.artifact_id)), 11)
        self.assertEqual(len(self.repository.list_preprocessing_features(outcome.artifact_id)), 145)
        self.assertGreater(len(self.repository.list_metrics(outcome.training_run_id)), 80)
        self.assertNotIn("pickle", artifact.provenance_snapshot.lower())

    def test_raw_probability_contract_is_canonical_monotonic_and_reproducible(self):
        outcome = self.train()
        artifact = self.repository.load_model_artifact(outcome.artifact_id)
        example = self.training_repository.load_training_example(
            self.repository.list_training_examples(outcome.training_run_id)[0].training_example_id
        )
        kwargs = dict(feature_schema_version=example.feature_schema_version,
                      feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
                      ordered_feature_names=FEATURE_NAMES)
        first = predict_raw_probabilities(artifact, example.ordered_feature_vector, example.missingness_mask, **kwargs)
        second = predict_raw_probabilities(artifact, example.ordered_feature_vector, example.missingness_mask, **kwargs)
        self.assertEqual(first, second)
        self.assertEqual(verify_probability_contract(first.raw_probabilities), ())
        values = {item.target.value: item.probability for item in first.raw_probabilities.ordered_probabilities}
        self.assertLessEqual(values["OVER_3_5"], values["OVER_2_5"])
        self.assertLessEqual(values["OVER_2_5"], values["OVER_1_5"])
        self.assertEqual(values["BTTS_YES"] + values["BTTS_NO"], Decimal(1))

    def test_exact_replay_is_idempotent_without_refit_or_duplicates(self):
        first = self.train()
        second = self.train()
        self.assertEqual(second.status, TrainingStatus.IDEMPOTENT_EXISTING)
        self.assertEqual((first.training_run_fingerprint, first.artifact_fingerprint), (second.training_run_fingerprint, second.artifact_fingerprint))
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_model_training_runs").fetchone()[0], 1)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_model_artifacts").fetchone()[0], 1)

    def test_changed_request_id_content_conflicts_without_writes(self):
        self.train()
        changed = replace(command(self.split, self.fold), training_run_name="Changed")
        self.assertEqual(self.service.train(changed).status, TrainingStatus.CONFLICT)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_model_training_runs").fetchone()[0], 1)

    def test_split_and_fold_fingerprint_mismatches_reject_without_writes(self):
        for changed in (
            replace(command(self.split, self.fold), source_split_fingerprint="a" * 64),
            replace(command(self.split, self.fold), fold_fingerprint="b" * 64),
        ):
            self.assertEqual(self.service.train(changed).status, TrainingStatus.REJECTED_SOURCE_SPLIT)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_model_training_runs").fetchone()[0], 0)

    def test_only_train_and_validation_links_exist_and_test_is_never_persisted(self):
        outcome = self.train()
        links = self.repository.list_training_examples(outcome.training_run_id)
        self.assertEqual({item.partition for item in links}, {Partition.TRAIN, Partition.VALIDATION})
        self.assertNotIn(Partition.TEST, {item.partition for item in links})
        self.assertEqual(verify_training_partition_only(self.repository, outcome.training_run_id), ())

    def test_test_examples_are_never_materialized_by_training(self):
        loaded = []
        underlying = self.training_repository

        class SpyTrainingRepository:
            def load_dataset_identity(self, dataset_build_id):
                return underlying.load_dataset_identity(dataset_build_id)

            def load_training_example(self, training_example_id):
                loaded.append(training_example_id)
                return underlying.load_training_example(training_example_id)

        split_repository = SQLiteHistoricalDatasetSplitRepository(self.database, migrate=False)
        test_ids = {
            item.training_example_id
            for item in split_repository.list_assignments_by_partition(self.fold.fold_id, Partition.TEST)
        }
        trainer = HistoricalModelTrainer(SpyTrainingRepository(), split_repository, self.repository)
        outcome = trainer.train(command(self.split, self.fold))
        self.assertEqual(outcome.status, TrainingStatus.MODEL_TRAINED)
        self.assertTrue(test_ids)
        self.assertTrue(test_ids.isdisjoint(loaded))

    def test_preprocessing_is_train_only_stable_and_persisted(self):
        outcome = self.train()
        artifact = self.repository.load_model_artifact(outcome.artifact_id)
        train_links = tuple(item for item in self.repository.list_training_examples(outcome.training_run_id) if item.partition is Partition.TRAIN)
        examples = tuple(self.training_repository.load_training_example(item.training_example_id) for item in train_links)
        fitted = fit_preprocessing(examples, FEATURE_NAMES, PreprocessingPolicy())
        self.assertEqual(fitted.preprocessing_fingerprint, artifact.preprocessing.preprocessing_fingerprint)
        self.assertEqual(transform_examples(examples, fitted), transform_examples(examples, fitted))
        self.assertEqual(verify_preprocessing_train_only(self.repository, self.training_repository, outcome.training_run_id), ())

    def test_inspection_and_reproduction_are_read_only(self):
        outcome = self.train()
        before = self.database.connection.total_changes
        self.assertEqual(summarize_training_run(self.repository, outcome.training_run_id)["training_rows"], outcome.training_row_count)
        self.assertIsNotNone(inspect_model_artifact(self.repository, outcome.artifact_id))
        self.assertEqual(inspect_target_estimator(self.repository, outcome.artifact_id, "HOME_WIN").target_order, 0)
        self.assertEqual(verify_artifact_fingerprint(self.repository, outcome.artifact_id), ())
        self.assertEqual(verify_estimator_fingerprints(self.repository, outcome.artifact_id), ())
        self.assertTrue(reproduce_training_metrics(self.repository, self.training_repository, outcome.training_run_id))
        self.assertEqual(compare_reproduced_predictions((1,), (1,)), ())
        self.assertEqual(before, self.database.connection.total_changes)

    def test_repository_queries_and_bounded_parameter_stream(self):
        outcome = self.train()
        self.assertEqual(self.repository.find_by_request_id("model-training-request").training_run_id, outcome.training_run_id)
        self.assertEqual(self.repository.find_by_training_run_fingerprint(outcome.training_run_fingerprint).artifact.artifact_id, outcome.artifact_id)
        self.assertEqual(len(self.repository.list_training_runs_for_fold(self.fold.fold_id)), 1)
        self.assertEqual(len(tuple(self.repository.stream_artifact_parameters(outcome.artifact_id))), 11)

    def test_feature_compatibility_rejects_order_and_fingerprint_changes(self):
        outcome = self.train()
        artifact = self.repository.load_model_artifact(outcome.artifact_id)
        self.assertEqual(verify_feature_compatibility(artifact, artifact.feature_schema_version, FEATURE_SCHEMA_FINGERPRINT, FEATURE_NAMES), ())
        self.assertIn("FEATURE_ORDER_MISMATCH", verify_feature_compatibility(artifact, artifact.feature_schema_version, FEATURE_SCHEMA_FINGERPRINT, tuple(reversed(FEATURE_NAMES))))

    def test_append_only_triggers_protect_all_six_tables(self):
        outcome = self.train()
        cases = (
            ("historical_model_training_runs", "training_run_id", outcome.training_run_id),
            ("historical_model_artifacts", "artifact_id", outcome.artifact_id),
            ("historical_model_artifact_targets", "artifact_id", outcome.artifact_id),
            ("historical_model_preprocessing_features", "artifact_id", outcome.artifact_id),
            ("historical_model_training_examples", "training_run_id", outcome.training_run_id),
            ("historical_model_metrics", "training_run_id", outcome.training_run_id),
        )
        for table, column, value in cases:
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.database.connection.execute(f"DELETE FROM {table} WHERE {column}=?", (value,))

    def test_atomic_rollback_removes_partial_run_and_artifact(self):
        self.database.connection.execute("""
            CREATE TRIGGER reject_model_target BEFORE INSERT ON historical_model_artifact_targets
            BEGIN SELECT RAISE(ABORT, 'injected target failure'); END
        """)
        outcome = self.train()
        self.assertEqual(outcome.status, TrainingStatus.PERSISTENCE_FAILURE)
        for table in ("historical_model_training_runs", "historical_model_artifacts", "historical_model_artifact_targets"):
            self.assertEqual(self.database.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)


class LightweightContractTests(unittest.TestCase):
    def test_train_only_median_scaling_and_all_missing_rejection(self):
        rows = (
            SimpleNamespace(ordered_feature_vector=(Decimal("1"), None)),
            SimpleNamespace(ordered_feature_vector=(Decimal("3"), Decimal("2"))),
            SimpleNamespace(ordered_feature_vector=(Decimal("9"), Decimal("4"))),
        )
        fitted = fit_preprocessing(rows, ("first", "second"), PreprocessingPolicy())
        self.assertEqual(fitted.features[0].imputation_value, 3.0)
        self.assertEqual(fitted.features[1].imputation_value, 3.0)
        all_missing = tuple(SimpleNamespace(ordered_feature_vector=(None,)) for _ in range(3))
        with self.assertRaises(PreprocessingError):
            fit_preprocessing(all_missing, ("missing",), PreprocessingPolicy())

    def test_validation_values_cannot_change_train_fitted_preprocessing(self):
        train = tuple(SimpleNamespace(ordered_feature_vector=(Decimal(value),)) for value in (1, 3, 5))
        first = fit_preprocessing(train, ("feature",), PreprocessingPolicy())
        validation = (SimpleNamespace(ordered_feature_vector=(Decimal("999999"),)),)
        self.assertEqual(first, fit_preprocessing(train, ("feature",), PreprocessingPolicy()))
        self.assertNotEqual(first.features[0].scaling_mean, float(validation[0].ordered_feature_vector[0]))

    def test_deterministic_estimators_repeat_exact_parameters(self):
        matrix = tuple((float(index % 3), float((index + 1) % 4)) for index in range(24))
        targets = {
            "MATCH_RESULT": tuple(index % 3 for index in range(24)),
            "TOTAL_GOALS_BUCKET": tuple(index % 4 for index in range(24)),
            "BTTS_YES": tuple(index % 2 for index in range(24)),
        }
        policy = ModelTrainingPolicy(convergence_tolerance=Decimal("0.002"))
        self.assertEqual(fit_estimators(matrix, targets, policy, 17), fit_estimators(matrix, targets, policy, 17))

    def test_non_convergence_fails_closed(self):
        matrix = tuple((float(index), 1.0) for index in range(12))
        targets = {
            "MATCH_RESULT": tuple(index % 3 for index in range(12)),
            "TOTAL_GOALS_BUCKET": tuple(index % 4 for index in range(12)),
            "BTTS_YES": tuple(index % 2 for index in range(12)),
        }
        policy = ModelTrainingPolicy(maximum_iterations=1, convergence_tolerance=Decimal("0.000000000001"))
        with self.assertRaises(EstimatorConvergenceError):
            fit_estimators(matrix, targets, policy, 0)

    def test_insufficient_result_binary_and_totals_support_reject(self):
        with self.assertRaises(InsufficientClassSupportError):
            validate_class_support({
                "MATCH_RESULT": (0, 1, 0, 1),
                "TOTAL_GOALS_BUCKET": (0, 1, 2, 3),
                "BTTS_YES": (0, 1, 0, 1),
            })
        with self.assertRaises(InsufficientClassSupportError):
            validate_class_support({
                "MATCH_RESULT": (0, 1, 2, 0),
                "TOTAL_GOALS_BUCKET": (0, 0, 0, 0),
                "BTTS_YES": (0, 1, 0, 1),
            })


class MigrationAndStartupTests(unittest.TestCase):
    def test_fresh_v26_and_v25_upgrade(self):
        fresh = Database(":memory:")
        MigrationManager(fresh.connection).migrate()
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 36)
        self.assertEqual(fresh.connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'historical_model_%'").fetchone()[0], 6)
        fresh.close()

        upgrade = Database(":memory:")
        for migration in MIGRATIONS:
            if migration.version > 25:
                break
            for statement in migration.statements:
                upgrade.connection.execute(statement)
            upgrade.connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            upgrade.connection.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?, 'now')", (migration.version,))
        MigrationManager(upgrade.connection).migrate()
        self.assertEqual(upgrade.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 36)
        upgrade.close()

    def test_import_is_inert_and_creates_no_training_rows(self):
        database = Database(":memory:")
        MigrationManager(database.connection).migrate()
        before = database.connection.total_changes
        import app.historical_model_training
        self.assertEqual(database.connection.execute("SELECT COUNT(*) FROM historical_model_training_runs").fetchone()[0], 0)
        self.assertEqual(before, database.connection.total_changes)
        database.close()


if __name__ == "__main__":
    unittest.main()
