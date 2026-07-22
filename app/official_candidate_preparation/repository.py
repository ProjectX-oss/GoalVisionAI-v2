"""Append-only SQLite audit history for candidate preparation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.database import Database, MigrationManager
from app.match_data_snapshot import canonical_json
from app.official_prediction_candidate_registry import CandidateRegistrationStatus
from app.quality_gate import QualityGateStatus
from app.risk_management import (
    BankrollStateSnapshot,
    DrawdownState,
    ExposureAssessment,
    ExposurePosition,
    ExposureSnapshot,
    ExposureType,
    LossStreakState,
    RiskAssessmentDecision,
    RiskAssessmentPhase,
    RiskAuditRecord,
    RiskProductScope,
    RiskReason,
    RiskWarning,
    StakeBand,
    StakeRecommendation,
    StakeStars,
)

from .exceptions import (
    CandidatePreparationConflictError,
    CandidatePreparationPersistenceError,
)
from .models import (
    CandidatePreparationReason,
    CandidatePreparationStatus,
    OfficialCandidatePreparationExecution,
    OfficialCandidatePreparationRiskSnapshot,
    PreparationExecutionWithRiskSnapshot,
)


class SQLiteOfficialCandidatePreparationRepository:
    """Persist one immutable execution and optional validated risk snapshot."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self._connection = database.connection
        if migrate:
            MigrationManager(self._connection).migrate()

    def append_preparation_execution(
        self,
        execution: OfficialCandidatePreparationExecution,
        risk_snapshot: OfficialCandidatePreparationRiskSnapshot | None,
    ) -> tuple[PreparationExecutionWithRiskSnapshot, bool]:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._by_request(execution.integration_request_identity)
            if existing is not None:
                stored = self._with_risk(existing)
                if stored != PreparationExecutionWithRiskSnapshot(execution, risk_snapshot):
                    raise CandidatePreparationConflictError(
                        "Preparation request identity conflicts with immutable history."
                    )
                self._connection.commit()
                return stored, True
            self._insert_execution(execution)
            if risk_snapshot is not None:
                if risk_snapshot.integration_execution_id != execution.integration_execution_id:
                    raise CandidatePreparationConflictError(
                        "Risk snapshot execution identity is inconsistent."
                    )
                self._insert_risk(execution, risk_snapshot)
            self._connection.commit()
            stored = self.load_execution_with_risk_snapshot(
                execution.integration_execution_id
            )
            if stored is None:
                raise CandidatePreparationPersistenceError(
                    "Stored preparation execution is unavailable."
                )
            return stored, False
        except CandidatePreparationConflictError:
            self._connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            self._connection.rollback()
            existing = self._by_request(execution.integration_request_identity)
            if existing is not None:
                stored = self._with_risk(existing)
                if stored == PreparationExecutionWithRiskSnapshot(execution, risk_snapshot):
                    return stored, True
                raise CandidatePreparationConflictError(
                    "Preparation uniqueness conflicts with immutable content."
                ) from exc
            raise CandidatePreparationPersistenceError(
                "Atomic preparation append failed."
            ) from exc
        except CandidatePreparationPersistenceError:
            self._connection.rollback()
            raise
        except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
            self._connection.rollback()
            raise CandidatePreparationPersistenceError(
                "Atomic preparation append failed."
            ) from exc

    def find_by_integration_fingerprint(
        self, value: str
    ) -> OfficialCandidatePreparationExecution | None:
        return self._one("integration_fingerprint = ?", (value,))

    def find_by_request_identity(
        self, value: str
    ) -> OfficialCandidatePreparationExecution | None:
        return self._one("integration_request_identity = ?", (value,))

    def load_preparation_execution(
        self, value: str
    ) -> OfficialCandidatePreparationExecution | None:
        return self._one("integration_execution_id = ?", (value,))

    def load_execution_with_risk_snapshot(
        self, value: str
    ) -> PreparationExecutionWithRiskSnapshot | None:
        execution = self.load_preparation_execution(value)
        return None if execution is None else self._with_risk(execution)

    def list_executions_for_selection(
        self, value: str
    ) -> tuple[OfficialCandidatePreparationExecution, ...]:
        return self._many("selection_decision_id = ?", (value,))

    def list_executions_for_match(
        self, value: str
    ) -> tuple[OfficialCandidatePreparationExecution, ...]:
        return self._many("match_id = ?", (value,))

    def list_registered_candidates(
        self,
    ) -> tuple[OfficialCandidatePreparationExecution, ...]:
        return self._many("registry_candidate_id IS NOT NULL", ())

    def list_no_registration_decisions(
        self,
    ) -> tuple[OfficialCandidatePreparationExecution, ...]:
        return self._many(
            "final_status IN ('NO_REGISTRATION_INELIGIBLE', "
            "'NO_REGISTRATION_REVIEW_REQUIRED')",
            (),
        )

    def find_latest_for_selection(
        self, value: str
    ) -> OfficialCandidatePreparationExecution | None:
        items = self._many("selection_decision_id = ?", (value,), descending=True)
        return items[0] if items else None

    def _insert_execution(self, value: OfficialCandidatePreparationExecution) -> None:
        self._connection.execute(
            """
            INSERT INTO official_candidate_preparation_executions VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
            """,
            (
                value.integration_execution_id,
                value.integration_request_identity,
                value.preparation_request_fingerprint,
                value.integration_fingerprint,
                value.selection_decision_id,
                value.selected_value_assessment_id,
                value.match_id,
                value.kickoff_timestamp.isoformat(),
                value.risk_assessment_timestamp.isoformat(),
                value.candidate_preparation_timestamp.isoformat(),
                value.bankroll_snapshot_identity,
                value.bankroll_fingerprint,
                value.exposure_snapshot_identity,
                value.exposure_fingerprint,
                value.risk_handoff_fingerprint,
                _enum(value.risk_outcome),
                value.risk_assessment_id,
                value.risk_fingerprint,
                value.candidate_mapping_fingerprint,
                _enum(value.candidate_registry_outcome),
                value.registry_candidate_id,
                value.candidate_version,
                value.candidate_fingerprint,
                value.previous_candidate_id,
                value.final_status.value,
                value.integration_policy_version,
                canonical_json(value.ordered_reason_codes),
                canonical_json(value.explanations),
                canonical_json(value.deterministic_execution_summary),
                canonical_json(value),
                value.created_timestamp.isoformat(),
            ),
        )

    def _insert_risk(
        self,
        execution: OfficialCandidatePreparationExecution,
        value: OfficialCandidatePreparationRiskSnapshot,
    ) -> None:
        recommendation = value.audit.recommendation
        self._connection.execute(
            """
            INSERT INTO official_candidate_preparation_risk_snapshots VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
            """,
            (
                value.risk_snapshot_id,
                value.integration_execution_id,
                value.audit.assessment_id,
                value.risk_handoff_fingerprint,
                value.risk_fingerprint,
                value.audit.final_decision.value,
                value.audit.policy_version,
                _decimal(recommendation.final_stake) if recommendation else None,
                recommendation.currency if recommendation else None,
                _decimal(recommendation.internal_stake_percentage) if recommendation else None,
                _decimal(value.audit.bankroll_snapshot.current_bankroll),
                _decimal(
                    value.audit.bankroll_snapshot.current_bankroll
                    - value.audit.bankroll_snapshot.unsettled_exposure
                ),
                execution.bankroll_snapshot_identity,
                execution.bankroll_fingerprint,
                execution.exposure_snapshot_identity,
                execution.exposure_fingerprint,
                canonical_json(value.audit.exposure_assessments),
                canonical_json(value.audit.ordered_reasons),
                canonical_json(value),
                value.created_timestamp.isoformat(),
            ),
        )

    def _one(
        self, where: str, params: tuple[object, ...]
    ) -> OfficialCandidatePreparationExecution | None:
        try:
            row = self._connection.execute(
                "SELECT deterministic_execution_snapshot "
                f"FROM official_candidate_preparation_executions WHERE {where}",
                params,
            ).fetchone()
            return _execution(row[0]) if row else None
        except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
            raise CandidatePreparationPersistenceError(
                "Preparation execution lookup failed."
            ) from exc

    def _many(
        self,
        where: str,
        params: tuple[object, ...],
        descending: bool = False,
    ) -> tuple[OfficialCandidatePreparationExecution, ...]:
        direction = "DESC" if descending else "ASC"
        try:
            rows = self._connection.execute(
                "SELECT deterministic_execution_snapshot "
                "FROM official_candidate_preparation_executions "
                f"WHERE {where} ORDER BY candidate_preparation_timestamp {direction}, "
                f"integration_execution_id {direction}",
                params,
            )
            return tuple(_execution(row[0]) for row in rows)
        except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
            raise CandidatePreparationPersistenceError(
                "Preparation history query failed."
            ) from exc

    def _by_request(
        self, value: str
    ) -> OfficialCandidatePreparationExecution | None:
        row = self._connection.execute(
            "SELECT deterministic_execution_snapshot "
            "FROM official_candidate_preparation_executions "
            "WHERE integration_request_identity = ?",
            (value,),
        ).fetchone()
        return _execution(row[0]) if row else None

    def _with_risk(
        self, execution: OfficialCandidatePreparationExecution
    ) -> PreparationExecutionWithRiskSnapshot:
        row = self._connection.execute(
            "SELECT deterministic_risk_snapshot "
            "FROM official_candidate_preparation_risk_snapshots "
            "WHERE integration_execution_id = ?",
            (execution.integration_execution_id,),
        ).fetchone()
        return PreparationExecutionWithRiskSnapshot(
            execution,
            _risk_snapshot(row[0]) if row else None,
        )


def _execution(value: str) -> OfficialCandidatePreparationExecution:
    raw = json.loads(value)
    return OfficialCandidatePreparationExecution(
        integration_execution_id=raw["integration_execution_id"],
        integration_request_identity=raw["integration_request_identity"],
        preparation_request_fingerprint=raw["preparation_request_fingerprint"],
        integration_fingerprint=raw["integration_fingerprint"],
        selection_decision_id=raw["selection_decision_id"],
        selected_value_assessment_id=raw["selected_value_assessment_id"],
        match_id=raw["match_id"],
        kickoff_timestamp=datetime.fromisoformat(raw["kickoff_timestamp"]),
        risk_assessment_timestamp=datetime.fromisoformat(raw["risk_assessment_timestamp"]),
        candidate_preparation_timestamp=datetime.fromisoformat(
            raw["candidate_preparation_timestamp"]
        ),
        bankroll_snapshot_identity=raw["bankroll_snapshot_identity"],
        bankroll_fingerprint=raw["bankroll_fingerprint"],
        exposure_snapshot_identity=raw["exposure_snapshot_identity"],
        exposure_fingerprint=raw["exposure_fingerprint"],
        risk_handoff_fingerprint=raw["risk_handoff_fingerprint"],
        risk_outcome=_optional_enum(RiskAssessmentDecision, raw["risk_outcome"]),
        risk_assessment_id=raw["risk_assessment_id"],
        risk_fingerprint=raw["risk_fingerprint"],
        candidate_mapping_fingerprint=raw["candidate_mapping_fingerprint"],
        candidate_registry_outcome=_optional_enum(
            CandidateRegistrationStatus, raw["candidate_registry_outcome"]
        ),
        registry_candidate_id=raw["registry_candidate_id"],
        candidate_version=raw["candidate_version"],
        candidate_fingerprint=raw["candidate_fingerprint"],
        previous_candidate_id=raw["previous_candidate_id"],
        final_status=CandidatePreparationStatus(raw["final_status"]),
        integration_policy_version=raw["integration_policy_version"],
        ordered_reason_codes=tuple(
            CandidatePreparationReason(item)
            for item in raw["ordered_reason_codes"]
        ),
        explanations=tuple(raw["explanations"]),
        deterministic_execution_summary=tuple(
            tuple(item) for item in raw["deterministic_execution_summary"]
        ),
        created_timestamp=datetime.fromisoformat(raw["created_timestamp"]),
    )


def _risk_snapshot(value: str) -> OfficialCandidatePreparationRiskSnapshot:
    raw = json.loads(value)
    return OfficialCandidatePreparationRiskSnapshot(
        risk_snapshot_id=raw["risk_snapshot_id"],
        integration_execution_id=raw["integration_execution_id"],
        risk_handoff_fingerprint=raw["risk_handoff_fingerprint"],
        risk_fingerprint=raw["risk_fingerprint"],
        audit=_audit(raw["audit"]),
        created_timestamp=datetime.fromisoformat(raw["created_timestamp"]),
    )


def _audit(raw: dict[str, Any]) -> RiskAuditRecord:
    return RiskAuditRecord(
        assessment_id=raw["assessment_id"],
        prediction_id=raw["prediction_id"],
        product_scope=RiskProductScope(raw["product_scope"]),
        policy_version=raw["policy_version"],
        bankroll_snapshot=_bankroll(raw["bankroll_snapshot"]),
        exposure_snapshot=_exposure(raw["exposure_snapshot"]),
        quality_gate_status=_optional_enum(QualityGateStatus, raw["quality_gate_status"]),
        base_stake=Decimal(raw["base_stake"]),
        reductions=tuple(
            (RiskReason(item[0]), Decimal(item[1]), Decimal(item[2]))
            for item in raw["reductions"]
        ),
        recommendation=_stake(raw["recommendation"]),
        final_decision=RiskAssessmentDecision(raw["final_decision"]),
        ordered_reasons=tuple(RiskReason(item) for item in raw["ordered_reasons"]),
        ordered_warnings=tuple(RiskWarning(item) for item in raw["ordered_warnings"]),
        drawdown_state=DrawdownState(raw["drawdown_state"]),
        loss_streak_state=LossStreakState(raw["loss_streak_state"]),
        limiting_exposure=_exposure_assessment(raw["limiting_exposure"]),
        exposure_assessments=tuple(
            _exposure_assessment(item) for item in raw["exposure_assessments"]
        ),
        assessed_at=datetime.fromisoformat(raw["assessed_at"]),
        assessment_phase=RiskAssessmentPhase(raw["assessment_phase"]),
    )


def _bankroll(raw: dict[str, Any]) -> BankrollStateSnapshot:
    return BankrollStateSnapshot(
        product_scope=RiskProductScope(raw["product_scope"]),
        currency=raw["currency"],
        opening_bankroll=Decimal(raw["opening_bankroll"]),
        current_bankroll=Decimal(raw["current_bankroll"]),
        peak_bankroll=Decimal(raw["peak_bankroll"]),
        current_drawdown_amount=Decimal(raw["current_drawdown_amount"]),
        current_drawdown_percentage=Decimal(raw["current_drawdown_percentage"]),
        consecutive_wins=raw["consecutive_wins"],
        consecutive_losses=raw["consecutive_losses"],
        settled_bet_count=raw["settled_bet_count"],
        unsettled_exposure=Decimal(raw["unsettled_exposure"]),
        snapshot_timestamp=datetime.fromisoformat(raw["snapshot_timestamp"]),
        authoritative_source_reference=raw["authoritative_source_reference"],
    )


def _exposure(raw: dict[str, Any]) -> ExposureSnapshot:
    return ExposureSnapshot(
        product_scope=RiskProductScope(raw["product_scope"]),
        positions=tuple(
            ExposurePosition(
                exposure_type=ExposureType(item["exposure_type"]),
                scope_key=item["scope_key"],
                current_amount=Decimal(item["current_amount"]),
                currency=item["currency"],
                source_timestamp=datetime.fromisoformat(item["source_timestamp"]),
            )
            for item in raw["positions"]
        ),
        snapshot_timestamp=datetime.fromisoformat(raw["snapshot_timestamp"]),
        authoritative_source_reference=raw["authoritative_source_reference"],
    )


def _stake(raw: dict[str, Any] | None) -> StakeRecommendation | None:
    if raw is None:
        return None
    stars = raw["public_stars"]
    return StakeRecommendation(
        band=StakeBand(raw["band"]),
        unquantized_stake=Decimal(raw["unquantized_stake"]),
        final_stake=Decimal(raw["final_stake"]),
        internal_stake_percentage=Decimal(raw["internal_stake_percentage"]),
        public_stars=StakeStars(stars) if stars is not None else None,
        currency=raw["currency"],
        currency_quantum=Decimal(raw["currency_quantum"]),
    )


def _exposure_assessment(raw: dict[str, Any] | None) -> ExposureAssessment | None:
    if raw is None:
        return None
    return ExposureAssessment(
        exposure_type=ExposureType(raw["exposure_type"]),
        scope_key=raw["scope_key"],
        current_amount=Decimal(raw["current_amount"]),
        proposed_amount=Decimal(raw["proposed_amount"]),
        limit_amount=Decimal(raw["limit_amount"]),
        currency=raw["currency"],
        percentage_of_bankroll=Decimal(raw["percentage_of_bankroll"]),
        source_timestamp=datetime.fromisoformat(raw["source_timestamp"]),
        remaining_capacity=Decimal(raw["remaining_capacity"]),
        limiting=raw["limiting"],
        reason=RiskReason(raw["reason"]),
    )


def _enum(value: Any) -> str | None:
    return value.value if value is not None else None


def _optional_enum(kind: type[Any], value: Any) -> Any:
    return None if value is None else kind(value)


def _decimal(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")
