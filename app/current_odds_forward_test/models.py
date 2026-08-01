"""Immutable contracts for Lab-only real-time forward testing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


ODDS_SCHEMA_VERSION = "goalvision-current-odds-snapshot-v1"
OBSERVATION_SCHEMA_VERSION = "goalvision-forward-test-observation-v1"
RESULT_SCHEMA_VERSION = "goalvision-forward-test-result-v1"
EVIDENCE_TIER = "FORWARD_TEST_REAL_TIME"


class CurrentOddsSourceType(str, Enum):
    API_FOOTBALL_CURRENT_ODDS = "API_FOOTBALL_CURRENT_ODDS"
    OPERATOR_SUPPLIED_CURRENT_ODDS = "OPERATOR_SUPPLIED_CURRENT_ODDS"
    OPERATOR_TRANSCRIBED_CURRENT_ODDS = "OPERATOR_TRANSCRIBED_CURRENT_ODDS"


class ObservationStatus(str, Enum):
    ANALYSIS_COMPLETED = "ANALYSIS_COMPLETED"
    NO_SELECTION = "NO_SELECTION"
    BLOCKED = "BLOCKED"


class SettlementOutcome(str, Enum):
    WON = "WON"
    LOST = "LOST"
    VOID = "VOID"
    UNSETTLED = "UNSETTLED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ForwardTestSampleStatus(str, Enum):
    FORWARD_TEST_SAMPLE_INSUFFICIENT = "FORWARD_TEST_SAMPLE_INSUFFICIENT"
    FORWARD_TEST_EARLY_EVIDENCE = "FORWARD_TEST_EARLY_EVIDENCE"
    FORWARD_TEST_REVIEWABLE = "FORWARD_TEST_REVIEWABLE"
    FORWARD_TEST_STATISTICALLY_MEANINGFUL = "FORWARD_TEST_STATISTICALLY_MEANINGFUL"


class ForwardTestIntegrityStatus(str, Enum):
    FORWARD_TEST_INTEGRITY_PASSED = "FORWARD_TEST_INTEGRITY_PASSED"
    FORWARD_TEST_INTEGRITY_BLOCKED = "FORWARD_TEST_INTEGRITY_BLOCKED"
    FORWARD_TEST_RESULT_PENDING = "FORWARD_TEST_RESULT_PENDING"


@dataclass(frozen=True, slots=True)
class CurrentOddsQuote:
    quote_id: str
    provider_source_id: str
    provider_type: CurrentOddsSourceType
    bookmaker_name: str
    provider_event_id: str
    canonical_fixture_id: str
    market: str
    selection: str
    decimal_odds: Decimal
    captured_at_utc: datetime
    source_retrieval_timestamp_utc: datetime
    provider_origin_timestamp_utc: datetime | None
    captured_at_by_goalvision: bool
    direct_bookmaker: bool
    operator_supplied: bool
    provenance: str
    quote_fingerprint: str


@dataclass(frozen=True, slots=True)
class CurrentOddsSnapshot:
    snapshot_id: str
    schema_version: str
    canonical_fixture_id: str
    kickoff_utc: datetime
    fixture_status: str
    provider_source_id: str
    provider_type: CurrentOddsSourceType
    bookmaker_name: str
    source_selected_at_utc: datetime
    captured_at_utc: datetime
    sealed_at_utc: datetime
    freshness_status: str
    quotes: tuple[CurrentOddsQuote, ...]
    snapshot_fingerprint: str


@dataclass(frozen=True, slots=True)
class ForwardTestObservation:
    observation_id: str
    schema_version: str
    evidence_tier: str
    request_id: str
    request_fingerprint: str
    analysis_id: str
    analysis_result_fingerprint: str
    odds_snapshot_id: str
    odds_snapshot_fingerprint: str
    canonical_fixture_id: str
    fixture_snapshot_fingerprint: str
    feature_snapshot_fingerprint: str | None
    model_input_fingerprint: str | None
    model_artifact_id: str | None
    model_artifact_fingerprint: str | None
    calibration_id: str | None
    calibration_fingerprint: str | None
    calibration_quality: object
    distribution_shift: object
    raw_probability_fingerprint: str | None
    calibrated_probability_fingerprint: str | None
    market_evaluations: tuple[object, ...]
    mathematical_top_market: str | None
    actionable_market: str | None
    status: ObservationStatus
    analysis_completed: bool
    actionable: bool
    forward_test_recorded: bool
    preview_available: bool
    lab_send_eligible: bool
    official_eligible: bool
    message_preview: str | None
    message_fingerprint: str | None
    rejection_reasons: tuple[str, ...]
    inference_at_utc: datetime
    created_at_utc: datetime
    observation_fingerprint: str


@dataclass(frozen=True, slots=True)
class ForwardTestResult:
    result_id: str
    schema_version: str
    observation_id: str
    canonical_fixture_id: str
    final_home_score: int
    final_away_score: int
    final_status: str
    result_source: str
    result_retrieval_timestamp_utc: datetime
    provenance: str
    result_fingerprint: str


@dataclass(frozen=True, slots=True)
class ForwardTestSettlement:
    settlement_id: str
    observation_id: str
    result_id: str
    market: str | None
    outcome: SettlementOutcome
    quoted_odds: Decimal | None
    hypothetical_flat_stake: Decimal
    hypothetical_net_return: Decimal
    reason_code: str
    settled_at_utc: datetime
    settlement_fingerprint: str


@dataclass(frozen=True, slots=True)
class ForwardTestStatistics:
    sample_status: ForwardTestSampleStatus
    total_analyses: int
    selected: int
    no_selection: int
    actionable: int
    non_actionable: int
    preview_available: int
    published: int
    unpublished: int
    settled: int
    unsettled: int
    wins: int
    losses: int
    voids: int
    hit_rate: Decimal | None
    average_quoted_odds: Decimal | None
    average_calibrated_probability: Decimal | None
    average_ev_at_capture: Decimal | None
    hypothetical_flat_stake_roi: Decimal | None
    maximum_simulated_drawdown: Decimal | None
    longest_winning_run: int
    longest_losing_run: int
    brier_score: Decimal | None
    log_loss: Decimal | None
    raw_brier_score: Decimal | None
    raw_log_loss: Decimal | None
    match_result_accuracy: Decimal | None
    per_market_accuracy: tuple[tuple[str, Decimal], ...]
    calibration_buckets: tuple[tuple[str, int, Decimal, Decimal], ...]
    confidence_buckets: tuple[tuple[str, int, int], ...]
    market_distribution: tuple[tuple[str, int], ...]
    competition_distribution: tuple[tuple[str, int], ...]
    source_distribution: tuple[tuple[str, int], ...]
    monthly_results: tuple[tuple[str, int, int], ...]
    average_feature_completeness: Decimal | None
    required_missing_count: int
    distribution_shift_counts: tuple[tuple[str, int], ...]
    calibration_quality_outcomes: tuple[tuple[str, int], ...]
    lineup_availability: tuple[tuple[str, int], ...]
    rejection_counts: tuple[tuple[str, int], ...]
    limitations: tuple[str, ...]
    statistics_fingerprint: str


@dataclass(frozen=True, slots=True)
class ForwardTestIntegrityReport:
    status: ForwardTestIntegrityStatus
    observation_id: str
    checks: tuple[tuple[str, bool], ...]
    blocker_codes: tuple[str, ...]
    report_fingerprint: str
