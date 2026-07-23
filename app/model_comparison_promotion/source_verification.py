"""Fail-closed verification of model, calibration, and completed TEST backtests."""

from __future__ import annotations

import json

from app.historical_backtesting import verify_bankroll_ledger
from app.historical_backtesting.fingerprint import sha256_fingerprint

from .exceptions import ComparisonSourceError
from .fingerprint import canonical_json, source_compatibility_fingerprint
from .models import CompatibilityStatus, SourceEvidence, VerifiedSourceBundle


def verify_source_bundle(
    *,
    model_repository,
    calibration_repository,
    backtest_repository,
    model_artifact_id: str,
    model_artifact_fingerprint: str,
    calibration_artifact_set_id: str,
    calibration_artifact_set_fingerprint: str,
    backtest_run_id: str,
    backtest_run_fingerprint: str,
    source_role: str,
) -> VerifiedSourceBundle:
    model = model_repository.load_model_artifact(model_artifact_id)
    if model is None:
        raise ComparisonSourceError(f"{source_role}_MODEL_NOT_FOUND")
    if model.artifact_fingerprint != model_artifact_fingerprint:
        raise ComparisonSourceError(f"{source_role}_MODEL_FINGERPRINT_MISMATCH")
    calibration = calibration_repository.load_calibration_artifact_set(
        calibration_artifact_set_id
    )
    if calibration is None:
        raise ComparisonSourceError(f"{source_role}_CALIBRATION_NOT_FOUND")
    if calibration.artifact_set_fingerprint != calibration_artifact_set_fingerprint:
        raise ComparisonSourceError(f"{source_role}_CALIBRATION_FINGERPRINT_MISMATCH")
    if (
        calibration.command.source_model_artifact_id != model.artifact_id
        or calibration.command.source_model_artifact_fingerprint != model.artifact_fingerprint
    ):
        raise ComparisonSourceError(f"{source_role}_CALIBRATION_MODEL_MISMATCH")
    backtest = backtest_repository.load_backtest_run(backtest_run_id)
    if backtest is None:
        raise ComparisonSourceError(f"{source_role}_BACKTEST_NOT_FOUND")
    if backtest.backtest_run_fingerprint != backtest_run_fingerprint:
        raise ComparisonSourceError(f"{source_role}_BACKTEST_FINGERPRINT_MISMATCH")
    command = backtest.command
    if (
        command.model_artifact_id != model.artifact_id
        or command.model_artifact_fingerprint != model.artifact_fingerprint
        or command.calibration_artifact_set_id != calibration.artifact_set_id
        or command.calibration_artifact_set_fingerprint
        != calibration.artifact_set_fingerprint
    ):
        raise ComparisonSourceError(f"{source_role}_BACKTEST_SOURCE_LINKAGE_MISMATCH")
    if (
        command.source_split_id != model.source_split_id
        or command.source_split_fingerprint != model.source_split_fingerprint
        or command.fold_id != model.fold_id
        or command.fold_fingerprint != model.fold_fingerprint
    ):
        raise ComparisonSourceError(f"{source_role}_BACKTEST_TEST_PROVENANCE_MISMATCH")
    if len(model.canonical_target_order) != 11:
        raise ComparisonSourceError(f"{source_role}_PROBABILITY_TARGET_CONTRACT_MISMATCH")
    if not backtest.predictions:
        raise ComparisonSourceError(f"{source_role}_BACKTEST_HAS_NO_TEST_PREDICTIONS")
    if len({item.training_example_id for item in backtest.predictions}) != len(
        backtest.predictions
    ):
        raise ComparisonSourceError(f"{source_role}_BACKTEST_DUPLICATE_TEST_PREDICTION")
    if len(backtest.selections) != len(backtest.settlements):
        raise ComparisonSourceError(f"{source_role}_BACKTEST_INCOMPLETE_SETTLEMENTS")
    ledger_failures = verify_bankroll_ledger(
        command.initial_bankroll,
        backtest.selections,
        backtest.settlements,
        backtest.ledger,
        run_namespace=backtest.backtest_run_id,
    )
    if ledger_failures:
        raise ComparisonSourceError(f"{source_role}_BACKTEST_BANKROLL_INTEGRITY_FAILURE")
    snapshot = json.loads(backtest.deterministic_run_snapshot)
    if sha256_fingerprint(snapshot["run_material"]) != backtest.backtest_run_fingerprint:
        raise ComparisonSourceError(f"{source_role}_BACKTEST_RUN_FINGERPRINT_MISMATCH")
    metric_keys = {
        (item.category, item.grouping_identity, item.metric_name)
        for item in backtest.metrics
    }
    required_metrics = {
        ("PREDICTIVE", "CALIBRATED:AGGREGATE", "multiclass_log_loss"),
        ("PREDICTIVE", "CALIBRATED:AGGREGATE", "multiclass_brier_score"),
        ("PREDICTIVE", "CALIBRATED:AGGREGATE", "accuracy"),
        ("BETTING", "OVERALL", "roi"),
        ("BETTING", "OVERALL", "maximum_percentage_drawdown"),
    }
    if not required_metrics.issubset(metric_keys):
        raise ComparisonSourceError(f"{source_role}_BACKTEST_METRIC_INTEGRITY_FAILURE")
    evidence_values = (
        ("MODEL", "artifact_fingerprint", model.artifact_fingerprint),
        ("CALIBRATION", "artifact_set_fingerprint", calibration.artifact_set_fingerprint),
        ("BACKTEST", "run_fingerprint", backtest.backtest_run_fingerprint),
        ("BACKTEST", "test_prediction_count", len(backtest.predictions)),
        ("BACKTEST", "selected_bet_count", len(backtest.selections)),
        ("BACKTEST", "ledger_entry_count", len(backtest.ledger)),
    )
    evidence = tuple(
        _evidence(source_role, category, name, value, index)
        for index, (category, name, value) in enumerate(evidence_values)
    )
    return VerifiedSourceBundle(
        model_artifact=model,
        calibration_artifact_set=calibration,
        backtest_run=backtest,
        evidence=evidence,
        source_fingerprint=source_compatibility_fingerprint(evidence),
    )


def verify_champion_source_integrity(*args, **kwargs):
    kwargs["source_role"] = "CHAMPION"
    return verify_source_bundle(*args, **kwargs)


def verify_challenger_source_integrity(*args, **kwargs):
    kwargs["source_role"] = "CHALLENGER"
    return verify_source_bundle(*args, **kwargs)


def _evidence(role, category, name, value, order):
    snapshot = canonical_json(value)
    material = {
        "role": role,
        "category": category,
        "name": name,
        "value": value,
        "status": CompatibilityStatus.COMPATIBLE,
    }
    return SourceEvidence(
        evidence_row_id=f"model-comparison-source-{sha256_fingerprint(material)}",
        category=category,
        name=f"{role}_{name}",
        champion_value_snapshot=snapshot if role == "CHAMPION" else "null",
        challenger_value_snapshot=snapshot if role == "CHALLENGER" else "null",
        compatibility_status=CompatibilityStatus.COMPATIBLE,
        detail_snapshot=canonical_json({"verified": True}),
        evidence_fingerprint=sha256_fingerprint(material),
        deterministic_order=order,
    )
