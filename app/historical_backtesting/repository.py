"""Atomic append-only SQLite persistence for complete historical backtests."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

from app.database import Database, MigrationManager
from app.prediction_inference import PredictionTarget, RawProbability, RawProbabilitySet

from .exceptions import BacktestConflictError, BacktestPersistenceError
from .fingerprint import canonical_json
from .models import (
    BacktestExclusion,
    BacktestMetric,
    BacktestPrediction,
    BacktestReliabilityBin,
    BacktestSelection,
    BacktestSettlement,
    BankrollLedgerEntry,
    HistoricalOddsSnapshot,
    MarketAssessment,
    NormalizedBacktestCommand,
    OddsMarketStatus,
    PreparedBacktestRun,
    SettlementStatus,
    StoredOddsSnapshot,
    SupportedMarket,
)


class SQLiteHistoricalBacktestingRepository:
    def __init__(self, database: Database, *, migrate: bool = True):
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_backtest_run(self, run: PreparedBacktestRun):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._connection.execute(
                "SELECT request_fingerprint FROM historical_backtest_runs WHERE backtest_request_id=?",
                (run.command.backtest_request_id,),
            ).fetchone()
            if existing:
                if existing[0] != run.request_fingerprint:
                    raise BacktestConflictError("Backtest request ID has different immutable content.")
                self._connection.commit()
                return
            self._insert_run(run)
            self._insert_predictions(run)
            self._insert_odds(run)
            self._insert_assessments(run)
            self._insert_selections(run)
            self._insert_settlements(run)
            self._insert_ledger(run)
            self._insert_metrics(run)
            self._insert_bins(run)
            self._insert_exclusions(run)
            self._connection.commit()
        except BacktestConflictError:
            self._rollback()
            raise
        except sqlite3.DatabaseError as exc:
            self._rollback()
            raise BacktestPersistenceError(f"Historical backtest transaction failed: {exc}") from exc

    def find_by_backtest_run_fingerprint(self, fingerprint):
        row = self._connection.execute(
            "SELECT backtest_run_id FROM historical_backtest_runs WHERE backtest_run_fingerprint=?", (fingerprint,)
        ).fetchone()
        return self.load_backtest_run(row[0]) if row else None

    def find_by_request_id(self, request_id):
        row = self._connection.execute(
            "SELECT backtest_run_id FROM historical_backtest_runs WHERE backtest_request_id=?", (request_id,)
        ).fetchone()
        return self.load_backtest_run(row[0]) if row else None

    def load_backtest_run(self, backtest_run_id):
        row = self._connection.execute(
            "SELECT * FROM historical_backtest_runs WHERE backtest_run_id=?", (backtest_run_id,)
        ).fetchone()
        if row is None:
            return None
        snapshot = json.loads(row["deterministic_run_snapshot"])
        return PreparedBacktestRun(
            backtest_run_id=backtest_run_id,
            command=_command(snapshot["command"]),
            request_fingerprint=row["request_fingerprint"],
            backtest_run_fingerprint=row["backtest_run_fingerprint"],
            predictions=self.list_predictions(backtest_run_id),
            odds_snapshots=self.list_odds_snapshots(backtest_run_id),
            assessments=self.list_market_assessments(backtest_run_id),
            selections=self.list_selections(backtest_run_id),
            settlements=self.list_settlements(backtest_run_id),
            ledger=self.list_bankroll_ledger(backtest_run_id),
            metrics=self.list_metrics(backtest_run_id),
            reliability_bins=self.list_reliability_bins(backtest_run_id),
            exclusions=self.list_exclusions(backtest_run_id),
            aggregate_predictive_metrics=tuple(
                (name, Decimal(value)) for name, value in json.loads(row["aggregate_predictive_metrics_snapshot"])
            ),
            aggregate_betting_metrics=tuple(
                (name, Decimal(value)) for name, value in json.loads(row["aggregate_betting_metrics_snapshot"])
            ),
            final_bankroll=Decimal(row["final_bankroll"]),
            maximum_drawdown=Decimal(row["maximum_drawdown"]),
            deterministic_run_snapshot=row["deterministic_run_snapshot"],
        )

    def list_predictions(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_predictions WHERE backtest_run_id=? ORDER BY deterministic_order", (run_id,)
        ).fetchall()
        metadata = json.loads(self._connection.execute(
            "SELECT deterministic_run_snapshot FROM historical_backtest_runs WHERE backtest_run_id=?", (run_id,)
        ).fetchone()[0]) if rows else {}
        by_id = metadata.get("prediction_metadata", {})
        return tuple(
            BacktestPrediction(
                prediction_row_id=row["prediction_row_id"],
                training_example_id=row["training_example_id"],
                historical_match_id=row["historical_match_id"],
                example_fingerprint=row["example_fingerprint"],
                competition=by_id.get(row["prediction_row_id"], {}).get("competition", ""),
                season=by_id.get(row["prediction_row_id"], {}).get("season", ""),
                kickoff_utc=row["kickoff_timestamp"],
                raw_probabilities=_probabilities(row["raw_probabilities_snapshot"]),
                calibrated_probabilities=_probabilities(row["calibrated_probabilities_snapshot"]),
                labels=tuple((name, int(value)) for name, value in json.loads(row["label_snapshot"])),
                raw_prediction_fingerprint=row["raw_prediction_fingerprint"],
                calibrated_prediction_fingerprint=row["calibrated_prediction_fingerprint"],
                deterministic_order=row["deterministic_order"],
            ) for row in rows
        )

    def list_odds_snapshots(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_odds_snapshots WHERE backtest_run_id=? ORDER BY closing_flag,deterministic_order", (run_id,)
        ).fetchall()
        return tuple(_odds(row) for row in rows)

    def list_market_assessments(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_market_assessments WHERE backtest_run_id=? ORDER BY deterministic_rank", (run_id,)
        ).fetchall()
        prediction_match = {
            row["prediction_row_id"]: row["historical_match_id"]
            for row in self._connection.execute(
                "SELECT prediction_row_id,historical_match_id FROM historical_backtest_predictions WHERE backtest_run_id=?", (run_id,)
            )
        }
        return tuple(
            MarketAssessment(
                assessment_id=row["assessment_id"], prediction_row_id=row["prediction_row_id"],
                odds_row_id=row["odds_row_id"], historical_match_id=prediction_match[row["prediction_row_id"]],
                market_identity=SupportedMarket(row["market_identity"]),
                calibrated_probability=_decimal(row["calibrated_probability"]),
                fair_odds=_decimal(row["fair_odds"]), decimal_odds=_decimal(row["decimal_odds"]),
                implied_probability=_decimal(row["implied_probability"]),
                expected_value=_decimal(row["expected_value"]), edge=_decimal(row["edge"]),
                odds_age_seconds=row["odds_age_seconds"], eligible=bool(row["eligible_flag"]),
                rejection_reasons=tuple(json.loads(row["rejection_reasons_snapshot"])),
                assessment_fingerprint=row["assessment_fingerprint"],
                deterministic_rank=row["deterministic_rank"],
            ) for row in rows
        )

    def list_selections(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_selections WHERE backtest_run_id=? ORDER BY deterministic_order", (run_id,)
        ).fetchall()
        kickoffs = {
            row["historical_match_id"]: row["kickoff_timestamp"]
            for row in self._connection.execute(
                "SELECT historical_match_id,kickoff_timestamp FROM historical_backtest_predictions WHERE backtest_run_id=?", (run_id,)
            )
        }
        return tuple(
            BacktestSelection(
                selection_id=row["selection_id"], historical_match_id=row["historical_match_id"],
                kickoff_utc=kickoffs[row["historical_match_id"]], kickoff_group_id=row["kickoff_group_id"],
                selected_assessment_id=row["selected_assessment_id"],
                market_identity=SupportedMarket(row["market_identity"]),
                decimal_odds=Decimal(row["decimal_odds"]),
                calibrated_probability=Decimal(row["calibrated_probability"]),
                expected_value=Decimal(row["expected_value"]),
                bankroll_snapshot=Decimal(row["bankroll_snapshot"]),
                stake_percentage=Decimal(row["stake_percentage"]),
                recommended_stake_amount=Decimal(row["recommended_stake_amount"]),
                applied_stake_amount=Decimal(row["applied_stake_amount"]),
                stake_classification=row["stake_classification"],
                reduction_reason=row["reduction_reason"], rejection_reason=row["rejection_reason"],
                selection_fingerprint=row["selection_fingerprint"], stake_fingerprint=row["stake_fingerprint"],
                deterministic_order=row["deterministic_order"],
            ) for row in rows
        )

    def list_settlements(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_settlements WHERE backtest_run_id=? ORDER BY settled_order", (run_id,)
        ).fetchall()
        return tuple(
            BacktestSettlement(
                settlement_id=row["settlement_id"], selection_id=row["selection_id"],
                final_home_score=row["final_home_score"], final_away_score=row["final_away_score"],
                status=SettlementStatus(row["settlement_status"]),
                gross_return=Decimal(row["gross_return"]),
                net_profit_loss=Decimal(row["net_profit_loss"]),
                settlement_reason=row["settlement_reason"],
                settlement_fingerprint=row["settlement_fingerprint"],
                settled_order=row["settled_order"],
            ) for row in rows
        )

    def list_bankroll_ledger(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_bankroll_ledger WHERE backtest_run_id=? ORDER BY deterministic_order", (run_id,)
        ).fetchall()
        return tuple(
            BankrollLedgerEntry(
                ledger_entry_id=row["ledger_entry_id"], selection_id=row["selection_id"],
                kickoff_group_id=row["kickoff_group_id"], bankroll_before=Decimal(row["bankroll_before"]),
                stake_reserved=Decimal(row["stake_reserved"]), gross_return=Decimal(row["gross_return"]),
                net_result=Decimal(row["net_result"]), bankroll_after=Decimal(row["bankroll_after"]),
                cumulative_profit=Decimal(row["cumulative_profit"]), cumulative_return=Decimal(row["cumulative_return"]),
                running_peak=Decimal(row["running_peak"]), absolute_drawdown=Decimal(row["absolute_drawdown"]),
                percentage_drawdown=Decimal(row["percentage_drawdown"]),
                ledger_fingerprint=row["ledger_fingerprint"], deterministic_order=row["deterministic_order"],
            ) for row in rows
        )

    def list_metrics(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_metrics WHERE backtest_run_id=? ORDER BY deterministic_order", (run_id,)
        ).fetchall()
        return tuple(
            BacktestMetric(
                metric_row_id=row["metric_row_id"], category=row["metric_category"],
                grouping_identity=row["grouping_identity"], metric_name=row["metric_name"],
                metric_value=_decimal(row["metric_value"]), metric_snapshot=row["metric_snapshot"],
                deterministic_order=row["deterministic_order"],
            ) for row in rows
        )

    def list_reliability_bins(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_reliability_bins WHERE backtest_run_id=? ORDER BY target_identity,probability_phase,bin_index", (run_id,)
        ).fetchall()
        return tuple(
            BacktestReliabilityBin(
                bin_row_id=row["bin_row_id"], target_identity=row["target_identity"],
                probability_phase=row["probability_phase"], bin_index=row["bin_index"],
                lower_bound=Decimal(row["lower_bound"]), upper_bound=Decimal(row["upper_bound"]),
                sample_count=row["sample_count"], mean_predicted_probability=_decimal(row["mean_predicted_probability"]),
                observed_frequency=_decimal(row["observed_frequency"]), absolute_gap=_decimal(row["absolute_gap"]),
                bin_fingerprint=row["bin_fingerprint"],
            ) for row in rows
        )

    def list_exclusions(self, run_id):
        rows = self._connection.execute(
            "SELECT * FROM historical_backtest_exclusions WHERE backtest_run_id=? ORDER BY deterministic_order", (run_id,)
        ).fetchall()
        return tuple(
            BacktestExclusion(
                exclusion_id=row["exclusion_id"], historical_match_id=row["historical_match_id"],
                training_example_id=row["training_example_id"],
                market_identity=SupportedMarket(row["market_identity"]) if row["market_identity"] else None,
                stage=row["exclusion_stage"], reason=row["exclusion_reason"],
                detail_snapshot=row["detail_snapshot"], deterministic_order=row["deterministic_order"],
            ) for row in rows
        )

    def list_backtests_for_model_artifact(self, artifact_id):
        return self._list_runs("model_artifact_id", artifact_id)

    def list_backtests_for_calibration_artifact(self, artifact_set_id):
        return self._list_runs("calibration_artifact_set_id", artifact_set_id)

    def stream_backtest_events(self, run_id):
        queries = (
            ("PREDICTION", "historical_backtest_predictions", "prediction_row_id", "deterministic_order"),
            ("ODDS", "historical_backtest_odds_snapshots", "stored_odds_row_id", "deterministic_order"),
            ("ASSESSMENT", "historical_backtest_market_assessments", "assessment_id", "deterministic_rank"),
            ("SELECTION", "historical_backtest_selections", "selection_id", "deterministic_order"),
            ("SETTLEMENT", "historical_backtest_settlements", "settlement_id", "settled_order"),
            ("LEDGER", "historical_backtest_bankroll_ledger", "ledger_entry_id", "deterministic_order"),
            ("METRIC", "historical_backtest_metrics", "metric_row_id", "deterministic_order"),
            ("EXCLUSION", "historical_backtest_exclusions", "exclusion_id", "deterministic_order"),
        )
        for event_type, table, identity, order in queries:
            cursor = self._connection.execute(
                f"SELECT {identity},{order} FROM {table} WHERE backtest_run_id=? ORDER BY {order}", (run_id,)
            )
            while True:
                chunk = cursor.fetchmany(100)
                if not chunk:
                    break
                for row in chunk:
                    yield event_type, row[0], row[1]

    def _list_runs(self, column, value):
        rows = self._connection.execute(
            f"SELECT backtest_run_id FROM historical_backtest_runs WHERE {column}=? ORDER BY backtest_timestamp,backtest_run_id", (value,)
        ).fetchall()
        return tuple(self.load_backtest_run(row[0]) for row in rows)

    def _insert_run(self, run):
        c = run.command
        settled = tuple(item for item in run.settlements if item.status in (SettlementStatus.WON, SettlementStatus.LOST, SettlementStatus.VOID, SettlementStatus.PUSH))
        net = run.final_bankroll - c.initial_bankroll
        total_stake = sum((item.applied_stake_amount for item in run.selections), Decimal(0))
        self._connection.execute(
            """INSERT INTO historical_backtest_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run.backtest_run_id, c.backtest_request_id, run.request_fingerprint,
                run.backtest_run_fingerprint, c.source_split_id, c.source_split_fingerprint,
                c.fold_id, c.fold_fingerprint, c.source_training_run_id,
                c.source_training_run_fingerprint, c.model_artifact_id,
                c.model_artifact_fingerprint, c.calibration_run_id,
                c.calibration_run_fingerprint, c.calibration_artifact_set_id,
                c.calibration_artifact_set_fingerprint, c.odds_dataset_id,
                c.odds_dataset_fingerprint, c.closing_odds_dataset_id,
                c.closing_odds_dataset_fingerprint, canonical_json(_policy_versions(c)),
                len(run.predictions), len(run.predictions), len(run.assessments),
                len(run.selections), len(settled),
                sum(item.status is SettlementStatus.WON for item in settled),
                sum(item.status is SettlementStatus.LOST for item in settled),
                sum(item.status is SettlementStatus.VOID for item in settled),
                str(c.initial_bankroll), str(run.final_bankroll), str(net),
                str(net / total_stake) if total_stake else None,
                str(run.maximum_drawdown), canonical_json(run.aggregate_predictive_metrics),
                canonical_json(run.aggregate_betting_metrics), run.deterministic_run_snapshot,
                "BACKTEST_COMPLETED", canonical_json(("BACKTEST_PERSISTED",)),
                c.backtest_timestamp, c.backtest_timestamp,
            ),
        )

    def _insert_predictions(self, run):
        for item in run.predictions:
            self._connection.execute(
                "INSERT INTO historical_backtest_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.prediction_row_id, run.backtest_run_id, item.training_example_id,
                 item.historical_match_id, item.example_fingerprint, item.kickoff_utc,
                 _probability_snapshot(item.raw_probabilities),
                 _probability_snapshot(item.calibrated_probabilities),
                 item.raw_prediction_fingerprint, item.calibrated_prediction_fingerprint,
                 canonical_json(item.labels), item.deterministic_order, run.command.backtest_timestamp),
            )

    def _insert_odds(self, run):
        for item in run.odds_snapshots:
            s = item.snapshot
            self._connection.execute(
                "INSERT INTO historical_backtest_odds_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.stored_odds_row_id, run.backtest_run_id, s.odds_snapshot_id,
                 s.historical_match_id, s.competition, item.normalized_kickoff_utc,
                 item.market_identity.value, s.selection_identity,
                 item.normalized_snapshot_timestamp_utc, str(s.decimal_odds), s.currency,
                 s.bookmaker_identity, item.market_status.value, s.source_identity,
                 s.source_version, s.source_record_identity, s.source_fingerprint,
                 s.metadata_version, int(item.closing), item.deterministic_order,
                 run.command.backtest_timestamp),
            )

    def _insert_assessments(self, run):
        for item in run.assessments:
            self._connection.execute(
                "INSERT INTO historical_backtest_market_assessments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.assessment_id, run.backtest_run_id, item.prediction_row_id,
                 item.odds_row_id, item.market_identity.value, _text(item.calibrated_probability),
                 _text(item.fair_odds), _text(item.decimal_odds), _text(item.implied_probability),
                 _text(item.expected_value), _text(item.edge), item.odds_age_seconds,
                 int(item.eligible), canonical_json(item.rejection_reasons),
                 item.assessment_fingerprint, item.deterministic_rank,
                 run.command.backtest_timestamp),
            )

    def _insert_selections(self, run):
        for item in run.selections:
            self._connection.execute(
                "INSERT INTO historical_backtest_selections VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.selection_id, run.backtest_run_id, item.historical_match_id,
                 item.kickoff_group_id, item.selected_assessment_id, item.market_identity.value,
                 str(item.decimal_odds), str(item.calibrated_probability), str(item.expected_value),
                 str(item.bankroll_snapshot), str(item.stake_percentage),
                 str(item.recommended_stake_amount), str(item.applied_stake_amount),
                 item.stake_classification, item.reduction_reason, item.rejection_reason,
                 item.selection_fingerprint, item.stake_fingerprint,
                 item.deterministic_order, run.command.backtest_timestamp),
            )

    def _insert_settlements(self, run):
        for item in run.settlements:
            self._connection.execute(
                "INSERT INTO historical_backtest_settlements VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.settlement_id, run.backtest_run_id, item.selection_id,
                 item.final_home_score, item.final_away_score, item.status.value,
                 str(item.gross_return), str(item.net_profit_loss), item.settlement_reason,
                 item.settlement_fingerprint, item.settled_order, run.command.backtest_timestamp),
            )

    def _insert_ledger(self, run):
        for item in run.ledger:
            self._connection.execute(
                "INSERT INTO historical_backtest_bankroll_ledger VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.ledger_entry_id, run.backtest_run_id, item.selection_id,
                 item.kickoff_group_id, str(item.bankroll_before), str(item.stake_reserved),
                 str(item.gross_return), str(item.net_result), str(item.bankroll_after),
                 str(item.cumulative_profit), str(item.cumulative_return), str(item.running_peak),
                 str(item.absolute_drawdown), str(item.percentage_drawdown),
                 item.ledger_fingerprint, item.deterministic_order, run.command.backtest_timestamp),
            )

    def _insert_metrics(self, run):
        for item in run.metrics:
            self._connection.execute(
                "INSERT INTO historical_backtest_metrics VALUES (?,?,?,?,?,?,?,?,?)",
                (item.metric_row_id, run.backtest_run_id, item.category,
                 item.grouping_identity, item.metric_name, _text(item.metric_value),
                 item.metric_snapshot, item.deterministic_order, run.command.backtest_timestamp),
            )

    def _insert_bins(self, run):
        for item in run.reliability_bins:
            self._connection.execute(
                "INSERT INTO historical_backtest_reliability_bins VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (item.bin_row_id, run.backtest_run_id, item.target_identity,
                 item.probability_phase, item.bin_index, str(item.lower_bound),
                 str(item.upper_bound), item.sample_count, _text(item.mean_predicted_probability),
                 _text(item.observed_frequency), _text(item.absolute_gap),
                 item.bin_fingerprint, run.command.backtest_timestamp),
            )

    def _insert_exclusions(self, run):
        for item in run.exclusions:
            self._connection.execute(
                "INSERT INTO historical_backtest_exclusions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (item.exclusion_id, run.backtest_run_id, item.historical_match_id,
                 item.training_example_id, item.market_identity.value if item.market_identity else None,
                 item.stage, item.reason, item.detail_snapshot,
                 item.deterministic_order, run.command.backtest_timestamp),
            )

    def _rollback(self):
        if self._connection.in_transaction:
            self._connection.rollback()


def _probability_snapshot(value):
    return canonical_json(tuple((item.target.value, item.probability) for item in value.ordered_probabilities))


def _probabilities(snapshot):
    return RawProbabilitySet(
        tuple(RawProbability(PredictionTarget(target), Decimal(value)) for target, value in json.loads(snapshot))
    )


def _decimal(value):
    return Decimal(value) if value is not None else None


def _text(value):
    return str(value) if value is not None else None


def _odds(row):
    snapshot = HistoricalOddsSnapshot(
        odds_snapshot_id=row["odds_snapshot_id"], source_identity=row["source_identity"],
        source_version=row["source_version"], historical_match_id=row["historical_match_id"],
        competition=row["competition"], kickoff_utc=row["kickoff_timestamp"],
        snapshot_timestamp_utc=row["snapshot_timestamp"], bookmaker_identity=row["bookmaker_identity"],
        market_identity=SupportedMarket(row["market_identity"]), selection_identity=row["selection_identity"],
        decimal_odds=Decimal(row["decimal_odds"]), currency=row["currency"],
        market_status=OddsMarketStatus(row["market_status"]),
        source_record_identity=row["source_record_identity"], source_fingerprint=row["source_fingerprint"],
        metadata_version=row["metadata_version"],
    )
    return StoredOddsSnapshot(
        stored_odds_row_id=row["stored_odds_row_id"], snapshot=snapshot,
        normalized_kickoff_utc=row["kickoff_timestamp"],
        normalized_snapshot_timestamp_utc=row["snapshot_timestamp"],
        market_identity=SupportedMarket(row["market_identity"]),
        market_status=OddsMarketStatus(row["market_status"]),
        closing=bool(row["closing_flag"]), deterministic_order=row["deterministic_order"],
    )


def _command(value):
    decimal_fields = {"initial_bankroll"}
    tuple_fields = {"bookmaker_filters", "competitions", "seasons"}
    converted = {}
    for key, item in value.items():
        if key in decimal_fields:
            converted[key] = Decimal(item)
        elif key in tuple_fields:
            converted[key] = tuple(item)
        elif key == "markets":
            converted[key] = tuple(SupportedMarket(market) for market in item)
        else:
            converted[key] = item
    return NormalizedBacktestCommand(**converted)


def _policy_versions(command):
    return tuple(
        (name, getattr(command, field))
        for name, field in (
            ("backtest", "backtest_policy_version"), ("odds_selection", "odds_selection_policy_version"),
            ("decision_snapshot", "decision_snapshot_policy"), ("market_eligibility", "market_eligibility_policy_version"),
            ("value", "value_policy_version"), ("selection", "selection_policy_version"),
            ("staking", "staking_policy_version"), ("settlement", "settlement_policy_version"),
            ("bankroll", "bankroll_policy_version"), ("metrics", "metric_policy_version"),
        )
    )
