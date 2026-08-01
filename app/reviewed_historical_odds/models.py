"""Typed immutable records for reviewed historical pre-kickoff odds."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from app.historical_backtesting.models import SupportedMarket
from app.reviewed_real_historical_data.models import SourceApprovalStatus


class EventLinkStatus(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    REVIEWED_ALIAS_MATCH = "REVIEWED_ALIAS_MATCH"
    TIMESTAMP_TOLERANCE_MATCH = "TIMESTAMP_TOLERANCE_MATCH"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    NO_MATCH = "NO_MATCH"
    CONFLICTING_MATCH = "CONFLICTING_MATCH"


class QuoteTimingStatus(str, Enum):
    OPENING = "OPENING"
    FIXED_CUTOFF = "FIXED_CUTOFF"
    CLOSING_PRE_KICKOFF = "CLOSING_PRE_KICKOFF"
    PRE_KICKOFF_OTHER = "PRE_KICKOFF_OTHER"
    POST_KICKOFF = "POST_KICKOFF"
    UNKNOWN_CAPTURE_TIME = "UNKNOWN_CAPTURE_TIME"


class BacktestIntegrityStatus(str, Enum):
    BACKTEST_INTEGRITY_PASSED = "BACKTEST_INTEGRITY_PASSED"
    BACKTEST_INTEGRITY_BLOCKED = "BACKTEST_INTEGRITY_BLOCKED"


class CoverageSufficiencyStatus(str, Enum):
    SUFFICIENT_TEST_ODDS_COVERAGE = "SUFFICIENT_TEST_ODDS_COVERAGE"
    INSUFFICIENT_TEST_ODDS_COVERAGE = "INSUFFICIENT_TEST_ODDS_COVERAGE"
    REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE = "REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE"


class QuoteSelectionPolicyType(str, Enum):
    FIXED_BOOKMAKER_LATEST_AT_OR_BEFORE_CUTOFF = "FIXED_BOOKMAKER_LATEST_AT_OR_BEFORE_CUTOFF"
    REVIEWED_BOOKMAKER_SET_BEST_AVAILABLE_AT_OR_BEFORE_CUTOFF = "REVIEWED_BOOKMAKER_SET_BEST_AVAILABLE_AT_OR_BEFORE_CUTOFF"


@dataclass(frozen=True, slots=True)
class OddsSourceReview:
    source_id: str
    source_name: str
    source_owner_provider: str
    source_category: str
    source_url_or_api_identifier: str
    access_method: str
    authentication_requirement: str
    terms_of_use_status: str
    licensing_or_redistribution_status: str
    commercial_use_status: str
    storage_permission: str
    derived_data_permission: str
    historical_coverage: str
    competition_coverage: str
    bookmaker_coverage: str
    market_coverage: str
    timestamp_precision: str
    quote_semantics: str
    capture_time_available: bool
    event_identity_quality: str
    rate_limits: str
    reliability_assessment: str
    review_timestamp_utc: str
    operator_note: str
    approval_status: SourceApprovalStatus
    review_fingerprint: str = ""
    pricing_or_access_tier: str = "not specified"
    redistribution_permission: str = "not specified"
    update_cadence: str = "not specified"


@dataclass(frozen=True, slots=True)
class OddsSourceFile:
    file_name: str
    sha256: str
    byte_count: int
    raw_row_count: int


@dataclass(frozen=True, slots=True)
class OddsSourceManifest:
    source_id: str
    source_version: str
    provider: str
    acquisition_timestamp_utc: str
    effective_date_start: str
    effective_date_end: str
    competition_scope: tuple[str, ...]
    season_scope: tuple[str, ...]
    bookmaker_list: tuple[str, ...]
    market_list: tuple[str, ...]
    source_files: tuple[OddsSourceFile, ...]
    raw_row_count: int
    normalized_quote_count: int
    event_count: int
    capture_time_coverage: int
    pre_kickoff_validation_coverage: int
    source_review_id: str
    parser_version: str
    normalization_version: str
    manifest_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class HistoricalMatchReference:
    historical_match_id: str
    source_match_id: str
    competition: str
    season: str
    kickoff_utc: str
    home_team: str
    away_team: str
    round_name: str | None = None


@dataclass(frozen=True, slots=True)
class SourceOddsEvent:
    source_event_id: str
    competition: str
    kickoff_utc: str
    home_team: str
    away_team: str
    season: str | None = None
    round_name: str | None = None
    venue: str | None = None
    kickoff_precision_seconds: int = 0


@dataclass(frozen=True, slots=True)
class SourceOddsQuote:
    source_quote_id: str
    source_event_id: str
    source_bookmaker_id: str
    source_bookmaker_name: str
    source_market_name: str
    source_selection_name: str
    odds_value: str
    original_odds_format: str
    captured_at_utc: str | None
    source_effective_timestamp_utc: str
    source_point: str | None = None


@dataclass(frozen=True, slots=True)
class EventLinkDecision:
    event_link_id: str
    source_event_id: str
    historical_match_id: str | None
    status: EventLinkStatus
    kickoff_delta_seconds: int | None
    home_alias_used: bool
    away_alias_used: bool
    reason_codes: tuple[str, ...]
    link_fingerprint: str


@dataclass(frozen=True, slots=True)
class NormalizedOddsQuote:
    quote_id: str
    source_quote_id: str
    source_event_id: str
    historical_match_id: str
    source_bookmaker_id: str
    source_bookmaker_name: str
    canonical_bookmaker_id: str
    canonical_bookmaker_name: str
    source_market_name: str
    canonical_market: SupportedMarket
    selection: str
    decimal_odds: Decimal
    original_odds_format: str
    normalized_decimal_conversion: str
    captured_at_utc: str
    source_effective_timestamp_utc: str
    linked_kickoff_utc: str
    source_manifest_id: str
    timing_status: QuoteTimingStatus
    provenance_fingerprint: str
    quote_fingerprint: str


@dataclass(frozen=True, slots=True)
class QuoteSelectionPolicy:
    version: str = "fixed-pinnacle-latest-at-or-before-24h-v1"
    cutoff_seconds_before_kickoff: int = 86400
    canonical_bookmaker_id: str = "pinnacle"
    policy_type: QuoteSelectionPolicyType = QuoteSelectionPolicyType.FIXED_BOOKMAKER_LATEST_AT_OR_BEFORE_CUTOFF
    reviewed_bookmaker_ids: tuple[str, ...] = ()
    historical_odds_comparison_available: bool = False


@dataclass(frozen=True, slots=True)
class QuoteSelectionDecision:
    quote_selection_id: str
    historical_match_id: str
    canonical_market: SupportedMarket
    selected_quote_id: str
    cutoff_timestamp_utc: str
    policy_version: str
    selection_fingerprint: str


@dataclass(frozen=True, slots=True)
class OddsCoverageReport:
    reviewed_match_count: int
    matches_with_any_odds: int
    matches_with_1x2_odds: int
    matches_with_totals_odds: int
    matches_with_btts_odds: int
    matches_with_all_11_markets: int
    per_market_quote_count: tuple[tuple[str, int], ...]
    per_bookmaker_coverage: tuple[tuple[str, int], ...]
    per_season_coverage: tuple[tuple[str, int], ...]
    per_capture_window_coverage: tuple[tuple[str, int], ...]
    missing_capture_timestamps: int
    post_kickoff_exclusions: int
    ambiguous_event_links: int
    unlinked_events: int
    duplicate_quote_count: int
    conflicting_quote_count: int
    decimal_conversion_errors: int
    valid_train_partition_odds_count: int
    valid_validation_partition_odds_count: int
    valid_test_partition_odds_count: int
    report_fingerprint: str

@dataclass(frozen=True, slots=True)
class BacktestIntegrityReport:
    status: BacktestIntegrityStatus
    checks: tuple[tuple[str, bool], ...]
    blocker_codes: tuple[str, ...]
    checked_quote_count: int
    checked_selection_count: int
    report_fingerprint: str


@dataclass(frozen=True, slots=True)
class OddsAcquisitionWindow:
    split_id: str
    split_fingerprint: str
    equal_kickoff_grouping_policy: str
    train_start_utc: str
    train_end_utc: str
    validation_start_utc: str
    validation_end_utc: str
    test_start_utc: str
    test_end_utc: str
    train_match_count: int
    validation_match_count: int
    test_match_count: int
    temporal_gap_count: int
    seasons: tuple[str, ...]
    required_primary_markets: tuple[SupportedMarket, ...]
    preferred_markets: tuple[SupportedMarket, ...]
    window_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class PartitionCoverageReport:
    acquisition_window_id: str
    odds_manifest_id: str | None
    coverage_status: CoverageSufficiencyStatus
    validation_matches_with_odds: int
    test_matches_with_odds: int
    test_candidate_market_count: int
    selected_quote_count: int
    ambiguous_event_count: int
    unmatched_event_count: int
    post_kickoff_exclusion_count: int
    missing_timestamp_count: int
    per_month_test_coverage: tuple[tuple[str, int], ...]
    per_market_test_coverage: tuple[tuple[str, int], ...]
    per_bookmaker_test_coverage: tuple[tuple[str, int], ...]
    blocker_codes: tuple[str, ...]
    report_fingerprint: str = ""
