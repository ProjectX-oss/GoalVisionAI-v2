"""Immutable contracts for one manual Real Match Lab analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


SCHEMA_VERSION = "goalvision-real-match-lab-analysis-v1"
INPUT_SCHEMA_VERSION = "goalvision-real-match-lab-input-v1"
OUTPUT_SCHEMA_VERSION = "goalvision-real-match-lab-output-v1"
LAB_CHAT_ID = "-1003510920417"
LAB_BOT_USERNAME = "@GoalVision_AI_Lab_Bot"
SEND_CONFIRMATION = "SEND_TO_GOALVISION_AI_LAB"
MODEL_SCOPE = "OFFICIAL_GLOBAL"


class AnalysisStatus(str, Enum):
    COMPLETED = "COMPLETED"
    NO_SELECTION = "NO_SELECTION"
    REJECTED = "REJECTED"
    CONFLICT = "CONFLICT"


class DeliveryStatus(str, Enum):
    CLAIMED = "CLAIMED"
    SENT = "SENT"
    FAILED = "FAILED"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True, slots=True)
class ManualOdds:
    snapshot_id: str
    market: str
    decimal_odds: Decimal
    source_provider: str
    bookmaker_id: str
    source_event_id: str
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class RealMatchLabInput:
    schema_version: str
    request_id: str
    environment: str
    scope: str
    operator_identity: str
    match_id: str
    competition_id: str | None
    competition: str
    season: str
    home_team_id: str | None
    home_team: str
    away_team_id: str | None
    away_team: str
    kickoff_utc: datetime
    collected_at: datetime
    source_updated_at: datetime
    source_provider: str
    source_event_id: str
    source_snapshot_id: str
    match_snapshot: object
    odds: tuple[ManualOdds, ...]
    operator_notes: str | None = None


@dataclass(frozen=True, slots=True)
class MarketEvaluation:
    market: str
    raw_probability: Decimal
    calibrated_probability: Decimal
    fair_odds: Decimal
    bookmaker_odds: Decimal
    implied_probability: Decimal
    edge: Decimal
    expected_value: Decimal
    confidence: str
    freshness: str
    selected: bool
    official_minimum_odds_pass: bool
    official_quality_gate_pass: bool
    rejection_reasons: tuple[str, ...]
    odds_fingerprint: str
    value_assessment_id: str


@dataclass(frozen=True, slots=True)
class EngineEvidence:
    snapshot_id: str
    feature_set_id: str
    feature_fingerprint: str
    model_input_id: str
    model_input_fingerprint: str
    model_artifact_id: str
    model_artifact_fingerprint: str
    calibration_set_id: str
    calibration_fingerprint: str
    inference_id: str
    inference_fingerprint: str
    calibrated_assembly_id: str
    evaluations: tuple[MarketEvaluation, ...]
    feature_age_seconds: int
    lineup_status: str
    reasoning_facts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisRecord:
    analysis_id: str
    request_id: str
    request_fingerprint: str
    result_fingerprint: str
    status: AnalysisStatus
    input: RealMatchLabInput
    evidence: EngineEvidence | None
    selected_market: MarketEvaluation | None
    message_html: str | None
    message_fingerprint: str | None
    rejection_reasons: tuple[str, ...]
    created_at: datetime
    destination_chat_id: str = LAB_CHAT_ID
    destination_bot: str = LAB_BOT_USERNAME


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    delivery_id: str
    analysis_id: str
    attempt_number: int
    status: DeliveryStatus
    destination_chat_id: str
    message_fingerprint: str
    occurred_at: datetime
    telegram_message_id: int | None = None
    reason_code: str | None = None
