"""Adapters over the existing deterministic runtime calibration fitters."""

from __future__ import annotations

from datetime import datetime

from app.calibration import (
    CalibrationFitRequest, CalibrationFittingError, CalibrationFittingPolicy,
    CalibrationNonConvergenceError, CalibrationObservation, CalibrationScope,
    CalibrationTrainingWindow, CalibratorSerializer, IdentityCalibrator,
    IsotonicCalibrator, IsotonicFittingConfig, PlattCalibrator, PlattFittingConfig,
)

from .exceptions import (
    CalibrationConvergenceError, CalibrationFitError, InsufficientClassSupportError,
)
from .fingerprint import canonical_json, sha256_fingerprint
from .models import TargetCalibrationArtifact
from .policy import CalibrationMethod, HistoricalCalibrationPolicy


FITTED_TARGETS = ("HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "OVER_2_5", "OVER_3_5", "BTTS_YES")
DERIVED_TARGETS = (
    ("UNDER_1_5", "OVER_1_5"), ("UNDER_2_5", "OVER_2_5"),
    ("UNDER_3_5", "OVER_3_5"), ("BTTS_NO", "BTTS_YES"),
)


def fit_target_calibrators(command, examples_and_predictions, policy: HistoricalCalibrationPolicy):
    methods = _methods(command)
    timestamp = datetime.fromisoformat(command.calibration_timestamp.replace("Z", "+00:00"))
    canonical_order = (
        "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5",
        "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO",
    )
    calibrators = {}
    artifacts = []
    for target in FITTED_TARGETS:
        observations = _observations(examples_and_predictions, target, command.source_model_artifact_id)
        positives = sum(item.binary_outcome for item in observations)
        negatives = len(observations) - positives
        minimum_class = policy.minimum_examples_per_match_result_class if target in {"HOME_WIN", "DRAW", "AWAY_WIN"} else policy.minimum_positive_per_binary_target
        minimum_negative = policy.minimum_negative_per_binary_target
        if positives < minimum_class or negatives < minimum_negative:
            raise InsufficientClassSupportError(f"{target} has insufficient positive/negative support.")
        method = methods[target]
        if method is CalibrationMethod.ISOTONIC_REGRESSION_V1 and len({item.raw_probability for item in observations}) < policy.minimum_distinct_probabilities_for_isotonic:
            raise InsufficientClassSupportError(f"{target} has insufficient distinct probabilities for isotonic fitting.")
        calibrator = _fit(
            method, observations, timestamp, command, policy,
            minimum_positive=minimum_class, minimum_negative=minimum_negative,
        )
        serialized = CalibratorSerializer().serialize(calibrator)
        parameters = canonical_json(serialized)
        convergence = canonical_json(serialized.get("diagnostics", {"converged": True, "identity": True}))
        support = canonical_json({"sample_count": len(observations), "positive_count": positives, "negative_count": negatives, "distinct_raw_probabilities": len({item.raw_probability for item in observations})})
        class_order = ("HOME_WIN", "DRAW", "AWAY_WIN") if target in {"HOME_WIN", "DRAW", "AWAY_WIN"} else ("NEGATIVE", "POSITIVE")
        fingerprint = sha256_fingerprint({
            "target_identity": target, "calibration_method": method,
            "fitted_parameters": serialized, "class_order": class_order, "support_counts": support,
            "convergence_data": convergence,
            "policy_versions": (command.calibration_policy_version, command.runtime_compatibility_version),
        })
        calibrators[target] = calibrator
        artifacts.append(TargetCalibrationArtifact(
            target_identity=target, target_order=canonical_order.index(target), method=method,
            target_artifact_fingerprint=fingerprint, fitted_parameters_snapshot=parameters,
            class_order=class_order, support_snapshot=support, convergence_snapshot=convergence,
            derivation_snapshot="{}",
        ))
    return calibrators, tuple(artifacts)


def derived_target_artifacts(fitted, command):
    by_target = {item.target_identity: item for item in fitted}
    canonical_order = ("HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO")
    all_items = list(fitted)
    for target, source in DERIVED_TARGETS:
        source_item = by_target[source]
        derivation = canonical_json({"complement_source_target": source, "derivation_rule": "ONE_MINUS_SOURCE_AFTER_RECONCILIATION_OR_PROJECTION"})
        fingerprint = sha256_fingerprint({
            "target_identity": target, "calibration_method": source_item.method,
            "fitted_parameters": (), "class_order": (), "support_counts": source_item.support_snapshot,
            "convergence_data": (), "derivation": derivation,
            "policy_versions": (command.calibration_policy_version, command.runtime_compatibility_version),
        })
        all_items.append(TargetCalibrationArtifact(
            target_identity=target, target_order=canonical_order.index(target), method=source_item.method,
            target_artifact_fingerprint=fingerprint, fitted_parameters_snapshot="{}", class_order=(),
            support_snapshot=source_item.support_snapshot, convergence_snapshot="{}",
            derivation_snapshot=derivation,
        ))
    return tuple(sorted(all_items, key=lambda item: canonical_order.index(item.target_identity)))


def _fit(method, observations, timestamp, command, policy, *, minimum_positive, minimum_negative):
    if method is CalibrationMethod.IDENTITY_V1:
        if not policy.allow_identity_calibration:
            raise CalibrationFitError("Identity calibration is not allowed by policy.")
        trainer = IdentityCalibrator
    else:
        fitting_policy = CalibrationFittingPolicy(
            global_minimum=policy.minimum_validation_examples, market_minimum=policy.minimum_validation_examples,
            competition_minimum=policy.minimum_validation_examples,
            competition_market_minimum=policy.minimum_validation_examples,
            odds_band_minimum=policy.minimum_validation_examples,
            minimum_positive=minimum_positive,
            minimum_negative=minimum_negative,
        )
        trainer = PlattCalibrator(
            PlattFittingConfig(policy.platt_epsilon, policy.platt_regularization, policy.platt_maximum_iterations, policy.platt_convergence_tolerance),
            fitting_policy,
        ) if method is CalibrationMethod.PLATT_SCALING_V1 else IsotonicCalibrator(
            IsotonicFittingConfig(output_epsilon=policy.minimum_probability), fitting_policy,
        )
    window = CalibrationTrainingWindow(
        min(item.prediction_timestamp for item in observations),
        max(item.outcome_timestamp for item in observations),
    )
    request = CalibrationFitRequest(
        fitted_at=timestamp, training_window=window, scope=CalibrationScope.global_scope(),
        version=command.runtime_compatibility_version, model_version=command.source_model_artifact_id,
    )
    try:
        return trainer.fit(observations, request)
    except CalibrationNonConvergenceError as exc:
        raise CalibrationConvergenceError(str(exc)) from exc
    except (CalibrationFittingError, ValueError) as exc:
        raise CalibrationFitError(str(exc)) from exc


def _observations(items, target, model_version):
    result = []
    for order, (example, prediction) in enumerate(items):
        raw = next(item.probability for item in prediction.raw_probabilities.ordered_probabilities if item.target.value == target)
        kickoff = datetime.fromisoformat(example.kickoff_utc.replace("Z", "+00:00"))
        result.append(CalibrationObservation(
            observation_id=f"{example.training_example_id}:{target}", fixture_id=order + 1,
            competition=example.competition, market=target, selection=target,
            prediction_timestamp=kickoff, outcome_timestamp=kickoff,
            raw_probability=raw, binary_outcome=dict(example.labels)[target], model_version=model_version,
        ))
    return tuple(result)


def _methods(command):
    result = {
        "HOME_WIN": command.match_result_method, "DRAW": command.match_result_method,
        "AWAY_WIN": command.match_result_method, "OVER_1_5": command.totals_method,
        "OVER_2_5": command.totals_method, "OVER_3_5": command.totals_method,
        "BTTS_YES": command.btts_method,
    }
    result.update({item.target_identity: item.method for item in command.target_method_overrides})
    return result
