"""Strict immutable request validation and normalization."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from .exceptions import ComparisonValidationError
from .models import (
    ChallengerCandidate,
    ComparisonMode,
    ComparisonScope,
    ModelComparisonCommand,
    NormalizedComparisonCommand,
    NormalizedComparisonScope,
)


def validate_comparison_command(
    command: ModelComparisonCommand,
    policy,
) -> NormalizedComparisonCommand:
    if not isinstance(command, ModelComparisonCommand):
        raise ComparisonValidationError("Comparison command must be ModelComparisonCommand.")
    if not isinstance(command.scope, ComparisonScope):
        raise ComparisonValidationError("Comparison scope must be ComparisonScope.")
    if not command.challengers:
        raise ComparisonValidationError("At least one challenger is required.")
    required = (
        command.comparison_request_id,
        command.comparison_run_name,
        command.champion_model_artifact_id,
        command.champion_model_artifact_fingerprint,
        command.champion_calibration_artifact_set_id,
        command.champion_calibration_artifact_set_fingerprint,
        command.champion_backtest_run_id,
        command.champion_backtest_run_fingerprint,
    )
    if not all(isinstance(item, str) and item.strip() for item in required):
        raise ComparisonValidationError("All champion and request identities are required.")
    if not all(isinstance(item, ChallengerCandidate) for item in command.challengers):
        raise ComparisonValidationError("Every challenger must be ChallengerCandidate.")
    ids: set[str] = set()
    tuples: set[tuple[str, str]] = set()
    for candidate in command.challengers:
        values = (
            candidate.challenger_candidate_id,
            candidate.model_artifact_id,
            candidate.model_artifact_fingerprint,
            candidate.calibration_artifact_set_id,
            candidate.calibration_artifact_set_fingerprint,
            candidate.backtest_run_id,
            candidate.backtest_run_fingerprint,
        )
        if not all(isinstance(item, str) and item.strip() for item in values):
            raise ComparisonValidationError("Every challenger identity and fingerprint is required.")
        if candidate.challenger_candidate_id in ids:
            raise ComparisonValidationError("Duplicate challenger candidate ID.")
        ids.add(candidate.challenger_candidate_id)
        source_tuple = (candidate.model_artifact_id, candidate.backtest_run_id)
        if source_tuple in tuples:
            raise ComparisonValidationError("Duplicate challenger model/backtest tuple.")
        tuples.add(source_tuple)
        if (
            candidate.model_artifact_id == command.champion_model_artifact_id
            or candidate.backtest_run_id == command.champion_backtest_run_id
        ):
            raise ComparisonValidationError("Champion self-comparison is prohibited.")
    expected_versions = dict(policy.versions)
    supplied_versions = {
        "promotion": command.promotion_policy_version,
        "evidence": command.evidence_policy_version,
        "compatibility": command.compatibility_policy_version,
        "significance": command.significance_policy_version,
        "predictive_score": command.predictive_score_policy_version,
        "calibration_score": command.calibration_score_policy_version,
        "betting_score": command.betting_score_policy_version,
        "risk_score": command.risk_score_policy_version,
        "stability_score": command.stability_score_policy_version,
        "tie_break": command.tie_break_policy_version,
    }
    if supplied_versions != expected_versions:
        raise ComparisonValidationError("Command promotion policy versions do not match the explicit policy.")
    scope = command.scope
    if not scope.comparison_scope_version.strip():
        raise ComparisonValidationError("Comparison scope version is required.")
    if scope.required_minimum_shared_sample_size < 1:
        raise ComparisonValidationError("Minimum shared sample size must be positive.")
    if scope.required_minimum_selected_bet_count < 1:
        raise ComparisonValidationError("Minimum selected-bet count must be positive.")
    try:
        mode = ComparisonMode(scope.mode)
        timestamp = _utc(command.comparison_timestamp, required=True)
        lower = _utc(scope.kickoff_lower_bound, required=False)
        upper = _utc(scope.kickoff_upper_bound, required=False)
    except (TypeError, ValueError) as exc:
        raise ComparisonValidationError(str(exc)) from exc
    if lower and upper and lower > upper:
        raise ComparisonValidationError("Kickoff lower bound must not exceed upper bound.")
    scope_versions = (
        scope.required_odds_policy_version,
        scope.required_selection_policy_version,
        scope.required_staking_policy_version,
        scope.required_settlement_policy_version,
        scope.required_metric_policy_version,
    )
    if not all(isinstance(item, str) and item.strip() for item in scope_versions):
        raise ComparisonValidationError("Every required comparison policy version is required.")
    normalized_scope = NormalizedComparisonScope(
        comparison_scope_version=scope.comparison_scope_version.strip(),
        mode=mode,
        required_competitions=_normalized_set(scope.required_competitions),
        required_seasons=_normalized_set(scope.required_seasons),
        required_markets=_normalized_set(scope.required_markets),
        kickoff_lower_bound=lower,
        kickoff_upper_bound=upper,
        required_odds_policy_version=scope.required_odds_policy_version,
        required_selection_policy_version=scope.required_selection_policy_version,
        required_staking_policy_version=scope.required_staking_policy_version,
        required_settlement_policy_version=scope.required_settlement_policy_version,
        required_metric_policy_version=scope.required_metric_policy_version,
        required_minimum_shared_sample_size=scope.required_minimum_shared_sample_size,
        required_minimum_selected_bet_count=scope.required_minimum_selected_bet_count,
    )
    return NormalizedComparisonCommand(
        comparison_request_id=command.comparison_request_id.strip(),
        comparison_run_name=command.comparison_run_name.strip(),
        champion_model_artifact_id=command.champion_model_artifact_id.strip(),
        champion_model_artifact_fingerprint=command.champion_model_artifact_fingerprint.strip(),
        champion_calibration_artifact_set_id=command.champion_calibration_artifact_set_id.strip(),
        champion_calibration_artifact_set_fingerprint=command.champion_calibration_artifact_set_fingerprint.strip(),
        champion_backtest_run_id=command.champion_backtest_run_id.strip(),
        champion_backtest_run_fingerprint=command.champion_backtest_run_fingerprint.strip(),
        challengers=tuple(
            replace(
                item,
                challenger_candidate_id=item.challenger_candidate_id.strip(),
                model_artifact_id=item.model_artifact_id.strip(),
                model_artifact_fingerprint=item.model_artifact_fingerprint.strip(),
                calibration_artifact_set_id=item.calibration_artifact_set_id.strip(),
                calibration_artifact_set_fingerprint=item.calibration_artifact_set_fingerprint.strip(),
                backtest_run_id=item.backtest_run_id.strip(),
                backtest_run_fingerprint=item.backtest_run_fingerprint.strip(),
                label=item.label.strip() if item.label and item.label.strip() else None,
            )
            for item in command.challengers
        ),
        scope=normalized_scope,
        comparison_timestamp=timestamp,
        promotion_policy_version=command.promotion_policy_version,
        evidence_policy_version=command.evidence_policy_version,
        compatibility_policy_version=command.compatibility_policy_version,
        significance_policy_version=command.significance_policy_version,
        predictive_score_policy_version=command.predictive_score_policy_version,
        calibration_score_policy_version=command.calibration_score_policy_version,
        betting_score_policy_version=command.betting_score_policy_version,
        risk_score_policy_version=command.risk_score_policy_version,
        stability_score_policy_version=command.stability_score_policy_version,
        tie_break_policy_version=command.tie_break_policy_version,
        code_metadata_version=command.code_metadata_version,
        dependency_metadata_version=command.dependency_metadata_version,
        environment_metadata_version=command.environment_metadata_version,
        metadata_version=command.metadata_version,
    )


def _utc(value, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise ValueError("Explicit comparison timestamp is required.")
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Comparison timestamps must be timezone-aware.")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalized_set(values) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ComparisonValidationError("Scope collections must be immutable tuples.")
    normalized = tuple(sorted({str(item).strip() for item in values if str(item).strip()}))
    if len(normalized) != len(values):
        raise ComparisonValidationError("Scope collections cannot contain blank or duplicate values.")
    return normalized
