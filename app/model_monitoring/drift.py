from decimal import Decimal, localcontext

from .models import (
    AlertSeverity,
    DriftFinding,
    DriftFindingType,
    MetricDriftThreshold,
    MonitoringObservation,
    MonitoringPolicy,
    MonitoringReport,
    SafeDecimal,
    ThresholdComparison,
)


ZERO = Decimal("0")
DEFAULT_THRESHOLDS = (
    ("brier", MetricDriftThreshold(True, Decimal("0.02"), Decimal("0.05"))),
    ("log_loss", MetricDriftThreshold(True, Decimal("0.05"), Decimal("0.15"))),
    ("ece", MetricDriftThreshold(True, Decimal("0.02"), Decimal("0.05"))),
    ("roi", MetricDriftThreshold(True, Decimal("0.05"), Decimal("0.15"))),
    ("clv", MetricDriftThreshold(True, Decimal("0.02"), Decimal("0.05"))),
    ("hit_rate", MetricDriftThreshold(True, Decimal("0.05"), Decimal("0.10"))),
    ("drawdown", MetricDriftThreshold(True, Decimal("2"), Decimal("5"))),
    ("class_balance", MetricDriftThreshold(True, Decimal("0.10"), Decimal("0.20"))),
    ("probability_psi", MetricDriftThreshold(True, Decimal("0.10"), Decimal("0.25"))),
    ("calibrated_probability_psi", MetricDriftThreshold(True, Decimal("0.10"), Decimal("0.25"))),
    ("calibration_bins", MetricDriftThreshold(True, Decimal("0.03"), Decimal("0.08"))),
    ("data_completeness", MetricDriftThreshold(True, Decimal("0.10"), Decimal("0.25"))),
)


class DriftDetectionService:
    """Descriptive threshold checks only; findings never state causality."""

    def compare(
        self,
        baseline: MonitoringReport,
        current: MonitoringReport,
        baseline_observations: tuple[MonitoringObservation, ...],
        current_observations: tuple[MonitoringObservation, ...],
        *,
        policy: MonitoringPolicy,
        scope: str,
        artifact_id: str | None = None,
    ) -> tuple[DriftFinding, ...]:
        if (
            not policy.allow_window_overlap
            and baseline.report_window.end_at > current.report_window.start_at
        ):
            raise ValueError("Monitoring baseline and current windows overlap.")
        if (
            baseline.observation_count < policy.minimum_observations
            or baseline.settled_count < policy.minimum_settled_observations
            or
            current.observation_count < policy.minimum_observations
            or current.settled_count < policy.minimum_settled_observations
        ):
            return (
                DriftFinding(
                    DriftFindingType.SAMPLE_TOO_SMALL,
                    "sample_size",
                    SafeDecimal(Decimal(baseline.settled_count)),
                    SafeDecimal(Decimal(current.settled_count)),
                    SafeDecimal(
                        Decimal(current.settled_count - baseline.settled_count)
                    ),
                    None,
                    Decimal(policy.minimum_settled_observations),
                    AlertSeverity.INFO,
                    baseline.settled_count,
                    current.settled_count,
                    scope,
                    (
                        "BASELINE_SAMPLE_BELOW_MINIMUM"
                        if (
                            baseline.observation_count < policy.minimum_observations
                            or baseline.settled_count
                            < policy.minimum_settled_observations
                        )
                        else "CURRENT_SAMPLE_BELOW_MINIMUM"
                    ),
                ),
            )
        thresholds = dict(DEFAULT_THRESHOLDS)
        thresholds.update(dict(policy.thresholds))
        for key, values in policy.competition_overrides:
            if scope == f"competition:{key}":
                thresholds.update(dict(values))
        for key, values in policy.market_overrides:
            if scope == f"market:{key}":
                thresholds.update(dict(values))
        if artifact_id:
            for key, values in policy.artifact_overrides:
                if key == artifact_id:
                    thresholds.update(dict(values))
        specifications = (
            (DriftFindingType.BRIER_DEGRADATION, "brier", baseline.raw_brier_score, current.raw_brier_score, 1),
            (DriftFindingType.LOG_LOSS_DEGRADATION, "log_loss", _safe_value(baseline.raw_log_loss), _safe_value(current.raw_log_loss), 1),
            (DriftFindingType.ECE_DEGRADATION, "ece", baseline.raw_ece, current.raw_ece, 1),
            (DriftFindingType.ROI_DEGRADATION, "roi", baseline.roi, current.roi, -1),
            (DriftFindingType.CLV_DEGRADATION, "clv", baseline.average_clv, current.average_clv, -1),
            (DriftFindingType.HIT_RATE_DEGRADATION, "hit_rate", baseline.hit_rate, current.hit_rate, -1),
            (DriftFindingType.DRAWDOWN_INCREASE, "drawdown", baseline.maximum_drawdown, current.maximum_drawdown, 1),
            (DriftFindingType.CLASS_BALANCE_SHIFT, "class_balance", baseline.hit_rate, current.hit_rate, 0),
            (
                DriftFindingType.PROBABILITY_DISTRIBUTION_SHIFT,
                "probability_psi",
                ZERO,
                self.population_stability_index(
                    tuple(item.raw_probability for item in baseline_observations),
                    tuple(item.raw_probability for item in current_observations),
                    policy.probability_bins,
                    policy.psi_smoothing,
                ),
                1,
            ),
            (
                DriftFindingType.CALIBRATION_BIN_DRIFT,
                "calibration_bins",
                ZERO,
                self.calibration_bin_drift(baseline, current),
                1,
            ),
            (
                DriftFindingType.DATA_COMPLETENESS_DEGRADATION,
                "data_completeness",
                baseline.data_completeness.settlement_fraction,
                current.data_completeness.settlement_fraction,
                -1,
            ),
        )
        if all(
            item.calibrated_probability is not None
            for item in baseline_observations + current_observations
        ) and baseline_observations and current_observations:
            specifications += (
                (
                    DriftFindingType.PROBABILITY_DISTRIBUTION_SHIFT,
                    "calibrated_probability_psi",
                    ZERO,
                    self.population_stability_index(
                        tuple(
                            item.calibrated_probability
                            for item in baseline_observations
                        ),
                        tuple(
                            item.calibrated_probability
                            for item in current_observations
                        ),
                        policy.probability_bins,
                        policy.psi_smoothing,
                    ),
                    1,
                ),
            )
        findings = []
        for finding_type, metric, before, after, direction in specifications:
            threshold = thresholds[metric]
            if not threshold.enabled or before is None or after is None:
                continue
            degradation = (
                abs(after - before)
                if direction == 0
                else (after - before) * Decimal(direction)
            )
            compared = (
                degradation
                if threshold.comparison is ThresholdComparison.ABSOLUTE
                else _relative(degradation, before)
            )
            if compared is None or compared < threshold.warning:
                continue
            severity = (
                AlertSeverity.CRITICAL
                if compared >= threshold.critical
                else AlertSeverity.WARNING
            )
            findings.append(
                DriftFinding(
                    finding_type,
                    metric,
                    SafeDecimal.from_decimal(before),
                    SafeDecimal.from_decimal(after),
                    SafeDecimal.from_decimal(after - before),
                    (
                        SafeDecimal.from_decimal((after - before) / abs(before))
                        if before != 0
                        else None
                    ),
                    (
                        threshold.critical
                        if severity is AlertSeverity.CRITICAL
                        else threshold.warning
                    ),
                    severity,
                    baseline.settled_count,
                    current.settled_count,
                    scope,
                    f"{metric.upper()}_{severity.value}_THRESHOLD_EXCEEDED",
                )
            )
        if artifact_id:
            brier = next(
                (
                    item
                    for item in findings
                    if item.finding_type is DriftFindingType.BRIER_DEGRADATION
                ),
                None,
            )
            if brier is not None:
                findings.append(
                    DriftFinding(
                        DriftFindingType.ARTIFACT_PERFORMANCE_DEGRADATION,
                        "artifact_brier",
                        brier.baseline_value,
                        brier.current_value,
                        brier.absolute_change,
                        brier.relative_change,
                        brier.configured_threshold,
                        brier.severity,
                        brier.baseline_sample_count,
                        brier.current_sample_count,
                        scope,
                        "ARTIFACT_BRIER_DEGRADATION_OBSERVED",
                    )
                )
        return tuple(sorted(findings, key=lambda item: (item.finding_type.value, item.metric)))

    @staticmethod
    def population_stability_index(
        baseline: tuple[Decimal, ...],
        current: tuple[Decimal, ...],
        bins: tuple[Decimal, ...],
        smoothing: Decimal,
    ) -> Decimal:
        """PSI=sum((c-b)*ln(c/b)); zero proportions use fixed epsilon smoothing."""
        if not baseline or not current:
            return ZERO
        with localcontext() as context:
            context.prec = 50
            total = ZERO
            for lower, upper in zip(bins, bins[1:]):
                final = upper == bins[-1]
                base_count = sum(
                    lower <= value <= upper if final else lower <= value < upper
                    for value in baseline
                )
                current_count = sum(
                    lower <= value <= upper if final else lower <= value < upper
                    for value in current
                )
                base_fraction = max(
                    Decimal(base_count) / Decimal(len(baseline)), smoothing
                )
                current_fraction = max(
                    Decimal(current_count) / Decimal(len(current)), smoothing
                )
                total += (
                    current_fraction - base_fraction
                ) * (current_fraction / base_fraction).ln()
            return total

    @staticmethod
    def calibration_bin_drift(
        baseline: MonitoringReport, current: MonitoringReport
    ) -> Decimal:
        """Current-count weighted gap change, preferring calibrated reliability bins."""
        baseline_bins = (
            baseline.calibrated_calibration_bins
            if (
                baseline.calibrated_calibration_bins is not None
                and current.calibrated_calibration_bins is not None
            )
            else baseline.raw_calibration_bins
        )
        current_bins = (
            current.calibrated_calibration_bins
            if (
                baseline.calibrated_calibration_bins is not None
                and current.calibrated_calibration_bins is not None
            )
            else current.raw_calibration_bins
        )
        total = sum(item.observation_count for item in current_bins)
        if not total:
            return ZERO
        changes = ZERO
        for before, after in zip(baseline_bins, current_bins):
            if before.calibration_gap is None or after.calibration_gap is None:
                continue
            changes += Decimal(after.observation_count) * abs(
                after.calibration_gap - before.calibration_gap
            )
        return changes / Decimal(total)


def _safe_value(value: SafeDecimal) -> Decimal | None:
    return value.finite_value


def _relative(change: Decimal, baseline: Decimal) -> Decimal | None:
    return change / abs(baseline) if baseline != 0 else None
