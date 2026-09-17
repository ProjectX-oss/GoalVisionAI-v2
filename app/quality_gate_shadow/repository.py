import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from app.calibration import CalibrationScope, CalibrationScopeKind
from app.database import Database, MigrationManager
from app.quality_gate import (
    CheckStatus,
    ComboSelection,
    EvidenceAssessment,
    EvidenceCategory,
    EvidenceStatus,
    ProbabilitySource,
    PublicationCandidate,
    PublicationType,
    QualityGateCheck,
    QualityGateCheckResult,
    QualityGateContext,
    QualityGateStatus,
    RejectionReason,
    ReviewReason,
)
from app.results import ResolutionStatus

from .models import (
    ShadowEvaluationError,
    ShadowEvaluationRecord,
    ShadowEvaluationStage,
    ShadowSettlementFacts,
)


@runtime_checkable
class ShadowEvaluationRepository(Protocol):
    def insert_once(
        self,
        record: ShadowEvaluationRecord,
    ) -> tuple[ShadowEvaluationRecord, bool]: ...

    def get(self, shadow_evaluation_id: str) -> ShadowEvaluationRecord | None: ...

    def get_by_identity(
        self,
        prediction_id: str,
        policy_version: str,
        stage: ShadowEvaluationStage,
    ) -> ShadowEvaluationRecord | None: ...

    def by_prediction(self, prediction_id: str) -> tuple[ShadowEvaluationRecord, ...]: ...

    def by_fixture(self, fixture_id: int) -> tuple[ShadowEvaluationRecord, ...]: ...

    def query(
        self,
        start_at: datetime,
        end_at: datetime,
        policy_version: str | None = None,
        gate_status: QualityGateStatus | None = None,
        actually_published: bool | None = None,
    ) -> tuple[ShadowEvaluationRecord, ...]: ...

    def attach_settlement(
        self,
        shadow_evaluation_id: str,
        facts: ShadowSettlementFacts,
    ) -> ShadowEvaluationRecord: ...

    def insert_error_once(
        self,
        error: ShadowEvaluationError,
    ) -> tuple[ShadowEvaluationError, bool]: ...

    def query_errors(
        self,
        start_at: datetime,
        end_at: datetime,
        policy_version: str | None = None,
    ) -> tuple[ShadowEvaluationError, ...]: ...


class SQLiteShadowEvaluationRepository:
    """SQLite audit adapter; all decision logic remains in domain services."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._database = database
        if migrate:
            MigrationManager(database.connection).migrate()

    def insert_once(
        self,
        record: ShadowEvaluationRecord,
    ) -> tuple[ShadowEvaluationRecord, bool]:
        values = self._record_values(record)
        with self._database.connection:
            cursor = self._database.connection.execute(
                """
                INSERT OR IGNORE INTO quality_gate_shadow_evaluations (
                    shadow_evaluation_id, prediction_id, fixture_id,
                    product_scope, evaluation_stage, policy_version,
                    evaluation_timestamp, candidate_snapshot, context_snapshot,
                    gate_status, check_results, rejection_reasons,
                    review_reasons,
                    evaluated_probability, probability_source,
                    calculated_expected_value, market_disagreement,
                    actually_published, actual_publication_timestamp,
                    actual_offered_odds, settlement_outcome,
                    eventual_profit_loss_units, settled_at, created_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                values,
            )
        stored = self.get_by_identity(
            record.prediction_id,
            record.policy_version,
            record.stage,
        )
        if stored is None:
            raise RuntimeError("Shadow insert did not produce an audit record.")
        return stored, cursor.rowcount == 1

    def get(self, shadow_evaluation_id: str) -> ShadowEvaluationRecord | None:
        row = self._database.connection.execute(
            """
            SELECT * FROM quality_gate_shadow_evaluations
            WHERE shadow_evaluation_id = ?
            """,
            (shadow_evaluation_id,),
        ).fetchone()
        return self._to_record(row) if row is not None else None

    def get_by_identity(
        self,
        prediction_id: str,
        policy_version: str,
        stage: ShadowEvaluationStage,
    ) -> ShadowEvaluationRecord | None:
        row = self._database.connection.execute(
            """
            SELECT * FROM quality_gate_shadow_evaluations
            WHERE prediction_id = ? AND policy_version = ?
                AND evaluation_stage = ?
            """,
            (prediction_id, policy_version, stage.value),
        ).fetchone()
        return self._to_record(row) if row is not None else None

    def by_prediction(
        self,
        prediction_id: str,
    ) -> tuple[ShadowEvaluationRecord, ...]:
        return self._rows(
            """
            SELECT * FROM quality_gate_shadow_evaluations
            WHERE prediction_id = ?
            ORDER BY evaluation_timestamp, evaluation_stage, shadow_evaluation_id
            """,
            (prediction_id,),
        )

    def by_fixture(self, fixture_id: int) -> tuple[ShadowEvaluationRecord, ...]:
        return self._rows(
            """
            SELECT * FROM quality_gate_shadow_evaluations
            WHERE fixture_id = ?
            ORDER BY evaluation_timestamp, prediction_id, evaluation_stage
            """,
            (fixture_id,),
        )

    def query(
        self,
        start_at: datetime,
        end_at: datetime,
        policy_version: str | None = None,
        gate_status: QualityGateStatus | None = None,
        actually_published: bool | None = None,
    ) -> tuple[ShadowEvaluationRecord, ...]:
        clauses = [
            "julianday(evaluation_timestamp) >= julianday(?)",
            "julianday(evaluation_timestamp) < julianday(?)",
        ]
        parameters: list[object] = [start_at.isoformat(), end_at.isoformat()]
        if policy_version is not None:
            clauses.append("policy_version = ?")
            parameters.append(policy_version)
        if gate_status is not None:
            clauses.append("gate_status = ?")
            parameters.append(gate_status.value)
        if actually_published is not None:
            clauses.append("actually_published = ?")
            parameters.append(int(actually_published))
        sql = f"""
            SELECT * FROM quality_gate_shadow_evaluations
            WHERE {' AND '.join(clauses)}
            ORDER BY evaluation_timestamp, prediction_id, evaluation_stage
        """
        return self._rows(sql, tuple(parameters))

    def attach_settlement(
        self,
        shadow_evaluation_id: str,
        facts: ShadowSettlementFacts,
    ) -> ShadowEvaluationRecord:
        existing = self.get(shadow_evaluation_id)
        if existing is None:
            raise KeyError("Shadow evaluation does not exist.")
        current = (
            existing.settlement_outcome,
            existing.eventual_profit_loss_units,
            existing.settled_at,
        )
        incoming = (facts.outcome, facts.profit_loss_units, facts.settled_at)
        if current == incoming:
            return existing
        if any(value is not None for value in current):
            raise ValueError("Conflicting shadow settlement facts.")
        with self._database.connection:
            self._database.connection.execute(
                """
                UPDATE quality_gate_shadow_evaluations
                SET settlement_outcome = ?, eventual_profit_loss_units = ?,
                    settled_at = ?
                WHERE shadow_evaluation_id = ? AND settlement_outcome IS NULL
                """,
                (
                    facts.outcome.value,
                    str(facts.profit_loss_units),
                    facts.settled_at.isoformat(),
                    shadow_evaluation_id,
                ),
            )
        updated = self.get(shadow_evaluation_id)
        if updated is None:
            raise RuntimeError("Shadow settlement update lost its record.")
        updated_facts = (
            updated.settlement_outcome,
            updated.eventual_profit_loss_units,
            updated.settled_at,
        )
        if updated_facts != incoming:
            raise ValueError("Conflicting shadow settlement facts.")
        return updated

    def insert_error_once(
        self,
        error: ShadowEvaluationError,
    ) -> tuple[ShadowEvaluationError, bool]:
        with self._database.connection:
            cursor = self._database.connection.execute(
                """
                INSERT OR IGNORE INTO quality_gate_shadow_errors (
                    shadow_evaluation_id, prediction_id, evaluation_stage,
                    policy_version, error_type, safe_message, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    error.shadow_evaluation_id,
                    error.prediction_id,
                    error.stage.value,
                    error.policy_version,
                    error.error_type,
                    error.safe_message,
                    error.occurred_at.isoformat(),
                ),
            )
        row = self._database.connection.execute(
            """
            SELECT * FROM quality_gate_shadow_errors
            WHERE prediction_id = ? AND policy_version = ?
                AND evaluation_stage = ?
            """,
            (error.prediction_id, error.policy_version, error.stage.value),
        ).fetchone()
        if row is None:
            raise RuntimeError("Shadow error insert did not produce an audit row.")
        return self._to_error(row), cursor.rowcount == 1

    def query_errors(
        self,
        start_at: datetime,
        end_at: datetime,
        policy_version: str | None = None,
    ) -> tuple[ShadowEvaluationError, ...]:
        clauses = [
            "julianday(occurred_at) >= julianday(?)",
            "julianday(occurred_at) < julianday(?)",
        ]
        parameters: list[object] = [start_at.isoformat(), end_at.isoformat()]
        if policy_version is not None:
            clauses.append("policy_version = ?")
            parameters.append(policy_version)
        rows = self._database.connection.execute(
            f"""
            SELECT * FROM quality_gate_shadow_errors
            WHERE {' AND '.join(clauses)}
            ORDER BY occurred_at, prediction_id, evaluation_stage
            """,
            tuple(parameters),
        ).fetchall()
        return tuple(self._to_error(row) for row in rows)

    def _rows(
        self,
        sql: str,
        parameters: tuple[object, ...],
    ) -> tuple[ShadowEvaluationRecord, ...]:
        rows = self._database.connection.execute(sql, parameters).fetchall()
        return tuple(self._to_record(row) for row in rows)

    @staticmethod
    def _record_values(record: ShadowEvaluationRecord) -> tuple[object, ...]:
        return (
            record.shadow_evaluation_id,
            record.prediction_id,
            record.fixture_id,
            record.product_scope,
            record.stage.value,
            record.policy_version,
            record.evaluation_timestamp.isoformat(),
            _candidate_json(record.candidate_snapshot),
            _context_json(record.context_snapshot),
            record.gate_status.value,
            _check_results_json(record.ordered_check_results),
            json.dumps([item.value for item in record.rejection_reasons]),
            json.dumps([item.value for item in record.review_reasons]),
            _decimal_text(record.evaluated_probability),
            record.probability_source.value if record.probability_source else None,
            _decimal_text(record.calculated_expected_value),
            _decimal_text(record.market_disagreement),
            int(record.actually_published),
            _datetime_text(record.actual_publication_timestamp),
            _decimal_text(record.actual_offered_odds),
            record.settlement_outcome.value if record.settlement_outcome else None,
            _decimal_text(record.eventual_profit_loss_units),
            _datetime_text(record.settled_at),
            record.created_at.isoformat(),
        )

    @staticmethod
    def _to_record(row: sqlite3.Row) -> ShadowEvaluationRecord:
        return ShadowEvaluationRecord(
            shadow_evaluation_id=row["shadow_evaluation_id"],
            prediction_id=row["prediction_id"],
            fixture_id=row["fixture_id"],
            product_scope=row["product_scope"],
            stage=ShadowEvaluationStage(row["evaluation_stage"]),
            candidate_snapshot=_candidate_from_json(row["candidate_snapshot"]),
            context_snapshot=_context_from_json(row["context_snapshot"]),
            policy_version=row["policy_version"],
            evaluation_timestamp=datetime.fromisoformat(row["evaluation_timestamp"]),
            gate_status=QualityGateStatus(row["gate_status"]),
            ordered_check_results=_check_results_from_json(row["check_results"]),
            rejection_reasons=tuple(
                RejectionReason(value) for value in json.loads(row["rejection_reasons"])
            ),
            review_reasons=tuple(
                ReviewReason(value) for value in json.loads(row["review_reasons"])
            ),
            evaluated_probability=_decimal(row["evaluated_probability"]),
            probability_source=(
                ProbabilitySource(row["probability_source"])
                if row["probability_source"] is not None
                else None
            ),
            calculated_expected_value=_decimal(row["calculated_expected_value"]),
            market_disagreement=_decimal(row["market_disagreement"]),
            actually_published=bool(row["actually_published"]),
            actual_publication_timestamp=_datetime(
                row["actual_publication_timestamp"]
            ),
            actual_offered_odds=_decimal(row["actual_offered_odds"]),
            settlement_outcome=(
                ResolutionStatus(row["settlement_outcome"])
                if row["settlement_outcome"] is not None
                else None
            ),
            eventual_profit_loss_units=_decimal(
                row["eventual_profit_loss_units"]
            ),
            settled_at=_datetime(row["settled_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _to_error(row: sqlite3.Row) -> ShadowEvaluationError:
        return ShadowEvaluationError(
            shadow_evaluation_id=row["shadow_evaluation_id"],
            prediction_id=row["prediction_id"],
            stage=ShadowEvaluationStage(row["evaluation_stage"]),
            policy_version=row["policy_version"],
            error_type=row["error_type"],
            safe_message=row["safe_message"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
        )


def _candidate_json(candidate: PublicationCandidate) -> str:
    values = {
        "prediction_id": candidate.prediction_id,
        "fixture_id": candidate.fixture_id,
        "competition": candidate.competition,
        "kickoff_time": candidate.kickoff_time.isoformat(),
        "prediction_timestamp": candidate.prediction_timestamp.isoformat(),
        "market": candidate.market,
        "selection": candidate.selection,
        "raw_probability": str(candidate.raw_probability),
        "offered_odds": str(candidate.offered_odds),
        "odds_timestamp": candidate.odds_timestamp.isoformat(),
        "calibrated_probability": _decimal_text(candidate.calibrated_probability),
        "reference_odds": _decimal_text(candidate.reference_odds),
        "expected_value": _decimal_text(candidate.expected_value),
        "model_version": candidate.model_version,
        "calibration_scope": (
            {
                "kind": candidate.calibration_scope.kind.value,
                "competition": candidate.calibration_scope.competition,
                "market": candidate.calibration_scope.market,
                "odds_band": candidate.calibration_scope.odds_band,
            }
            if candidate.calibration_scope
            else None
        ),
        "calibration_method": candidate.calibration_method,
        "calibration_sample_size": candidate.calibration_sample_size,
        "calibration_fit_timestamp": _datetime_text(
            candidate.calibration_fit_timestamp
        ),
        "calibration_training_cutoff": _datetime_text(
            candidate.calibration_training_cutoff
        ),
        "confidence_score": _decimal_text(candidate.confidence_score),
        "uncertainty_score": _decimal_text(candidate.uncertainty_score),
        "publication_type": candidate.publication_type.value,
        "combo_selections": [
            {
                "market": item.market,
                "selection": item.selection,
                "offered_odds": str(item.offered_odds),
                "confidence_score": str(item.confidence_score),
            }
            for item in candidate.combo_selections
        ],
        "product_scope": candidate.product_scope,
    }
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


def _candidate_from_json(value: str) -> PublicationCandidate:
    data = json.loads(value)
    return PublicationCandidate(
        prediction_id=data["prediction_id"],
        fixture_id=data["fixture_id"],
        competition=data["competition"],
        kickoff_time=datetime.fromisoformat(data["kickoff_time"]),
        prediction_timestamp=datetime.fromisoformat(data["prediction_timestamp"]),
        market=data["market"],
        selection=data["selection"],
        raw_probability=Decimal(data["raw_probability"]),
        offered_odds=Decimal(data["offered_odds"]),
        odds_timestamp=datetime.fromisoformat(data["odds_timestamp"]),
        calibrated_probability=_decimal(data["calibrated_probability"]),
        reference_odds=_decimal(data["reference_odds"]),
        expected_value=_decimal(data["expected_value"]),
        model_version=data["model_version"],
        calibration_scope=_calibration_scope(data["calibration_scope"]),
        calibration_method=data["calibration_method"],
        calibration_sample_size=data["calibration_sample_size"],
        calibration_fit_timestamp=_datetime(data["calibration_fit_timestamp"]),
        calibration_training_cutoff=_datetime(
            data["calibration_training_cutoff"]
        ),
        confidence_score=_decimal(data["confidence_score"]),
        uncertainty_score=_decimal(data["uncertainty_score"]),
        publication_type=PublicationType(data["publication_type"]),
        combo_selections=tuple(
            ComboSelection(
                market=item["market"],
                selection=item["selection"],
                offered_odds=Decimal(item["offered_odds"]),
                confidence_score=Decimal(item["confidence_score"]),
            )
            for item in data["combo_selections"]
        ),
        product_scope=data["product_scope"],
    )


def _context_json(context: QualityGateContext) -> str:
    values = {
        "evaluation_timestamp": context.evaluation_timestamp.isoformat(),
        "data_completeness_status": context.data_completeness_status.value,
        "data_freshness_status": context.data_freshness_status.value,
        "lineup_status": context.lineup_status.value,
        "injury_data_status": context.injury_data_status.value,
        "market_consensus_probability": _decimal_text(
            context.market_consensus_probability
        ),
        "market_disagreement": _decimal_text(context.market_disagreement),
        "current_exposure": str(context.current_exposure),
        "daily_exposure": str(context.daily_exposure),
        "competition_exposure": str(context.competition_exposure),
        "correlated_exposure": str(context.correlated_exposure),
        "sample_size": context.sample_size,
        "calibration_sample_size": context.calibration_sample_size,
        "evidence": [
            {"category": item.category.value, "status": item.status.value}
            for item in context.evidence
        ],
    }
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


def _context_from_json(value: str) -> QualityGateContext:
    data = json.loads(value)
    return QualityGateContext(
        evaluation_timestamp=datetime.fromisoformat(data["evaluation_timestamp"]),
        data_completeness_status=EvidenceStatus(data["data_completeness_status"]),
        data_freshness_status=EvidenceStatus(data["data_freshness_status"]),
        lineup_status=EvidenceStatus(data["lineup_status"]),
        injury_data_status=EvidenceStatus(data["injury_data_status"]),
        market_consensus_probability=_decimal(
            data["market_consensus_probability"]
        ),
        market_disagreement=_decimal(data["market_disagreement"]),
        current_exposure=Decimal(data["current_exposure"]),
        daily_exposure=Decimal(data["daily_exposure"]),
        competition_exposure=Decimal(data["competition_exposure"]),
        correlated_exposure=Decimal(data["correlated_exposure"]),
        sample_size=data["sample_size"],
        calibration_sample_size=data["calibration_sample_size"],
        evidence=tuple(
            EvidenceAssessment(
                category=EvidenceCategory(item["category"]),
                status=EvidenceStatus(item["status"]),
            )
            for item in data["evidence"]
        ),
    )


def _check_results_json(
    checks: tuple[QualityGateCheckResult, ...],
) -> str:
    values = [
        {
            "check": item.check.value,
            "status": item.status.value,
            "rejection_reasons": [
                reason.value for reason in item.rejection_reasons
            ],
            "review_reasons": [
                reason.value for reason in item.review_reasons
            ],
            "evaluated_probability": _decimal_text(
                item.evaluated_probability
            ),
            "probability_source": (
                item.probability_source.value
                if item.probability_source
                else None
            ),
            "expected_value": _decimal_text(item.expected_value),
            "market_disagreement": _decimal_text(item.market_disagreement),
        }
        for item in checks
    ]
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


def _check_results_from_json(
    value: str,
) -> tuple[QualityGateCheckResult, ...]:
    return tuple(
        QualityGateCheckResult(
            check=QualityGateCheck(item["check"]),
            status=CheckStatus(item["status"]),
            rejection_reasons=tuple(
                RejectionReason(reason)
                for reason in item["rejection_reasons"]
            ),
            review_reasons=tuple(
                ReviewReason(reason) for reason in item["review_reasons"]
            ),
            evaluated_probability=_decimal(item["evaluated_probability"]),
            probability_source=(
                ProbabilitySource(item["probability_source"])
                if item["probability_source"] is not None
                else None
            ),
            expected_value=_decimal(item["expected_value"]),
            market_disagreement=_decimal(item["market_disagreement"]),
        )
        for item in json.loads(value)
    )


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _calibration_scope(value: dict | None) -> CalibrationScope | None:
    if value is None:
        return None
    return CalibrationScope(
        kind=CalibrationScopeKind(value["kind"]),
        competition=value["competition"],
        market=value["market"],
        odds_band=value["odds_band"],
    )
