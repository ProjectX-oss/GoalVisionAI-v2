"""Fail-closed request and persisted assessment provenance validation."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import NoReturn

from app.market_value_assessment import MarketValueAssessment
from app.market_value_assessment.fingerprint import assessment_fingerprint
from app.risk_management import RiskProductScope

from .exceptions import (
    InvalidSelectionRequestError,
    SelectionPersistenceError,
    SelectionProvenanceError,
    SelectionScopeError,
)
from .models import OfficialPredictionSelectionCommand, SelectionReason
from .policy import OfficialPredictionSelectionPolicy
from .ports import PersistedMarketValueAssessmentReader


_FORBIDDEN_METADATA = re.compile(
    r"https?://|www\.|token|secret|password|api[_ -]?key|affiliate",
    re.IGNORECASE,
)


def validate_selection_request(
    command: OfficialPredictionSelectionCommand,
    policy: OfficialPredictionSelectionPolicy,
    assessments: PersistedMarketValueAssessmentReader,
) -> OfficialPredictionSelectionCommand:
    if not isinstance(command, OfficialPredictionSelectionCommand):
        _invalid(SelectionReason.INVALID_REQUEST, "Immutable selection command required.")
    request_identity = _text(
        command.selection_request_identity,
        "Selection request identity",
    )
    match_id = _text(command.match_id, "Match ID")
    if command.selection_policy_version != policy.version:
        _invalid(
            SelectionReason.POLICY_INCOMPATIBLE,
            "Selection command policy version is unsupported.",
        )
    if command.metadata_version != policy.metadata_version:
        _invalid(
            SelectionReason.POLICY_INCOMPATIBLE,
            "Selection metadata version is unsupported.",
        )
    selection_timestamp = _timestamp(
        command.selection_timestamp,
        "Selection timestamp",
    )
    kickoff_timestamp = _timestamp(command.kickoff_timestamp, "Kickoff timestamp")
    if selection_timestamp >= kickoff_timestamp:
        _invalid(
            SelectionReason.INVALID_REQUEST,
            "Selection timestamp must precede kickoff.",
        )
    if command.bankroll_scope is not RiskProductScope.OFFICIAL:
        raise SelectionScopeError(
            SelectionReason.NON_OFFICIAL_SCOPE,
            "Official selection requires the Official bankroll scope.",
        )
    if command.destination_scope is not RiskProductScope.OFFICIAL:
        raise SelectionScopeError(
            SelectionReason.NON_OFFICIAL_DESTINATION,
            "Official selection requires the Official destination scope.",
        )
    if not isinstance(command.assessments, tuple):
        _invalid(
            SelectionReason.INVALID_REQUEST,
            "Assessments must be supplied as an immutable tuple.",
        )
    if len(command.assessments) > policy.maximum_assessment_count:
        _invalid(
            SelectionReason.COLLECTION_LIMIT_EXCEEDED,
            "Selection assessment collection exceeds the policy limit.",
        )
    metadata = _metadata(command.metadata)
    source_run_identity = (
        _text(command.source_run_identity, "Source run identity")
        if command.source_run_identity is not None
        else None
    )

    values = command.assessments
    if any(not isinstance(item, MarketValueAssessment) for item in values):
        _invalid(
            SelectionReason.INVALID_REQUEST,
            "Every selection input must be a market value assessment.",
        )
    assessment_ids = tuple(item.value_assessment_id for item in values)
    assessment_fingerprints = tuple(item.assessment_fingerprint for item in values)
    if len(assessment_ids) != len(set(assessment_ids)) or len(
        assessment_fingerprints
    ) != len(set(assessment_fingerprints)):
        _invalid(
            SelectionReason.DUPLICATE_ASSESSMENT,
            "Duplicate assessment identity or fingerprint is not permitted.",
        )

    for item in values:
        _validate_assessment_shape(item, policy)
        if item.match_id != match_id:
            raise SelectionProvenanceError(
                SelectionReason.MATCH_MISMATCH,
                "A supplied assessment belongs to another match.",
            )
        assessment_kickoff = _timestamp(
            item.kickoff_timestamp,
            "Assessment kickoff",
        )
        if assessment_kickoff != kickoff_timestamp:
            raise SelectionProvenanceError(
                SelectionReason.KICKOFF_MISMATCH,
                "Assessment kickoff conflicts with the selection request.",
            )
        assessment_timestamp = _timestamp(
            item.assessment_timestamp,
            "Assessment timestamp",
        )
        if assessment_timestamp > selection_timestamp:
            raise SelectionProvenanceError(
                SelectionReason.PROVENANCE_INVALID,
                "Assessment timestamp is newer than the selection timestamp.",
            )
        try:
            expected_fingerprint = assessment_fingerprint(item)
        except (AttributeError, TypeError, ValueError) as exc:
            raise SelectionProvenanceError(
                SelectionReason.FINGERPRINT_MISMATCH,
                "Assessment fingerprint cannot be verified.",
            ) from exc
        if expected_fingerprint != item.assessment_fingerprint:
            raise SelectionProvenanceError(
                SelectionReason.FINGERPRINT_MISMATCH,
                "Assessment fingerprint verification failed.",
            )
        try:
            persisted = assessments.load_market_value_assessment(
                item.value_assessment_id
            )
        except SelectionPersistenceError:
            raise
        except Exception as exc:
            raise SelectionPersistenceError(
                "Persisted value assessment lookup failed."
            ) from exc
        if persisted is None or persisted != item:
            raise SelectionProvenanceError(
                SelectionReason.PROVENANCE_INVALID,
                "Assessment is not persisted or differs from immutable history.",
            )

    ordered = tuple(
        sorted(
            values,
            key=lambda item: (
                item.assessment_fingerprint,
                item.value_assessment_id,
            ),
        )
    )
    return replace(
        command,
        selection_request_identity=request_identity,
        match_id=match_id,
        selection_timestamp=selection_timestamp,
        kickoff_timestamp=kickoff_timestamp,
        assessments=ordered,
        source_run_identity=source_run_identity,
        metadata=metadata,
    )


def _validate_assessment_shape(
    value: MarketValueAssessment,
    policy: OfficialPredictionSelectionPolicy,
) -> None:
    required = (
        value.value_assessment_id,
        value.calibrated_assembly_id,
        value.inference_id,
        value.model_input_id,
        value.match_id,
        value.source_snapshot_id,
        value.feature_set_id,
        value.source_model_artifact_id,
        value.source_model_version,
        value.calibration_set_fingerprint,
        value.odds_record_id,
        value.odds_fingerprint,
        value.source_provider,
        value.bookmaker_id,
        value.value_policy_version,
        value.calibrated_assembly_fingerprint,
        value.assessment_fingerprint,
    )
    if any(not isinstance(item, str) or not item.strip() for item in required):
        raise SelectionProvenanceError(
            SelectionReason.PROVENANCE_INVALID,
            "Assessment provenance is incomplete.",
        )
    if value.value_policy_version not in policy.supported_value_policy_versions:
        _invalid(
            SelectionReason.POLICY_INCOMPATIBLE,
            "Assessment value policy version is unsupported.",
        )
    decimals = (
        value.fair_probability,
        value.fair_decimal_odds,
        value.bookmaker_decimal_odds,
        value.implied_probability,
        value.break_even_probability,
        value.absolute_probability_edge,
        value.relative_probability_edge,
        value.expected_value,
        value.expected_return,
        value.potential_profit,
    )
    if any(
        not isinstance(item, Decimal) or not item.is_finite() for item in decimals
    ):
        _invalid(
            SelectionReason.INVALID_REQUEST,
            "Assessment numeric facts must be finite Decimals.",
        )
    if (
        not isinstance(value.odds_age_seconds, int)
        or not isinstance(value.calibrated_age_seconds, int)
        or not isinstance(value.time_to_kickoff_seconds, int)
        or min(
            value.odds_age_seconds,
            value.calibrated_age_seconds,
            value.time_to_kickoff_seconds,
        )
        < 0
    ):
        _invalid(
            SelectionReason.INVALID_REQUEST,
            "Assessment age and kickoff facts are malformed.",
        )


def _text(value: object, label: str, maximum: int = 512) -> str:
    if not isinstance(value, str):
        _invalid(SelectionReason.INVALID_REQUEST, f"{label} must be text.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not normalized or len(normalized) > maximum:
        _invalid(SelectionReason.INVALID_REQUEST, f"{label} is malformed.")
    return normalized


def _timestamp(value: object, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        _invalid(
            SelectionReason.INVALID_REQUEST,
            f"{label} must be timezone-aware.",
        )
    return value.astimezone(timezone.utc)


def _metadata(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        _invalid(
            SelectionReason.INVALID_METADATA,
            "Selection metadata must be an immutable tuple.",
        )
    normalized: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            _invalid(
                SelectionReason.INVALID_METADATA,
                "Selection metadata must contain immutable text pairs.",
            )
        key = _text(item[0], "Metadata key")
        item_value = _text(item[1], "Metadata value", 2048)
        if _FORBIDDEN_METADATA.search(key) or _FORBIDDEN_METADATA.search(item_value):
            _invalid(
                SelectionReason.INVALID_METADATA,
                "Selection metadata contains forbidden sensitive or URL content.",
            )
        normalized.append((key, item_value))
    ordered = tuple(sorted(normalized))
    if len({key for key, _ in ordered}) != len(ordered):
        _invalid(
            SelectionReason.INVALID_METADATA,
            "Selection metadata contains duplicate normalized keys.",
        )
    return ordered


def _invalid(reason: SelectionReason, explanation: str) -> NoReturn:
    raise InvalidSelectionRequestError(reason, explanation)
