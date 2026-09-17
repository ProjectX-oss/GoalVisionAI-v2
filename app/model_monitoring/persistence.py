import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.database import Database, MigrationManager

from .models import (
    AlertSeverity,
    DriftFinding,
    DriftFindingType,
    MonitoringAlert,
    MonitoringRun,
    MonitoringRunStatus,
    MonitoringWindow,
    MonitoringWindowKind,
    SafeDecimal,
)


class SQLiteMonitoringRepository:
    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._database = database
        if migrate:
            MigrationManager(database.connection).migrate()

    def insert_run(self, run: MonitoringRun) -> tuple[MonitoringRun, bool]:
        with self._database.connection:
            cursor = self._database.connection.execute(
                """
                INSERT OR IGNORE INTO model_monitoring_runs (
                    run_id, policy_version, baseline_window, current_window,
                    scope, artifact_id, started_at, completed_at,
                    baseline_observation_count, current_observation_count,
                    report_snapshot, findings, run_status,
                    safe_error_type, safe_error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.policy_version,
                    _json(run.baseline_window),
                    _json(run.current_window),
                    run.scope,
                    run.artifact_id,
                    run.started_at.isoformat(),
                    run.completed_at.isoformat(),
                    run.baseline_observation_count,
                    run.current_observation_count,
                    _json(dict(run.report_snapshot)),
                    _json(run.findings),
                    run.status.value,
                    run.safe_error_type,
                    run.safe_error_message,
                ),
            )
        stored = self.get_run(run.run_id)
        if stored is None or stored != run:
            raise ValueError("Monitoring run identity conflicts with immutable data.")
        return stored, cursor.rowcount == 1

    def get_run(self, run_id: str) -> MonitoringRun | None:
        row = self._database.connection.execute(
            "SELECT * FROM model_monitoring_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        return MonitoringRun(
            run_id=row["run_id"],
            policy_version=row["policy_version"],
            baseline_window=_window(row["baseline_window"]),
            current_window=_window(row["current_window"]),
            scope=row["scope"],
            artifact_id=row["artifact_id"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]),
            baseline_observation_count=row["baseline_observation_count"],
            current_observation_count=row["current_observation_count"],
            report_snapshot=tuple(sorted(json.loads(row["report_snapshot"]).items())),
            findings=tuple(_finding(item) for item in json.loads(row["findings"])),
            status=MonitoringRunStatus(row["run_status"]),
            safe_error_type=row["safe_error_type"],
            safe_error_message=row["safe_error_message"],
        )

    def insert_alert(
        self, alert: MonitoringAlert
    ) -> tuple[MonitoringAlert, bool]:
        with self._database.connection:
            cursor = self._database.connection.execute(
                """
                INSERT OR IGNORE INTO model_monitoring_alerts (
                    alert_id, run_id, scope, finding_type, metric,
                    threshold_version, severity, reason_code, created_at,
                    finding_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.alert_id,
                    alert.run_id,
                    alert.scope,
                    alert.finding_type.value,
                    alert.metric,
                    alert.threshold_version,
                    alert.severity.value,
                    alert.reason_code,
                    alert.created_at.isoformat(),
                    _json(alert.finding),
                ),
            )
        stored = self.get_alert(alert.alert_id)
        if stored is None or stored != alert:
            raise ValueError("Monitoring alert identity conflicts with immutable data.")
        return stored, cursor.rowcount == 1

    def get_alert(self, alert_id: str) -> MonitoringAlert | None:
        row = self._database.connection.execute(
            "SELECT * FROM model_monitoring_alerts WHERE alert_id = ?", (alert_id,)
        ).fetchone()
        if row is None:
            return None
        finding = _finding(json.loads(row["finding_snapshot"]))
        return MonitoringAlert(
            row["alert_id"],
            row["run_id"],
            row["scope"],
            DriftFindingType(row["finding_type"]),
            row["metric"],
            row["threshold_version"],
            AlertSeverity(row["severity"]),
            row["reason_code"],
            datetime.fromisoformat(row["created_at"]),
            finding,
        )

    @staticmethod
    def alert_for_finding(
        run_id: str,
        finding: DriftFinding,
        *,
        threshold_version: str,
        created_at: datetime,
    ) -> MonitoringAlert:
        seed = "|".join(
            (
                run_id,
                finding.scope,
                finding.finding_type.value,
                finding.metric,
                threshold_version,
            )
        )
        return MonitoringAlert(
            "alert-" + hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            run_id,
            finding.scope,
            finding.finding_type,
            finding.metric,
            threshold_version,
            finding.severity,
            finding.reason_code,
            created_at,
            finding,
        )


def monitoring_snapshot_json(value: object) -> str:
    """Returns the same deterministic, non-finite-safe JSON used in persistence."""
    return _json(value)


def _json(value: object) -> str:
    return json.dumps(
        value,
        default=_encode,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _encode(value: object) -> object:
    if isinstance(value, Decimal):
        return {"__decimal__": str(value)}
    if isinstance(value, datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}.")


def _decode(value: object) -> object:
    if isinstance(value, dict) and set(value) == {"__decimal__"}:
        return Decimal(value["__decimal__"])
    if isinstance(value, dict) and set(value) == {"__datetime__"}:
        return datetime.fromisoformat(value["__datetime__"])
    return value


def _loads(value: str):
    return json.loads(value, object_hook=_decode)


def _window(value: str) -> MonitoringWindow:
    item = _loads(value)
    return MonitoringWindow(
        MonitoringWindowKind(item["kind"]),
        item["start_at"],
        item["end_at"],
        item["observation_limit"],
    )


def _safe(item: dict | None) -> SafeDecimal | None:
    if item is None:
        return None
    value = item["finite_value"]
    if isinstance(value, dict):
        value = _decode(value)
    return SafeDecimal(value, item["is_positive_infinity"])


def _finding(item: dict) -> DriftFinding:
    def decimal_value(value):
        if isinstance(value, dict):
            return _decode(value)
        return value

    return DriftFinding(
        DriftFindingType(item["finding_type"]),
        item["metric"],
        _safe(item["baseline_value"]),
        _safe(item["current_value"]),
        _safe(item["absolute_change"]),
        _safe(item["relative_change"]),
        decimal_value(item["configured_threshold"]),
        AlertSeverity(item["severity"]),
        item["baseline_sample_count"],
        item["current_sample_count"],
        item["scope"],
        item["reason_code"],
    )
