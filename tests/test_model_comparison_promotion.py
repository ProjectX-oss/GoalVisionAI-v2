import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.historical_backtesting import (
    HistoricalBacktestCommand,
    HistoricalOddsSnapshot,
    OddsMarketStatus,
    SQLiteHistoricalBacktestingRepository,
    SupportedMarket,
    build_historical_backtesting_service,
    create_odds_dataset,
    odds_source_fingerprint,
)
from app.historical_dataset_split import (
    DatasetSplitCommand,
    RatioByChronology,
    SQLiteHistoricalDatasetSplitRepository,
    SplitStrategy,
    build_historical_dataset_split_service,
)
from app.historical_model_training import (
    FEATURE_SCHEMA_FINGERPRINT,
    SQLiteHistoricalModelTrainingRepository,
    build_historical_model_training_service,
)
from app.historical_probability_calibration import (
    CalibrationMethod,
    HistoricalCalibrationCommand,
    SQLiteHistoricalProbabilityCalibrationRepository,
    build_historical_probability_calibration_service,
)
from app.model_comparison_promotion import (
    ChallengerCandidate,
    ComparisonMode,
    ComparisonScope,
    ComparisonStatus,
    Direction,
    GateStatus,
    ModelComparisonCommand,
    Recommendation,
    SQLiteModelComparisonRepository,
    build_metric_evaluation,
    build_model_comparison_promotion_service,
    calculate_promotion_score,
    calculate_statistical_evidence,
    inspect_challenger_evaluation,
    inspect_final_recommendation,
    rank_challengers,
    summarize_comparison_run,
    validate_comparison_command,
    verify_comparison_fingerprints,
    verify_scope_compatibility,
)
from tests.test_historical_model_training import (
    build_foundations,
    command as training_command,
)
from tests.test_historical_probability_calibration import low_support_policy


class ModelComparisonPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = Database(":memory:")
        dataset, _, _ = build_foundations(cls.database)
        split_outcome = build_historical_dataset_split_service(
            cls.database, migrate=False
        ).create(
            DatasetSplitCommand(
                split_request_id="comparison-source-split",
                split_name="Comparison source split",
                source_dataset_build_id=dataset.dataset_build_id,
                source_dataset_fingerprint=dataset.dataset_fingerprint,
                strategy=SplitStrategy.RATIO_BY_CHRONOLOGY_V1,
                ratios=RatioByChronology("0.45", "0.45", "0.10"),
                split_timestamp="2026-07-23T01:00:00Z",
            )
        )
        split_repository = SQLiteHistoricalDatasetSplitRepository(
            cls.database, migrate=False
        )
        cls.split = split_repository.load_dataset_split(split_outcome.split_id)
        cls.fold = cls.split.folds[0]
        model_service = build_historical_model_training_service(
            cls.database, migrate=False
        )
        first = model_service.train(
            training_command(cls.split, cls.fold, "comparison-champion-training")
        )
        second = model_service.train(
            training_command(cls.split, cls.fold, "comparison-challenger-training")
        )
        cls.model_repository = SQLiteHistoricalModelTrainingRepository(
            cls.database, migrate=False
        )
        cls.champion_training = cls.model_repository.load_training_run(
            first.training_run_id
        )
        cls.challenger_training = cls.model_repository.load_training_run(
            second.training_run_id
        )
        calibration_service = build_historical_probability_calibration_service(
            cls.database, policy=low_support_policy(), migrate=False
        )
        cls.champion_calibration = cls._calibrate(
            calibration_service, cls.champion_training, "comparison-champion-calibration"
        )
        cls.challenger_calibration = cls._calibrate(
            calibration_service, cls.challenger_training, "comparison-challenger-calibration"
        )
        calibration_repository = SQLiteHistoricalProbabilityCalibrationRepository(
            cls.database, migrate=False
        )
        cls.champion_calibration = calibration_repository.load_calibration_run(
            cls.champion_calibration.calibration_run_id
        )
        cls.challenger_calibration = calibration_repository.load_calibration_run(
            cls.challenger_calibration.calibration_run_id
        )
        from app.historical_dataset_split import Partition
        from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository

        training_repository = SQLiteHistoricalTrainingDatasetRepository(
            cls.database, migrate=False
        )
        examples = tuple(
            training_repository.load_training_example(item.training_example_id)
            for item in split_repository.list_assignments_by_partition(
                cls.fold.fold_id, Partition.TEST
            )
        )
        cls.odds = cls._odds_dataset("comparison-shared-odds", examples)
        backtest_service = build_historical_backtesting_service(
            cls.database, migrate=False
        )
        cls.champion_outcome = backtest_service.run(
            cls._backtest_command(
                "comparison-champion-backtest",
                cls.champion_training,
                cls.champion_calibration,
            ),
            odds_dataset=cls.odds,
        )
        cls.challenger_outcome = backtest_service.run(
            cls._backtest_command(
                "comparison-challenger-backtest",
                cls.challenger_training,
                cls.challenger_calibration,
            ),
            odds_dataset=cls.odds,
        )
        if cls.champion_outcome.backtest_run_id is None:
            raise AssertionError(cls.champion_outcome)
        if cls.challenger_outcome.backtest_run_id is None:
            raise AssertionError(cls.challenger_outcome)
        cls.backtest_repository = SQLiteHistoricalBacktestingRepository(
            cls.database, migrate=False
        )
        cls.champion_backtest = cls.backtest_repository.load_backtest_run(
            cls.champion_outcome.backtest_run_id
        )
        cls.challenger_backtest = cls.backtest_repository.load_backtest_run(
            cls.challenger_outcome.backtest_run_id
        )
        cls.service = build_model_comparison_promotion_service(
            cls.database, migrate=False
        )
        cls.command = cls._comparison_command("comparison-request")
        cls.outcome = cls.service.compare(cls.command)
        cls.repository = SQLiteModelComparisonRepository(cls.database, migrate=False)

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    @classmethod
    def _calibrate(cls, service, training, request_id):
        artifact = training.artifact
        return service.fit(
            HistoricalCalibrationCommand(
                calibration_request_id=request_id,
                calibration_run_name=request_id,
                source_training_run_id=training.training_run_id,
                source_training_run_fingerprint=training.training_run_fingerprint,
                source_model_artifact_id=artifact.artifact_id,
                source_model_artifact_fingerprint=artifact.artifact_fingerprint,
                source_split_id=cls.split.split_id,
                source_split_fingerprint=cls.split.split_fingerprint,
                fold_id=cls.fold.fold_id,
                fold_fingerprint=cls.fold.fold_fingerprint,
                feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
                match_result_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
                totals_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
                btts_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
                calibration_timestamp="2026-07-23T02:00:00Z",
            )
        )

    @classmethod
    def _odds_dataset(cls, identity, examples):
        snapshots = []
        for example in examples:
            kickoff = datetime.fromisoformat(
                example.kickoff_utc.replace("Z", "+00:00")
            )
            for market in SupportedMarket:
                snapshot = HistoricalOddsSnapshot(
                    odds_snapshot_id=f"{identity}-{example.historical_match_id}-{market.value}",
                    source_identity="supplied-fixture",
                    source_version="v1",
                    historical_match_id=example.historical_match_id,
                    competition=example.competition,
                    kickoff_utc=example.kickoff_utc,
                    snapshot_timestamp_utc=kickoff - timedelta(hours=1),
                    bookmaker_identity="fixture-bookmaker",
                    market_identity=market,
                    selection_identity=market.value,
                    decimal_odds=Decimal("3.00"),
                    currency="EUR",
                    market_status=OddsMarketStatus.ACTIVE,
                    source_record_identity=f"record-{example.historical_match_id}-{market.value}",
                    source_fingerprint="0" * 64,
                )
                snapshots.append(
                    replace(
                        snapshot,
                        source_fingerprint=odds_source_fingerprint(snapshot),
                    )
                )
        return create_odds_dataset(identity, tuple(snapshots))

    @classmethod
    def _backtest_command(cls, request_id, training, calibration):
        artifact = training.artifact
        artifact_set = calibration.artifact_set
        return HistoricalBacktestCommand(
            backtest_request_id=request_id,
            backtest_run_name=request_id,
            source_split_id=cls.split.split_id,
            source_split_fingerprint=cls.split.split_fingerprint,
            fold_id=cls.fold.fold_id,
            fold_fingerprint=cls.fold.fold_fingerprint,
            source_training_run_id=training.training_run_id,
            source_training_run_fingerprint=training.training_run_fingerprint,
            model_artifact_id=artifact.artifact_id,
            model_artifact_fingerprint=artifact.artifact_fingerprint,
            calibration_run_id=calibration.calibration_run_id,
            calibration_run_fingerprint=calibration.calibration_run_fingerprint,
            calibration_artifact_set_id=artifact_set.artifact_set_id,
            calibration_artifact_set_fingerprint=artifact_set.artifact_set_fingerprint,
            odds_dataset_id=cls.odds.odds_dataset_id,
            odds_dataset_fingerprint=cls.odds.odds_dataset_fingerprint,
            initial_bankroll=Decimal("1000"),
            backtest_timestamp="2026-07-23T03:00:00Z",
        )

    @classmethod
    def _comparison_command(cls, request_id, **changes):
        candidate = ChallengerCandidate(
            challenger_candidate_id="challenger-a",
            model_artifact_id=cls.challenger_training.artifact.artifact_id,
            model_artifact_fingerprint=cls.challenger_training.artifact.artifact_fingerprint,
            calibration_artifact_set_id=cls.challenger_calibration.artifact_set.artifact_set_id,
            calibration_artifact_set_fingerprint=cls.challenger_calibration.artifact_set.artifact_set_fingerprint,
            backtest_run_id=cls.challenger_backtest.backtest_run_id,
            backtest_run_fingerprint=cls.challenger_backtest.backtest_run_fingerprint,
            label="Challenger A",
        )
        values = dict(
            comparison_request_id=request_id,
            comparison_run_name="Champion vs challenger",
            champion_model_artifact_id=cls.champion_training.artifact.artifact_id,
            champion_model_artifact_fingerprint=cls.champion_training.artifact.artifact_fingerprint,
            champion_calibration_artifact_set_id=cls.champion_calibration.artifact_set.artifact_set_id,
            champion_calibration_artifact_set_fingerprint=cls.champion_calibration.artifact_set.artifact_set_fingerprint,
            champion_backtest_run_id=cls.champion_backtest.backtest_run_id,
            champion_backtest_run_fingerprint=cls.champion_backtest.backtest_run_fingerprint,
            challengers=(candidate,),
            scope=ComparisonScope(
                comparison_scope_version="comparison-scope-v1",
                required_minimum_shared_sample_size=1,
                required_minimum_selected_bet_count=1,
            ),
            comparison_timestamp="2026-07-23T04:00:00Z",
        )
        values.update(changes)
        return ModelComparisonCommand(**values)

    def test_complete_comparison_persists_all_evidence_without_activation(self):
        self.assertEqual(self.outcome.status, ComparisonStatus.COMPARISON_COMPLETED)
        self.assertEqual(self.outcome.valid_challenger_count, 1)
        run = self.repository.load_comparison_run(self.outcome.comparison_run_id)
        evaluation = run.evaluations[0]
        self.assertTrue(evaluation.source_evidence)
        self.assertTrue(evaluation.metric_evaluations)
        self.assertTrue(evaluation.stability_groups)
        self.assertEqual(len(evaluation.statistical_evidence), 4)
        self.assertTrue(evaluation.gate_evaluations)
        self.assertEqual(len(evaluation.score_components), 6)
        self.assertIn(
            evaluation.recommendation,
            set(Recommendation),
        )
        self.assertIn(
            run.final_recommendation,
            set(Recommendation),
        )

    def test_validation_rejects_dictionary_duplicates_self_comparison_and_missing_timestamp(self):
        self.assertEqual(
            self.service.compare({}).status,
            ComparisonStatus.REJECTED_INVALID_REQUEST,
        )
        candidate = self.command.challengers[0]
        duplicate = replace(
            candidate, challenger_candidate_id="challenger-b"
        )
        self.assertEqual(
            self.service.compare(
                replace(
                    self.command,
                    comparison_request_id="duplicate-request",
                    challengers=(candidate, duplicate),
                )
            ).status,
            ComparisonStatus.REJECTED_INVALID_REQUEST,
        )
        self_compare = replace(
            candidate,
            model_artifact_id=self.command.champion_model_artifact_id,
        )
        self.assertEqual(
            self.service.compare(
                replace(
                    self.command,
                    comparison_request_id="self-request",
                    challengers=(self_compare,),
                )
            ).status,
            ComparisonStatus.REJECTED_INVALID_REQUEST,
        )
        self.assertEqual(
            self.service.compare(
                replace(
                    self.command,
                    comparison_request_id="timestamp-request",
                    comparison_timestamp=None,
                )
            ).status,
            ComparisonStatus.REJECTED_INVALID_REQUEST,
        )

    def test_source_fingerprint_mismatch_is_excluded_without_writes(self):
        before = self.database.connection.execute(
            "SELECT COUNT(*) FROM model_comparison_runs"
        ).fetchone()[0]
        bad = replace(
            self.command.challengers[0],
            model_artifact_fingerprint="bad",
        )
        outcome = self.service.compare(
            replace(
                self.command,
                comparison_request_id="bad-source-request",
                challengers=(bad,),
            )
        )
        self.assertEqual(outcome.status, ComparisonStatus.NO_VALID_CHALLENGERS)
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM model_comparison_runs"
            ).fetchone()[0],
            before,
        )

    def test_repeated_pair_requires_materially_distinct_scope_or_policy(self):
        repeated = self.service.compare(
            replace(
                self.command,
                comparison_request_id="repeated-pair-request",
                comparison_timestamp="2026-07-23T04:30:00Z",
            )
        )
        self.assertEqual(
            repeated.status, ComparisonStatus.NO_VALID_CHALLENGERS
        )
        self.assertIn(
            "REPEATED_CHAMPION_CHALLENGER_PAIR_WITHOUT_DISTINCT_SCOPE_OR_POLICY",
            repeated.ordered_reason_codes,
        )

    def test_missing_challenger_sources_fail_closed(self):
        candidate = replace(
            self.command.challengers[0],
            challenger_candidate_id="missing-model",
            model_artifact_id="missing",
        )
        outcome = self.service.compare(
            replace(
                self.command,
                comparison_request_id="missing-source-request",
                challengers=(candidate,),
            )
        )
        self.assertEqual(outcome.status, ComparisonStatus.NO_VALID_CHALLENGERS)
        self.assertIn("CHALLENGER_MODEL_NOT_FOUND", outcome.ordered_reason_codes)

    def test_exact_intersection_and_policy_normalized_scope_modes(self):
        exact = validate_comparison_command(self.command, self.service._policy)
        self.assertEqual(exact.scope.mode, ComparisonMode.EXACT_SHARED_BACKTEST_SCOPE)
        intersection = self.service.compare(
            replace(
                self.command,
                comparison_request_id="intersection-request",
                scope=replace(
                    self.command.scope,
                    mode=ComparisonMode.INTERSECTION_SCOPE,
                ),
            )
        )
        normalized = self.service.compare(
            replace(
                self.command,
                comparison_request_id="normalized-request",
                scope=replace(
                    self.command.scope,
                    mode=ComparisonMode.POLICY_NORMALIZED_SCOPE,
                ),
            )
        )
        self.assertEqual(
            intersection.status,
            ComparisonStatus.COMPARISON_COMPLETED,
            intersection.ordered_reason_codes,
        )
        self.assertEqual(
            normalized.status,
            ComparisonStatus.COMPARISON_COMPLETED,
            normalized.ordered_reason_codes,
        )

    def test_metric_direction_scoring_and_failed_gate_cannot_be_overridden(self):
        lower = build_metric_evaluation(
            "PREDICTIVE",
            "OVERALL",
            "log_loss",
            Decimal(".5"),
            Decimal(".4"),
            Direction.LOWER_IS_BETTER,
            0,
            Decimal(".02"),
        )
        higher = build_metric_evaluation(
            "BETTING",
            "OVERALL",
            "roi",
            Decimal(".1"),
            Decimal(".2"),
            Direction.HIGHER_IS_BETTER,
            1,
            Decimal(".02"),
        )
        self.assertGreater(lower.normalized_score, Decimal(".5"))
        self.assertGreater(higher.normalized_score, Decimal(".5"))
        evaluation = self.outcome.challenger_evaluations[0]
        components, score = calculate_promotion_score(
            evaluation.metric_evaluations,
            evaluation.stability_groups,
            evaluation.gate_evaluations,
            evaluation.statistical_evidence,
            self.service._policy,
        )
        self.assertEqual(sum(item.weight for item in components), Decimal(1))
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 1)
        if any(
            item.mandatory and item.status is GateStatus.FAIL
            for item in evaluation.gate_evaluations
        ):
            self.assertIsNot(
                evaluation.recommendation,
                Recommendation.PROMOTE_CHALLENGER,
            )

    def test_insufficient_evidence_is_explicit(self):
        outcome = self.service.compare(
            replace(
                self.command,
                comparison_request_id="insufficient-request",
                scope=replace(
                    self.command.scope,
                    comparison_scope_version="insufficient-scope-v1",
                    required_minimum_shared_sample_size=100000,
                    required_minimum_selected_bet_count=100000,
                ),
            )
        )
        self.assertEqual(outcome.status, ComparisonStatus.COMPARISON_COMPLETED)
        self.assertEqual(
            outcome.challenger_evaluations[0].recommendation,
            Recommendation.INSUFFICIENT_EVIDENCE,
        )

    def test_exact_scope_rejects_different_odds_identity(self):
        incompatible = replace(
            self.challenger_backtest,
            command=replace(
                self.challenger_backtest.command,
                odds_dataset_fingerprint="different",
            ),
        )
        self.assertEqual(
            verify_scope_compatibility(
                self.champion_backtest,
                incompatible,
                validate_comparison_command(
                    self.command, self.service._policy
                ).scope,
            ),
            ("EXACT_SHARED_SCOPE_MISMATCH",),
        )

    def test_multiple_challenger_ranking_has_one_winner_and_candidate_id_tie_break(self):
        base = self.outcome.challenger_evaluations[0]
        first = replace(
            base,
            candidate=replace(
                base.candidate, challenger_candidate_id="challenger-z"
            ),
            recommendation=Recommendation.PROMOTE_CHALLENGER,
        )
        second = replace(
            base,
            candidate=replace(
                base.candidate, challenger_candidate_id="challenger-a"
            ),
            recommendation=Recommendation.PROMOTE_CHALLENGER,
        )
        ranked = rank_challengers((first, second))
        self.assertEqual(
            ranked[0].candidate.challenger_candidate_id, "challenger-a"
        )
        finalized = self.service._rank_and_limit_winner((first, second))
        self.assertEqual(
            sum(
                item.recommendation is Recommendation.PROMOTE_CHALLENGER
                for item in finalized
            ),
            1,
        )
        self.assertEqual(
            finalized[1].recommendation, Recommendation.KEEP_CHAMPION
        )

    def test_statistical_bootstrap_is_seeded_and_has_no_random_drift(self):
        first = calculate_statistical_evidence(
            self.champion_backtest,
            self.challenger_backtest,
            comparison_fingerprint="comparison",
            policy=self.service._policy,
        )
        second = calculate_statistical_evidence(
            self.champion_backtest,
            self.challenger_backtest,
            comparison_fingerprint="comparison",
            policy=self.service._policy,
        )
        self.assertEqual(first, second)
        self.assertTrue(all(item.bootstrap_iterations == 500 for item in first))

    def test_idempotency_conflict_and_atomic_rollback(self):
        replay = self.service.compare(self.command)
        conflict = self.service.compare(
            replace(self.command, comparison_run_name="Different")
        )
        self.assertEqual(replay.status, ComparisonStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(conflict.status, ComparisonStatus.CONFLICT)
        failing = self._comparison_command(
            "comparison-atomic-failure",
            scope=replace(
                self.command.scope,
                comparison_scope_version="comparison-scope-atomic-v1",
            ),
        )
        original = self.service._comparisons._insert_metrics
        self.service._comparisons._insert_metrics = lambda *_: (_ for _ in ()).throw(
            sqlite3.IntegrityError("forced")
        )
        try:
            outcome = self.service.compare(failing)
        finally:
            self.service._comparisons._insert_metrics = original
        self.assertEqual(outcome.status, ComparisonStatus.PERSISTENCE_FAILURE)
        self.assertEqual(
            self.database.connection.execute(
                "SELECT COUNT(*) FROM model_comparison_runs WHERE comparison_request_id='comparison-atomic-failure'"
            ).fetchone()[0],
            0,
        )

    def test_every_persistence_stage_rolls_back_atomically(self):
        stages = (
            "_insert_run",
            "_insert_candidates",
            "_insert_evidence",
            "_insert_metrics",
            "_insert_stability",
            "_insert_statistics",
            "_insert_gates",
            "_insert_scores",
            "_insert_recommendations",
            "_insert_exclusions",
        )
        for index, stage in enumerate(stages):
            with self.subTest(stage=stage):
                request_id = f"rollback-{index}"
                command = self._comparison_command(
                    request_id,
                    scope=replace(
                        self.command.scope,
                        comparison_scope_version=f"rollback-scope-{index}",
                    ),
                )
                original = getattr(self.service._comparisons, stage)
                setattr(
                    self.service._comparisons,
                    stage,
                    lambda *_: (_ for _ in ()).throw(
                        sqlite3.IntegrityError("forced")
                    ),
                )
                try:
                    outcome = self.service.compare(command)
                finally:
                    setattr(self.service._comparisons, stage, original)
                self.assertEqual(
                    outcome.status, ComparisonStatus.PERSISTENCE_FAILURE
                )
                self.assertEqual(
                    self.database.connection.execute(
                        "SELECT COUNT(*) FROM model_comparison_runs WHERE comparison_request_id=?",
                        (request_id,),
                    ).fetchone()[0],
                    0,
                )

    def test_append_only_inspection_and_fingerprints_are_read_only(self):
        before = self.database.connection.total_changes
        summary = summarize_comparison_run(
            self.repository, self.outcome.comparison_run_id
        )
        self.assertEqual(summary["valid_challenger_count"], 1)
        self.assertIsNotNone(
            inspect_challenger_evaluation(
                self.repository,
                self.outcome.comparison_run_id,
                "challenger-a",
            )
        )
        self.assertIsNotNone(
            inspect_final_recommendation(
                self.repository, self.outcome.comparison_run_id
            )
        )
        self.assertEqual(
            verify_comparison_fingerprints(
                self.repository, self.outcome.comparison_run_id
            ),
            (),
        )
        self.assertEqual(before, self.database.connection.total_changes)
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "UPDATE model_comparison_runs SET outcome='CHANGED' WHERE comparison_run_id=?",
                (self.outcome.comparison_run_id,),
            )
        self.database.rollback()

    def test_repository_queries_and_bounded_streaming(self):
        run_id = self.outcome.comparison_run_id
        champion_runs = self.repository.list_comparisons_for_champion_model(
            self.command.champion_model_artifact_id
        )
        challenger_runs = self.repository.list_comparisons_for_challenger_model(
            self.command.challengers[0].model_artifact_id
        )
        self.assertIn(run_id, {item.comparison_run_id for item in champion_runs})
        self.assertIn(run_id, {item.comparison_run_id for item in challenger_runs})
        self.assertTrue(tuple(self.repository.stream_comparison_events(run_id)))


class ModelComparisonMigrationTests(unittest.TestCase):
    def test_fresh_v29_and_v28_upgrade(self):
        fresh = Database(":memory:")
        SQLiteModelComparisonRepository(fresh)
        self.assertEqual(
            fresh.connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0],
            34,
        )
        self.assertEqual(
            len(
                fresh.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'model_comparison_%'"
                ).fetchall()
            ),
            10,
        )
        self.assertEqual(
            len(
                fresh.connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'model_comparison_%_no_%'"
                ).fetchall()
            ),
            20,
        )
        fresh.close()
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        with patch("app.database.migrations.MIGRATIONS", MIGRATIONS[:28]):
            MigrationManager(connection).migrate()
        MigrationManager(connection).migrate()
        self.assertEqual(
            connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0],
            34,
        )
        connection.close()

    def test_import_and_factory_have_zero_automatic_comparisons(self):
        database = Database(":memory:")
        SQLiteModelComparisonRepository(database)
        before = database.connection.total_changes
        service = build_model_comparison_promotion_service(database, migrate=False)
        self.assertIsNotNone(service)
        self.assertEqual(before, database.connection.total_changes)
        self.assertEqual(
            database.connection.execute(
                "SELECT COUNT(*) FROM model_comparison_runs"
            ).fetchone()[0],
            0,
        )
        database.close()


class ModelComparisonStabilityRegressionTests(unittest.TestCase):
    def test_profit_and_loss_concentrations_restore_as_decimals(self):
        from app.model_comparison_promotion.stability import _snapshot

        restored = _snapshot(
            '{"loss_concentration":"0.25","profit_concentration":"0.75"}'
        )
        self.assertEqual(restored["profit_concentration"], Decimal("0.75"))
        self.assertEqual(restored["loss_concentration"], Decimal("0.25"))


if __name__ == "__main__":
    unittest.main()
