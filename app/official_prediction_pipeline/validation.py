"""Fail-closed request and provenance validation."""

from __future__ import annotations

import re
from decimal import Decimal

from app.official_prediction_candidate_registry import CandidateLifecycleState
from app.risk_management import RiskAssessmentDecision, RiskProductScope

from .exceptions import PipelineValidationError
from .models import OfficialPredictionPipelineCommand, PipelineStatus
from .policy import OfficialPredictionPipelinePolicy


_UNSAFE = re.compile(r"(?:https?://|www\.|t\.me/|token|secret|credential|affiliate|promo\s*code)", re.I)
_SUPPORTED = {"MATCH WINNER", "DOUBLE CHANCE", "TOTALS", "BTTS"}
_PROVENANCE_KEYS = (
    "preparation_execution_id", "selection_decision_id", "selected_value_assessment_id",
    "model_input_id", "inference_id", "calibrated_assembly_id", "calibration_set_id",
    "odds_snapshot_identity", "bookmaker_provider_identity", "odds_fingerprint",
    "calibrated_assembly_fingerprint", "selection_fingerprint",
    "value_assessment_fingerprint", "risk_fingerprint",
    "candidate_preparation_fingerprint", "bankroll_snapshot_identity",
    "exposure_snapshot_identity",
)


def validate_command(command: object, policy: OfficialPredictionPipelinePolicy) -> OfficialPredictionPipelineCommand:
    if not isinstance(command, OfficialPredictionPipelineCommand):
        _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "INVALID_REQUEST", "A typed pipeline command is required.")
    assert isinstance(command, OfficialPredictionPipelineCommand)
    if command.pipeline_policy_version != policy.version or command.metadata_version != policy.metadata_version:
        _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "UNSUPPORTED_POLICY", "Pipeline policy or metadata version is unsupported.")
    if command.candidate is None or command.assembly_request is None:
        _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "MISSING_CANDIDATE", "Candidate and assembly facts are required.")
    if not command.pipeline_request_identity.strip() or not command.candidate_id.strip() or command.candidate_version <= 0:
        _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "INVALID_IDENTITY", "Request and candidate identities are required.")
    lifecycle = _enum(command.candidate_lifecycle_status)
    if lifecycle != CandidateLifecycleState.READY.value:
        _fail(PipelineStatus.REJECTED_CANDIDATE_STATE, lifecycle or "UNKNOWN_STATE", "Only a READY candidate can execute.")
    if _enum(command.bankroll_scope) != RiskProductScope.OFFICIAL.value or _enum(command.destination_scope) != RiskProductScope.OFFICIAL.value:
        _fail(PipelineStatus.REJECTED_SCOPE, "NON_OFFICIAL_SCOPE", "Official bankroll and destination scopes are required.")
    candidate = command.candidate
    prepared = candidate.prepared
    request = command.assembly_request
    prediction = request.prediction
    expected_identity = (
        candidate.registry_candidate_id == command.candidate_id,
        candidate.candidate_version == command.candidate_version,
        candidate.content_fingerprint == command.candidate_fingerprint,
        prepared.match_id == command.match_id == prediction.match_id,
        prepared.kickoff_timestamp == command.kickoff_timestamp == prediction.kickoff_timestamp,
        request.evaluation_timestamp == command.quality_gate_evaluation_timestamp,
        prepared.decimal_odds == command.bookmaker_odds == prediction.decimal_odds,
        prepared.supplied_expected_value == command.expected_value == prediction.expected_value,
        _normalize(prepared.market_identity.market.value) == _normalize(command.normalized_market),
        _normalize(prepared.market_identity.selection) == _normalize(command.normalized_selection),
        prepared.market_identity.market_line == command.normalized_line == prediction.market_line,
    )
    if not all(expected_identity):
        _fail(PipelineStatus.REJECTED_PROVENANCE, "CANDIDATE_FACT_MISMATCH", "Candidate, command, and orchestration facts conflict.")
    if getattr(prepared, "is_live", False) or getattr(prepared, "is_accumulator", False):
        _fail(PipelineStatus.REJECTED_SCOPE, "NON_SINGLE_PREMATCH", "Live and accumulator candidates are forbidden.")
    market = _normalize(command.normalized_market)
    if market not in _SUPPORTED or "CORRECT SCORE" in market or "EXACT SCORE" in market:
        _fail(PipelineStatus.REJECTED_SCOPE, "UNSUPPORTED_MARKET", "Only supported single Official markets are allowed.")
    for value, label in ((command.quality_gate_evaluation_timestamp, "Quality Gate"), (command.pipeline_execution_timestamp, "Pipeline")):
        if value.tzinfo is None or value.utcoffset() is None or value >= command.kickoff_timestamp:
            _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "INVALID_TIMESTAMP", f"{label} timestamp must be aware and before kickoff.")
    upstream = (prepared.prediction_creation_timestamp, prepared.odds_timestamp, prepared.core_match_data_timestamp, prepared.registration_timestamp)
    if any(item.tzinfo is None or item.utcoffset() is None or item > command.pipeline_execution_timestamp for item in upstream):
        _fail(PipelineStatus.REJECTED_PROVENANCE, "UPSTREAM_TIMESTAMP_CONFLICT", "Pipeline execution precedes required upstream facts.")
    for value, label in ((command.bookmaker_odds, "odds"), (command.calibrated_probability, "probability"), (command.fair_odds, "fair odds"), (command.implied_probability, "implied probability"), (command.expected_value, "EV"), (command.internal_stake_percentage, "stake percentage"), (command.stake_amount, "stake amount")):
        if not isinstance(value, Decimal) or not value.is_finite():
            _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "MALFORMED_DECIMAL", f"{label} must be a finite Decimal.")
    if command.bookmaker_odds < policy.minimum_odds:
        _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "ODDS_BELOW_MINIMUM", "Candidate odds are below 1.60.")
    if command.expected_value < policy.minimum_expected_value:
        _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "EV_BELOW_MINIMUM", "Candidate EV is below 0.02.")
    if not Decimal("0") < command.calibrated_probability < Decimal("1") or command.fair_odds <= Decimal("1") or not Decimal("0") < command.implied_probability < Decimal("1"):
        _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "INVALID_PROBABILITY", "Probability and fair-odds facts are malformed.")
    if command.stake_recommendation is None or command.stake_amount <= 0 or command.internal_stake_percentage <= 0:
        _fail(PipelineStatus.REJECTED_PROVENANCE, "INVALID_STAKE", "A positive upstream stake recommendation is required.")
    if _enum(command.risk_outcome) not in {RiskAssessmentDecision.ELIGIBLE.value, RiskAssessmentDecision.REDUCED_STAKE.value}:
        _fail(PipelineStatus.REJECTED_PROVENANCE, "INVALID_RISK_OUTCOME", "Candidate risk outcome is not publication eligible.")
    missing = tuple(name for name in _PROVENANCE_KEYS if not str(getattr(command, name, "")).strip())
    if missing:
        _fail(PipelineStatus.REJECTED_PROVENANCE, "PROVENANCE_INCOMPLETE", "Required model, calibration, selection, risk, bankroll, or exposure provenance is missing.")
    provenance = dict(prepared.provenance)
    expected = {
        "selection_decision_id": command.selection_decision_id,
        "selected_value_assessment_id": command.selected_value_assessment_id,
        "model_input_id": command.model_input_id,
        "inference_id": command.inference_id,
        "calibrated_assembly_id": command.calibrated_assembly_id,
        "calibration_set_id": command.calibration_set_id,
        "odds_record_id": command.odds_snapshot_identity,
        "bookmaker_id": command.bookmaker_provider_identity,
        "odds_fingerprint": command.odds_fingerprint,
        "calibrated_assembly_fingerprint": command.calibrated_assembly_fingerprint,
        "selection_fingerprint": command.selection_fingerprint,
        "assessment_fingerprint": command.value_assessment_fingerprint,
        "risk_fingerprint": command.risk_fingerprint,
        "preparation_request_fingerprint": command.candidate_preparation_fingerprint,
        "bankroll_snapshot_identity": command.bankroll_snapshot_identity,
        "exposure_snapshot_identity": command.exposure_snapshot_identity,
    }
    if any(provenance.get(key) != value for key, value in expected.items()):
        _fail(PipelineStatus.REJECTED_PROVENANCE, "PROVENANCE_CONFLICT", "Candidate provenance conflicts with the command.")
    if len(command.metadata) > policy.maximum_metadata_items or any(not key.strip() or not value.strip() or _UNSAFE.search(key) or _UNSAFE.search(value) for key, value in command.metadata):
        _fail(PipelineStatus.REJECTED_INVALID_REQUEST, "INVALID_METADATA", "Metadata contains unsafe or uncontrolled content.")
    return command


def _enum(value: object) -> str:
    return str(getattr(value, "value", value)).strip().upper()


def _normalize(value: str) -> str:
    return " ".join(value.strip().upper().replace("_", " ").replace("/", " ").split())


def _fail(status: PipelineStatus, reason: str, explanation: str) -> None:
    raise PipelineValidationError(status.value, (reason,), (explanation,))
