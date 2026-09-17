"""Fail-closed validation of selection, bankroll, exposure, and provenance."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import NoReturn

from app.market_value_assessment import (
    ActionabilityStatus,
    FreshnessState,
    MarketValueAssessment,
    ValueClassification,
)
from app.market_value_assessment.fingerprint import assessment_fingerprint
from app.official_prediction_candidate_registry import (
    OfficialPredictionReasoningFact,
)
from app.official_prediction_selection import (
    AssessmentEligibilityEvaluation,
    AssessmentEligibilityStatus,
    SelectionDecisionWithEvaluations,
    SelectedOfficialPrediction,
)
from app.official_prediction_selection.fingerprint import (
    logical_market_identity,
    selected_fingerprint,
)
from app.official_prediction_selection.ranking import ranking_values
from app.publication_quality_gate import (
    ConfidenceLevel,
    FactStatus,
    LineupStatus,
    MarketAvailability,
)
from app.risk_management import CorrelationGroup, ExposureSnapshot, RiskProductScope

from .exceptions import (
    CandidatePreparationPersistenceError,
    CandidatePreparationProvenanceError,
    CandidatePreparationScopeError,
    CandidatePreparationValidationError,
)
from .fingerprint import (
    bankroll_context_fingerprint,
    exposure_context_fingerprint,
)
from .models import (
    CandidatePreparationReason,
    OfficialBankrollPreparationContext,
    OfficialCandidatePreparationCommand,
    OfficialCandidateRegistrationFacts,
    OfficialExposurePreparationContext,
)
from .policy import OfficialCandidatePreparationPolicy
from .ports import SelectionHistoryReader, ValueAssessmentHistoryReader


_FORBIDDEN = re.compile(
    r"https?://|www\.|t\.me/|token|secret|password|api[_ -]?key|affiliate|promo",
    re.IGNORECASE,
)
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._:/-]*$")
_RESERVED_METADATA_KEYS = {
    "assessment_fingerprint",
    "bankroll_fingerprint",
    "bankroll_snapshot_identity",
    "bookmaker_id",
    "calibrated_assembly_fingerprint",
    "calibrated_assembly_id",
    "calibration_set_fingerprint",
    "calibration_set_id",
    "candidate_preparation_policy",
    "candidate_facts_fingerprint",
    "calibration_artifact_references",
    "exposure_fingerprint",
    "exposure_decision",
    "exposure_snapshot_identity",
    "fair_decimal_odds",
    "fair_probability",
    "feature_set_id",
    "freshness_calibrated",
    "freshness_odds",
    "freshness_overall",
    "implied_probability",
    "inference_id",
    "integration_request_identity",
    "metadata_version",
    "model_name",
    "model_input_id",
    "odds_fingerprint",
    "odds_record_id",
    "probability_edge_absolute",
    "probability_edge_relative",
    "preparation_request_fingerprint",
    "ranking_policy_version",
    "risk_assessment_id",
    "risk_decision",
    "risk_fingerprint",
    "risk_handoff_fingerprint",
    "risk_policy_version",
    "risk_reason_codes",
    "risk_warning_codes",
    "bankroll_available_amount",
    "bankroll_currency",
    "bankroll_current_amount",
    "bankroll_reserved_exposure",
    "selection_decision_id",
    "selection_fingerprint",
    "selection_policy_version",
    "selection_request_identity",
    "selected_rank",
    "selected_value_assessment_id",
    "source_model_artifact_id",
    "source_provider",
    "source_run_identity",
    "source_snapshot_id",
    "stake_amount",
    "stake_band",
    "stake_currency",
    "stake_internal_percentage",
    "value_classification",
    "value_expected_return",
}


@dataclass(frozen=True, slots=True)
class ValidatedCandidatePreparation:
    command: OfficialCandidatePreparationCommand
    selection: SelectedOfficialPrediction
    evaluation: AssessmentEligibilityEvaluation
    assessment: MarketValueAssessment


def validate_candidate_preparation(
    command: OfficialCandidatePreparationCommand,
    policy: OfficialCandidatePreparationPolicy,
    selections: SelectionHistoryReader,
    assessments: ValueAssessmentHistoryReader,
) -> ValidatedCandidatePreparation:
    if not isinstance(command, OfficialCandidatePreparationCommand):
        _invalid(CandidatePreparationReason.INVALID_REQUEST, "Immutable command required.")
    request_identity = _text(
        command.integration_request_identity,
        "Integration request identity",
    )
    if command.integration_policy_version != policy.version:
        _invalid(
            CandidatePreparationReason.POLICY_INCOMPATIBLE,
            "Integration policy version is unsupported.",
        )
    if command.metadata_version != policy.metadata_version:
        _invalid(
            CandidatePreparationReason.POLICY_INCOMPATIBLE,
            "Integration metadata version is unsupported.",
        )
    if command.bankroll_scope is not RiskProductScope.OFFICIAL:
        raise CandidatePreparationScopeError(
            CandidatePreparationReason.NON_OFFICIAL_SCOPE,
            "Official preparation requires the Official bankroll scope.",
        )
    if command.destination_scope is not RiskProductScope.OFFICIAL:
        raise CandidatePreparationScopeError(
            CandidatePreparationReason.NON_OFFICIAL_SCOPE,
            "Official preparation requires the Official destination scope.",
        )
    if command.selection is None:
        _invalid(
            CandidatePreparationReason.NO_SELECTED_DECISION,
            "A persisted selected decision is required.",
        )
    if not isinstance(command.selection, SelectedOfficialPrediction):
        _invalid(
            CandidatePreparationReason.SELECTION_NOT_SELECTED,
            "Only a successful selected decision can enter risk processing.",
        )
    selection = command.selection
    risk_at = _timestamp(command.risk_assessment_timestamp, "Risk timestamp")
    prepared_at = _timestamp(
        command.candidate_preparation_timestamp,
        "Candidate-preparation timestamp",
    )
    kickoff = _timestamp(selection.kickoff_timestamp, "Selection kickoff")
    selected_at = _timestamp(selection.selection_timestamp, "Selection timestamp")
    if risk_at >= kickoff or prepared_at >= kickoff:
        _invalid(
            CandidatePreparationReason.INVALID_TIMESTAMP,
            "Risk and candidate preparation must precede kickoff.",
        )
    if risk_at < selected_at or prepared_at < selected_at:
        _invalid(
            CandidatePreparationReason.INVALID_TIMESTAMP,
            "Risk and preparation cannot precede the selected decision.",
        )
    if policy.require_risk_at_or_before_preparation and risk_at > prepared_at:
        _invalid(
            CandidatePreparationReason.INVALID_TIMESTAMP,
            "Risk assessment cannot postdate candidate preparation.",
        )

    persisted = _load_selection(selections, selection.selection_decision_id)
    if persisted is None or persisted.decision != selection:
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.PERSISTED_SELECTION_MISMATCH,
            "Selected decision differs from immutable selection history.",
        )
    selected_evaluations = tuple(
        item
        for item in persisted.evaluations
        if item.value_assessment_id == selection.selected_value_assessment_id
    )
    if len(selected_evaluations) != 1:
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.PROVENANCE_INCOMPLETE,
            "Selected assessment evaluation is missing or ambiguous.",
        )
    evaluation = selected_evaluations[0]
    if evaluation.eligibility_status is not AssessmentEligibilityStatus.ELIGIBLE:
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.PROVENANCE_INCOMPLETE,
            "Selected assessment evaluation is not eligible.",
        )
    assessment = _load_assessment(
        assessments, selection.selected_value_assessment_id
    )
    if assessment is None:
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.PERSISTED_ASSESSMENT_MISMATCH,
            "Selected value assessment is absent from immutable history.",
        )
    try:
        expected_assessment_fingerprint = assessment_fingerprint(assessment)
    except (AttributeError, TypeError, ValueError) as exc:
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.ASSESSMENT_FINGERPRINT_INVALID,
            "Selected assessment fingerprint cannot be verified.",
        ) from exc
    if (
        expected_assessment_fingerprint != assessment.assessment_fingerprint
        or assessment.assessment_fingerprint
        != selection.selected_assessment_fingerprint
    ):
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.ASSESSMENT_FINGERPRINT_INVALID,
            "Selected assessment fingerprint verification failed.",
        )
    expected_selection_fingerprint = selected_fingerprint(
        request_identity_fingerprint=selection.selection_request_fingerprint,
        evaluation=evaluation,
        ranking_values=ranking_values(evaluation, assessment),
        selected_rank=selection.selected_rank,
        eligible_count=selection.eligible_assessment_count,
        rejected_count=selection.rejected_assessment_count,
        selection_policy_version=selection.selection_policy_version,
        ranking_policy_version=selection.ranking_policy_version,
    )
    if expected_selection_fingerprint != selection.selection_fingerprint:
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.SELECTION_FINGERPRINT_INVALID,
            "Selected decision fingerprint verification failed.",
        )
    _selection_matches_assessment(selection, assessment, evaluation)
    _selection_policy(selection, assessment, policy)

    bankroll = _bankroll(command.bankroll, selection, risk_at, policy)
    exposure = _exposure(command.exposure, selection, risk_at, policy)
    facts = _facts(command.candidate_facts, selection, prepared_at)
    metadata = _metadata(command.metadata, policy)
    source_run = (
        _text(command.source_run_identity, "Source run identity")
        if command.source_run_identity is not None
        else None
    )
    normalized = replace(
        command,
        integration_request_identity=request_identity,
        selection=selection,
        bankroll=bankroll,
        exposure=exposure,
        candidate_facts=facts,
        risk_assessment_timestamp=risk_at,
        candidate_preparation_timestamp=prepared_at,
        source_run_identity=source_run,
        metadata=metadata,
    )
    return ValidatedCandidatePreparation(
        normalized, selection, evaluation, assessment
    )


def _load_selection(
    reader: SelectionHistoryReader, decision_id: str
) -> SelectionDecisionWithEvaluations | None:
    try:
        return reader.load_selection_with_evaluations(decision_id)
    except Exception as exc:
        raise CandidatePreparationPersistenceError(
            "Selection history lookup failed."
        ) from exc


def _load_assessment(
    reader: ValueAssessmentHistoryReader, assessment_id: str
) -> MarketValueAssessment | None:
    try:
        return reader.load_market_value_assessment(assessment_id)
    except Exception as exc:
        raise CandidatePreparationPersistenceError(
            "Value-assessment history lookup failed."
        ) from exc


def _selection_matches_assessment(
    selection: SelectedOfficialPrediction,
    assessment: MarketValueAssessment,
    evaluation: AssessmentEligibilityEvaluation,
) -> None:
    expected_identity = logical_market_identity(
        assessment.match_id,
        assessment.market_type,
        assessment.selection,
        assessment.market_line,
    )
    pairs = (
        (selection.match_id, assessment.match_id),
        (selection.kickoff_timestamp, assessment.kickoff_timestamp),
        (selection.logical_market_identity, expected_identity),
        (selection.market_type, assessment.market_type),
        (selection.selection, assessment.selection),
        (selection.market_line, assessment.market_line),
        (selection.source_provider, assessment.source_provider),
        (selection.bookmaker_id, assessment.bookmaker_id),
        (selection.fair_probability, assessment.fair_probability),
        (selection.bookmaker_decimal_odds, assessment.bookmaker_decimal_odds),
        (selection.implied_probability, assessment.implied_probability),
        (selection.fair_decimal_odds, assessment.fair_decimal_odds),
        (selection.absolute_probability_edge, assessment.absolute_probability_edge),
        (selection.relative_probability_edge, assessment.relative_probability_edge),
        (selection.expected_value, assessment.expected_value),
        (selection.expected_return, assessment.expected_return),
        (selection.value_classification, assessment.value_classification),
        (selection.source_model_artifact_id, assessment.source_model_artifact_id),
        (selection.source_model_version, assessment.source_model_version),
        (selection.source_calibrated_targets, assessment.source_calibrated_targets),
        (selection.inference_id, assessment.inference_id),
        (selection.model_input_id, assessment.model_input_id),
        (selection.source_snapshot_id, assessment.source_snapshot_id),
        (selection.feature_set_id, assessment.feature_set_id),
        (selection.calibrated_assembly_id, assessment.calibrated_assembly_id),
        (selection.calibration_set_id, assessment.calibration_set_id),
        (
            selection.calibration_set_fingerprint,
            assessment.calibration_set_fingerprint,
        ),
        (selection.odds_fingerprint, assessment.odds_fingerprint),
        (
            selection.calibrated_assembly_fingerprint,
            assessment.calibrated_assembly_fingerprint,
        ),
        (selection.value_policy_version, assessment.value_policy_version),
        (selection.freshness, evaluation.freshness),
    )
    if any(left != right for left, right in pairs):
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.PERSISTED_ASSESSMENT_MISMATCH,
            "Selected facts conflict with the persisted value assessment.",
        )


def _selection_policy(
    selection: SelectedOfficialPrediction,
    assessment: MarketValueAssessment,
    policy: OfficialCandidatePreparationPolicy,
) -> None:
    if assessment.actionability_status is not ActionabilityStatus.ACTIONABLE:
        _invalid(
            CandidatePreparationReason.SELECTION_NOT_ACTIONABLE,
            "The selected assessment is no longer structurally actionable.",
        )
    if assessment.market_type not in policy.supported_markets:
        _invalid(
            CandidatePreparationReason.UNSUPPORTED_MARKET,
            "The selected market is unsupported for Official preparation.",
        )
    states = (
        assessment.odds_freshness,
        assessment.calibrated_freshness,
        assessment.overall_freshness,
    )
    if any(state not in policy.allowed_freshness_states for state in states):
        _invalid(
            CandidatePreparationReason.SELECTION_NOT_FRESH,
            "Official candidate preparation requires fresh selected facts.",
        )
    if selection.bookmaker_decimal_odds < policy.minimum_decimal_odds:
        _invalid(
            CandidatePreparationReason.ODDS_BELOW_OFFICIAL_MINIMUM,
            "Selected odds are below the Official 1.60 minimum.",
        )
    if selection.expected_value < policy.minimum_expected_value:
        _invalid(
            CandidatePreparationReason.EV_BELOW_OFFICIAL_MINIMUM,
            "Selected expected value is below the Official 0.02 minimum.",
        )
    if selection.value_classification not in {
        ValueClassification.POSITIVE_VALUE,
        ValueClassification.STRONG_VALUE,
    }:
        _invalid(
            CandidatePreparationReason.SELECTION_NOT_ACTIONABLE,
            "Selected value classification is not Official-compatible.",
        )


def _bankroll(
    value: OfficialBankrollPreparationContext,
    selection: SelectedOfficialPrediction,
    risk_at: datetime,
    policy: OfficialCandidatePreparationPolicy,
) -> OfficialBankrollPreparationContext:
    if not isinstance(value, OfficialBankrollPreparationContext):
        _invalid(
            CandidatePreparationReason.INVALID_BANKROLL,
            "Bankroll context required.",
        )
    identity = _text(value.snapshot_identity, "Bankroll snapshot identity")
    match_id = _text(value.match_id, "Bankroll match ID")
    kickoff = _timestamp(value.kickoff_timestamp, "Bankroll kickoff")
    state = value.state
    decimals = (
        value.available_bankroll,
        value.reserved_exposure,
        state.opening_bankroll,
        state.current_bankroll,
        state.peak_bankroll,
        state.unsettled_exposure,
    )
    if any(
        not isinstance(item, Decimal) or not item.is_finite()
        for item in decimals
    ):
        _invalid(
            CandidatePreparationReason.INVALID_BANKROLL,
            "Bankroll values must be finite Decimals.",
        )
    if (
        state.product_scope is not RiskProductScope.OFFICIAL
        or state.currency != policy.currency
    ):
        raise CandidatePreparationScopeError(
            CandidatePreparationReason.NON_OFFICIAL_SCOPE,
            "Bankroll context must use the Official EUR policy.",
        )
    if (
        min(state.opening_bankroll, state.current_bankroll, state.peak_bankroll)
        <= 0
        or value.available_bankroll < 0
        or value.reserved_exposure < 0
        or value.available_bankroll > state.current_bankroll
        or value.reserved_exposure > state.current_bankroll
        or value.reserved_exposure != state.unsettled_exposure
        or value.available_bankroll
        != state.current_bankroll - value.reserved_exposure
    ):
        _invalid(
            CandidatePreparationReason.INVALID_BANKROLL,
            "Bankroll availability or reserved exposure is contradictory.",
        )
    if match_id != selection.match_id or kickoff != selection.kickoff_timestamp:
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.MATCH_MISMATCH,
            "Bankroll context does not match the selected fixture.",
        )
    if _timestamp(state.snapshot_timestamp, "Bankroll effective timestamp") > risk_at:
        _invalid(
            CandidatePreparationReason.INVALID_TIMESTAMP,
            "Bankroll snapshot cannot postdate risk assessment.",
        )
    normalized = replace(
        value,
        snapshot_identity=identity,
        match_id=match_id,
        kickoff_timestamp=kickoff,
    )
    if value.fingerprint != bankroll_context_fingerprint(normalized):
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.PROVENANCE_INCOMPLETE,
            "Bankroll fingerprint verification failed.",
        )
    return normalized


def _exposure(
    value: OfficialExposurePreparationContext,
    selection: SelectedOfficialPrediction,
    risk_at: datetime,
    policy: OfficialCandidatePreparationPolicy,
) -> OfficialExposurePreparationContext:
    if not isinstance(value, OfficialExposurePreparationContext):
        _invalid(
            CandidatePreparationReason.INVALID_EXPOSURE,
            "Exposure context required.",
        )
    identity = _text(value.snapshot_identity, "Exposure snapshot identity")
    match_id = _text(value.match_id, "Exposure match ID")
    kickoff = _timestamp(value.kickoff_timestamp, "Exposure kickoff")
    snapshot = value.snapshot
    if not isinstance(snapshot, ExposureSnapshot):
        _invalid(
            CandidatePreparationReason.INVALID_EXPOSURE,
            "Exposure snapshot is malformed.",
        )
    if snapshot.product_scope is not RiskProductScope.OFFICIAL:
        raise CandidatePreparationScopeError(
            CandidatePreparationReason.NON_OFFICIAL_SCOPE,
            "Exposure context must use the Official scope.",
        )
    if any(
        not isinstance(item.current_amount, Decimal)
        or not item.current_amount.is_finite()
        or item.current_amount < 0
        or item.currency != policy.currency
        for item in snapshot.positions
    ):
        _invalid(
            CandidatePreparationReason.INVALID_EXPOSURE,
            "Exposure positions must contain non-negative Official EUR amounts.",
        )
    if match_id != selection.match_id or kickoff != selection.kickoff_timestamp:
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.MATCH_MISMATCH,
            "Exposure context does not match the selected fixture.",
        )
    if (
        _timestamp(snapshot.snapshot_timestamp, "Exposure effective timestamp")
        > risk_at
    ):
        _invalid(
            CandidatePreparationReason.INVALID_TIMESTAMP,
            "Exposure snapshot cannot postdate risk assessment.",
        )
    ordered = tuple(
        sorted(
            snapshot.positions,
            key=lambda item: (item.exposure_type.value, item.scope_key),
        )
    )
    normalized_snapshot = replace(snapshot, positions=ordered)
    normalized = replace(
        value,
        snapshot_identity=identity,
        match_id=match_id,
        kickoff_timestamp=kickoff,
        snapshot=normalized_snapshot,
    )
    if value.fingerprint != exposure_context_fingerprint(normalized):
        raise CandidatePreparationProvenanceError(
            CandidatePreparationReason.PROVENANCE_INCOMPLETE,
            "Exposure fingerprint verification failed.",
        )
    return normalized


def _facts(
    value: OfficialCandidateRegistrationFacts,
    selection: SelectedOfficialPrediction,
    prepared_at: datetime,
) -> OfficialCandidateRegistrationFacts:
    if not isinstance(value, OfficialCandidateRegistrationFacts):
        _invalid(
            CandidatePreparationReason.INVALID_REQUEST,
            "Typed candidate facts required.",
        )
    if value.fixture_id <= 0:
        _invalid(
            CandidatePreparationReason.INVALID_REQUEST,
            "Fixture ID must be positive.",
        )
    required_text = (
        value.source_event_id,
        value.odds_source_id,
        value.competition_name,
        value.home_team_name,
        value.away_team_name,
        value.source_data_version,
    )
    if any(not isinstance(item, str) or not item.strip() for item in required_text):
        _invalid(
            CandidatePreparationReason.PROVENANCE_INCOMPLETE,
            "Candidate identity facts are incomplete.",
        )
    if (
        not isinstance(value.raw_model_probability, Decimal)
        or not value.raw_model_probability.is_finite()
        or not Decimal("0.001")
        <= value.raw_model_probability
        <= Decimal("0.999")
    ):
        _invalid(
            CandidatePreparationReason.INVALID_REQUEST,
            "Raw model probability is invalid.",
        )
    for item in (value.model_confidence, value.uncertainty):
        if item is not None and (
            not isinstance(item, Decimal)
            or not item.is_finite()
            or not Decimal("0") <= item <= Decimal("1")
        ):
            _invalid(
                CandidatePreparationReason.INVALID_REQUEST,
                "Model confidence and uncertainty must be finite probabilities.",
            )
    if value.calibration_sample_size < 0 or value.model_sample_size < 0:
        _invalid(
            CandidatePreparationReason.INVALID_REQUEST,
            "Model sample sizes cannot be negative.",
        )
    if (
        not isinstance(value.public_reasoning_facts, tuple)
        or not value.public_reasoning_facts
        or any(
            not isinstance(item, OfficialPredictionReasoningFact)
            for item in value.public_reasoning_facts
        )
    ):
        _invalid(
            CandidatePreparationReason.INVALID_REQUEST,
            "Structured public reasoning facts are required.",
        )
    for field, enum_type in (
        (value.lineup_status, LineupStatus),
        (value.injury_suspension_status, FactStatus),
        (value.confidence_level, ConfidenceLevel),
        (value.supporting_data_status, FactStatus),
        (value.market_availability, MarketAvailability),
    ):
        if not isinstance(field, enum_type):
            _invalid(
                CandidatePreparationReason.INVALID_REQUEST,
                "Candidate status facts are malformed.",
            )
    timestamps = tuple(
        item
        for item in (
            value.core_match_data_timestamp,
            value.lineup_data_timestamp,
            value.injury_suspension_data_timestamp,
        )
        if item is not None
    )
    if any(
        _timestamp(item, "Candidate source timestamp") > prepared_at
        for item in timestamps
    ):
        _invalid(
            CandidatePreparationReason.INVALID_TIMESTAMP,
            "Candidate source facts cannot postdate preparation.",
        )
    if (
        not isinstance(value.correlation_groups, tuple)
        or len(value.correlation_groups) > 32
        or any(
            not isinstance(item, CorrelationGroup)
            for item in value.correlation_groups
        )
    ):
        _invalid(
            CandidatePreparationReason.INVALID_EXPOSURE,
            "Correlation groups are malformed.",
        )
    ordered_groups = tuple(
        sorted(value.correlation_groups, key=lambda item: item.group_id)
    )
    if len({item.group_id for item in ordered_groups}) != len(ordered_groups):
        _invalid(
            CandidatePreparationReason.INVALID_EXPOSURE,
            "Correlation groups are duplicated.",
        )
    if (
        not isinstance(value.team_ids, tuple)
        or not isinstance(value.calibration_artifact_references, tuple)
        or len(value.team_ids) > 32
        or len(value.calibration_artifact_references) > 32
    ):
        _invalid(
            CandidatePreparationReason.INVALID_REQUEST,
            "Candidate reference collections exceed their bounds.",
        )
    team_ids = tuple(
        sorted(_domain_identifier(item, "Team ID") for item in value.team_ids)
    )
    if len(set(team_ids)) != len(team_ids):
        _invalid(
            CandidatePreparationReason.INVALID_REQUEST,
            "Team IDs are duplicated.",
        )
    artifacts = tuple(
        sorted(
            _text(item, "Calibration artifact reference")
            for item in value.calibration_artifact_references
        )
    )
    if len(set(artifacts)) != len(artifacts):
        _invalid(
            CandidatePreparationReason.INVALID_REQUEST,
            "Calibration artifact references are duplicated.",
        )
    return replace(
        value,
        source_event_id=_domain_identifier(value.source_event_id, "Source event ID"),
        odds_source_id=_domain_identifier(value.odds_source_id, "Odds source ID"),
        competition_id=_optional_domain_identifier(
            value.competition_id, "Competition ID"
        ),
        home_team_id=_optional_domain_identifier(value.home_team_id, "Home team ID"),
        away_team_id=_optional_domain_identifier(value.away_team_id, "Away team ID"),
        source_data_version=_domain_identifier(
            value.source_data_version, "Source data version"
        ),
        correlation_groups=ordered_groups,
        team_ids=team_ids,
        calibration_artifact_references=artifacts,
        model_name=(
            _text(value.model_name, "Model name")
            if value.model_name is not None
            else None
        ),
        market_family=(
            _text(value.market_family, "Market family")
            if value.market_family is not None
            else None
        ),
    )


def _metadata(
    value: object, policy: OfficialCandidatePreparationPolicy
) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple) or len(value) > policy.maximum_metadata_items:
        _invalid(
            CandidatePreparationReason.INVALID_METADATA,
            "Metadata must be a bounded immutable tuple.",
        )
    normalized: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            _invalid(
                CandidatePreparationReason.INVALID_METADATA,
                "Metadata must contain text pairs.",
            )
        key = _identifier(item[0], "Metadata key")
        item_value = _text(
            item[1], "Metadata value", policy.maximum_metadata_value_length
        )
        if _FORBIDDEN.search(key) or _FORBIDDEN.search(item_value):
            _invalid(
                CandidatePreparationReason.INVALID_METADATA,
                "Metadata contains unsafe content.",
            )
        normalized.append((key, item_value))
    ordered = tuple(sorted(normalized))
    if len({key for key, _ in ordered}) != len(ordered):
        _invalid(
            CandidatePreparationReason.INVALID_METADATA,
            "Metadata keys are duplicated.",
        )
    if any(key in _RESERVED_METADATA_KEYS for key, _ in ordered):
        _invalid(
            CandidatePreparationReason.INVALID_METADATA,
            "Metadata cannot replace deterministic provenance fields.",
        )
    return ordered


def _text(value: object, label: str, maximum: int = 512) -> str:
    if not isinstance(value, str):
        _invalid(CandidatePreparationReason.INVALID_REQUEST, f"{label} must be text.")
    normalized = " ".join(unicodedata.normalize("NFKC", value).strip().split())
    if not normalized or len(normalized) > maximum:
        _invalid(CandidatePreparationReason.INVALID_REQUEST, f"{label} is malformed.")
    return normalized


def _identifier(value: object, label: str) -> str:
    normalized = _text(value, label, 128).casefold()
    if _IDENTIFIER.fullmatch(normalized) is None:
        _invalid(CandidatePreparationReason.INVALID_METADATA, f"{label} is malformed.")
    return normalized


def _domain_identifier(value: object, label: str) -> str:
    normalized = _text(value, label, 128).casefold()
    if _IDENTIFIER.fullmatch(normalized) is None:
        _invalid(CandidatePreparationReason.INVALID_REQUEST, f"{label} is malformed.")
    return normalized


def _optional_domain_identifier(value: object, label: str) -> str | None:
    return None if value is None else _domain_identifier(value, label)


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        _invalid(CandidatePreparationReason.INVALID_TIMESTAMP, f"{label} must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _invalid(reason: CandidatePreparationReason, explanation: str) -> NoReturn:
    raise CandidatePreparationValidationError(reason, explanation)
