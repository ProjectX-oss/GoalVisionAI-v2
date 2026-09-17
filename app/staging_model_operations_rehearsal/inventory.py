"""Read-only persisted artifact-chain discovery."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ArtifactCandidate, ArtifactInventory


def inventory_real_artifacts(
    source: Path,
) -> ArtifactInventory:
    connection = sqlite3.connect(
        f"{source.as_uri()}?mode=ro", uri=True, timeout=5.0
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required = {
            "historical_model_artifacts",
            "historical_probability_calibration_artifact_sets",
            "historical_backtest_runs",
            "model_comparison_runs",
            "model_comparison_recommendations",
            "shadow_evaluation_executions",
            "shadow_evaluation_settlements",
        }
        if not required.issubset(tables):
            return ArtifactInventory(
                (), None, False, ("SOURCE_SCHEMA_LACKS_COMPLETE_ML_CHAIN",)
            )
        candidates = tuple(
            _candidate(connection, row)
            for row in connection.execute(
                """SELECT artifact_id,artifact_fingerprint,training_run_id,
                          preprocessing_fingerprint,
                          estimator_bundle_fingerprint,
                          compatibility_snapshot
                   FROM historical_model_artifacts
                   ORDER BY created_timestamp,artifact_id"""
            )
        )
        eligible = tuple(item for item in candidates if item.audit_eligible)
        if eligible:
            return ArtifactInventory(
                candidates,
                eligible[-1].model_artifact_id,
                False,
                ("COMPLETE_REAL_ARTIFACT_CHAIN_SELECTED",),
            )
        reasons = ("NO_COMPLETE_REAL_ARTIFACT_CHAIN",)
        return ArtifactInventory(candidates, None, False, reasons)
    finally:
        connection.close()


def _candidate(connection, model) -> ArtifactCandidate:
    compatibility = _json(model["compatibility_snapshot"])
    calibration = connection.execute(
        """SELECT artifact_set_id,artifact_set_fingerprint,
                  runtime_compatibility_version
           FROM historical_probability_calibration_artifact_sets
           WHERE json_extract(compatibility_snapshot,'$.source_model_artifact_id')=?
           ORDER BY created_timestamp DESC LIMIT 1""",
        (model["artifact_id"],),
    ).fetchone()
    backtest = None
    comparison = None
    recommendation = None
    settled = 0
    reasons = []
    if calibration is None:
        reasons.append("CALIBRATION_ARTIFACT_SET_MISSING")
    else:
        backtest = connection.execute(
            """SELECT backtest_run_id,backtest_run_fingerprint
               FROM historical_backtest_runs
               WHERE model_artifact_id=? AND calibration_artifact_set_id=?
               ORDER BY backtest_timestamp DESC LIMIT 1""",
            (model["artifact_id"], calibration["artifact_set_id"]),
        ).fetchone()
        if backtest is None:
            reasons.append("BACKTEST_RUN_MISSING")
    comparison = connection.execute(
        """SELECT comparison_run_id,comparison_run_fingerprint,
                  final_recommendation
           FROM model_comparison_runs
           WHERE champion_model_artifact_id=? OR
                 final_recommended_challenger_id IN (
                   SELECT challenger_candidate_id
                   FROM model_comparison_candidates
                   WHERE model_artifact_id=?
                 )
           ORDER BY comparison_timestamp DESC LIMIT 1""",
        (model["artifact_id"], model["artifact_id"]),
    ).fetchone()
    if comparison is None:
        reasons.append("COMPARISON_DECISION_MISSING")
    else:
        recommendation = connection.execute(
            """SELECT recommendation_id,recommendation
               FROM model_comparison_recommendations
               WHERE comparison_run_id=? AND recommendation='PROMOTE_CHALLENGER'
               ORDER BY created_timestamp DESC LIMIT 1""",
            (comparison["comparison_run_id"],),
        ).fetchone()
        if recommendation is None:
            reasons.append("PROMOTE_CHALLENGER_RECOMMENDATION_MISSING")
        settled = connection.execute(
            """SELECT COUNT(*)
               FROM shadow_evaluation_settlements s
               JOIN shadow_evaluation_executions e
                 ON e.shadow_execution_id=s.shadow_execution_id
               WHERE e.comparison_run_id=?""",
            (comparison["comparison_run_id"],),
        ).fetchone()[0]
        if settled == 0:
            reasons.append("SETTLED_SHADOW_EVIDENCE_MISSING")
    complete = not reasons
    return ArtifactCandidate(
        model_artifact_id=model["artifact_id"],
        model_artifact_fingerprint=model["artifact_fingerprint"],
        training_run_id=model["training_run_id"],
        preprocessing_fingerprint=model["preprocessing_fingerprint"],
        estimator_fingerprint=model["estimator_bundle_fingerprint"],
        calibration_artifact_set_id=(
            calibration["artifact_set_id"] if calibration else None
        ),
        calibration_artifact_set_fingerprint=(
            calibration["artifact_set_fingerprint"] if calibration else None
        ),
        backtest_run_id=backtest["backtest_run_id"] if backtest else None,
        comparison_run_id=(
            comparison["comparison_run_id"] if comparison else None
        ),
        recommendation_id=(
            recommendation["recommendation_id"] if recommendation else None
        ),
        settled_shadow_count=settled,
        feature_schema_version=compatibility.get("feature_schema_version"),
        probability_contract_version=compatibility.get(
            "probability_contract_version",
            "goalvision-raw-probability-contract-v1",
        ),
        runtime_compatibility_version=(
            calibration["runtime_compatibility_version"]
            if calibration else None
        ),
        complete=complete,
        audit_eligible=complete,
        rejection_reasons=tuple(reasons),
    )


def _json(value):
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}
