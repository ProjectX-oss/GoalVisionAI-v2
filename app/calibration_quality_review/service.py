"""Read-only deterministic quality review over persisted calibration evidence."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from statistics import median

from app.calibration import CalibratorSerializer
from app.historical_dataset_split import Partition, SQLiteHistoricalDatasetSplitRepository
from app.historical_model_training import SQLiteHistoricalModelTrainingRepository
from app.historical_probability_calibration.artifact import _bounded_simplex, _decreasing_pava
from app.historical_probability_calibration.fingerprint import sha256_fingerprint
from app.historical_training_dataset import SQLiteHistoricalTrainingDatasetRepository

from .models import (
    CalibrationQualityReport, CalibrationQualityStatus, CalibrationTrace,
    DistributionShiftReport, DistributionShiftStatus, FeatureShiftEvidence,
    TargetQualityEvidence,
)
from .policy import DEFAULT_CALIBRATION_QUALITY_POLICY


FITTED_TARGETS = (
    "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "OVER_2_5",
    "OVER_3_5", "BTTS_YES",
)
TARGET_ORDER = (
    "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5",
    "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5",
    "BTTS_YES", "BTTS_NO",
)


def build_calibration_quality_report(
    database, model_artifact, calibration_set, calibration_run, raw_probabilities,
    model_input, *, audit_status: str, freshness_status: str,
    policy=DEFAULT_CALIBRATION_QUALITY_POLICY,
) -> CalibrationQualityReport:
    training = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
    target_evidence = _target_evidence(
        calibration_set, calibration_run, training, policy
    )
    traces = _traces(calibration_set, raw_probabilities, target_evidence, policy)
    shift = _distribution_shift(database, model_artifact, model_input, policy)
    controlled = "CONTROLLED_SYNTHETIC" in calibration_set.provenance_snapshot
    artifact_reasons = []
    if audit_status != "AUDIT_PASSED":
        artifact_reasons.append("CALIBRATION_AUDIT_NOT_PASSED")
    if freshness_status != "ACTIONABLE_FOR_LAB":
        artifact_reasons.append("CALIBRATION_FRESHNESS_NOT_ACTIONABLE")
    if any(item.support_status != "CALIBRATION_SUPPORT_ACCEPTABLE" for item in target_evidence if not item.derived_complement):
        artifact_reasons.append("CALIBRATION_SUPPORT_INSUFFICIENT")
    artifact_status = (
        CalibrationQualityStatus.INELIGIBLE if artifact_reasons
        else CalibrationQualityStatus.ACCEPTABLE
    )
    inference_reasons = []
    if any(item.extreme_status == "CALIBRATION_EXTREME_UNSUPPORTED" for item in traces):
        inference_reasons.append("CALIBRATION_EXTREME_UNSUPPORTED")
    if shift.status is not DistributionShiftStatus.ACCEPTABLE:
        inference_reasons.append(shift.status.value)
    if controlled:
        inference_reasons.append("CONTROLLED_SYNTHETIC_CALIBRATION_NOT_PUBLICATION_ELIGIBLE")
    reasons = tuple(dict.fromkeys((*artifact_reasons, *inference_reasons)))
    lab = (
        CalibrationQualityStatus.INELIGIBLE
        if artifact_status is CalibrationQualityStatus.INELIGIBLE
        or "CALIBRATION_EXTREME_UNSUPPORTED" in inference_reasons
        or shift.status is DistributionShiftStatus.INELIGIBLE
        else CalibrationQualityStatus.REVIEW_REQUIRED
        if reasons else CalibrationQualityStatus.ACCEPTABLE
    )
    material = {
        "schema_version": "goalvision-calibration-quality-report-v1",
        "policy_version": policy.version,
        "model_artifact_id": model_artifact.artifact_id,
        "model_artifact_fingerprint": model_artifact.artifact_fingerprint,
        "calibration_artifact_set_id": calibration_set.artifact_set_id,
        "calibration_artifact_set_fingerprint": calibration_set.artifact_set_fingerprint,
        "source_mode": _source_mode(calibration_set.provenance_snapshot),
        "controlled_synthetic": controlled,
        "target_evidence": target_evidence,
        "traces": traces,
        "distribution_shift": shift,
        "artifact_status": artifact_status,
        "lab_outcome": lab,
        "official_outcome": CalibrationQualityStatus.INELIGIBLE,
        "analysis_preview_allowed": True,
        "send_eligible": (
            not controlled
            and lab is CalibrationQualityStatus.ACCEPTABLE
        ),
        "reason_codes": reasons,
    }
    return CalibrationQualityReport(
        **material, fingerprint=sha256_fingerprint(material)
    )


def market_quality_reasons(report: CalibrationQualityReport, trace: CalibrationTrace) -> tuple[str, ...]:
    reasons = []
    if trace.extreme_status == "CALIBRATION_EXTREME_UNSUPPORTED":
        reasons.append("CALIBRATION_EXTREME_UNSUPPORTED")
    if trace.absolute_adjustment > DEFAULT_CALIBRATION_QUALITY_POLICY.maximum_single_adjustment:
        reasons.append("CALIBRATION_ADJUSTMENT_EXCESSIVE")
    if report.distribution_shift.status is not DistributionShiftStatus.ACCEPTABLE:
        reasons.append(report.distribution_shift.status.value)
    if report.controlled_synthetic:
        reasons.append("CONTROLLED_SYNTHETIC_CALIBRATION_NOT_PUBLICATION_ELIGIBLE")
    if report.artifact_status is CalibrationQualityStatus.INELIGIBLE:
        reasons.append("CALIBRATION_QUALITY_INELIGIBLE")
    return tuple(dict.fromkeys(reasons))


def _target_evidence(calibration_set, run, training, policy):
    artifacts = {item.target_identity: item for item in calibration_set.target_artifacts}
    metrics = {
        (item.target_identity, item.metric_phase, item.metric_name): item.metric_value
        for item in run.metrics
    }
    result = []
    for target in TARGET_ORDER:
        artifact = artifacts[target]
        derivation = json.loads(artifact.derivation_snapshot)
        source = derivation.get("complement_source_target", target)
        source_artifact = artifacts[source]
        support = json.loads(source_artifact.support_snapshot)
        raw = tuple(_prob(item.raw_probabilities, source) for item in run.predictions)
        calibrated = tuple(_prob(item.calibrated_probabilities, target) for item in run.predictions)
        source_calibrated = tuple(_prob(item.calibrated_probabilities, source) for item in run.predictions)
        bins = tuple(item for item in run.reliability_bins if item.target_identity == target and item.metric_phase == "CALIBRATED")
        populated = tuple(item.sample_count for item in bins if item.sample_count)
        adjustments = tuple(abs(a-b) for a, b in zip(raw if source == target else tuple(Decimal(1)-v for v in raw), calibrated))
        reasons = []
        if support["sample_count"] < policy.minimum_validation_count: reasons.append("CALIBRATION_SUPPORT_INSUFFICIENT")
        if support["positive_count"] < policy.minimum_positive_count: reasons.append("CALIBRATION_POSITIVE_SUPPORT_INSUFFICIENT")
        if support["negative_count"] < policy.minimum_negative_count: reasons.append("CALIBRATION_NEGATIVE_SUPPORT_INSUFFICIENT")
        if support["distinct_raw_probabilities"] < policy.minimum_unique_raw_probabilities: reasons.append("CALIBRATION_UNIQUE_RAW_SUPPORT_INSUFFICIENT")
        if len(populated) < policy.minimum_populated_reliability_bins: reasons.append("CALIBRATION_RELIABILITY_SUPPORT_INSUFFICIENT")
        ece = metrics[(target, "CALIBRATED", "expected_calibration_error")]
        mce = metrics[(target, "CALIBRATED", "maximum_calibration_error")]
        brier_before = metrics[(target, "RAW", "brier_score")]
        brier_after = metrics[(target, "CALIBRATED", "brier_score")]
        loss_before = metrics[(target, "RAW", "log_loss")]
        loss_after = metrics[(target, "CALIBRATED", "log_loss")]
        if ece > policy.maximum_ece: reasons.append("CALIBRATION_ECE_EXCESSIVE")
        if mce > policy.maximum_mce: reasons.append("CALIBRATION_MCE_EXCESSIVE")
        if brier_after-brier_before > policy.maximum_brier_degradation: reasons.append("CALIBRATION_BRIER_DEGRADED")
        if loss_after-loss_before > policy.maximum_log_loss_degradation: reasons.append("CALIBRATION_LOG_LOSS_DEGRADED")
        parameters = json.loads(source_artifact.fitted_parameters_snapshot).get("parameters", {})
        corrections = _correction_counts(run.predictions, target, source != target)
        material = {
            "target": target, "source": source, "method": artifact.method.value,
            "support": support, "raw": raw, "calibrated": calibrated,
            "reasons": reasons, "corrections": corrections,
        }
        result.append(TargetQualityEvidence(
            target, source, source != target, artifact.method.value, len(parameters),
            support["sample_count"], support["positive_count"], support["negative_count"],
            Decimal(support["positive_count"])/Decimal(support["sample_count"]),
            len(set(raw)), len(set(calibrated)), (min(raw), max(raw)), _quantiles(raw),
            (min(calibrated), max(calibrated)), _quantiles(calibrated), len(bins),
            len(populated), min(populated, default=0), max(populated, default=0), ece, mce,
            brier_before, brier_after, loss_before, loss_after,
            metrics.get((source, "CALIBRATED", "calibration_slope")),
            metrics.get((source, "CALIBRATED", "calibration_intercept")),
            _roc_auc(
                raw,
                tuple(
                    dict(training.load_training_example(item.training_example_id).labels)[source]
                    for item in run.predictions
                ),
            ),
            _fraction(calibrated, lambda v: v == policy.extreme_minimum),
            _fraction(calibrated, lambda v: v == policy.extreme_maximum),
            _fraction(calibrated, lambda v: v < Decimal("0.01")),
            _fraction(calibrated, lambda v: v > Decimal("0.99")),
            _fraction(adjustments, lambda v: v > Decimal("0.10")),
            _fraction(adjustments, lambda v: v > Decimal("0.25")),
            max(adjustments), corrections[0], corrections[1], corrections[2],
            "CALIBRATION_SUPPORT_ACCEPTABLE" if not reasons else "CALIBRATION_SUPPORT_INSUFFICIENT",
            tuple(reasons), sha256_fingerprint(material),
        ))
    return tuple(result)


def _traces(calibration_set, raw_probabilities, evidence, policy):
    artifacts = {item.target_identity: item for item in calibration_set.target_artifacts}
    raw = {item.target.value: item.probability for item in raw_probabilities.ordered_probabilities}
    calibrators = {
        name: CalibratorSerializer().deserialize(json.loads(artifacts[name].fitted_parameters_snapshot))
        for name in FITTED_TARGETS
    }
    unbounded = {name: calibrators[name].calibrate(raw[name]) for name in FITTED_TARGETS}
    bounded = {name: min(policy.extreme_maximum, max(policy.extreme_minimum, value)) for name, value in unbounded.items()}
    simplex = _bounded_simplex(tuple(bounded[name] for name in ("HOME_WIN", "DRAW", "AWAY_WIN")), policy.extreme_minimum)
    totals = _decreasing_pava(tuple(bounded[name] for name in ("OVER_1_5", "OVER_2_5", "OVER_3_5")))
    finals = {
        "HOME_WIN": simplex[0], "DRAW": simplex[1], "AWAY_WIN": simplex[2],
        "OVER_1_5": totals[0], "UNDER_1_5": Decimal(1)-totals[0],
        "OVER_2_5": totals[1], "UNDER_2_5": Decimal(1)-totals[1],
        "OVER_3_5": totals[2], "UNDER_3_5": Decimal(1)-totals[2],
        "BTTS_YES": bounded["BTTS_YES"], "BTTS_NO": Decimal(1)-bounded["BTTS_YES"],
    }
    support = {item.target: item for item in evidence}
    result = []
    for target in TARGET_ORDER:
        item = support[target]
        source = item.fitted_source_target
        derived = target != source
        before = Decimal(1)-unbounded[source] if derived else unbounded[source]
        after_clamp = Decimal(1)-bounded[source] if derived else bounded[source]
        final = finals[target]
        source_input = raw[source]
        outside = source_input < item.raw_range[0] or source_input > item.raw_range[1]
        extreme = final in {policy.extreme_minimum, policy.extreme_maximum}
        unsupported = extreme and outside
        parameters = artifacts[source].fitted_parameters_snapshot
        material = {"target": target, "raw": raw[target], "source": source, "before": before, "after_clamp": after_clamp, "final": final, "outside": outside}
        result.append(CalibrationTrace(
            target, source, artifacts[source].method.value, raw[target], parameters,
            item.validation_count, item.positive_count, item.negative_count,
            item.unique_raw_probability_count, item.raw_range, before, after_clamp,
            final, final, derived, source in {"HOME_WIN", "DRAW", "AWAY_WIN"} and final != after_clamp,
            source.startswith("OVER_") and final != after_clamp, before != after_clamp,
            outside, abs(final-raw[target]),
            "CALIBRATION_EXTREME_UNSUPPORTED" if unsupported else "CALIBRATION_EXTREME_SUPPORTED" if extreme else "NOT_EXTREME",
            sha256_fingerprint(material),
        ))
    return tuple(result)


def _distribution_shift(database, artifact, model_input, policy):
    split = SQLiteHistoricalDatasetSplitRepository(database, migrate=False)
    training = SQLiteHistoricalTrainingDatasetRepository(database, migrate=False)
    partitions = {}
    for partition in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST):
        partitions[partition] = tuple(split.stream_partition_examples(artifact.fold_id, partition))
    features = []
    matches = 0
    comparisons = 0
    for index, (name, live, missing, metadata, preprocessing) in enumerate(zip(
        model_input.ordered_feature_names, model_input.ordered_feature_values,
        model_input.missingness_mask, model_input.feature_metadata,
        artifact.preprocessing.features, strict=True,
    )):
        values = {
            p: tuple(
                _decimal(row.ordered_feature_vector[index])
                for row in rows
                if row.ordered_feature_vector[index] is not None
            )
            for p, rows in partitions.items()
        }
        combined = tuple(v for rows in values.values() for v in rows)
        live_decimal = None if live is None else _decimal(live)
        medians = {p: _median(rows) for p, rows in values.items()}
        dispersion = _median(tuple(abs(v-medians[Partition.TRAIN]) for v in values[Partition.TRAIN])) if values[Partition.TRAIN] else None
        percentile = None if missing or not combined else Decimal(sum(v <= live_decimal for v in combined))/Decimal(len(combined))
        distance = None
        if not missing and medians[Partition.TRAIN] is not None:
            scale = dispersion if dispersion and dispersion > 0 else Decimal(str(preprocessing.scaling_scale))
            distance = abs(live_decimal-medians[Partition.TRAIN])/scale if scale else Decimal(0)
        outside = bool(combined and not missing and (live_decimal < min(combined) or live_decimal > max(combined)))
        strong = outside or (distance is not None and distance > policy.strong_shift_distance)
        historical_missing = sum(row.missingness_mask[index] for rows in partitions.values() for row in rows)
        historical_total = sum(len(rows) for rows in partitions.values())
        modal_missing = historical_missing * 2 >= historical_total if historical_total else False
        comparisons += 1
        matches += missing == modal_missing
        features.append(FeatureShiftEvidence(
            name, live_decimal, missing, medians[Partition.TRAIN], medians[Partition.VALIDATION],
            medians[Partition.TEST], dispersion, percentile, distance,
            min(combined) if combined else None, max(combined) if combined else None,
            outside, missing, not bool(combined), strong,
        ))
    required_missing = sum(item.missing and meta.required_baseline for item, meta in zip(features, model_input.feature_metadata))
    optional_missing = sum(item.missing and not meta.required_baseline for item, meta in zip(features, model_input.feature_metadata))
    strong = tuple(item.feature_name for item in features if item.strongly_shifted)
    reasons = []
    if required_missing: reasons.append("REQUIRED_FEATURES_MISSING")
    if len(strong) > policy.maximum_strongly_shifted_features: reasons.append("LIVE_INPUT_STRONGLY_SHIFTED")
    status = DistributionShiftStatus.INELIGIBLE if required_missing else DistributionShiftStatus.REVIEW_REQUIRED if reasons or strong else DistributionShiftStatus.ACCEPTABLE
    material = {"features": features, "status": status, "reasons": reasons}
    return DistributionShiftReport(
        len(features), model_input.completeness_score, optional_missing, required_missing,
        sum(item.outside_historical_range for item in features), len(strong),
        sum(item.imputed for item in features), Decimal(matches)/Decimal(comparisons),
        status, strong, tuple(features), tuple(reasons), sha256_fingerprint(material),
    )


def _prob(values, target):
    return next(item.probability for item in values.ordered_probabilities if item.target.value == target)


def _quantiles(values):
    ordered = sorted(values)
    return tuple((name, ordered[round((len(ordered)-1)*point)]) for name, point in (("p01", .01), ("p05", .05), ("p25", .25), ("p50", .5), ("p75", .75), ("p95", .95), ("p99", .99)))


def _fraction(values, predicate):
    return Decimal(sum(predicate(value) for value in values))/Decimal(len(values))


def _roc_auc(probabilities, labels):
    positives = tuple(p for p, y in zip(probabilities, labels) if y == 1)
    negatives = tuple(p for p, y in zip(probabilities, labels) if y == 0)
    if not positives or not negatives:
        return None
    wins = sum(
        (
            Decimal(1)
            if positive > negative
            else Decimal("0.5")
            if positive == negative
            else Decimal(0)
        )
        for positive in positives
        for negative in negatives
    )
    return wins / Decimal(len(positives) * len(negatives))


def _correction_counts(predictions, target, complement):
    monotonic = simplex = 0
    for item in predictions:
        mono = json.loads(item.monotonicity_adjustment_snapshot)
        recon = json.loads(item.reconciliation_snapshot)
        if target.startswith(("OVER_", "UNDER_")) and mono.get("affected"): monotonic += 1
        if target in {"HOME_WIN", "DRAW", "AWAY_WIN"} and Decimal(str(recon.get("maximum_adjustment", 0))) > 0: simplex += 1
    return monotonic, len(predictions) if complement else 0, simplex


def _median(values):
    return Decimal(str(median(values))) if values else None


def _decimal(value):
    if isinstance(value, bool):
        return Decimal(int(value))
    return Decimal(str(value))


def _source_mode(snapshot):
    try:
        value = json.loads(snapshot)
    except json.JSONDecodeError:
        return "UNKNOWN"
    text = json.dumps(value, sort_keys=True)
    return "CONTROLLED_SYNTHETIC" if "CONTROLLED_SYNTHETIC" in text else "UNVERIFIED_OR_REAL"
