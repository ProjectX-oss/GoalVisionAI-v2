from dataclasses import dataclass, replace
from decimal import Decimal

from app.calibration import (
    CalibrationObservation,
    CalibrationReportService,
    CalibratorSerializer,
)
from app.calibration_registry import CalibrationArtifact

from .models import SafeDecimal


@dataclass(frozen=True, slots=True)
class ArtifactComparisonResult:
    artifact_id: str
    method: str
    scope: str
    observation_count: int
    brier_score: Decimal
    log_loss: SafeDecimal
    expected_calibration_error: Decimal
    maximum_calibration_error: Decimal
    ranking: int
    tie_reason: str | None
    eligible: bool


@dataclass(frozen=True, slots=True)
class ArtifactComparisonReport:
    ranking_metric: str
    results: tuple[ArtifactComparisonResult, ...]


class CalibrationArtifactComparisonService:
    def __init__(self) -> None:
        self._serializer = CalibratorSerializer()
        self._reports = CalibrationReportService()

    def compare(
        self,
        artifacts: tuple[CalibrationArtifact, ...],
        validation: tuple[CalibrationObservation, ...],
        *,
        ranking_metric: str = "BRIER_SCORE",
        tie_tolerance: Decimal = Decimal("0.000000001"),
    ) -> ArtifactComparisonReport:
        if not validation:
            raise ValueError("Artifact comparison requires validation observations.")
        evaluations = []
        for artifact in artifacts:
            calibrator = self._serializer.deserialize(
                __import__("json").loads(artifact.serialized_calibrator)
            )
            calibrated = tuple(
                replace(item, raw_probability=calibrator.calibrate(item.raw_probability))
                for item in validation
            )
            report = self._reports.evaluate(calibrated)
            metric = {
                "BRIER_SCORE": report.brier_score,
                "LOG_LOSS": report.log_loss,
                "EXPECTED_CALIBRATION_ERROR": report.expected_calibration_error,
            }[ranking_metric]
            evaluations.append((artifact, report, metric))
        ordered = sorted(
            evaluations,
            key=lambda item: (
                item[2],
                {"identity": 0, "platt": 1, "isotonic": 2}.get(
                    item[0].identity.method, 99
                ),
                item[0].artifact_id,
            ),
        )
        results = []
        for index, (artifact, report, metric) in enumerate(ordered, 1):
            tied = index > 1 and (
                metric == Decimal("Infinity")
                and ordered[index - 2][2] == Decimal("Infinity")
                or metric.is_finite()
                and ordered[index - 2][2].is_finite()
                and metric - ordered[index - 2][2] <= tie_tolerance
            )
            results.append(
                ArtifactComparisonResult(
                    artifact.artifact_id,
                    artifact.identity.method,
                    artifact.metadata.calibration_scope.kind.value,
                    len(validation),
                    report.brier_score,
                    SafeDecimal.from_decimal(report.log_loss),
                    report.expected_calibration_error,
                    report.maximum_calibration_error,
                    index,
                    "CONSERVATIVE_METHOD_ORDER" if tied else None,
                    True,
                )
            )
        return ArtifactComparisonReport(ranking_metric, tuple(results))
