"""Immutable commands, supplied odds, decisions, metrics, and outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from app.prediction_inference import RawProbabilitySet

from .policy import (
    BACKTEST_POLICY_VERSION,
    BANKROLL_POLICY_VERSION,
    DECISION_SNAPSHOT_POLICY,
    METADATA_VERSION,
    METRIC_POLICY_VERSION,
    ODDS_SELECTION_POLICY_VERSION,
    SETTLEMENT_POLICY_VERSION,
)


class SupportedMarket(str, Enum):
    HOME_WIN = "HOME_WIN"
    DRAW = "DRAW"
    AWAY_WIN = "AWAY_WIN"
    OVER_1_5 = "OVER_1_5"
    UNDER_1_5 = "UNDER_1_5"
    OVER_2_5 = "OVER_2_5"
    UNDER_2_5 = "UNDER_2_5"
    OVER_3_5 = "OVER_3_5"
    UNDER_3_5 = "UNDER_3_5"
    BTTS_YES = "BTTS_YES"
    BTTS_NO = "BTTS_NO"


class OddsMarketStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"
    VOID = "VOID"


class SettlementStatus(str, Enum):
    WON = "WON"
    LOST = "LOST"
    VOID = "VOID"
    PUSH = "PUSH"
    UNSETTLED = "UNSETTLED"
    REJECTED = "REJECTED"


class BacktestStatus(str, Enum):
    BACKTEST_COMPLETED = "BACKTEST_COMPLETED"
    IDEMPOTENT_EXISTING = "IDEMPOTENT_EXISTING"
    NO_ELIGIBLE_TEST_EXAMPLES = "NO_ELIGIBLE_TEST_EXAMPLES"
    NO_VALID_ODDS = "NO_VALID_ODDS"
    REJECTED_INVALID_REQUEST = "REJECTED_INVALID_REQUEST"
    REJECTED_SOURCE_SPLIT = "REJECTED_SOURCE_SPLIT"
    REJECTED_SOURCE_MODEL = "REJECTED_SOURCE_MODEL"
    REJECTED_SOURCE_CALIBRATION = "REJECTED_SOURCE_CALIBRATION"
    REJECTED_PARTITION_SAFETY = "REJECTED_PARTITION_SAFETY"
    REJECTED_SCHEMA_COMPATIBILITY = "REJECTED_SCHEMA_COMPATIBILITY"
    REJECTED_ODDS_PROVENANCE = "REJECTED_ODDS_PROVENANCE"
    REJECTED_BANKROLL_POLICY = "REJECTED_BANKROLL_POLICY"
    REJECTED_SETTLEMENT_DATA = "REJECTED_SETTLEMENT_DATA"
    REJECTED_PROBABILITY_CONTRACT = "REJECTED_PROBABILITY_CONTRACT"
    CONFLICT = "CONFLICT"
    PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"


@dataclass(frozen=True, slots=True)
class HistoricalOddsSnapshot:
    odds_snapshot_id: str
    source_identity: str
    source_version: str
    historical_match_id: str
    competition: str
    kickoff_utc: datetime | str
    snapshot_timestamp_utc: datetime | str
    bookmaker_identity: str
    market_identity: SupportedMarket | str
    selection_identity: str
    decimal_odds: Decimal
    currency: str | None
    market_status: OddsMarketStatus | str
    source_record_identity: str
    source_fingerprint: str
    metadata_version: str = METADATA_VERSION


@dataclass(frozen=True, slots=True)
class HistoricalOddsDataset:
    odds_dataset_id: str
    odds_dataset_fingerprint: str
    snapshots: tuple[HistoricalOddsSnapshot, ...]
    metadata_version: str = METADATA_VERSION


@dataclass(frozen=True, slots=True)
class HistoricalBacktestCommand:
    backtest_request_id: str
    backtest_run_name: str
    source_split_id: str
    source_split_fingerprint: str
    fold_id: str
    fold_fingerprint: str
    source_training_run_id: str
    source_training_run_fingerprint: str
    model_artifact_id: str
    model_artifact_fingerprint: str
    calibration_run_id: str
    calibration_run_fingerprint: str
    calibration_artifact_set_id: str
    calibration_artifact_set_fingerprint: str
    odds_dataset_id: str
    odds_dataset_fingerprint: str
    initial_bankroll: Decimal
    backtest_timestamp: datetime | str
    currency: str = "EUR"
    odds_selection_policy_version: str = ODDS_SELECTION_POLICY_VERSION
    decision_snapshot_policy: str = DECISION_SNAPSHOT_POLICY
    closing_odds_dataset_id: str | None = None
    closing_odds_dataset_fingerprint: str | None = None
    bookmaker_filters: tuple[str, ...] = ()
    backtest_policy_version: str = BACKTEST_POLICY_VERSION
    market_eligibility_policy_version: str = "official-prediction-selection-policy-v1"
    value_policy_version: str = "market-value-assessment-policy-v1"
    selection_policy_version: str = "official-prediction-selection-policy-v1"
    staking_policy_version: str = "official-risk-v1"
    settlement_policy_version: str = SETTLEMENT_POLICY_VERSION
    bankroll_policy_version: str = BANKROLL_POLICY_VERSION
    metric_policy_version: str = METRIC_POLICY_VERSION
    code_metadata_version: str = "goalvision-ai"
    dependency_metadata_version: str = "v1"
    environment_metadata_version: str = "v1"
    metadata_version: str = METADATA_VERSION
    competitions: tuple[str, ...] = ()
    seasons: tuple[str, ...] = ()
    kickoff_lower_bound: datetime | str | None = None
    kickoff_upper_bound: datetime | str | None = None
    markets: tuple[SupportedMarket | str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizedBacktestCommand:
    backtest_request_id: str
    backtest_run_name: str
    source_split_id: str
    source_split_fingerprint: str
    fold_id: str
    fold_fingerprint: str
    source_training_run_id: str
    source_training_run_fingerprint: str
    model_artifact_id: str
    model_artifact_fingerprint: str
    calibration_run_id: str
    calibration_run_fingerprint: str
    calibration_artifact_set_id: str
    calibration_artifact_set_fingerprint: str
    odds_dataset_id: str
    odds_dataset_fingerprint: str
    initial_bankroll: Decimal
    backtest_timestamp: str
    currency: str
    odds_selection_policy_version: str
    decision_snapshot_policy: str
    closing_odds_dataset_id: str | None
    closing_odds_dataset_fingerprint: str | None
    bookmaker_filters: tuple[str, ...]
    backtest_policy_version: str
    market_eligibility_policy_version: str
    value_policy_version: str
    selection_policy_version: str
    staking_policy_version: str
    settlement_policy_version: str
    bankroll_policy_version: str
    metric_policy_version: str
    code_metadata_version: str
    dependency_metadata_version: str
    environment_metadata_version: str
    metadata_version: str
    competitions: tuple[str, ...]
    seasons: tuple[str, ...]
    kickoff_lower_bound: str | None
    kickoff_upper_bound: str | None
    markets: tuple[SupportedMarket, ...]


@dataclass(frozen=True, slots=True)
class BacktestPrediction:
    prediction_row_id: str
    training_example_id: str
    historical_match_id: str
    example_fingerprint: str
    competition: str
    season: str
    kickoff_utc: str
    raw_probabilities: RawProbabilitySet
    calibrated_probabilities: RawProbabilitySet
    labels: tuple[tuple[str, int], ...]
    raw_prediction_fingerprint: str
    calibrated_prediction_fingerprint: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class StoredOddsSnapshot:
    stored_odds_row_id: str
    snapshot: HistoricalOddsSnapshot
    normalized_kickoff_utc: str
    normalized_snapshot_timestamp_utc: str
    market_identity: SupportedMarket
    market_status: OddsMarketStatus
    closing: bool
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class MarketAssessment:
    assessment_id: str
    prediction_row_id: str
    odds_row_id: str | None
    historical_match_id: str
    market_identity: SupportedMarket
    calibrated_probability: Decimal | None
    fair_odds: Decimal | None
    decimal_odds: Decimal | None
    implied_probability: Decimal | None
    expected_value: Decimal | None
    edge: Decimal | None
    odds_age_seconds: int | None
    eligible: bool
    rejection_reasons: tuple[str, ...]
    assessment_fingerprint: str
    deterministic_rank: int


@dataclass(frozen=True, slots=True)
class BacktestSelection:
    selection_id: str
    historical_match_id: str
    kickoff_utc: str
    kickoff_group_id: str
    selected_assessment_id: str
    market_identity: SupportedMarket
    decimal_odds: Decimal
    calibrated_probability: Decimal
    expected_value: Decimal
    bankroll_snapshot: Decimal
    stake_percentage: Decimal
    recommended_stake_amount: Decimal
    applied_stake_amount: Decimal
    stake_classification: str
    reduction_reason: str | None
    rejection_reason: str | None
    selection_fingerprint: str
    stake_fingerprint: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class BacktestSettlement:
    settlement_id: str
    selection_id: str
    final_home_score: int | None
    final_away_score: int | None
    status: SettlementStatus
    gross_return: Decimal
    net_profit_loss: Decimal
    settlement_reason: str
    settlement_fingerprint: str
    settled_order: int


@dataclass(frozen=True, slots=True)
class BankrollLedgerEntry:
    ledger_entry_id: str
    selection_id: str
    kickoff_group_id: str
    bankroll_before: Decimal
    stake_reserved: Decimal
    gross_return: Decimal
    net_result: Decimal
    bankroll_after: Decimal
    cumulative_profit: Decimal
    cumulative_return: Decimal
    running_peak: Decimal
    absolute_drawdown: Decimal
    percentage_drawdown: Decimal
    ledger_fingerprint: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class BacktestMetric:
    metric_row_id: str
    category: str
    grouping_identity: str
    metric_name: str
    metric_value: Decimal | None
    metric_snapshot: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class BacktestReliabilityBin:
    bin_row_id: str
    target_identity: str
    probability_phase: str
    bin_index: int
    lower_bound: Decimal
    upper_bound: Decimal
    sample_count: int
    mean_predicted_probability: Decimal | None
    observed_frequency: Decimal | None
    absolute_gap: Decimal | None
    bin_fingerprint: str


@dataclass(frozen=True, slots=True)
class BacktestExclusion:
    exclusion_id: str
    historical_match_id: str | None
    training_example_id: str | None
    market_identity: SupportedMarket | None
    stage: str
    reason: str
    detail_snapshot: str
    deterministic_order: int


@dataclass(frozen=True, slots=True)
class PreparedBacktestRun:
    backtest_run_id: str
    command: NormalizedBacktestCommand
    request_fingerprint: str
    backtest_run_fingerprint: str
    predictions: tuple[BacktestPrediction, ...]
    odds_snapshots: tuple[StoredOddsSnapshot, ...]
    assessments: tuple[MarketAssessment, ...]
    selections: tuple[BacktestSelection, ...]
    settlements: tuple[BacktestSettlement, ...]
    ledger: tuple[BankrollLedgerEntry, ...]
    metrics: tuple[BacktestMetric, ...]
    reliability_bins: tuple[BacktestReliabilityBin, ...]
    exclusions: tuple[BacktestExclusion, ...]
    aggregate_predictive_metrics: tuple[tuple[str, Decimal], ...]
    aggregate_betting_metrics: tuple[tuple[str, Decimal], ...]
    final_bankroll: Decimal
    maximum_drawdown: Decimal
    deterministic_run_snapshot: str


@dataclass(frozen=True, slots=True)
class BacktestOutcome:
    status: BacktestStatus
    backtest_run_id: str | None
    backtest_request_id: str
    request_fingerprint: str | None
    backtest_run_fingerprint: str | None
    source_split_id: str
    fold_id: str
    model_artifact_id: str
    model_artifact_fingerprint: str
    calibration_artifact_set_id: str
    calibration_artifact_set_fingerprint: str
    test_example_count: int
    prediction_count: int
    assessed_market_count: int
    selected_bet_count: int
    settled_bet_count: int
    win_count: int
    loss_count: int
    void_count: int
    initial_bankroll: Decimal
    final_bankroll: Decimal
    net_profit: Decimal
    roi: Decimal | None
    maximum_drawdown: Decimal
    aggregate_predictive_metrics: tuple[tuple[str, Decimal], ...]
    aggregate_betting_metrics: tuple[tuple[str, Decimal], ...]
    ordered_reason_codes: tuple[str, ...]
    policy_versions: tuple[tuple[str, str], ...]
    backtest_timestamp: str | None
