import hashlib
import json
import sqlite3
from dataclasses import asdict, replace
from datetime import datetime
from decimal import Decimal

from app.calibration import CalibratorSerializer
from app.database import Database, MigrationManager

from .models import (
    ArtifactMetricSnapshot,
    CalibrationArtifact,
    CalibrationArtifactConflictError,
    CalibrationArtifactIdentity,
    CalibrationArtifactMetadata,
    CalibrationArtifactStatus,
    CalibrationRegistrationResult,
    CalibrationRegistryQuery,
    CalibrationStatusTransition,
    CalibrationValidationResult,
    InvalidCalibrationStatusTransition,
)


_ALLOWED_TRANSITIONS = {
    CalibrationArtifactStatus.CANDIDATE: {
        CalibrationArtifactStatus.VALIDATED,
        CalibrationArtifactStatus.REJECTED,
        CalibrationArtifactStatus.RETIRED,
    },
    CalibrationArtifactStatus.VALIDATED: {
        CalibrationArtifactStatus.SHADOW,
        CalibrationArtifactStatus.RETIRED,
    },
    CalibrationArtifactStatus.SHADOW: {CalibrationArtifactStatus.RETIRED},
    CalibrationArtifactStatus.RETIRED: set(),
    CalibrationArtifactStatus.REJECTED: set(),
}


class CalibrationRegistryService:
    """Insert-once calibrator registry; status changes are append-only events."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._database = database
        self._serializer = CalibratorSerializer()
        if migrate:
            MigrationManager(database.connection).migrate()

    @staticmethod
    def artifact_from_calibrator(
        calibrator,
        *,
        created_at: datetime,
        status_reason: str,
        validation_metrics: ArtifactMetricSnapshot | None = None,
        parent_artifact_id: str | None = None,
        method_version: str | None = None,
    ) -> CalibrationArtifact:
        serializer = CalibratorSerializer()
        payload = serializer.serialize(calibrator)
        serialized = _stable_json(payload)
        metadata = calibrator.metadata
        diagnostics = getattr(calibrator, "diagnostics", None)
        training = ArtifactMetricSnapshot(
            brier_score=(
                diagnostics.training_brier_score if diagnostics else Decimal("0")
            ),
            log_loss=(
                None
                if diagnostics and diagnostics.training_log_loss.is_infinite()
                else diagnostics.training_log_loss
                if diagnostics
                else Decimal("0")
            ),
            log_loss_is_infinite=bool(
                diagnostics and diagnostics.training_log_loss.is_infinite()
            ),
            expected_calibration_error=(
                diagnostics.training_expected_calibration_error
                if diagnostics
                else Decimal("0")
            ),
            maximum_calibration_error=(
                diagnostics.training_maximum_calibration_error
                if diagnostics
                else Decimal("0")
            ),
        )
        parameters = _stable_json(payload["parameters"])
        scope = metadata.scope
        identity_payload = {
            "method": metadata.method_name,
            "method_version": method_version or metadata.version,
            "configuration_fingerprint": metadata.configuration_fingerprint,
            "scope": payload["metadata"]["scope"],
            "model_version": metadata.model_version,
            "training_cutoff": metadata.training_cutoff.isoformat(),
            "parameters": json.loads(parameters),
        }
        artifact_id = "cal-" + hashlib.sha256(
            _stable_json(identity_payload).encode("utf-8")
        ).hexdigest()
        diagnostic_items = (
            tuple(
                sorted(
                    (
                        key,
                        str(value) if isinstance(value, Decimal) else value,
                    )
                    for key, value in asdict(diagnostics).items()
                )
            )
            if diagnostics
            else ()
        )
        return CalibrationArtifact(
            identity=CalibrationArtifactIdentity(
                artifact_id=artifact_id,
                method=metadata.method_name,
                method_version=method_version or metadata.version,
                configuration_fingerprint=metadata.configuration_fingerprint,
            ),
            serialized_calibrator=serialized,
            metadata=CalibrationArtifactMetadata(
                created_at=created_at,
                fitted_at=metadata.fitted_at,
                training_window_start=metadata.training_window.start,
                training_window_end=metadata.training_window.end,
                training_cutoff=metadata.training_cutoff,
                observation_count=metadata.observation_count,
                positive_count=metadata.positive_outcome_count,
                negative_count=metadata.negative_outcome_count,
                competition_scope=scope.competition,
                market_scope=scope.market,
                odds_band_scope=scope.odds_band,
                model_version_scope=metadata.model_version,
                calibration_scope=scope,
                fit_version=metadata.version,
                parent_artifact_id=parent_artifact_id,
            ),
            fitting_diagnostics=diagnostic_items,
            training_metrics=training,
            validation_metrics=validation_metrics,
            status=CalibrationArtifactStatus.CANDIDATE,
            status_reason=status_reason,
        )

    def register(self, artifact: CalibrationArtifact) -> CalibrationRegistrationResult:
        validation = self.validate_serialized_artifact(artifact)
        if not validation.valid:
            raise CalibrationArtifactConflictError(validation.safe_message)
        values = _artifact_values(artifact)
        try:
            with self._database.connection:
                cursor = self._database.connection.execute(
                    """
                    INSERT OR IGNORE INTO calibration_artifacts (
                        artifact_id, method, method_version, serialized_calibrator,
                        serialized_parameters_fingerprint, configuration_fingerprint,
                        created_at, fitted_at, training_window_start,
                        training_window_end, training_cutoff, observation_count,
                        positive_count, negative_count, competition_scope,
                        market_scope, odds_band_scope, model_version_scope,
                        calibration_scope, fit_version, fitting_diagnostics,
                        training_metrics, validation_metrics, status,
                        status_reason, parent_artifact_id
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    values,
                )
        except sqlite3.DatabaseError as exc:
            raise CalibrationArtifactConflictError(
                "Calibration artifact could not be registered safely."
            ) from exc
        stored = self.get(artifact.artifact_id)
        if stored is None:
            stored = self._get_equivalent(artifact)
        if stored is None:
            raise CalibrationArtifactConflictError("Artifact registration was not persisted.")
        if stored != artifact:
            raise CalibrationArtifactConflictError(
                "Equivalent artifact already exists with different immutable metadata."
            )
        return CalibrationRegistrationResult(stored, cursor.rowcount == 1)

    def get(self, artifact_id: str) -> CalibrationArtifact | None:
        row = self._database.connection.execute(
            "SELECT * FROM calibration_artifacts WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        return _artifact_from_row(row) if row else None

    def query(
        self, query: CalibrationRegistryQuery = CalibrationRegistryQuery()
    ) -> tuple[CalibrationArtifact, ...]:
        clauses: list[str] = []
        values: list[object] = []
        for column, value in (
            ("method", query.method),
            ("competition_scope", query.competition_scope),
            ("market_scope", query.market_scope),
            ("model_version_scope", query.model_version_scope),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        if query.cutoff_at_or_before is not None:
            clauses.append("julianday(training_cutoff) <= julianday(?)")
            values.append(query.cutoff_at_or_before.isoformat())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._database.connection.execute(
            f"""
            SELECT * FROM calibration_artifacts
            {where}
            ORDER BY julianday(fitted_at), julianday(training_cutoff), artifact_id
            """,
            tuple(values),
        ).fetchall()
        artifacts = tuple(
            self._with_current_status(_artifact_from_row(row)) for row in rows
        )
        if query.status is not None:
            artifacts = tuple(
                artifact
                for artifact in artifacts
                if self.current_status(artifact.artifact_id) is query.status
            )
        return artifacts

    def latest(
        self, query: CalibrationRegistryQuery
    ) -> CalibrationArtifact | None:
        matches = self.query(query)
        return matches[-1] if matches else None

    def validate_serialized_artifact(
        self, artifact: CalibrationArtifact
    ) -> CalibrationValidationResult:
        try:
            payload = json.loads(artifact.serialized_calibrator)
            calibrator = self._serializer.deserialize(payload)
            canonical = _stable_json(self._serializer.serialize(calibrator))
            if canonical != artifact.serialized_calibrator:
                raise ValueError("Serialized calibrator is not canonical.")
            if calibrator.metadata.method_name != artifact.identity.method:
                raise ValueError("Artifact method conflicts with serialized calibrator.")
            if (
                calibrator.metadata.configuration_fingerprint
                != artifact.identity.configuration_fingerprint
            ):
                raise ValueError("Configuration fingerprint mismatch.")
            if calibrator.metadata.training_cutoff != artifact.metadata.training_cutoff:
                raise ValueError("Training cutoff mismatch.")
            return CalibrationValidationResult(
                True,
                artifact.artifact_id,
                artifact.identity.method,
                payload.get("serialization_version"),
                "VALID",
                "Serialized calibrator is valid.",
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return CalibrationValidationResult(
                False,
                artifact.artifact_id,
                artifact.identity.method,
                None,
                "INVALID_SERIALIZED_ARTIFACT",
                str(exc)[:300] or "Serialized calibrator is invalid.",
            )

    def deserialize(self, artifact_id: str):
        artifact = self.get(artifact_id)
        if artifact is None:
            raise KeyError("Calibration artifact does not exist.")
        return self._serializer.deserialize(json.loads(artifact.serialized_calibrator))

    def transition_status(
        self,
        artifact_id: str,
        new_status: CalibrationArtifactStatus,
        *,
        reason: str,
        changed_at: datetime,
        actor_source: str,
    ) -> CalibrationStatusTransition:
        artifact = self.get(artifact_id)
        if artifact is None:
            raise KeyError("Calibration artifact does not exist.")
        previous = self.current_status(artifact_id)
        history = self.status_history(artifact_id)
        if history and changed_at <= history[-1].changed_at:
            raise InvalidCalibrationStatusTransition(
                "Status changes must be strictly chronological."
            )
        if new_status not in _ALLOWED_TRANSITIONS[previous]:
            raise InvalidCalibrationStatusTransition(
                f"Transition {previous.value} -> {new_status.value} is not allowed."
            )
        seed = "|".join(
            (
                artifact_id,
                previous.value,
                new_status.value,
                reason,
                changed_at.isoformat(),
                actor_source,
            )
        )
        transition = CalibrationStatusTransition(
            "cst-" + hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            artifact_id,
            previous,
            new_status,
            reason,
            changed_at,
            actor_source,
        )
        with self._database.connection:
            self._database.connection.execute(
                """
                INSERT OR IGNORE INTO calibration_artifact_status_history (
                    transition_id, artifact_id, previous_status, new_status,
                    reason, changed_at, actor_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.transition_id,
                    transition.artifact_id,
                    transition.previous_status.value,
                    transition.new_status.value,
                    transition.reason,
                    transition.changed_at.isoformat(),
                    transition.actor_source,
                ),
            )
        return transition

    def status_history(
        self, artifact_id: str
    ) -> tuple[CalibrationStatusTransition, ...]:
        rows = self._database.connection.execute(
            """
            SELECT * FROM calibration_artifact_status_history
            WHERE artifact_id = ?
            ORDER BY changed_at, transition_id
            """,
            (artifact_id,),
        ).fetchall()
        return tuple(
            CalibrationStatusTransition(
                row["transition_id"],
                row["artifact_id"],
                CalibrationArtifactStatus(row["previous_status"]),
                CalibrationArtifactStatus(row["new_status"]),
                row["reason"],
                datetime.fromisoformat(row["changed_at"]),
                row["actor_source"],
            )
            for row in rows
        )

    def current_status(self, artifact_id: str) -> CalibrationArtifactStatus:
        artifact = self.get(artifact_id)
        if artifact is None:
            raise KeyError("Calibration artifact does not exist.")
        history = self.status_history(artifact_id)
        return history[-1].new_status if history else artifact.status

    def _with_current_status(
        self, artifact: CalibrationArtifact
    ) -> CalibrationArtifact:
        history = self.status_history(artifact.artifact_id)
        if not history:
            return artifact
        latest = history[-1]
        return replace(
            artifact,
            status=latest.new_status,
            status_reason=latest.reason,
        )

    def _get_equivalent(
        self, artifact: CalibrationArtifact
    ) -> CalibrationArtifact | None:
        row = self._database.connection.execute(
            """
            SELECT * FROM calibration_artifacts
            WHERE method = ? AND method_version = ?
              AND configuration_fingerprint = ?
              AND competition_scope IS ?
              AND market_scope IS ?
              AND odds_band_scope IS ?
              AND model_version_scope IS ?
              AND calibration_scope = ?
              AND training_cutoff = ?
              AND serialized_parameters_fingerprint = ?
            """,
            (
                artifact.identity.method,
                artifact.identity.method_version,
                artifact.identity.configuration_fingerprint,
                artifact.metadata.competition_scope,
                artifact.metadata.market_scope,
                artifact.metadata.odds_band_scope,
                artifact.metadata.model_version_scope,
                _scope_json(artifact.metadata.calibration_scope),
                artifact.metadata.training_cutoff.isoformat(),
                _parameters_fingerprint(artifact.serialized_calibrator),
            ),
        ).fetchone()
        return _artifact_from_row(row) if row else None


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _parameters_fingerprint(serialized: str) -> str:
    parameters = json.loads(serialized)["parameters"]
    return hashlib.sha256(_stable_json(parameters).encode("utf-8")).hexdigest()


def _scope_json(scope) -> str:
    return _stable_json(
        {
            "kind": scope.kind.value,
            "competition": scope.competition,
            "market": scope.market,
            "odds_band": scope.odds_band,
        }
    )


def _metric_json(metric: ArtifactMetricSnapshot | None) -> str | None:
    if metric is None:
        return None
    return _stable_json(
        {
            "brier_score": str(metric.brier_score),
            "log_loss": str(metric.log_loss) if metric.log_loss is not None else None,
            "log_loss_is_infinite": metric.log_loss_is_infinite,
            "expected_calibration_error": str(metric.expected_calibration_error),
            "maximum_calibration_error": str(metric.maximum_calibration_error),
        }
    )


def _metric_from_json(value: str | None) -> ArtifactMetricSnapshot | None:
    if value is None:
        return None
    item = json.loads(value)
    return ArtifactMetricSnapshot(
        Decimal(item["brier_score"]),
        Decimal(item["log_loss"]) if item["log_loss"] is not None else None,
        item["log_loss_is_infinite"],
        Decimal(item["expected_calibration_error"]),
        Decimal(item["maximum_calibration_error"]),
    )


def _artifact_values(artifact: CalibrationArtifact) -> tuple[object, ...]:
    metadata = artifact.metadata
    return (
        artifact.artifact_id,
        artifact.identity.method,
        artifact.identity.method_version,
        artifact.serialized_calibrator,
        _parameters_fingerprint(artifact.serialized_calibrator),
        artifact.identity.configuration_fingerprint,
        metadata.created_at.isoformat(),
        metadata.fitted_at.isoformat(),
        metadata.training_window_start.isoformat(),
        metadata.training_window_end.isoformat(),
        metadata.training_cutoff.isoformat(),
        metadata.observation_count,
        metadata.positive_count,
        metadata.negative_count,
        metadata.competition_scope,
        metadata.market_scope,
        metadata.odds_band_scope,
        metadata.model_version_scope,
        _scope_json(metadata.calibration_scope),
        metadata.fit_version,
        _stable_json(dict(artifact.fitting_diagnostics)),
        _metric_json(artifact.training_metrics),
        _metric_json(artifact.validation_metrics),
        artifact.status.value,
        artifact.status_reason,
        metadata.parent_artifact_id,
    )


def _artifact_from_row(row: sqlite3.Row) -> CalibrationArtifact:
    from app.calibration import CalibrationScope, CalibrationScopeKind

    scope_data = json.loads(row["calibration_scope"])
    return CalibrationArtifact(
        CalibrationArtifactIdentity(
            row["artifact_id"],
            row["method"],
            row["method_version"],
            row["configuration_fingerprint"],
        ),
        row["serialized_calibrator"],
        CalibrationArtifactMetadata(
            datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["fitted_at"]),
            datetime.fromisoformat(row["training_window_start"]),
            datetime.fromisoformat(row["training_window_end"]),
            datetime.fromisoformat(row["training_cutoff"]),
            row["observation_count"],
            row["positive_count"],
            row["negative_count"],
            row["competition_scope"],
            row["market_scope"],
            row["odds_band_scope"],
            row["model_version_scope"],
            CalibrationScope(
                CalibrationScopeKind(scope_data["kind"]),
                scope_data["competition"],
                scope_data["market"],
                scope_data["odds_band"],
            ),
            row["fit_version"],
            row["parent_artifact_id"],
        ),
        tuple(sorted(json.loads(row["fitting_diagnostics"]).items())),
        _metric_from_json(row["training_metrics"]),
        _metric_from_json(row["validation_metrics"]),
        CalibrationArtifactStatus(row["status"]),
        row["status_reason"],
    )
