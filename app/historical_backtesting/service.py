"""TEST-only orchestration for deterministic immutable historical backtests."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.historical_model_training.exceptions import HistoricalModelTrainingError
from app.historical_probability_calibration.exceptions import HistoricalCalibrationError

from .bankroll import build_ledger
from .betting_metrics import calculate_betting_metrics
from .exceptions import (
    BacktestConflictError,
    BacktestOddsProvenanceError,
    BacktestPartitionSafetyError,
    BacktestPersistenceError,
    BacktestProbabilityContractError,
    BacktestRequestValidationError,
    BacktestSchemaCompatibilityError,
    BacktestSettlementError,
    BacktestSourceError,
)
from .fingerprint import canonical_json, sha256_fingerprint
from .models import (
    BacktestOutcome,
    BacktestStatus,
    PreparedBacktestRun,
    SettlementStatus,
)
from .odds import verify_and_select_odds
from .prediction_loader import reproduce_predictions
from .predictive_metrics import calculate_predictive_metrics
from .selection import select_assessments
from .settlement import settle_selection
from .source_verification import verify_sources
from .staking import create_group_selections
from .validation import normalize_command
from .value_assessment import assess_markets


class HistoricalBacktestingService:
    def __init__(
        self, training_repository, split_repository, model_repository,
        calibration_repository, backtesting_repository, final_score_reader, policy,
    ):
        self._training = training_repository
        self._splits = split_repository
        self._models = model_repository
        self._calibrations = calibration_repository
        self._backtests = backtesting_repository
        self._scores = final_score_reader
        self._policy = policy

    def run(self, command, *, odds_dataset, closing_odds_dataset=None):
        normalized = None
        request_fingerprint = None
        try:
            normalized = normalize_command(command, self._policy)
            request_fingerprint = sha256_fingerprint(normalized)
            existing = self._backtests.find_by_request_id(normalized.backtest_request_id)
            if existing is not None:
                if existing.request_fingerprint != request_fingerprint:
                    return _rejected(command, BacktestStatus.CONFLICT, ("BACKTEST_REQUEST_CONFLICT",), request_fingerprint)
                return _outcome(existing, BacktestStatus.IDEMPOTENT_EXISTING, ("IDENTICAL_BACKTEST_ALREADY_PERSISTED",), self._policy)
            (
                split, fold, dataset, training_run, artifact,
                calibration_run, calibration_set, source_examples,
            ) = verify_sources(
                normalized, self._training, self._splits, self._models,
                self._calibrations,
            )
            examples = tuple(item for item in source_examples if _selected(item, normalized))
            if not examples:
                return _rejected(command, BacktestStatus.NO_ELIGIBLE_TEST_EXAMPLES, ("NO_ELIGIBLE_TEST_EXAMPLES",), request_fingerprint, normalized)
            run_id = f"historical-backtest-run-{request_fingerprint}"
            decision_odds = verify_and_select_odds(
                odds_dataset, expected_id=normalized.odds_dataset_id,
                expected_fingerprint=normalized.odds_dataset_fingerprint,
                examples=examples, markets=normalized.markets,
                bookmaker_filters=normalized.bookmaker_filters,
            )
            if not any(item.market_status.value == "ACTIVE" for item in decision_odds):
                return _rejected(command, BacktestStatus.NO_VALID_ODDS, ("NO_VALID_PREMATCH_ODDS",), request_fingerprint, normalized)
            predictions = reproduce_predictions(
                examples, artifact, calibration_set, run_namespace=run_id
            )
            initial_assessments = assess_markets(
                predictions, decision_odds, self._policy, run_namespace=run_id
            )
            assessments, winners, exclusions = select_assessments(
                predictions, initial_assessments, self._policy, run_namespace=run_id
            )
            winners_by_kickoff = defaultdict(list)
            prediction_by_row = {item.prediction_row_id: item for item in predictions}
            for winner in winners:
                winners_by_kickoff[prediction_by_row[winner.prediction_row_id].kickoff_utc].append(winner)
            selections = []
            settlements = []
            bankroll = normalized.initial_bankroll
            for kickoff in sorted(winners_by_kickoff):
                group_predictions = tuple(item for item in predictions if item.kickoff_utc == kickoff)
                group_prediction_ids = {item.prediction_row_id for item in group_predictions}
                group_assessments = tuple(item for item in assessments if item.prediction_row_id in group_prediction_ids)
                group_selections = create_group_selections(
                    group_predictions, group_assessments, tuple(winners_by_kickoff[kickoff]),
                    bankroll, self._policy, len(selections), run_namespace=run_id,
                )
                group_settlements = tuple(
                    settle_selection(
                        selection,
                        self._scores.load_final_score(selection.historical_match_id),
                        self._policy, len(settlements) + index,
                        run_namespace=run_id,
                    )
                    for index, selection in enumerate(group_selections)
                    if selection.applied_stake_amount > 0
                )
                selections.extend(item for item in group_selections if item.applied_stake_amount > 0)
                settlements.extend(group_settlements)
                bankroll += sum((item.net_profit_loss for item in group_settlements), Decimal(0))
            selections = tuple(selections)
            settlements = tuple(settlements)
            closing_odds = ()
            if normalized.closing_odds_dataset_id is not None:
                if closing_odds_dataset is None:
                    raise BacktestOddsProvenanceError("Explicit closing odds dataset is missing.")
                closing_odds = verify_and_select_odds(
                    closing_odds_dataset, expected_id=normalized.closing_odds_dataset_id,
                    expected_fingerprint=normalized.closing_odds_dataset_fingerprint or "",
                    examples=examples, markets=normalized.markets,
                    bookmaker_filters=normalized.bookmaker_filters, closing=True,
                )
            ledger = build_ledger(
                normalized.initial_bankroll, selections, settlements, run_namespace=run_id
            )
            predictive_rows, bins, predictive_aggregate = calculate_predictive_metrics(
                predictions, self._policy.reliability_bin_count,
                run_namespace=run_id,
            )
            betting_rows, betting_aggregate = calculate_betting_metrics(
                predictions, assessments, selections, settlements, ledger,
                normalized.initial_bankroll, closing_odds,
                start_order=len(predictive_rows), run_namespace=run_id,
            )
            metrics = predictive_rows + betting_rows
            final_bankroll = ledger[-1].bankroll_after if ledger else normalized.initial_bankroll
            maximum_drawdown = max((item.percentage_drawdown for item in ledger), default=Decimal(0))
            odds_rows = decision_odds + tuple(
                item.__class__(
                    stored_odds_row_id=item.stored_odds_row_id,
                    snapshot=item.snapshot,
                    normalized_kickoff_utc=item.normalized_kickoff_utc,
                    normalized_snapshot_timestamp_utc=item.normalized_snapshot_timestamp_utc,
                    market_identity=item.market_identity, market_status=item.market_status,
                    closing=True, deterministic_order=len(decision_odds) + index,
                )
                for index, item in enumerate(closing_odds)
            )
            run_material = {
                "request_fingerprint": request_fingerprint,
                "prediction_fingerprints": tuple(item.calibrated_prediction_fingerprint for item in predictions),
                "assessment_fingerprints": tuple(item.assessment_fingerprint for item in assessments),
                "selection_fingerprints": tuple(item.selection_fingerprint for item in selections),
                "stake_fingerprints": tuple(item.stake_fingerprint for item in selections),
                "settlement_fingerprints": tuple(item.settlement_fingerprint for item in settlements),
                "ledger_fingerprints": tuple(item.ledger_fingerprint for item in ledger),
                "metric_snapshots": tuple((item.metric_row_id, item.metric_snapshot) for item in metrics),
                "exclusions": tuple(item for item in exclusions),
                "policy_versions": self._policy.versions,
            }
            run_fingerprint = sha256_fingerprint(run_material)
            deterministic_snapshot = canonical_json(
                {
                    "command": normalized,
                    "prediction_metadata": {
                        item.prediction_row_id: {
                            "competition": item.competition, "season": item.season
                        } for item in predictions
                    },
                    "source": {
                        "dataset_fingerprint": dataset.dataset_fingerprint,
                        "split_fingerprint": split.split_fingerprint,
                        "fold_fingerprint": fold.fold_fingerprint,
                        "training_run_fingerprint": training_run.training_run_fingerprint,
                        "artifact_fingerprint": artifact.artifact_fingerprint,
                        "calibration_run_fingerprint": calibration_run.calibration_run_fingerprint,
                        "calibration_artifact_set_fingerprint": calibration_set.artifact_set_fingerprint,
                    },
                    "run_material": run_material,
                    "outcome": BacktestStatus.BACKTEST_COMPLETED,
                }
            )
            run = PreparedBacktestRun(
                backtest_run_id=run_id, command=normalized,
                request_fingerprint=request_fingerprint,
                backtest_run_fingerprint=run_fingerprint,
                predictions=predictions, odds_snapshots=odds_rows,
                assessments=assessments, selections=selections,
                settlements=settlements, ledger=ledger, metrics=metrics,
                reliability_bins=bins, exclusions=exclusions,
                aggregate_predictive_metrics=predictive_aggregate,
                aggregate_betting_metrics=betting_aggregate,
                final_bankroll=final_bankroll,
                maximum_drawdown=maximum_drawdown,
                deterministic_run_snapshot=deterministic_snapshot,
            )
            self._backtests.append_backtest_run(run)
            return _outcome(run, BacktestStatus.BACKTEST_COMPLETED, ("BACKTEST_PERSISTED",), self._policy)
        except BacktestRequestValidationError as exc:
            return _rejected(command, BacktestStatus.REJECTED_INVALID_REQUEST, (str(exc),), request_fingerprint, normalized)
        except BacktestPartitionSafetyError as exc:
            return _rejected(command, BacktestStatus.REJECTED_PARTITION_SAFETY, (str(exc),), request_fingerprint, normalized)
        except BacktestSchemaCompatibilityError as exc:
            return _rejected(command, BacktestStatus.REJECTED_SCHEMA_COMPATIBILITY, (str(exc),), request_fingerprint, normalized)
        except BacktestOddsProvenanceError as exc:
            return _rejected(command, BacktestStatus.REJECTED_ODDS_PROVENANCE, (str(exc),), request_fingerprint, normalized)
        except BacktestSettlementError as exc:
            return _rejected(command, BacktestStatus.REJECTED_SETTLEMENT_DATA, (str(exc),), request_fingerprint, normalized)
        except BacktestProbabilityContractError as exc:
            return _rejected(command, BacktestStatus.REJECTED_PROBABILITY_CONTRACT, (str(exc),), request_fingerprint, normalized)
        except (HistoricalModelTrainingError, HistoricalCalibrationError) as exc:
            return _rejected(command, BacktestStatus.REJECTED_PROBABILITY_CONTRACT, (str(exc),), request_fingerprint, normalized)
        except BacktestConflictError as exc:
            return _rejected(command, BacktestStatus.CONFLICT, (str(exc),), request_fingerprint, normalized)
        except BacktestPersistenceError as exc:
            return _rejected(command, BacktestStatus.PERSISTENCE_FAILURE, (str(exc),), request_fingerprint, normalized)
        except BacktestSourceError as exc:
            message = str(exc)
            status = (
                BacktestStatus.REJECTED_SOURCE_CALIBRATION if "calibration" in message.lower()
                else BacktestStatus.REJECTED_SOURCE_MODEL if "model" in message.lower()
                else BacktestStatus.REJECTED_SOURCE_SPLIT
            )
            return _rejected(command, status, (message,), request_fingerprint, normalized)
        except (ValueError, KeyError, ArithmeticError) as exc:
            return _rejected(command, BacktestStatus.REJECTED_PROBABILITY_CONTRACT, (str(exc),), request_fingerprint, normalized)


def run_historical_backtest(service, command, *, odds_dataset, closing_odds_dataset=None):
    return service.run(
        command, odds_dataset=odds_dataset,
        closing_odds_dataset=closing_odds_dataset,
    )


def _selected(example, command):
    return (
        (not command.competitions or example.competition in command.competitions)
        and (not command.seasons or example.season in command.seasons)
        and (command.kickoff_lower_bound is None or example.kickoff_utc >= command.kickoff_lower_bound)
        and (command.kickoff_upper_bound is None or example.kickoff_utc < command.kickoff_upper_bound)
    )


def _outcome(run, status, reasons, policy):
    wins = sum(item.status is SettlementStatus.WON for item in run.settlements)
    losses = sum(item.status is SettlementStatus.LOST for item in run.settlements)
    voids = sum(item.status is SettlementStatus.VOID for item in run.settlements)
    net = run.final_bankroll - run.command.initial_bankroll
    stake = sum((item.applied_stake_amount for item in run.selections), Decimal(0))
    return BacktestOutcome(
        status=status, backtest_run_id=run.backtest_run_id,
        backtest_request_id=run.command.backtest_request_id,
        request_fingerprint=run.request_fingerprint,
        backtest_run_fingerprint=run.backtest_run_fingerprint,
        source_split_id=run.command.source_split_id, fold_id=run.command.fold_id,
        model_artifact_id=run.command.model_artifact_id,
        model_artifact_fingerprint=run.command.model_artifact_fingerprint,
        calibration_artifact_set_id=run.command.calibration_artifact_set_id,
        calibration_artifact_set_fingerprint=run.command.calibration_artifact_set_fingerprint,
        test_example_count=len(run.predictions), prediction_count=len(run.predictions),
        assessed_market_count=len(run.assessments), selected_bet_count=len(run.selections),
        settled_bet_count=len(run.settlements), win_count=wins, loss_count=losses,
        void_count=voids, initial_bankroll=run.command.initial_bankroll,
        final_bankroll=run.final_bankroll, net_profit=net,
        roi=net / stake if stake else Decimal(0), maximum_drawdown=run.maximum_drawdown,
        aggregate_predictive_metrics=run.aggregate_predictive_metrics,
        aggregate_betting_metrics=run.aggregate_betting_metrics,
        ordered_reason_codes=reasons, policy_versions=policy.versions,
        backtest_timestamp=run.command.backtest_timestamp,
    )


def _rejected(command, status, reasons, fingerprint=None, normalized=None):
    source = normalized or command
    def value(name, default=""):
        return getattr(source, name, default)
    initial = value("initial_bankroll", Decimal(0))
    return BacktestOutcome(
        status=status, backtest_run_id=None,
        backtest_request_id=value("backtest_request_id"),
        request_fingerprint=fingerprint, backtest_run_fingerprint=None,
        source_split_id=value("source_split_id"), fold_id=value("fold_id"),
        model_artifact_id=value("model_artifact_id"),
        model_artifact_fingerprint=value("model_artifact_fingerprint"),
        calibration_artifact_set_id=value("calibration_artifact_set_id"),
        calibration_artifact_set_fingerprint=value("calibration_artifact_set_fingerprint"),
        test_example_count=0, prediction_count=0, assessed_market_count=0,
        selected_bet_count=0, settled_bet_count=0, win_count=0, loss_count=0,
        void_count=0, initial_bankroll=initial if isinstance(initial, Decimal) else Decimal(0),
        final_bankroll=initial if isinstance(initial, Decimal) else Decimal(0),
        net_profit=Decimal(0), roi=None, maximum_drawdown=Decimal(0),
        aggregate_predictive_metrics=(), aggregate_betting_metrics=(),
        ordered_reason_codes=tuple(reasons), policy_versions=(),
        backtest_timestamp=value("backtest_timestamp", None) or None,
    )
