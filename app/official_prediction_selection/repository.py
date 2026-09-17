"""Append-only SQLite persistence for Official selection decisions."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.database import Database, MigrationManager
from app.market_value_assessment import (
    FreshnessState,
    MarketSelection,
    MarketType,
    MarketValueAssessment,
    SQLiteMarketValueAssessmentRepository,
    ValueClassification,
)
from app.market_value_assessment.exceptions import MarketValuePersistenceError
from app.match_data_snapshot import canonical_json
from app.prediction_inference import PredictionTarget

from .exceptions import SelectionConflictError, SelectionPersistenceError
from .models import (
    AssessmentEligibilityEvaluation,
    AssessmentEligibilityStatus,
    AssessmentFreshnessSummary,
    OfficialNoSelectionDecision,
    OfficialSelectionDecision,
    SelectedOfficialPrediction,
    SelectionDecisionWithEvaluations,
    SelectionReason,
)


class SQLiteOfficialPredictionSelectionRepository:
    """Persist decisions and their complete evaluations in one transaction."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self.connection = database.connection
        if migrate:
            MigrationManager(self.connection).migrate()
        self._assessments = SQLiteMarketValueAssessmentRepository(
            database, migrate=False
        )

    def load_market_value_assessment(
        self, value_assessment_id: str
    ) -> MarketValueAssessment | None:
        try:
            return self._assessments.load_assessment_by_id(value_assessment_id)
        except MarketValuePersistenceError as exc:
            raise SelectionPersistenceError(
                "Assessment provenance lookup failed."
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise SelectionPersistenceError(
                "Assessment provenance lookup failed."
            ) from exc

    def append_selection_decision(
        self,
        decision: OfficialSelectionDecision,
        evaluations: tuple[AssessmentEligibilityEvaluation, ...],
    ) -> tuple[SelectionDecisionWithEvaluations, bool]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self._find_by_request_identity(
                decision.selection_request_identity
            )
            if existing is not None:
                if existing != decision:
                    raise SelectionConflictError(
                        "Selection request identity content conflict."
                    )
                stored = self._load_with_evaluations(
                    existing.selection_decision_id
                )
                assert stored is not None
                if stored.evaluations != evaluations:
                    raise SelectionConflictError(
                        "Selection evaluation history content conflict."
                    )
                self.connection.commit()
                return stored, True

            self.connection.execute(
                """
                INSERT INTO official_prediction_selection_decisions (
                    selection_decision_id, selection_request_identity,
                    selection_request_fingerprint, match_id, kickoff_timestamp,
                    selection_timestamp, final_outcome_status,
                    selected_value_assessment_id,
                    selected_assessment_fingerprint, selected_market_identity,
                    selected_odds, selected_fair_probability,
                    selected_expected_value, eligible_assessment_count,
                    rejected_assessment_count, selection_policy_version,
                    ranking_policy_version, decision_fingerprint,
                    final_reason_code_snapshot,
                    deterministic_decision_snapshot, created_timestamp
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                _decision_values(decision),
            )
            for evaluation in evaluations:
                self.connection.execute(
                    """
                    INSERT INTO official_prediction_selection_evaluations (
                        evaluation_id, selection_decision_id,
                        value_assessment_id, assessment_fingerprint,
                        deterministic_input_order, eligibility_status,
                        logical_market_identity, verified_odds,
                        verified_fair_probability, verified_expected_value,
                        freshness_snapshot, ordered_rejection_reasons,
                        evaluation_fingerprint,
                        deterministic_evaluation_snapshot, created_timestamp
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    _evaluation_values(decision.selection_decision_id, evaluation),
                )
            self.connection.commit()
            return SelectionDecisionWithEvaluations(decision, evaluations), False
        except SelectionConflictError:
            self.connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            existing = self._find_by_request_identity(
                decision.selection_request_identity
            )
            if existing == decision:
                stored = self._load_with_evaluations(
                    existing.selection_decision_id
                )
                if stored is not None and stored.evaluations == evaluations:
                    return stored, True
            fingerprint_existing = self._find_by_decision_fingerprint(
                _decision_fingerprint(decision)
            )
            if existing is not None or fingerprint_existing is not None:
                raise SelectionConflictError(
                    "Official selection persistence conflict."
                ) from exc
            raise SelectionPersistenceError(
                "Atomic Official selection append failed."
            ) from exc
        except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
            self.connection.rollback()
            raise SelectionPersistenceError(
                "Atomic Official selection append failed."
            ) from exc

    def find_by_decision_fingerprint(
        self, decision_fingerprint: str
    ) -> OfficialSelectionDecision | None:
        return self._one(
            "decision_fingerprint = ?", (decision_fingerprint,)
        )

    def find_by_request_identity(
        self, request_identity: str
    ) -> OfficialSelectionDecision | None:
        return self._one(
            "selection_request_identity = ?", (request_identity,)
        )

    def load_selection_decision(
        self, selection_decision_id: str
    ) -> OfficialSelectionDecision | None:
        return self._one(
            "selection_decision_id = ?", (selection_decision_id,)
        )

    def load_selection_with_evaluations(
        self, selection_decision_id: str
    ) -> SelectionDecisionWithEvaluations | None:
        try:
            return self._load_with_evaluations(selection_decision_id)
        except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
            raise SelectionPersistenceError(
                "Official selection history lookup failed."
            ) from exc

    def list_selection_decisions_for_match(
        self, match_id: str
    ) -> tuple[OfficialSelectionDecision, ...]:
        return self._many("match_id = ?", (match_id,))

    def list_selected_decisions(self) -> tuple[OfficialSelectionDecision, ...]:
        return self._many("final_outcome_status = ?", ("SELECTED",))

    def list_no_selection_decisions(
        self,
    ) -> tuple[OfficialSelectionDecision, ...]:
        return self._many("final_outcome_status = ?", ("NO_SELECTION",))

    def find_latest_selection_for_match(
        self, match_id: str
    ) -> OfficialSelectionDecision | None:
        values = self._many("match_id = ?", (match_id,), descending=True)
        return values[0] if values else None

    def _find_by_request_identity(
        self, request_identity: str
    ) -> OfficialSelectionDecision | None:
        row = self.connection.execute(
            "SELECT deterministic_decision_snapshot "
            "FROM official_prediction_selection_decisions "
            "WHERE selection_request_identity = ?",
            (request_identity,),
        ).fetchone()
        return _decision(row[0]) if row else None

    def _find_by_decision_fingerprint(
        self, fingerprint: str
    ) -> OfficialSelectionDecision | None:
        row = self.connection.execute(
            "SELECT deterministic_decision_snapshot "
            "FROM official_prediction_selection_decisions "
            "WHERE decision_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return _decision(row[0]) if row else None

    def _one(
        self, where: str, params: tuple[object, ...]
    ) -> OfficialSelectionDecision | None:
        try:
            row = self.connection.execute(
                "SELECT deterministic_decision_snapshot "
                f"FROM official_prediction_selection_decisions WHERE {where}",
                params,
            ).fetchone()
            return _decision(row[0]) if row else None
        except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
            raise SelectionPersistenceError(
                "Official selection history lookup failed."
            ) from exc

    def _many(
        self,
        where: str,
        params: tuple[object, ...],
        descending: bool = False,
    ) -> tuple[OfficialSelectionDecision, ...]:
        direction = "DESC" if descending else "ASC"
        try:
            rows = self.connection.execute(
                "SELECT deterministic_decision_snapshot "
                f"FROM official_prediction_selection_decisions WHERE {where} "
                f"ORDER BY selection_timestamp {direction}, "
                f"selection_decision_id {direction}",
                params,
            )
            return tuple(_decision(row[0]) for row in rows)
        except (sqlite3.DatabaseError, KeyError, TypeError, ValueError) as exc:
            raise SelectionPersistenceError(
                "Official selection history query failed."
            ) from exc

    def _load_with_evaluations(
        self, selection_decision_id: str
    ) -> SelectionDecisionWithEvaluations | None:
        row = self.connection.execute(
            "SELECT deterministic_decision_snapshot "
            "FROM official_prediction_selection_decisions "
            "WHERE selection_decision_id = ?",
            (selection_decision_id,),
        ).fetchone()
        if row is None:
            return None
        evaluations = self.connection.execute(
            "SELECT deterministic_evaluation_snapshot "
            "FROM official_prediction_selection_evaluations "
            "WHERE selection_decision_id = ? "
            "ORDER BY deterministic_input_order, evaluation_id",
            (selection_decision_id,),
        )
        return SelectionDecisionWithEvaluations(
            _decision(row[0]), tuple(_evaluation(item[0]) for item in evaluations)
        )


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return "0" if value == 0 else format(value.normalize(), "f")


def _decision_values(decision: OfficialSelectionDecision) -> tuple[object, ...]:
    selected = isinstance(decision, SelectedOfficialPrediction)
    return (
        decision.selection_decision_id,
        decision.selection_request_identity,
        decision.selection_request_fingerprint,
        decision.match_id,
        decision.kickoff_timestamp.isoformat(),
        decision.selection_timestamp.isoformat(),
        "SELECTED" if selected else "NO_SELECTION",
        decision.selected_value_assessment_id if selected else None,
        decision.selected_assessment_fingerprint if selected else None,
        decision.logical_market_identity if selected else None,
        _decimal_text(decision.bookmaker_decimal_odds) if selected else None,
        _decimal_text(decision.fair_probability) if selected else None,
        _decimal_text(decision.expected_value) if selected else None,
        decision.eligible_assessment_count,
        decision.rejected_assessment_count,
        decision.selection_policy_version,
        decision.ranking_policy_version,
        _decision_fingerprint(decision),
        canonical_json(decision.ordered_reason_codes),
        canonical_json(decision),
        decision.created_timestamp.isoformat(),
    )


def _decision_fingerprint(decision: OfficialSelectionDecision) -> str:
    if isinstance(decision, SelectedOfficialPrediction):
        return decision.selection_fingerprint
    return decision.no_selection_fingerprint


def _evaluation_values(
    decision_id: str, value: AssessmentEligibilityEvaluation
) -> tuple[object, ...]:
    return (
        value.evaluation_id,
        decision_id,
        value.value_assessment_id,
        value.assessment_fingerprint,
        value.deterministic_input_order,
        value.eligibility_status.value,
        value.logical_market_identity,
        _decimal_text(value.verified_odds),
        _decimal_text(value.verified_fair_probability),
        _decimal_text(value.verified_expected_value),
        canonical_json(value.freshness),
        canonical_json(value.ordered_rejection_reasons),
        value.evaluation_fingerprint,
        canonical_json(value),
        value.created_timestamp.isoformat(),
    )


def _freshness(raw: dict[str, Any]) -> AssessmentFreshnessSummary:
    return AssessmentFreshnessSummary(
        FreshnessState(raw["odds_freshness"]),
        FreshnessState(raw["calibrated_freshness"]),
        FreshnessState(raw["overall_freshness"]),
        datetime.fromisoformat(raw["odds_effective_timestamp"]),
    )


def _evaluation(value: str | dict[str, Any]) -> AssessmentEligibilityEvaluation:
    raw = json.loads(value) if isinstance(value, str) else value
    line = raw["market_line"]
    return AssessmentEligibilityEvaluation(
        evaluation_id=raw["evaluation_id"],
        value_assessment_id=raw["value_assessment_id"],
        assessment_fingerprint=raw["assessment_fingerprint"],
        deterministic_input_order=raw["deterministic_input_order"],
        eligibility_status=AssessmentEligibilityStatus(raw["eligibility_status"]),
        logical_market_identity=raw["logical_market_identity"],
        market_type=MarketType(raw["market_type"]),
        selection=MarketSelection(raw["selection"]),
        market_line=Decimal(line) if line is not None else None,
        source_provider=raw["source_provider"],
        bookmaker_id=raw["bookmaker_id"],
        verified_odds=Decimal(raw["verified_odds"]),
        verified_fair_probability=Decimal(raw["verified_fair_probability"]),
        verified_expected_value=Decimal(raw["verified_expected_value"]),
        absolute_probability_edge=Decimal(raw["absolute_probability_edge"]),
        freshness=_freshness(raw["freshness"]),
        ordered_rejection_reasons=tuple(
            SelectionReason(item) for item in raw["ordered_rejection_reasons"]
        ),
        evaluation_fingerprint=raw["evaluation_fingerprint"],
        created_timestamp=datetime.fromisoformat(raw["created_timestamp"]),
    )


def _decision(value: str) -> OfficialSelectionDecision:
    raw = json.loads(value)
    if "selected_value_assessment_id" in raw:
        return _selected(raw)
    return _no_selection(raw)


def _selected(raw: dict[str, Any]) -> SelectedOfficialPrediction:
    line = raw["market_line"]
    decimal_names = (
        "fair_probability", "bookmaker_decimal_odds", "implied_probability",
        "fair_decimal_odds", "absolute_probability_edge",
        "relative_probability_edge", "expected_value", "expected_return",
    )
    decimals = {name: Decimal(raw[name]) for name in decimal_names}
    return SelectedOfficialPrediction(
        selection_decision_id=raw["selection_decision_id"],
        selection_request_identity=raw["selection_request_identity"],
        selection_request_fingerprint=raw["selection_request_fingerprint"],
        match_id=raw["match_id"],
        kickoff_timestamp=datetime.fromisoformat(raw["kickoff_timestamp"]),
        selection_timestamp=datetime.fromisoformat(raw["selection_timestamp"]),
        selected_value_assessment_id=raw["selected_value_assessment_id"],
        selected_assessment_fingerprint=raw["selected_assessment_fingerprint"],
        source_provider=raw["source_provider"],
        bookmaker_id=raw["bookmaker_id"],
        logical_market_identity=raw["logical_market_identity"],
        market_type=MarketType(raw["market_type"]),
        selection=MarketSelection(raw["selection"]),
        market_line=Decimal(line) if line is not None else None,
        **decimals,
        value_classification=ValueClassification(raw["value_classification"]),
        freshness=_freshness(raw["freshness"]),
        source_model_artifact_id=raw["source_model_artifact_id"],
        source_model_version=raw["source_model_version"],
        inference_id=raw["inference_id"],
        model_input_id=raw["model_input_id"],
        source_snapshot_id=raw["source_snapshot_id"],
        feature_set_id=raw["feature_set_id"],
        calibrated_assembly_id=raw["calibrated_assembly_id"],
        calibration_set_id=raw["calibration_set_id"],
        calibration_set_fingerprint=raw["calibration_set_fingerprint"],
        source_calibrated_targets=tuple(
            PredictionTarget(item) for item in raw["source_calibrated_targets"]
        ),
        odds_fingerprint=raw["odds_fingerprint"],
        calibrated_assembly_fingerprint=raw["calibrated_assembly_fingerprint"],
        value_policy_version=raw["value_policy_version"],
        selection_policy_version=raw["selection_policy_version"],
        ranking_policy_version=raw["ranking_policy_version"],
        selected_rank=raw["selected_rank"],
        eligible_assessment_count=raw["eligible_assessment_count"],
        rejected_assessment_count=raw["rejected_assessment_count"],
        selection_fingerprint=raw["selection_fingerprint"],
        ordered_reason_codes=tuple(
            SelectionReason(item) for item in raw["ordered_reason_codes"]
        ),
        deterministic_decision_summary=tuple(
            tuple(item) for item in raw["deterministic_decision_summary"]
        ),
        created_timestamp=datetime.fromisoformat(raw["created_timestamp"]),
    )


def _no_selection(raw: dict[str, Any]) -> OfficialNoSelectionDecision:
    return OfficialNoSelectionDecision(
        selection_decision_id=raw["selection_decision_id"],
        selection_request_identity=raw["selection_request_identity"],
        selection_request_fingerprint=raw["selection_request_fingerprint"],
        match_id=raw["match_id"],
        kickoff_timestamp=datetime.fromisoformat(raw["kickoff_timestamp"]),
        selection_timestamp=datetime.fromisoformat(raw["selection_timestamp"]),
        final_reason_code=SelectionReason(raw["final_reason_code"]),
        evaluation_summaries=tuple(
            _evaluation(item) for item in raw["evaluation_summaries"]
        ),
        assessment_count=raw["assessment_count"],
        eligible_assessment_count=raw["eligible_assessment_count"],
        rejected_assessment_count=raw["rejected_assessment_count"],
        rejection_reason_counts=tuple(
            (SelectionReason(item[0]), item[1])
            for item in raw["rejection_reason_counts"]
        ),
        selection_policy_version=raw["selection_policy_version"],
        ranking_policy_version=raw["ranking_policy_version"],
        no_selection_fingerprint=raw["no_selection_fingerprint"],
        ordered_reason_codes=tuple(
            SelectionReason(item) for item in raw["ordered_reason_codes"]
        ),
        deterministic_decision_summary=tuple(
            tuple(item) for item in raw["deterministic_decision_summary"]
        ),
        created_timestamp=datetime.fromisoformat(raw["created_timestamp"]),
    )
