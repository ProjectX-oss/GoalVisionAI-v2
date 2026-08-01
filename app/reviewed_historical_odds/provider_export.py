"""Deterministic bulk planning and strict authorization gates; no implicit download."""

from __future__ import annotations

from dataclasses import replace
import math

from app.reviewed_real_historical_data.models import SourceApprovalStatus

from .fingerprint import sha256_fingerprint
from .provider_models import BulkRequestPlan, CoverageProbeReport, HistoricalOddsProvider, ProviderOutcome


EXPORT_CONFIRMATION = "DOWNLOAD_REVIEWED_HISTORICAL_ODDS"


def build_bulk_request_plan(
    *, provider: HistoricalOddsProvider, split_id: str, competition_query: str,
    date_from: str = "2023-05-13T13:30:00Z", date_to: str = "2025-05-17T13:30:00Z",
    validation_events: int = 313, test_events: int = 313, page_size: int = 100,
) -> BulkRequestPlan:
    if page_size <= 0: raise ValueError("page_size must be positive")
    events = validation_events + test_events
    pages = math.ceil(events / page_size)
    baseline = pages + events
    margin = math.ceil(baseline * .10)
    raw = dict(
        provider=provider, split_id=split_id, competition_query=competition_query,
        date_from=date_from, date_to=date_to, expected_validation_events=validation_events,
        expected_test_events=test_events, fixture_list_requests=pages, fixture_detail_requests=0,
        odds_history_requests=events, pagination_requests=max(0, pages - 1), market_expansion_requests=0,
        bookmaker_expansion_requests=0, baseline_requests=baseline, safety_margin_requests=margin,
        total_expected_requests=baseline + margin, estimated_quota_units=None,
        quota_estimate_status="UNKNOWN_UNTIL_AUTHORIZED_PROVIDER_RESPONSE",
        estimated_duration_seconds=None, estimated_raw_bytes=events * 75_000,
        estimated_normalized_bytes=events * 25_000,
        planning_assumptions=(
            "626 immutable VALIDATION plus TEST fixtures", f"fixture listing page size {page_size}",
            "one odds-history request per fixture", "10 percent request safety margin",
            "75 KB raw and 25 KB normalized storage per fixture", "no monetary cost inferred",
        ),
    )
    fingerprint = sha256_fingerprint(raw)
    return BulkRequestPlan(plan_id=f"historical-odds-provider-plan-{fingerprint}", **raw, plan_fingerprint=fingerprint)


def assert_export_authorized(
    *, confirmation: str, credential_configured: bool, source_approval_status: SourceApprovalStatus,
    coverage_report: CoverageProbeReport, available_quota: int | None, plan: BulkRequestPlan,
) -> None:
    blockers = []
    if confirmation != EXPORT_CONFIRMATION: blockers.append("EXACT_CONFIRMATION_REQUIRED")
    if not credential_configured: blockers.append("PROVIDER_CREDENTIAL_NOT_CONFIGURED")
    if not source_approval_status.permits_import: blockers.append("SOURCE_TERMS_NOT_APPROVED")
    if coverage_report.status != ProviderOutcome.PROVIDER_COVERAGE_CONFIRMED: blockers.append("PROVIDER_COVERAGE_NOT_CONFIRMED")
    if available_quota is None or available_quota < plan.total_expected_requests: blockers.append("PROVIDER_QUOTA_NOT_CONFIRMED_SUFFICIENT")
    if blockers: raise PermissionError(",".join(blockers))


def verify_resume_manifest(page_manifest: tuple[tuple[int, str, str], ...]) -> None:
    expected_page = 1
    seen_hashes = set()
    for page, response_hash, state_hash in page_manifest:
        if page != expected_page or len(response_hash) != 64 or len(state_hash) != 64 or response_hash in seen_hashes:
            raise ValueError("Export resume manifest is not a contiguous immutable chain")
        expected_page += 1; seen_hashes.add(response_hash)
