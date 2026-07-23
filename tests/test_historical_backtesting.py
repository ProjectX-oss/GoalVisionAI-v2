import sqlite3
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

from app.database import Database, MigrationManager
from app.database.migrations import MIGRATIONS
from app.historical_backtesting import (
    BacktestStatus,
    HistoricalBacktestCommand,
    HistoricalOddsSnapshot,
    OddsMarketStatus,
    SQLiteHistoricalBacktestingRepository,
    SettlementStatus,
    SupportedMarket,
    build_historical_backtesting_service,
    calculate_betting_metrics,
    calculate_predictive_metrics,
    create_odds_dataset,
    inspect_backtest_prediction,
    inspect_backtest_selection,
    inspect_backtest_settlement,
    inspect_bankroll_entry,
    inspect_market_assessment,
    odds_source_fingerprint,
    settle_selection,
    summarize_backtest_run,
    verify_backtest_fingerprints,
    verify_equal_kickoff_group_handling,
    verify_odds_temporal_safety,
    verify_selection_policy_alignment,
    verify_test_partition_only,
)
from app.historical_dataset_split import (
    DatasetSplitCommand,
    Partition,
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
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository
from tests.test_historical_model_training import build_foundations, command as training_command
from tests.test_historical_probability_calibration import low_support_policy


class HistoricalBacktestingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = Database(":memory:")
        dataset, _, _ = build_foundations(cls.database)
        split_outcome = build_historical_dataset_split_service(cls.database, migrate=False).create(
            DatasetSplitCommand(
                split_request_id="backtesting-source-split",
                split_name="Backtesting source split",
                source_dataset_build_id=dataset.dataset_build_id,
                source_dataset_fingerprint=dataset.dataset_fingerprint,
                strategy=SplitStrategy.RATIO_BY_CHRONOLOGY_V1,
                ratios=RatioByChronology("0.45", "0.45", "0.10"),
                split_timestamp="2026-07-22T21:15:00Z",
            )
        )
        cls.split_repository = SQLiteHistoricalDatasetSplitRepository(cls.database, migrate=False)
        cls.split = cls.split_repository.load_dataset_split(split_outcome.split_id)
        cls.fold = cls.split.folds[0]
        training = build_historical_model_training_service(cls.database, migrate=False).train(
            training_command(cls.split, cls.fold, "backtesting-source-training")
        )
        cls.model_repository = SQLiteHistoricalModelTrainingRepository(cls.database, migrate=False)
        cls.training_run = cls.model_repository.load_training_run(training.training_run_id)
        cls.artifact = cls.training_run.artifact
        calibration_service = build_historical_probability_calibration_service(
            cls.database, policy=low_support_policy(), migrate=False
        )
        calibration = calibration_service.fit(
            HistoricalCalibrationCommand(
                calibration_request_id="backtesting-source-calibration",
                calibration_run_name="Backtesting calibration",
                source_training_run_id=cls.training_run.training_run_id,
                source_training_run_fingerprint=cls.training_run.training_run_fingerprint,
                source_model_artifact_id=cls.artifact.artifact_id,
                source_model_artifact_fingerprint=cls.artifact.artifact_fingerprint,
                source_split_id=cls.split.split_id,
                source_split_fingerprint=cls.split.split_fingerprint,
                fold_id=cls.fold.fold_id,
                fold_fingerprint=cls.fold.fold_fingerprint,
                feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
                match_result_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
                totals_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
                btts_method=CalibrationMethod.ISOTONIC_REGRESSION_V1,
                calibration_timestamp="2026-07-22T23:00:00Z",
            )
        )
        cls.calibration_repository = SQLiteHistoricalProbabilityCalibrationRepository(cls.database, migrate=False)
        cls.calibration_run = cls.calibration_repository.load_calibration_run(calibration.calibration_run_id)
        cls.calibration_set = cls.calibration_run.artifact_set
        cls.training_repository = SQLiteHistoricalTrainingDatasetRepository(cls.database, migrate=False)
        assignments = cls.split_repository.list_assignments_by_partition(cls.fold.fold_id, Partition.TEST)
        cls.examples = tuple(cls.training_repository.load_training_example(item.training_example_id) for item in assignments)
        cls.odds_dataset = cls._odds_dataset("backtesting-odds", cls.examples)
        cls.command = cls._command("backtesting-request", cls.odds_dataset)
        cls.service = build_historical_backtesting_service(cls.database, migrate=False)
        cls.outcome = cls.service.run(cls.command, odds_dataset=cls.odds_dataset)
        cls.repository = SQLiteHistoricalBacktestingRepository(cls.database, migrate=False)
        cls.backtest = cls.repository.load_backtest_run(cls.outcome.backtest_run_id)

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    @classmethod
    def _odds_dataset(cls, identity, examples, *, timestamp_delta=timedelta(hours=-1)):
        snapshots = []
        for example in examples:
            kickoff = datetime.fromisoformat(example.kickoff_utc.replace("Z", "+00:00"))
            for market in SupportedMarket:
                snapshot = HistoricalOddsSnapshot(
                    odds_snapshot_id=f"{identity}-{example.historical_match_id}-{market.value}",
                    source_identity="supplied-fixture", source_version="v1",
                    historical_match_id=example.historical_match_id,
                    competition=example.competition, kickoff_utc=example.kickoff_utc,
                    snapshot_timestamp_utc=kickoff + timestamp_delta,
                    bookmaker_identity="fixture-bookmaker",
                    market_identity=market, selection_identity=market.value,
                    decimal_odds=Decimal("3.00"), currency="EUR",
                    market_status=OddsMarketStatus.ACTIVE,
                    source_record_identity=f"record-{example.historical_match_id}-{market.value}",
                    source_fingerprint="0" * 64,
                )
                snapshots.append(replace(snapshot, source_fingerprint=odds_source_fingerprint(snapshot)))
        return create_odds_dataset(identity, tuple(snapshots))

    @classmethod
    def _command(cls, request_id, odds, **changes):
        values = dict(
            backtest_request_id=request_id, backtest_run_name="Complete TEST backtest",
            source_split_id=cls.split.split_id,
            source_split_fingerprint=cls.split.split_fingerprint,
            fold_id=cls.fold.fold_id, fold_fingerprint=cls.fold.fold_fingerprint,
            source_training_run_id=cls.training_run.training_run_id,
            source_training_run_fingerprint=cls.training_run.training_run_fingerprint,
            model_artifact_id=cls.artifact.artifact_id,
            model_artifact_fingerprint=cls.artifact.artifact_fingerprint,
            calibration_run_id=cls.calibration_run.calibration_run_id,
            calibration_run_fingerprint=cls.calibration_run.calibration_run_fingerprint,
            calibration_artifact_set_id=cls.calibration_set.artifact_set_id,
            calibration_artifact_set_fingerprint=cls.calibration_set.artifact_set_fingerprint,
            odds_dataset_id=odds.odds_dataset_id,
            odds_dataset_fingerprint=odds.odds_dataset_fingerprint,
            initial_bankroll=Decimal("1000"),
            backtest_timestamp="2026-07-23T00:00:00Z",
        )
        values.update(changes)
        return HistoricalBacktestCommand(**values)

    def test_complete_test_only_run_persists_all_evidence(self):
        self.assertEqual(self.outcome.status, BacktestStatus.BACKTEST_COMPLETED)
        self.assertEqual(self.outcome.prediction_count, len(self.examples))
        self.assertEqual(len(self.backtest.predictions), len(self.examples))
        self.assertEqual(len(self.backtest.assessments), len(self.examples) * len(SupportedMarket))
        self.assertEqual(len(self.backtest.selections), len(self.backtest.settlements))
        self.assertEqual(len(self.backtest.ledger), len(self.backtest.selections))
        self.assertTrue(self.backtest.metrics)
        self.assertEqual(len(self.backtest.reliability_bins), 11 * 2 * 10)
        self.assertEqual(
            verify_test_partition_only(
                self.split_repository, self.fold.fold_id,
                tuple(item.training_example_id for item in self.backtest.predictions),
            ),
            (),
        )

    def test_predictions_are_canonical_calibrated_and_metrics_include_every_test_row(self):
        for prediction in self.backtest.predictions:
            values = {item.target.value: item.probability for item in prediction.calibrated_probabilities.ordered_probabilities}
            self.assertEqual(values["HOME_WIN"] + values["DRAW"] + values["AWAY_WIN"], Decimal(1))
            self.assertGreaterEqual(values["OVER_1_5"], values["OVER_2_5"])
            self.assertGreaterEqual(values["OVER_2_5"], values["OVER_3_5"])
            self.assertEqual(values["BTTS_YES"] + values["BTTS_NO"], Decimal(1))
        metrics, bins, aggregate = calculate_predictive_metrics(self.backtest.predictions)
        self.assertTrue(metrics and bins and aggregate)
        self.assertIn(("calibrated_sample_count", Decimal(len(self.examples))), aggregate)

    def test_value_selection_staking_settlement_and_bankroll_are_aligned(self):
        self.assertEqual(verify_selection_policy_alignment(self.backtest.selections, self.backtest.assessments), ())
        self.assertEqual(verify_equal_kickoff_group_handling(self.backtest.selections), ())
        self.assertTrue(all(item.decimal_odds >= Decimal("1.60") for item in self.backtest.selections))
        self.assertTrue(all(item.expected_value >= Decimal("0.02") for item in self.backtest.selections))
        self.assertTrue(all(item.stake_percentage in {Decimal(".01"), Decimal(".02"), Decimal(".03")} for item in self.backtest.selections))
        self.assertTrue(all(item.applied_stake_amount <= item.bankroll_snapshot * Decimal(".03") for item in self.backtest.selections))
        self.assertEqual(self.backtest.final_bankroll, self.backtest.command.initial_bankroll + sum((item.net_profit_loss for item in self.backtest.settlements), Decimal(0)))
        self.assertGreaterEqual(self.backtest.final_bankroll, 0)

    def test_all_supported_market_settlement_rules(self):
        base = self.backtest.selections[0]
        cases = (
            (SupportedMarket.HOME_WIN, (2, 1), True),
            (SupportedMarket.DRAW, (1, 1), True),
            (SupportedMarket.AWAY_WIN, (0, 1), True),
            (SupportedMarket.OVER_1_5, (1, 1), True),
            (SupportedMarket.UNDER_1_5, (1, 0), True),
            (SupportedMarket.OVER_2_5, (2, 1), True),
            (SupportedMarket.UNDER_2_5, (1, 1), True),
            (SupportedMarket.OVER_3_5, (3, 1), True),
            (SupportedMarket.UNDER_3_5, (2, 1), True),
            (SupportedMarket.BTTS_YES, (1, 1), True),
            (SupportedMarket.BTTS_NO, (1, 0), True),
        )
        for market, score, won in cases:
            with self.subTest(market=market):
                settled = settle_selection(replace(base, market_identity=market), score, self.service._policy, 0)
                self.assertEqual(settled.status, SettlementStatus.WON if won else SettlementStatus.LOST)
                self.assertEqual(settled.gross_return, base.applied_stake_amount * base.decimal_odds)

    def test_idempotency_conflict_and_invalid_command_are_fail_closed(self):
        replay = self.service.run(self.command, odds_dataset=self.odds_dataset)
        conflict = self.service.run(replace(self.command, backtest_run_name="Different"), odds_dataset=self.odds_dataset)
        invalid = self.service.run({}, odds_dataset=self.odds_dataset)
        non_eur = self.service.run(
            replace(self.command, backtest_request_id="non-eur", currency="USD"),
            odds_dataset=self.odds_dataset,
        )
        self.assertEqual(replay.status, BacktestStatus.IDEMPOTENT_EXISTING)
        self.assertEqual(conflict.status, BacktestStatus.CONFLICT)
        self.assertEqual(invalid.status, BacktestStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(non_eur.status, BacktestStatus.REJECTED_INVALID_REQUEST)
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_backtest_runs").fetchone()[0], 1)

    def test_odds_provenance_temporal_safety_and_closing_isolation(self):
        post = self._odds_dataset("post-kickoff", self.examples, timestamp_delta=timedelta(0))
        outcome = self.service.run(
            self._command("post-kickoff-request", post), odds_dataset=post
        )
        self.assertEqual(outcome.status, BacktestStatus.REJECTED_ODDS_PROVENANCE)
        self.assertEqual(verify_odds_temporal_safety(self.backtest.odds_snapshots), ())
        self.assertEqual(self.database.connection.execute("SELECT COUNT(*) FROM historical_backtest_runs").fetchone()[0], 1)

    def test_inspection_and_metric_reproduction_are_read_only(self):
        before = self.database.connection.total_changes
        summary = summarize_backtest_run(self.repository, self.backtest.backtest_run_id)
        self.assertEqual(summary["test_examples"], len(self.examples))
        self.assertEqual(inspect_backtest_prediction(self.repository, self.backtest.backtest_run_id, self.backtest.predictions[0].prediction_row_id), self.backtest.predictions[0])
        self.assertEqual(inspect_market_assessment(self.repository, self.backtest.backtest_run_id, self.backtest.assessments[0].assessment_id), self.backtest.assessments[0])
        self.assertEqual(inspect_backtest_selection(self.repository, self.backtest.backtest_run_id, self.backtest.selections[0].selection_id), self.backtest.selections[0])
        self.assertEqual(inspect_backtest_settlement(self.repository, self.backtest.backtest_run_id, self.backtest.settlements[0].settlement_id), self.backtest.settlements[0])
        self.assertEqual(inspect_bankroll_entry(self.repository, self.backtest.backtest_run_id, self.backtest.ledger[0].ledger_entry_id), self.backtest.ledger[0])
        self.assertEqual(verify_backtest_fingerprints(self.repository, self.backtest.backtest_run_id), ())
        rows, aggregate = calculate_betting_metrics(
            self.backtest.predictions, self.backtest.assessments, self.backtest.selections,
            self.backtest.settlements, self.backtest.ledger, self.backtest.command.initial_bankroll,
        )
        self.assertTrue(rows and aggregate)
        self.assertEqual(before, self.database.connection.total_changes)

    def test_append_only_triggers_and_atomic_rollback(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.database.connection.execute(
                "UPDATE historical_backtest_runs SET outcome='CHANGED' WHERE backtest_run_id=?",
                (self.backtest.backtest_run_id,),
            )
        self.database.rollback()
        failing = self._command("atomic-backtest-failure", self.odds_dataset)
        original = self.service._backtests._insert_metrics
        self.service._backtests._insert_metrics = lambda *_: (_ for _ in ()).throw(sqlite3.IntegrityError("forced"))
        try:
            outcome = self.service.run(failing, odds_dataset=self.odds_dataset)
        finally:
            self.service._backtests._insert_metrics = original
        self.assertEqual(outcome.status, BacktestStatus.PERSISTENCE_FAILURE)
        self.assertEqual(self.database.connection.execute(
            "SELECT COUNT(*) FROM historical_backtest_runs WHERE backtest_request_id='atomic-backtest-failure'"
        ).fetchone()[0], 0)


class HistoricalBacktestingMigrationTests(unittest.TestCase):
    def test_backtesting_schema_survives_current_migration_and_v27_upgrade(self):
        fresh = Database(":memory:")
        SQLiteHistoricalBacktestingRepository(fresh)
        self.assertEqual(fresh.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 31)
        self.assertEqual(len(fresh.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'historical_backtest_%'"
        ).fetchall()), 10)
        fresh.close()

        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        with patch("app.database.migrations.MIGRATIONS", MIGRATIONS[:27]):
            MigrationManager(connection).migrate()
        MigrationManager(connection).migrate()
        self.assertEqual(connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 31)
        connection.close()

    def test_import_and_composition_have_zero_automatic_backtests(self):
        database = Database(":memory:")
        SQLiteHistoricalBacktestingRepository(database)
        before = database.connection.total_changes
        service = build_historical_backtesting_service(database, migrate=False)
        self.assertIsNotNone(service)
        self.assertEqual(before, database.connection.total_changes)
        self.assertEqual(database.connection.execute("SELECT COUNT(*) FROM historical_backtest_runs").fetchone()[0], 0)
        database.close()


if __name__ == "__main__":
    unittest.main()
