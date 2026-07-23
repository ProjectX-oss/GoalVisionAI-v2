"""Read-only inspection, integrity checks, and result reproduction."""

from __future__ import annotations

import json

from app.historical_model_training import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_FINGERPRINT,
    predict_raw_probabilities,
)

from .bankroll import reproduce_final_bankroll, verify_bankroll_ledger
from .betting_metrics import reproduce_betting_metrics
from .fingerprint import sha256_fingerprint
from .odds import verify_odds_temporal_safety
from .prediction_loader import reproduce_predictions
from .predictive_metrics import reproduce_predictive_metrics
from .selection import verify_selection_policy_alignment
from .settlement import verify_settlement_consistency
from .source_verification import verify_test_partition_only


def summarize_backtest_run(repository, backtest_run_id):
    run = repository.load_backtest_run(backtest_run_id)
    if run is None:
        return None
    return {
        "backtest_run_id": run.backtest_run_id,
        "request_id": run.command.backtest_request_id,
        "test_examples": len(run.predictions),
        "assessed_markets": len(run.assessments),
        "selected_bets": len(run.selections),
        "settled_bets": len(run.settlements),
        "initial_bankroll": run.command.initial_bankroll,
        "final_bankroll": run.final_bankroll,
        "maximum_drawdown": run.maximum_drawdown,
    }


def inspect_backtest_prediction(repository, backtest_run_id, prediction_row_id):
    return next((item for item in repository.list_predictions(backtest_run_id) if item.prediction_row_id == prediction_row_id), None)


def inspect_market_assessment(repository, backtest_run_id, assessment_id):
    return next((item for item in repository.list_market_assessments(backtest_run_id) if item.assessment_id == assessment_id), None)


def inspect_backtest_selection(repository, backtest_run_id, selection_id):
    return next((item for item in repository.list_selections(backtest_run_id) if item.selection_id == selection_id), None)


def inspect_backtest_settlement(repository, backtest_run_id, settlement_id):
    return next((item for item in repository.list_settlements(backtest_run_id) if item.settlement_id == settlement_id), None)


def inspect_bankroll_entry(repository, backtest_run_id, ledger_entry_id):
    return next((item for item in repository.list_bankroll_ledger(backtest_run_id) if item.ledger_entry_id == ledger_entry_id), None)


def verify_prediction_reproduction(repository, model_repository, training_repository, backtest_run_id):
    run = repository.load_backtest_run(backtest_run_id)
    if run is None:
        return ("BACKTEST_NOT_FOUND",)
    artifact = model_repository.load_model_artifact(run.command.model_artifact_id)
    examples = tuple(training_repository.load_training_example(item.training_example_id) for item in run.predictions)
    if artifact is None or any(item is None for item in examples):
        return ("PREDICTION_SOURCE_NOT_FOUND",)
    reproduced = tuple(
        predict_raw_probabilities(
            artifact, example.ordered_feature_vector, example.missingness_mask,
            feature_schema_version=example.feature_schema_version,
            feature_schema_fingerprint=FEATURE_SCHEMA_FINGERPRINT,
            ordered_feature_names=FEATURE_NAMES,
        ).raw_probabilities
        for example in examples
    )
    return () if reproduced == tuple(item.raw_probabilities for item in run.predictions) else ("RAW_PREDICTION_REPRODUCTION_MISMATCH",)


def verify_calibration_reproduction(
    repository, model_repository, calibration_repository, training_repository,
    backtest_run_id,
):
    run = repository.load_backtest_run(backtest_run_id)
    if run is None:
        return ("BACKTEST_NOT_FOUND",)
    artifact = model_repository.load_model_artifact(run.command.model_artifact_id)
    calibration = calibration_repository.load_calibration_artifact_set(run.command.calibration_artifact_set_id)
    examples = tuple(training_repository.load_training_example(item.training_example_id) for item in run.predictions)
    if artifact is None or calibration is None or any(item is None for item in examples):
        return ("CALIBRATION_SOURCE_NOT_FOUND",)
    reproduced = reproduce_predictions(examples, artifact, calibration, run_namespace=run.backtest_run_id)
    return () if tuple(item.calibrated_probabilities for item in reproduced) == tuple(item.calibrated_probabilities for item in run.predictions) else ("CALIBRATION_REPRODUCTION_MISMATCH",)


def verify_equal_kickoff_group_handling(selections):
    failures = []
    groups = {}
    for item in selections:
        group = groups.setdefault(item.kickoff_group_id, (item.kickoff_utc, item.bankroll_snapshot))
        if group != (item.kickoff_utc, item.bankroll_snapshot):
            failures.append(f"{item.kickoff_group_id}:INCONSISTENT_GROUP_SNAPSHOT")
    return tuple(failures)


def verify_backtest_fingerprints(repository, backtest_run_id):
    run = repository.load_backtest_run(backtest_run_id)
    if run is None:
        return ("BACKTEST_NOT_FOUND",)
    snapshot = json.loads(run.deterministic_run_snapshot)
    expected = sha256_fingerprint(snapshot["run_material"])
    return () if expected == run.backtest_run_fingerprint else ("BACKTEST_RUN_FINGERPRINT_MISMATCH",)


def reproduce_all_predictive_metrics(repository, backtest_run_id, bin_count=10):
    return reproduce_predictive_metrics(repository.list_predictions(backtest_run_id), bin_count)


def reproduce_all_betting_metrics(repository, backtest_run_id):
    run = repository.load_backtest_run(backtest_run_id)
    if run is None:
        return None
    closing = tuple(item for item in run.odds_snapshots if item.closing)
    return reproduce_betting_metrics(
        run.predictions, run.assessments, run.selections, run.settlements,
        run.ledger, run.command.initial_bankroll, closing,
    )


def verify_backtest_read_model(repository, split_repository, policy, backtest_run_id):
    run = repository.load_backtest_run(backtest_run_id)
    if run is None:
        return ("BACKTEST_NOT_FOUND",)
    return (
        verify_test_partition_only(split_repository, run.command.fold_id, tuple(item.training_example_id for item in run.predictions))
        + verify_odds_temporal_safety(run.odds_snapshots)
        + verify_selection_policy_alignment(run.selections, run.assessments)
        + verify_settlement_consistency(run.selections, run.settlements, policy, run_namespace=run.backtest_run_id)
        + verify_bankroll_ledger(
            run.command.initial_bankroll, run.selections, run.settlements, run.ledger,
            run_namespace=run.backtest_run_id,
        )
        + verify_equal_kickoff_group_handling(run.selections)
        + verify_backtest_fingerprints(repository, backtest_run_id)
    )
