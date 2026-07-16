import hashlib
from datetime import datetime

from .drift import DriftDetectionService
from .models import (
    MonitoringObservation,
    MonitoringPolicy,
    MonitoringRun,
    MonitoringRunStatus,
    MonitoringWindow,
)
from .persistence import SQLiteMonitoringRepository, monitoring_snapshot_json
from .reporting import MonitoringReportService


class ModelMonitoringService:
    def __init__(
        self,
        repository: SQLiteMonitoringRepository,
        *,
        reports: MonitoringReportService | None = None,
        drift: DriftDetectionService | None = None,
    ) -> None:
        self._repository = repository
        self._reports = reports or MonitoringReportService()
        self._drift = drift or DriftDetectionService()

    def run_once(
        self,
        *,
        baseline_observations: tuple[MonitoringObservation, ...],
        current_observations: tuple[MonitoringObservation, ...],
        baseline_window: MonitoringWindow,
        current_window: MonitoringWindow,
        policy: MonitoringPolicy,
        scope: str,
        artifact_id: str | None,
        started_at: datetime,
        completed_at: datetime,
    ) -> MonitoringRun:
        seed = "|".join(
            (
                policy.version,
                scope,
                artifact_id or "",
                baseline_window.start_at.isoformat(),
                baseline_window.end_at.isoformat(),
                current_window.start_at.isoformat(),
                current_window.end_at.isoformat(),
                started_at.isoformat(),
            )
        )
        run_id = "monitor-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()
        try:
            baseline = self._reports.build(
                baseline_observations,
                report_window=baseline_window,
                generated_for=completed_at,
            )
            current = self._reports.build(
                current_observations,
                report_window=current_window,
                generated_for=completed_at,
            )
            findings = self._drift.compare(
                baseline,
                current,
                baseline_observations,
                current_observations,
                policy=policy,
                scope=scope,
                artifact_id=artifact_id,
            )
            insufficient = any(
                item.finding_type.value == "SAMPLE_TOO_SMALL" for item in findings
            )
            run = MonitoringRun(
                run_id,
                policy.version,
                baseline_window,
                current_window,
                scope,
                artifact_id,
                started_at,
                completed_at,
                len(baseline_observations),
                len(current_observations),
                (
                    ("baseline_report", monitoring_snapshot_json(baseline)),
                    ("current_report", monitoring_snapshot_json(current)),
                ),
                findings,
                (
                    MonitoringRunStatus.INSUFFICIENT_DATA
                    if insufficient
                    else MonitoringRunStatus.COMPLETED
                ),
            )
        except Exception as exc:
            run = MonitoringRun(
                run_id,
                policy.version,
                baseline_window,
                current_window,
                scope,
                artifact_id,
                started_at,
                completed_at,
                len(baseline_observations),
                len(current_observations),
                (),
                (),
                MonitoringRunStatus.FAILED,
                type(exc).__name__ if type(exc).__name__.isidentifier() else "MonitoringError",
                "Monitoring run failed safely.",
            )
        stored, _ = self._repository.insert_run(run)
        for finding in stored.findings:
            alert = self._repository.alert_for_finding(
                stored.run_id,
                finding,
                threshold_version=policy.version,
                created_at=completed_at,
            )
            self._repository.insert_alert(alert)
        return stored
