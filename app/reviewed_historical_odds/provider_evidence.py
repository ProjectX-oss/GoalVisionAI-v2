"""Sanitized canonical evidence for the credential-ready provider adapter."""

from __future__ import annotations

from dataclasses import asdict

from .fingerprint import sha256_fingerprint
from .provider_config import load_provider_credential
from .provider_export import build_bulk_request_plan
from .provider_models import HistoricalOddsProvider
from .provider_probe import prepare_probe_request, run_coverage_probe


SPLIT_ID = "historical-dataset-split-a86228e7921bc560b897a3fd0e3187bb78df31adedfbc6f5ce107ff87d7d9977"
SPLIT_FINGERPRINT = "2fb37779db0dd6eab9f46cc12482809780f68c5083c499b61b137d06c318a077"


def build_credential_status_evidence(environment=None) -> dict[str, object]:
    provider = HistoricalOddsProvider.THESTATSAPI
    credential = load_provider_credential(provider, environment)
    request = prepare_probe_request(provider, "bundesliga", "2023-05-13T13:30:00Z", "2025-05-17T13:30:00Z")
    report = run_coverage_probe(request, None)
    plan = build_bulk_request_plan(provider=provider, split_id=SPLIT_ID, competition_query="bundesliga")
    evidence: dict[str, object] = {
        "schema_version": "goalvision-historical-odds-provider-coverage-probe-v1",
        "execution_timestamp_utc": "2026-08-01T00:00:00Z",
        "provider": provider.value,
        "terminal_status": report.status.value,
        "credential": {"environment_variable": credential.environment_variable, "configured": credential.configured, "secret_stored": False},
        "network_requests_executed": 0,
        "probe_request": asdict(request),
        "probe_report": asdict(report),
        "bulk_request_plan": asdict(plan),
        "split": {
            "split_id": SPLIT_ID, "split_fingerprint": SPLIT_FINGERPRINT,
            "validation_match_count": 313, "test_match_count": 313,
            "validation_start_utc": "2023-05-13T13:30:00Z", "validation_end_utc": "2024-05-11T13:30:00Z",
            "test_start_utc": "2024-05-11T16:30:00Z", "test_end_utc": "2025-05-17T13:30:00Z",
        },
        "source_review_status": "REVIEW_REQUIRED",
        "authorized_export_executed": False,
        "database_migration_required": False,
        "safety": {"telegram_calls": 0, "official_publications": 0, "bankroll_mutations": 0, "production_mutations": 0, "raw_odds_committed": 0},
        "next_required_step": "Configure the authorized credential, approve storage and usage terms, run the bounded coverage probe, then review quota before any explicitly confirmed export.",
    }
    evidence["evidence_fingerprint"] = sha256_fingerprint(evidence)
    return evidence
