"""Provider-neutral contracts for bounded historical-odds acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import SourceOddsEvent, SourceOddsQuote


class HistoricalOddsProvider(str, Enum):
    THESTATSAPI = "thestatsapi"
    THE_ODDS_API = "the_odds_api"


class ProviderOutcome(str, Enum):
    PROVIDER_CREDENTIAL_VALID = "PROVIDER_CREDENTIAL_VALID"
    PROVIDER_COVERAGE_CONFIRMED = "PROVIDER_COVERAGE_CONFIRMED"
    PROVIDER_COVERAGE_PARTIAL = "PROVIDER_COVERAGE_PARTIAL"
    PROVIDER_COVERAGE_INSUFFICIENT = "PROVIDER_COVERAGE_INSUFFICIENT"
    PROVIDER_AUTHORIZATION_REQUIRED = "PROVIDER_AUTHORIZATION_REQUIRED"
    PROVIDER_CREDENTIAL_NOT_CONFIGURED = "PROVIDER_CREDENTIAL_NOT_CONFIGURED"
    PROVIDER_AUTHENTICATION_FAILED = "PROVIDER_AUTHENTICATION_FAILED"
    PROVIDER_QUOTA_INSUFFICIENT = "PROVIDER_QUOTA_INSUFFICIENT"
    PROVIDER_TERMS_REVIEW_REQUIRED = "PROVIDER_TERMS_REVIEW_REQUIRED"
    PROVIDER_RESPONSE_INCOMPATIBLE = "PROVIDER_RESPONSE_INCOMPATIBLE"


class ExportExecutionStatus(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True, slots=True)
class ProviderCredentialConfig:
    provider: HistoricalOddsProvider
    environment_variable: str
    configured: bool
    secret_value: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderCompetition:
    provider_competition_id: str
    name: str
    country: str | None
    slug: str | None


@dataclass(frozen=True, slots=True)
class ProviderFixture:
    provider_fixture_id: str
    provider_competition_id: str
    kickoff_utc: str
    home_team: str
    away_team: str
    status: str
    season_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderQuotaSnapshot:
    remaining: int | None
    used: int | None
    limit: int | None
    retry_after_seconds: int | None
    fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class ProviderResponseReceipt:
    request_number: int
    method: str
    sanitized_endpoint: str
    status_code: int
    response_sha256: str
    byte_count: int
    quota: ProviderQuotaSnapshot
    receipt_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    provider: HistoricalOddsProvider
    base_url: str
    authentication_scheme: str
    advertised_history: str
    advertised_bookmakers: tuple[str, ...]
    advertised_markets: tuple[str, ...]
    opening_price_claimed: bool
    last_seen_price_claimed: bool
    rate_limit_per_minute: int | None
    monthly_request_limit: int | None
    metadata_timestamp_utc: str
    metadata_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class CoverageSamplePeriod:
    name: str
    partition: str
    date_from: str
    date_to: str


@dataclass(frozen=True, slots=True)
class CoverageProbeRequest:
    provider: HistoricalOddsProvider
    competition_query: str
    date_from: str
    date_to: str
    sample_limit: int = 10
    max_requests: int = 25
    request_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class CoverageProbeReport:
    provider: HistoricalOddsProvider
    status: ProviderOutcome
    credential_status: ProviderOutcome
    provider_competition_id: str | None
    sample_periods: tuple[CoverageSamplePeriod, ...]
    successful_sample_count: int
    failed_sample_count: int
    request_count: int
    fixture_count: int
    odds_fixture_count: int
    normalized_quote_count: int
    bookmakers: tuple[str, ...]
    markets: tuple[str, ...]
    opening_available: bool
    last_seen_available: bool
    capture_timestamps_complete: bool
    earliest_fixture_date: str | None
    latest_fixture_date: str | None
    validation_periods_covered: tuple[str, ...]
    test_periods_covered: tuple[str, ...]
    quota: ProviderQuotaSnapshot
    reason_codes: tuple[str, ...]
    response_receipts: tuple[ProviderResponseReceipt, ...]
    normalized_events: tuple[SourceOddsEvent, ...] = ()
    normalized_quotes: tuple[SourceOddsQuote, ...] = ()
    report_fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class BulkRequestPlan:
    plan_id: str
    provider: HistoricalOddsProvider
    split_id: str
    competition_query: str
    date_from: str
    date_to: str
    expected_validation_events: int
    expected_test_events: int
    fixture_list_requests: int
    fixture_detail_requests: int
    odds_history_requests: int
    pagination_requests: int
    market_expansion_requests: int
    bookmaker_expansion_requests: int
    baseline_requests: int
    safety_margin_requests: int
    total_expected_requests: int
    estimated_quota_units: int | None
    quota_estimate_status: str
    estimated_duration_seconds: int | None
    estimated_raw_bytes: int
    estimated_normalized_bytes: int
    planning_assumptions: tuple[str, ...]
    plan_fingerprint: str


@dataclass(frozen=True, slots=True)
class ProviderExportPackage:
    schema_version: str
    provider: HistoricalOddsProvider
    provider_version: str
    plan_id: str
    competition_id: str
    requested_date_from: str
    requested_date_to: str
    acquisition_timestamp_utc: str
    page_manifest: tuple[tuple[int, str, str], ...]
    fixtures: tuple[ProviderFixture, ...]
    odds_records: tuple[SourceOddsQuote, ...]
    pagination_state: str
    quota_summary: ProviderQuotaSnapshot
    completion_status: ExportExecutionStatus
    export_fingerprint: str = ""
