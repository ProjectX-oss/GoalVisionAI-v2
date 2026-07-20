import json
import sqlite3
from datetime import datetime
from decimal import Decimal

from app.calibration import CalibrationBinReport
from app.database import Database, MigrationManager

from .config import CalibrationMethod
from .models import (
    CalibrationMetricSummary,
    ConfidenceHistogramBin,
    ProbabilityCalibrationReport,
)


class CalibrationRunAlreadyExistsError(RuntimeError):
    """Raised when a caller attempts to overwrite an existing run ID."""


class SQLiteProbabilityCalibrationRepository:
    """Append-only SQLite audit storage for probability calibration runs."""

    def __init__(self, database: Database) -> None:
        self._database = database
        MigrationManager(database.connection).migrate()

    def append(self, report: ProbabilityCalibrationReport) -> None:
        summary = report.metric_summary
        try:
            with self._database.connection:
                self._database.connection.execute(
                    """
                    INSERT INTO probability_calibration_history (
                        calibration_run_id, created_at, model_version,
                        calibration_version, calibration_method,
                        raw_probability, calibrated_probability, delta,
                        observation_count, brier_score, log_loss,
                        expected_calibration_error, maximum_calibration_error,
                        reliability_bins, confidence_histogram
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.calibration_run_id,
                        report.timestamp.isoformat(),
                        report.model_version,
                        report.calibration_version,
                        report.calibration_method.value,
                        str(report.raw_probability),
                        str(report.calibrated_probability),
                        str(report.delta),
                        summary.observation_count,
                        str(summary.brier_score),
                        str(summary.log_loss),
                        str(summary.expected_calibration_error),
                        str(summary.maximum_calibration_error),
                        _bins_json(summary.reliability_bins),
                        _histogram_json(report.confidence_histogram),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            existing = self._database.connection.execute(
                """
                SELECT 1 FROM probability_calibration_history
                WHERE calibration_run_id = ?
                """,
                (report.calibration_run_id,),
            ).fetchone()
            if existing is not None:
                raise CalibrationRunAlreadyExistsError(
                    f"Calibration run already exists: {report.calibration_run_id}"
                ) from exc
            raise

    def get(self, calibration_run_id: str) -> ProbabilityCalibrationReport | None:
        row = self._database.connection.execute(
            """
            SELECT * FROM probability_calibration_history
            WHERE calibration_run_id = ?
            """,
            (calibration_run_id,),
        ).fetchone()
        return _report_from_row(row) if row is not None else None

    def history_for_model(
        self,
        model_version: str,
    ) -> tuple[ProbabilityCalibrationReport, ...]:
        rows = self._database.connection.execute(
            """
            SELECT * FROM probability_calibration_history
            WHERE model_version = ?
            ORDER BY created_at, calibration_run_id
            """,
            (model_version,),
        ).fetchall()
        return tuple(_report_from_row(row) for row in rows)


def _bins_json(values: tuple[CalibrationBinReport, ...]) -> str:
    return json.dumps(
        [
            {
                "index": item.index,
                "lower_bound": str(item.lower_bound),
                "upper_bound": str(item.upper_bound),
                "includes_upper_bound": item.includes_upper_bound,
                "observation_count": item.observation_count,
                "mean_predicted_probability": _optional_decimal(
                    item.mean_predicted_probability
                ),
                "observed_success_rate": _optional_decimal(
                    item.observed_success_rate
                ),
                "calibration_gap": _optional_decimal(item.calibration_gap),
            }
            for item in values
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _histogram_json(values: tuple[ConfidenceHistogramBin, ...]) -> str:
    return json.dumps(
        [
            {
                "index": item.index,
                "lower_bound": str(item.lower_bound),
                "upper_bound": str(item.upper_bound),
                "includes_upper_bound": item.includes_upper_bound,
                "observation_count": item.observation_count,
                "observation_fraction": str(item.observation_fraction),
            }
            for item in values
        ],
        sort_keys=True,
        separators=(",", ":"),
    )


def _optional_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _report_from_row(row: sqlite3.Row) -> ProbabilityCalibrationReport:
    bins = tuple(
        CalibrationBinReport(
            index=item["index"],
            lower_bound=Decimal(item["lower_bound"]),
            upper_bound=Decimal(item["upper_bound"]),
            includes_upper_bound=item["includes_upper_bound"],
            observation_count=item["observation_count"],
            mean_predicted_probability=_decimal_or_none(
                item["mean_predicted_probability"]
            ),
            observed_success_rate=_decimal_or_none(item["observed_success_rate"]),
            calibration_gap=_decimal_or_none(item["calibration_gap"]),
        )
        for item in json.loads(row["reliability_bins"])
    )
    histogram = tuple(
        ConfidenceHistogramBin(
            index=item["index"],
            lower_bound=Decimal(item["lower_bound"]),
            upper_bound=Decimal(item["upper_bound"]),
            includes_upper_bound=item["includes_upper_bound"],
            observation_count=item["observation_count"],
            observation_fraction=Decimal(item["observation_fraction"]),
        )
        for item in json.loads(row["confidence_histogram"])
    )
    summary = CalibrationMetricSummary(
        observation_count=row["observation_count"],
        brier_score=Decimal(row["brier_score"]),
        log_loss=Decimal(row["log_loss"]),
        expected_calibration_error=Decimal(row["expected_calibration_error"]),
        maximum_calibration_error=Decimal(row["maximum_calibration_error"]),
        reliability_bins=bins,
    )
    raw = Decimal(row["raw_probability"])
    calibrated = Decimal(row["calibrated_probability"])
    return ProbabilityCalibrationReport(
        calibration_run_id=row["calibration_run_id"],
        raw_probability=raw,
        calibrated_probability=calibrated,
        delta=Decimal(row["delta"]),
        calibration_method=CalibrationMethod(row["calibration_method"]),
        metric_summary=summary,
        confidence_histogram=histogram,
        timestamp=datetime.fromisoformat(row["created_at"]),
        model_version=row["model_version"],
        calibration_version=row["calibration_version"],
    )


def _decimal_or_none(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None
