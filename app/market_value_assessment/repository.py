"""Append-only SQLite persistence for market value assessments."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.database import Database, MigrationManager
from app.match_data_snapshot import canonical_json
from app.prediction_inference import PredictionTarget

from .exceptions import MarketValueConflictError, MarketValuePersistenceError
from .models import (
    ActionabilityStatus,
    AssessmentValidationSummary,
    FreshnessState,
    MarketOddsSnapshot,
    MarketSelection,
    MarketStatus,
    MarketType,
    MarketValueAssessment,
    ProbabilitySourceType,
    ValueClassification,
)


_ODDS_INSERT = (
    "INSERT INTO market_odds_snapshots VALUES ("
    + ",".join("?" for _ in range(27))
    + ")"
)
_ASSESSMENT_INSERT = (
    "INSERT INTO market_value_assessments VALUES ("
    + ",".join("?" for _ in range(47))
    + ")"
)


class SQLiteMarketValueAssessmentRepository:
    """Store immutable odds and assessments with fingerprint idempotency."""

    def __init__(self, database: Database, migrate: bool = True) -> None:
        self.connection = database.connection
        if migrate:
            MigrationManager(self.connection).migrate()

    def load_calibrated_assembly_fingerprint(
        self, calibrated_assembly_id: str
    ) -> str | None:
        try:
            row = self.connection.execute(
                "SELECT calibrated_assembly_fingerprint "
                "FROM calibrated_market_probability_assemblies "
                "WHERE calibrated_assembly_id = ?",
                (calibrated_assembly_id,),
            ).fetchone()
            return row[0] if row else None
        except sqlite3.DatabaseError as exc:
            raise MarketValuePersistenceError(
                "Calibrated assembly provenance lookup failed."
            ) from exc

    def load_source_kickoff(self, snapshot_id: str) -> datetime | None:
        try:
            row = self.connection.execute(
                "SELECT kickoff_timestamp FROM match_data_snapshot_versions "
                "WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            return datetime.fromisoformat(row[0]) if row else None
        except sqlite3.DatabaseError as exc:
            raise MarketValuePersistenceError(
                "Kickoff provenance lookup failed."
            ) from exc

    def append_assessment_with_odds(
        self,
        odds: MarketOddsSnapshot,
        assessment: MarketValueAssessment,
    ) -> tuple[MarketValueAssessment, bool]:
        """Atomically append an unseen odds snapshot and its assessment."""

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self._assessment_fp(assessment.assessment_fingerprint)
            if existing is not None:
                if existing != assessment:
                    raise MarketValueConflictError(
                        "Assessment fingerprint content conflict."
                    )
                self.connection.commit()
                return existing, True

            stored_odds = self._odds_fp(odds.odds_fingerprint)
            if stored_odds is None:
                self.connection.execute(_ODDS_INSERT, _odds_values(odds))

            self.connection.execute(
                _ASSESSMENT_INSERT,
                _assessment_values(assessment),
            )
            self.connection.commit()
            return assessment, False
        except MarketValueConflictError:
            self.connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            existing = self._assessment_fp(assessment.assessment_fingerprint)
            if existing == assessment:
                return existing, True
            raise MarketValueConflictError(
                "Market value persistence conflict."
            ) from exc
        except sqlite3.DatabaseError as exc:
            self.connection.rollback()
            raise MarketValuePersistenceError(
                "Atomic odds/assessment append failed."
            ) from exc

    def append_odds_snapshot(
        self, value: MarketOddsSnapshot
    ) -> tuple[MarketOddsSnapshot, bool]:
        """Append an odds snapshot, returning the existing row when idempotent."""

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self._odds_fp(value.odds_fingerprint)
            if existing is not None:
                self.connection.commit()
                return existing, True
            self.connection.execute(_ODDS_INSERT, _odds_values(value))
            self.connection.commit()
            return value, False
        except MarketValueConflictError:
            self.connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            existing = self._odds_fp(value.odds_fingerprint)
            if existing == value:
                return existing, True
            raise MarketValueConflictError("Odds persistence conflict.") from exc
        except sqlite3.DatabaseError as exc:
            self.connection.rollback()
            raise MarketValuePersistenceError("Odds append failed.") from exc

    def find_odds_by_fingerprint(
        self, fingerprint: str
    ) -> MarketOddsSnapshot | None:
        return self._odds_fp(fingerprint)

    def load_odds_snapshot_by_id(
        self, odds_record_id: str
    ) -> MarketOddsSnapshot | None:
        row = self.connection.execute(
            "SELECT * FROM market_odds_snapshots WHERE odds_record_id = ?",
            (odds_record_id,),
        ).fetchone()
        return _odds(row) if row else None

    def list_odds_for_match(self, match_id: str) -> tuple[MarketOddsSnapshot, ...]:
        rows = self.connection.execute(
            "SELECT * FROM market_odds_snapshots WHERE match_id = ? "
            "ORDER BY odds_effective_timestamp, odds_record_id",
            (match_id,),
        )
        return tuple(_odds(row) for row in rows)

    def find_latest_odds_for_market(
        self,
        match_id: str,
        bookmaker_id: str,
        market_type: MarketType,
        selection: MarketSelection,
        market_line: Decimal | None,
    ) -> MarketOddsSnapshot | None:
        row = self.connection.execute(
            "SELECT * FROM market_odds_snapshots "
            "WHERE match_id = ? AND bookmaker_id = ? AND market_type = ? "
            "AND selection = ? AND market_line IS ? "
            "ORDER BY odds_effective_timestamp DESC, odds_record_id DESC LIMIT 1",
            (
                match_id,
                bookmaker_id,
                market_type.value,
                selection.value,
                _decimal_text(market_line),
            ),
        ).fetchone()
        return _odds(row) if row else None

    def list_odds_by_kickoff_window(
        self, start: datetime, end: datetime
    ) -> tuple[MarketOddsSnapshot, ...]:
        rows = self.connection.execute(
            "SELECT * FROM market_odds_snapshots "
            "WHERE kickoff_timestamp >= ? AND kickoff_timestamp <= ? "
            "ORDER BY kickoff_timestamp, odds_record_id",
            (start.isoformat(), end.isoformat()),
        )
        return tuple(_odds(row) for row in rows)

    def append_value_assessment(
        self, value: MarketValueAssessment
    ) -> tuple[MarketValueAssessment, bool]:
        """Append an assessment whose immutable odds row already exists."""

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self._assessment_fp(value.assessment_fingerprint)
            if existing is not None:
                if existing != value:
                    raise MarketValueConflictError(
                        "Assessment fingerprint content conflict."
                    )
                self.connection.commit()
                return existing, True

            odds = self.load_odds_snapshot_by_id(value.odds_record_id)
            if odds is None or odds.odds_fingerprint != value.odds_fingerprint:
                raise MarketValueConflictError(
                    "Assessment odds provenance does not exist."
                )
            self.connection.execute(_ASSESSMENT_INSERT, _assessment_values(value))
            self.connection.commit()
            return value, False
        except MarketValueConflictError:
            self.connection.rollback()
            raise
        except sqlite3.IntegrityError as exc:
            self.connection.rollback()
            existing = self._assessment_fp(value.assessment_fingerprint)
            if existing == value:
                return existing, True
            raise MarketValueConflictError(
                "Assessment persistence conflict."
            ) from exc
        except sqlite3.DatabaseError as exc:
            self.connection.rollback()
            raise MarketValuePersistenceError("Assessment append failed.") from exc

    def find_assessment_by_fingerprint(
        self, fingerprint: str
    ) -> MarketValueAssessment | None:
        return self._assessment_fp(fingerprint)

    def load_assessment_by_id(
        self, value_assessment_id: str
    ) -> MarketValueAssessment | None:
        row = self.connection.execute(
            "SELECT * FROM market_value_assessments WHERE value_assessment_id = ?",
            (value_assessment_id,),
        ).fetchone()
        return _assessment(row) if row else None

    def list_assessments_for_calibrated_assembly(
        self, calibrated_assembly_id: str
    ) -> tuple[MarketValueAssessment, ...]:
        return self._assessments(
            "calibrated_assembly_id = ?", (calibrated_assembly_id,)
        )

    def list_assessments_for_match(
        self, match_id: str
    ) -> tuple[MarketValueAssessment, ...]:
        return self._assessments("match_id = ?", (match_id,))

    def find_latest_for_match_bookmaker_market(
        self,
        match_id: str,
        bookmaker_id: str,
        market_type: MarketType,
        selection: MarketSelection,
        market_line: Decimal | None,
    ) -> MarketValueAssessment | None:
        values = self._assessments(
            "match_id = ? AND bookmaker_id = ? AND market_type = ? "
            "AND selection = ? AND market_line IS ?",
            (
                match_id,
                bookmaker_id,
                market_type.value,
                selection.value,
                _decimal_text(market_line),
            ),
            descending=True,
        )
        return values[0] if values else None

    def list_actionable_assessments(self) -> tuple[MarketValueAssessment, ...]:
        return self._assessments(
            "actionability_status = ?", (ActionabilityStatus.ACTIONABLE.value,)
        )

    def _odds_fp(self, fingerprint: str) -> MarketOddsSnapshot | None:
        row = self.connection.execute(
            "SELECT * FROM market_odds_snapshots WHERE odds_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return _odds(row) if row else None

    def _assessment_fp(self, fingerprint: str) -> MarketValueAssessment | None:
        row = self.connection.execute(
            "SELECT * FROM market_value_assessments "
            "WHERE assessment_fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return _assessment(row) if row else None

    def _assessments(
        self,
        where: str,
        params: tuple[object, ...],
        descending: bool = False,
    ) -> tuple[MarketValueAssessment, ...]:
        direction = "DESC" if descending else "ASC"
        rows = self.connection.execute(
            f"SELECT * FROM market_value_assessments WHERE {where} "
            f"ORDER BY assessment_timestamp {direction}, value_assessment_id {direction}",
            params,
        )
        return tuple(_assessment(row) for row in rows)


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _odds_values(value: MarketOddsSnapshot) -> tuple[object, ...]:
    return (
        value.odds_record_id,
        value.supplied_snapshot_id,
        value.odds_fingerprint,
        value.source_provider,
        value.bookmaker_id,
        value.source_event_id,
        value.match_id,
        value.market_type.value,
        value.selection.value,
        _decimal_text(value.market_line),
        value.original_market,
        value.original_selection,
        _decimal_text(value.decimal_odds),
        value.odds_effective_timestamp.isoformat(),
        value.source_updated_timestamp.isoformat(),
        value.registration_timestamp.isoformat(),
        value.kickoff_timestamp.isoformat(),
        value.market_status.value,
        int(value.suspended),
        int(value.available),
        _decimal_text(value.minimum_stake),
        _decimal_text(value.maximum_stake),
        value.currency,
        value.source_data_version,
        value.metadata_version,
        canonical_json(value),
        value.created_timestamp.isoformat(),
    )


def _assessment_values(value: MarketValueAssessment) -> tuple[object, ...]:
    return (
        value.value_assessment_id,
        value.calibrated_assembly_id,
        value.inference_id,
        value.model_input_id,
        value.match_id,
        value.source_snapshot_id,
        value.feature_set_id,
        value.source_model_artifact_id,
        value.source_model_version,
        value.calibration_set_id,
        value.calibration_set_fingerprint,
        value.odds_record_id,
        value.odds_fingerprint,
        value.source_provider,
        value.bookmaker_id,
        value.market_type.value,
        value.selection.value,
        _decimal_text(value.market_line),
        canonical_json(tuple(target.value for target in value.source_calibrated_targets)),
        value.probability_derivation_type.value,
        value.derivation_version,
        _decimal_text(value.fair_probability),
        _decimal_text(value.fair_decimal_odds),
        _decimal_text(value.bookmaker_decimal_odds),
        _decimal_text(value.implied_probability),
        _decimal_text(value.break_even_probability),
        _decimal_text(value.absolute_probability_edge),
        _decimal_text(value.relative_probability_edge),
        _decimal_text(value.expected_value),
        _decimal_text(value.expected_return),
        _decimal_text(value.potential_profit),
        value.odds_age_seconds,
        value.calibrated_age_seconds,
        value.time_to_kickoff_seconds,
        value.value_classification.value,
        value.odds_freshness.value,
        value.calibrated_freshness.value,
        value.overall_freshness.value,
        value.actionability_status.value,
        value.assessment_timestamp.isoformat(),
        value.kickoff_timestamp.isoformat(),
        value.value_policy_version,
        value.calibrated_assembly_fingerprint,
        value.assessment_fingerprint,
        canonical_json(value.ordered_reason_codes),
        canonical_json(value.validation_summary),
        value.created_timestamp.isoformat(),
    )


def _odds(row: Any) -> MarketOddsSnapshot:
    raw = json.loads(row["deterministic_snapshot"])
    return MarketOddsSnapshot(
        row["odds_record_id"],
        row["supplied_snapshot_id"],
        row["odds_fingerprint"],
        row["source_provider"],
        row["bookmaker_id"],
        row["source_event_id"],
        row["match_id"],
        MarketType(row["market_type"]),
        MarketSelection(row["selection"]),
        Decimal(row["market_line"]) if row["market_line"] else None,
        row["original_market"],
        row["original_selection"],
        Decimal(row["decimal_odds"]),
        datetime.fromisoformat(row["odds_effective_timestamp"]),
        datetime.fromisoformat(row["source_updated_timestamp"]),
        datetime.fromisoformat(row["registration_timestamp"]),
        datetime.fromisoformat(row["kickoff_timestamp"]),
        MarketStatus(row["market_status"]),
        bool(row["suspended"]),
        bool(row["available"]),
        Decimal(row["minimum_stake"]) if row["minimum_stake"] else None,
        Decimal(row["maximum_stake"]) if row["maximum_stake"] else None,
        row["currency"],
        row["source_data_version"],
        row["metadata_version"],
        tuple(tuple(item) for item in raw["metadata"]),
        datetime.fromisoformat(row["created_timestamp"]),
    )


def _assessment(row: Any) -> MarketValueAssessment:
    decimal_columns = (
        "fair_probability",
        "fair_decimal_odds",
        "bookmaker_decimal_odds",
        "implied_probability",
        "break_even_probability",
        "absolute_probability_edge",
        "relative_probability_edge",
        "expected_value",
        "expected_return",
        "potential_profit",
    )
    validation = json.loads(row["validation_snapshot"])
    return MarketValueAssessment(
        row["value_assessment_id"],
        row["calibrated_assembly_id"],
        row["inference_id"],
        row["model_input_id"],
        row["match_id"],
        row["source_snapshot_id"],
        row["feature_set_id"],
        row["source_model_artifact_id"],
        row["source_model_version"],
        row["calibration_set_id"],
        row["calibration_set_fingerprint"],
        row["odds_record_id"],
        row["odds_fingerprint"],
        row["source_provider"],
        row["bookmaker_id"],
        MarketType(row["market_type"]),
        MarketSelection(row["selection"]),
        Decimal(row["market_line"]) if row["market_line"] else None,
        tuple(
            PredictionTarget(target)
            for target in json.loads(row["source_calibrated_targets"])
        ),
        ProbabilitySourceType(row["probability_derivation_type"]),
        row["derivation_version"],
        *(Decimal(row[column]) for column in decimal_columns),
        row["odds_age_seconds"],
        row["calibrated_age_seconds"],
        row["time_to_kickoff_seconds"],
        ValueClassification(row["value_classification"]),
        FreshnessState(row["odds_freshness"]),
        FreshnessState(row["calibrated_freshness"]),
        FreshnessState(row["overall_freshness"]),
        ActionabilityStatus(row["actionability_status"]),
        datetime.fromisoformat(row["assessment_timestamp"]),
        datetime.fromisoformat(row["kickoff_timestamp"]),
        row["value_policy_version"],
        row["calibrated_assembly_fingerprint"],
        row["assessment_fingerprint"],
        tuple(json.loads(row["reason_code_snapshot"])),
        AssessmentValidationSummary(
            mapping_version=validation["mapping_version"],
            ordered_checks=tuple(validation["ordered_checks"]),
        ),
        datetime.fromisoformat(row["created_timestamp"]),
    )
