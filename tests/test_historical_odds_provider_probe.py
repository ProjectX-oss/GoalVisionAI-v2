import io
import json
import os
import unittest
import urllib.error
from contextlib import redirect_stdout
from unittest.mock import patch

from app.reviewed_historical_odds.cli import main as cli_main
from app.reviewed_historical_odds.fingerprint import canonical_json
from app.reviewed_historical_odds.provider_config import load_provider_credential
from app.reviewed_historical_odds.provider_evidence import SPLIT_ID, build_credential_status_evidence
from app.reviewed_historical_odds.provider_export import (
    EXPORT_CONFIRMATION, assert_export_authorized, build_bulk_request_plan, verify_resume_manifest,
)
from app.reviewed_historical_odds.provider_http import (
    BoundedJsonHttpClient, ProviderHttpError, redact_provider_text,
)
from app.reviewed_historical_odds.provider_models import HistoricalOddsProvider, ProviderOutcome
from app.reviewed_historical_odds.provider_probe import (
    canonical_sample_periods, prepare_probe_request, run_coverage_probe,
)
from app.reviewed_historical_odds.thestatsapi_provider import TheStatsApiProvider
from app.reviewed_real_historical_data.models import SourceApprovalStatus


class Response:
    status = 200
    headers = {"X-RateLimit-Remaining": "77", "X-RateLimit-Limit": "100"}

    def __init__(self, payload): self.body = json.dumps(payload).encode()
    def read(self): return self.body


def client(payloads):
    values = iter(payloads)
    return BoundedJsonHttpClient(base_url="https://example.invalid/api", secret="super-secret", opener=lambda request, timeout: Response(next(values)), sleeper=lambda _: None)


class HistoricalOddsProviderProbeTests(unittest.TestCase):
    def test_environment_is_not_read_until_loader_call(self):
        with patch.dict(os.environ, {"GOALVISION_THESTATSAPI_API_KEY": "key"}, clear=False):
            value = load_provider_credential(HistoricalOddsProvider.THESTATSAPI)
        self.assertTrue(value.configured); self.assertEqual(value.secret_value, "key")

    def test_missing_credential_contains_no_secret(self):
        value = load_provider_credential(HistoricalOddsProvider.THESTATSAPI, {})
        self.assertFalse(value.configured); self.assertIsNone(value.secret_value)

    def test_redaction_covers_bearer_key_token_and_literal(self):
        value = redact_provider_text("Authorization: Bearer abc api_key=abc token:abc", ("abc",))
        self.assertNotIn("abc", value); self.assertGreaterEqual(value.count("[REDACTED]"), 3)

    def test_http_receipt_is_sanitized_and_hashed(self):
        api = client([{"data": []}]); response = api.get("matches", {"date": "2025-01-01"})
        self.assertEqual(response.receipt.status_code, 200); self.assertEqual(len(response.receipt.response_sha256), 64)
        self.assertNotIn("super-secret", response.receipt.sanitized_endpoint)
        self.assertEqual(response.receipt.quota.remaining, 77)

    def test_http_redacts_secret_query_parameters_from_receipt(self):
        api = client([{}]); response = api.get("matches", {"api_key": "query-secret"})
        self.assertNotIn("query-secret", response.receipt.sanitized_endpoint); self.assertIn("[REDACTED]", response.receipt.sanitized_endpoint)

    def test_http_timeout_is_bounded(self):
        seen = []
        api = BoundedJsonHttpClient(base_url="https://x.invalid", secret="x", timeout_seconds=3, max_retries=0, opener=lambda request, timeout: seen.append(timeout) or Response({}))
        api.get("x"); self.assertEqual(seen, [3])

    def test_http_retries_transient_at_most_twice(self):
        calls = []
        def failing(request, timeout):
            calls.append(1); raise urllib.error.URLError("down")
        with self.assertRaises(ProviderHttpError): BoundedJsonHttpClient(base_url="https://x.invalid", secret="x", opener=failing, sleeper=lambda _: None).get("x")
        self.assertEqual(len(calls), 3)

    def test_http_does_not_retry_auth_or_quota(self):
        for status in (400, 401, 403, 404, 429):
            calls = []
            def failing(request, timeout, code=status):
                calls.append(1); raise urllib.error.HTTPError(request.full_url, code, "secret", {}, None)
            with self.assertRaises(ProviderHttpError): BoundedJsonHttpClient(base_url="https://x.invalid", secret="secret", opener=failing).get("x")
            self.assertEqual(len(calls), 1)

    def test_http_rejects_invalid_bounds(self):
        for timeout, retries in ((0, 0), (1, -1), (1, 3)):
            with self.assertRaises(ValueError): BoundedJsonHttpClient(base_url="x", secret="x", timeout_seconds=timeout, max_retries=retries)

    def test_probe_request_limits_and_dates(self):
        valid = prepare_probe_request(HistoricalOddsProvider.THESTATSAPI, "bundesliga", "2023-01-01", "2025-01-01", 10, 25)
        self.assertEqual(len(valid.request_fingerprint), 64)
        for sample, requests in ((0, 25), (11, 25), (1, 1), (1, 26)):
            with self.assertRaises(ValueError): prepare_probe_request(valid.provider, "x", "2023-01-01", "2024-01-01", sample, requests)
        with self.assertRaises(ValueError): prepare_probe_request(valid.provider, "x", "2025-01-01", "2024-01-01")

    def test_sampling_is_six_stratified_periods(self):
        periods = canonical_sample_periods()
        self.assertEqual(len(periods), 6); self.assertEqual([p.partition for p in periods].count("VALIDATION"), 3); self.assertEqual([p.partition for p in periods].count("TEST"), 3)

    def test_missing_credential_probe_executes_zero_requests(self):
        request = prepare_probe_request(HistoricalOddsProvider.THESTATSAPI, "bundesliga", "2023-01-01", "2025-01-01")
        report = run_coverage_probe(request, None)
        self.assertEqual(report.status, ProviderOutcome.PROVIDER_CREDENTIAL_NOT_CONFIGURED); self.assertEqual(report.request_count, 0)

    def test_adapter_competition_and_fixture_are_deterministic(self):
        api = client([
            {"data": [{"id": 2, "name": "Bundesliga", "country": "Germany", "slug": "bundesliga"}]},
            {"data": [{"id": 9, "start_time": "2024-01-01T12:00:00Z", "home_team": {"name": "A"}, "away_team": {"name": "B"}, "status": "finished"}]},
        ])
        provider = TheStatsApiProvider(load_provider_credential(HistoricalOddsProvider.THESTATSAPI, {"GOALVISION_THESTATSAPI_API_KEY": "x"}), api)
        self.assertEqual(provider.resolve_competition("bundesliga").provider_competition_id, "2")
        fixture = provider.list_historical_fixtures("2", "2024-01-01", "2024-01-02")[0]
        self.assertEqual((fixture.home_team, fixture.away_team), ("A", "B"))

    def test_adapter_preserves_opening_and_last_seen_timestamps(self):
        api = client([{"match": {"id": "m1", "competition": "Bundesliga", "kickoff_utc": "2024-01-02T12:00:00Z", "home_team": "A", "away_team": "B"}, "odds": [
            {"bookmaker": "Pinnacle", "market": "1X2", "selection": "Home", "opening": "2.10", "opening_at": "2023-12-30T12:00:00Z", "last_seen": "2.00", "last_seen_at": "2024-01-02T10:00:00Z"}
        ]}])
        provider = TheStatsApiProvider(load_provider_credential(HistoricalOddsProvider.THESTATSAPI, {"GOALVISION_THESTATSAPI_API_KEY": "x"}), api)
        event, quotes = provider.fetch_fixture_odds_sample("m1")
        self.assertEqual(event.source_event_id, "m1"); self.assertEqual({q.source_point for q in quotes}, {"opening", "last_seen"}); self.assertTrue(all(q.captured_at_utc for q in quotes))

    def test_adapter_never_invents_capture_timestamp(self):
        api = client([{"match": {"id": "m1"}, "odds": [{"bookmaker": "P", "market": "1X2", "selection": "Home", "opening": 2.1}]}])
        provider = TheStatsApiProvider(load_provider_credential(HistoricalOddsProvider.THESTATSAPI, {"GOALVISION_THESTATSAPI_API_KEY": "x"}), api)
        _, quotes = provider.fetch_fixture_odds_sample("m1")
        self.assertIsNone(quotes[0].captured_at_utc); self.assertEqual(quotes[0].source_effective_timestamp_utc, "UNKNOWN_CAPTURE_TIME")

    def test_adapter_parses_documented_nested_bookmaker_shape(self):
        api = client([{"data": {"match_id": "m1", "bookmakers": [{"bookmaker": "Pinnacle", "markets": {"match_odds": {"home": {"opening": "2.15", "last_seen": "2.08"}, "draw": {"opening": "3.40", "last_seen": "3.50"}}}}]}}])
        provider = TheStatsApiProvider(load_provider_credential(HistoricalOddsProvider.THESTATSAPI, {"GOALVISION_THESTATSAPI_API_KEY": "x"}), api)
        event, quotes = provider.fetch_fixture_odds_sample("m1")
        self.assertEqual(event.source_event_id, "m1"); self.assertEqual(len(quotes), 4)
        self.assertEqual({q.source_bookmaker_name for q in quotes}, {"Pinnacle"}); self.assertTrue(all(q.captured_at_utc is None for q in quotes))

    def test_plan_counts_and_fingerprint_are_deterministic(self):
        first = build_bulk_request_plan(provider=HistoricalOddsProvider.THESTATSAPI, split_id=SPLIT_ID, competition_query="bundesliga")
        second = build_bulk_request_plan(provider=HistoricalOddsProvider.THESTATSAPI, split_id=SPLIT_ID, competition_query="bundesliga")
        self.assertEqual(first, second); self.assertEqual(first.odds_history_requests, 626); self.assertEqual(first.total_expected_requests, 697); self.assertIsNone(first.estimated_quota_units)

    def test_plan_rejects_invalid_page_size(self):
        with self.assertRaises(ValueError): build_bulk_request_plan(provider=HistoricalOddsProvider.THESTATSAPI, split_id="x", competition_query="x", page_size=0)

    def test_export_fails_closed_on_every_required_gate(self):
        report = run_coverage_probe(prepare_probe_request(HistoricalOddsProvider.THESTATSAPI, "x", "2023-01-01", "2025-01-01"), None)
        plan = build_bulk_request_plan(provider=HistoricalOddsProvider.THESTATSAPI, split_id="x", competition_query="x")
        with self.assertRaises(PermissionError) as raised:
            assert_export_authorized(confirmation="wrong", credential_configured=False, source_approval_status=SourceApprovalStatus.REVIEW_REQUIRED, coverage_report=report, available_quota=None, plan=plan)
        for blocker in ("EXACT_CONFIRMATION_REQUIRED", "PROVIDER_CREDENTIAL_NOT_CONFIGURED", "SOURCE_TERMS_NOT_APPROVED", "PROVIDER_COVERAGE_NOT_CONFIRMED", "PROVIDER_QUOTA_NOT_CONFIRMED_SUFFICIENT"):
            self.assertIn(blocker, str(raised.exception))

    def test_resume_manifest_requires_contiguous_unique_hashes(self):
        verify_resume_manifest(((1, "a" * 64, "b" * 64), (2, "c" * 64, "d" * 64)))
        for manifest in (((2, "a" * 64, "b" * 64),), ((1, "short", "b" * 64),), ((1, "a" * 64, "b" * 64), (2, "a" * 64, "c" * 64))):
            with self.assertRaises(ValueError): verify_resume_manifest(manifest)

    def test_evidence_is_sanitized_and_stable(self):
        first = build_credential_status_evidence({}); second = build_credential_status_evidence({})
        self.assertEqual(first, second); self.assertEqual(first["terminal_status"], "PROVIDER_CREDENTIAL_NOT_CONFIGURED")
        serialized = json.dumps(first); self.assertNotIn("secret_value", serialized); self.assertEqual(first["network_requests_executed"], 0)

    def test_cli_missing_credential_is_terminal_safe(self):
        out = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(out):
            result = cli_main(["provider-diagnose", "--provider", "thestatsapi", "--output", "json"])
        self.assertEqual(result, 0); self.assertEqual(json.loads(out.getvalue())["status"], "PROVIDER_CREDENTIAL_NOT_CONFIGURED")

    def test_cli_probe_enforces_bounds_before_network(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            cli_main(["coverage-probe", "--provider", "thestatsapi", "--competition", "bundesliga", "--date-from", "2023-01-01", "--date-to", "2025-01-01", "--sample-limit", "11"])

    def test_cli_authorized_export_is_terminal_safe_and_writes_nothing(self):
        out = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stdout(out):
            result = cli_main(["authorized-export", "--provider", "thestatsapi", "--confirmation", EXPORT_CONFIRMATION, "--destination", "never-created.json", "--output", "json"])
        document = json.loads(out.getvalue())
        self.assertEqual(result, 0); self.assertEqual(document["status"], "AUTHORIZED_EXPORT_BLOCKED"); self.assertFalse(document["destination_written"])

    def test_committed_evidence_matches_builder(self):
        path = os.path.join("docs", "rehearsals", "historical_odds_provider_coverage_probe_2026-08-01.json")
        with open(path, encoding="utf-8") as stream: committed = json.load(stream)
        self.assertEqual(committed, json.loads(canonical_json(build_credential_status_evidence({}))))


if __name__ == "__main__": unittest.main()
