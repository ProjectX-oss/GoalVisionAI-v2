"""Append-only persistence for monitoring evidence."""

from __future__ import annotations

import json
from typing import Any

from app.database import Database, MigrationManager
from app.real_match_lab_analysis.fingerprint import canonical_json

from .models import MonitoringConflictError, PersistOutcome


class SQLiteMonitoringRepository:
    def __init__(self, database: Database, *, migrate: bool = True) -> None:
        self.connection = database.connection
        if migrate:
            MigrationManager(self.connection).migrate()

    def append_snapshot(self, value: dict[str, Any]) -> PersistOutcome:
        return self._append(
            "forward_test_monitoring_snapshots", "snapshot_id", value["snapshot_id"],
            "snapshot_fingerprint", value["snapshot_fingerprint"],
            ("snapshot_id", "requested_cutoff_utc", "generated_at_utc", "policy_id", "policy_version",
             "source_database_identity", "source_fingerprint", "snapshot_fingerprint", "snapshot_json"),
            (value["snapshot_id"], value["requested_cutoff_utc"], value["generated_at_utc"], value["policy_id"],
             value["policy_version"], value["source_database_identity"], value["source_fingerprint"],
             value["snapshot_fingerprint"], canonical_json(value)),
        )

    def append_report(self, value: dict[str, Any]) -> PersistOutcome:
        return self._append(
            "forward_test_monitoring_reports", "request_fingerprint", value["request_fingerprint"],
            "report_fingerprint", value["report_fingerprint"],
            ("report_id", "report_kind", "period_start_utc", "period_end_utc", "generated_at_utc", "policy_id",
             "policy_version", "snapshot_id", "request_fingerprint", "report_fingerprint", "report_json"),
            (value["report_id"], value["report_kind"], value.get("period_start_utc"), value["period_end_utc"],
             value["generated_at_utc"], value["policy_id"], value["policy_version"], value["snapshot_id"],
             value["request_fingerprint"], value["report_fingerprint"], canonical_json(value)),
        )

    def append_audit(self, value: dict[str, Any]) -> PersistOutcome:
        existing = self.connection.execute(
            "SELECT * FROM forward_test_monitoring_audits WHERE observation_id=? AND cutoff_utc=?",
            (value["observation_id"], value["cutoff_utc"]),
        ).fetchone()
        if existing:
            if existing["audit_fingerprint"] != value["audit_fingerprint"]:
                raise MonitoringConflictError("MONITORING_AUDIT_REPLAY_CONFLICT")
            return PersistOutcome(existing["audit_id"], True, existing["audit_fingerprint"])
        columns = ("audit_id", "observation_id", "cutoff_utc", "status", "audit_fingerprint", "audit_json", "created_at_utc")
        values = (value["audit_id"], value["observation_id"], value["cutoff_utc"], value["status"],
                  value["audit_fingerprint"], canonical_json(value), value["created_at_utc"])
        return self._insert("forward_test_monitoring_audits", columns, values, value["audit_id"], value["audit_fingerprint"])

    def append_export(self, value: dict[str, Any]) -> PersistOutcome:
        existing = self.connection.execute("SELECT * FROM forward_test_monitoring_exports WHERE report_id=? AND export_format=? AND relative_path=?", (value["report_id"], value["export_format"], value["relative_path"])).fetchone()
        if existing:
            if existing["export_fingerprint"] != value["export_fingerprint"]: raise MonitoringConflictError("MONITORING_EXPORT_REPLAY_CONFLICT")
            return PersistOutcome(existing["export_id"], True, existing["export_fingerprint"])
        columns=("export_id","report_id","export_format","content_fingerprint","relative_path","created_at_utc","export_fingerprint","export_json")
        values=(value["export_id"],value["report_id"],value["export_format"],value["content_fingerprint"],value["relative_path"],value["created_at_utc"],value["export_fingerprint"],canonical_json(value))
        return self._insert("forward_test_monitoring_exports",columns,values,value["export_id"],value["export_fingerprint"])

    def report(self, report_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT report_json FROM forward_test_monitoring_reports WHERE report_id=?", (report_id,)).fetchone()
        if row is None:
            raise ValueError("Monitoring report not found.")
        return json.loads(row[0])

    def _append(self, table, key_column, key, fingerprint_column, value_fingerprint, columns, values):
        row = self.connection.execute(f"SELECT * FROM {table} WHERE {key_column}=?", (key,)).fetchone()
        if row:
            if row[fingerprint_column] != value_fingerprint:
                raise MonitoringConflictError(f"{table.upper()}_REPLAY_CONFLICT")
            return PersistOutcome(row[0], True, value_fingerprint)
        return self._insert(table, columns, values, values[0], value_fingerprint)

    def _insert(self, table, columns, values, identifier, value_fingerprint):
        placeholders = ",".join("?" for _ in columns)
        with self.connection:
            self.connection.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", values)
        return PersistOutcome(identifier, False, value_fingerprint)
