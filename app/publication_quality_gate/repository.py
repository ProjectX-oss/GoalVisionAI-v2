import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.database import Database, MigrationManager
from app.quality_gate import QualityGateStatus
from app.risk_management import RiskAssessmentDecision

from .models import (
    ConfidenceLevel,
    ExposureDecision,
    FindingSeverity,
    GateFinding,
    GateReason,
    OfficialQualityGateEvaluation,
)


@runtime_checkable
class QualityGateEvaluationRepository(Protocol):
    def append(
        self,
        evaluation: OfficialQualityGateEvaluation,
    ) -> OfficialQualityGateEvaluation: ...

    def get(self, evaluation_id: str) -> OfficialQualityGateEvaluation | None: ...


class SQLiteQualityGateEvaluationRepository:
    """Insert-once storage keyed by deterministic immutable candidate state."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append(
        self,
        evaluation: OfficialQualityGateEvaluation,
    ) -> OfficialQualityGateEvaluation:
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT OR IGNORE INTO official_quality_gate_evaluations (
                        evaluation_id, prediction_id, input_fingerprint,
                        final_decision, ordered_reason_codes,
                        internal_explanations, findings, policy_version,
                        model_version, raw_probability,
                        calibrated_probability, decimal_odds,
                        supplied_expected_value, recomputed_expected_value,
                        confidence, prediction_timestamp, kickoff_timestamp,
                        evaluated_at, normalized_input, risk_result,
                        exposure_result
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?
                    )
                    """,
                    _values(evaluation),
                )
        except sqlite3.DatabaseError as exc:
            raise ValueError("Quality Gate evaluation could not be stored.") from exc
        stored = self.get(evaluation.evaluation_id)
        if stored is None:
            raise ValueError("Quality Gate evaluation was not stored.")
        if stored != evaluation:
            raise ValueError("Stored Quality Gate evaluation conflicts with input.")
        return stored

    def get(self, evaluation_id: str) -> OfficialQualityGateEvaluation | None:
        if not evaluation_id.strip():
            raise ValueError("Evaluation ID must not be empty.")
        row = self._connection.execute(
            """
            SELECT * FROM official_quality_gate_evaluations
            WHERE evaluation_id = ?
            """,
            (evaluation_id,),
        ).fetchone()
        return _from_row(row) if row is not None else None

    def history_for_prediction(
        self,
        prediction_id: str,
    ) -> tuple[OfficialQualityGateEvaluation, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM official_quality_gate_evaluations
            WHERE prediction_id = ?
            ORDER BY evaluated_at, evaluation_id
            """,
            (prediction_id,),
        ).fetchall()
        return tuple(_from_row(row) for row in rows)


def _values(evaluation: OfficialQualityGateEvaluation) -> tuple[object, ...]:
    return (
        evaluation.evaluation_id,
        evaluation.prediction_id,
        evaluation.input_fingerprint,
        evaluation.final_decision.value,
        _json([item.value for item in evaluation.ordered_reason_codes]),
        _json(list(evaluation.internal_explanations)),
        _json([
            {
                "reason": item.reason.value,
                "severity": item.severity.value,
                "explanation": item.explanation,
            }
            for item in evaluation.findings
        ]),
        evaluation.policy_version,
        evaluation.model_version,
        str(evaluation.raw_probability),
        _decimal(evaluation.calibrated_probability),
        str(evaluation.decimal_odds),
        _decimal(evaluation.supplied_expected_value),
        _decimal(evaluation.recomputed_expected_value),
        evaluation.confidence.value,
        evaluation.prediction_timestamp.isoformat(),
        evaluation.kickoff_timestamp.isoformat(),
        evaluation.evaluated_at.isoformat(),
        _json([list(item) for item in evaluation.normalized_input]),
        evaluation.risk_result.value,
        evaluation.exposure_result.value,
    )


def _from_row(row: sqlite3.Row) -> OfficialQualityGateEvaluation:
    findings = tuple(
        GateFinding(
            reason=GateReason(item["reason"]),
            severity=FindingSeverity(item["severity"]),
            explanation=item["explanation"],
        )
        for item in json.loads(row["findings"])
    )
    return OfficialQualityGateEvaluation(
        evaluation_id=row["evaluation_id"],
        prediction_id=row["prediction_id"],
        final_decision=QualityGateStatus(row["final_decision"]),
        ordered_reason_codes=tuple(
            GateReason(item) for item in json.loads(row["ordered_reason_codes"])
        ),
        internal_explanations=tuple(json.loads(row["internal_explanations"])),
        findings=findings,
        policy_version=row["policy_version"],
        model_version=row["model_version"],
        raw_probability=Decimal(row["raw_probability"]),
        calibrated_probability=_decimal_or_none(row["calibrated_probability"]),
        decimal_odds=Decimal(row["decimal_odds"]),
        supplied_expected_value=_decimal_or_none(row["supplied_expected_value"]),
        recomputed_expected_value=_decimal_or_none(row["recomputed_expected_value"]),
        confidence=ConfidenceLevel(row["confidence"]),
        prediction_timestamp=datetime.fromisoformat(row["prediction_timestamp"]),
        kickoff_timestamp=datetime.fromisoformat(row["kickoff_timestamp"]),
        evaluated_at=datetime.fromisoformat(row["evaluated_at"]),
        input_fingerprint=row["input_fingerprint"],
        normalized_input=tuple(
            (item[0], item[1]) for item in json.loads(row["normalized_input"])
        ),
        risk_result=RiskAssessmentDecision(row["risk_result"]),
        exposure_result=ExposureDecision(row["exposure_result"]),
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal_or_none(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None
