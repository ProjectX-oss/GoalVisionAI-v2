import io
import json
import sqlite3
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from app.database import Database, MigrationManager
from app.historical_backtesting.models import SupportedMarket
from app.reviewed_historical_odds.cli import main as cli_main
from app.reviewed_historical_odds.models import (
    BacktestIntegrityStatus, EventLinkStatus, HistoricalMatchReference,
    OddsSourceReview, QuoteSelectionPolicy, SourceOddsEvent, SourceOddsQuote,
)
from app.reviewed_historical_odds.repository import SQLiteReviewedHistoricalOddsRepository
from app.reviewed_historical_odds.service import (
    audit_backtest_integrity, bootstrap_roi_confidence_interval,
    build_coverage_report, build_manifest, decimal_odds, link_events,
    normalize_quotes, normalize_utc, prepare_source_review, require_import_approval,
    select_quotes, validate_manifest_files,
)
from app.reviewed_historical_odds.the_odds_api import parse_historical_snapshot
from app.reviewed_real_historical_data.models import SourceApprovalStatus


FIXTURE = Path(__file__).parent / "fixtures" / "reviewed_historical_odds" / "synthetic_provider_shape.json"


def review(status=SourceApprovalStatus.APPROVED_FOR_INTERNAL_DERIVED_DATA):
    return prepare_source_review(OddsSourceReview(
        source_id="test-odds", source_name="Test Odds", source_owner_provider="Test Provider",
        source_category="TEST", source_url_or_api_identifier="https://example.invalid/api",
        access_method="offline fixture", authentication_requirement="none",
        terms_of_use_status="test fixture", licensing_or_redistribution_status="test only",
        commercial_use_status="not applicable", storage_permission="test only",
        derived_data_permission="test only", historical_coverage="one event",
        competition_coverage="Bundesliga", bookmaker_coverage="two",
        market_coverage="1X2", timestamp_precision="UTC seconds",
        quote_semantics="intermediate", capture_time_available=True,
        event_identity_quality="explicit", rate_limits="none",
        reliability_assessment="deterministic test fixture",
        review_timestamp_utc="2026-07-31T19:15:00Z", operator_note="test",
        approval_status=status,
    ))


def match(kickoff="2024-01-10T18:30:00Z", home="Home FC", away="Away FC", match_id="match-1"):
    return HistoricalMatchReference(match_id, "source-1", "Bundesliga", "2023", kickoff, home, away, "round")


def parsed_and_linked():
    parsed = parse_historical_snapshot(FIXTURE)
    links = link_events(
        parsed.events, (match(),), reviewed_aliases={},
        reviewed_competition_aliases={"bundesliga germany": "bundesliga"},
    )
    quotes, rejected = normalize_quotes(
        parsed.quotes, parsed.events, links, manifest_id="manifest-1",
        acquisition_timestamp_utc="2026-07-31T19:30:00Z",
    )
    return parsed, links, quotes, rejected


class ReviewedHistoricalOddsTests(unittest.TestCase):
    def test_source_review_required_and_statuses_fail_closed(self):
        approved = review()
        self.assertTrue(approved.approval_status.permits_import)
        self.assertEqual(len(approved.review_fingerprint), 64)
        require_import_approval(approved)
        for status in (SourceApprovalStatus.REJECTED, SourceApprovalStatus.TERMS_UNCLEAR, SourceApprovalStatus.ACCESS_UNAVAILABLE, SourceApprovalStatus.REVIEW_REQUIRED):
            with self.assertRaises(PermissionError): require_import_approval(review(status))

    def test_source_review_fingerprint_is_deterministic(self):
        self.assertEqual(review().review_fingerprint, review().review_fingerprint)
        self.assertNotEqual(review().review_fingerprint, review(SourceApprovalStatus.APPROVED_FOR_CONTROLLED_RESEARCH).review_fingerprint)

    def test_parser_preserves_timestamp_event_identity_and_supported_market(self):
        parsed = parse_historical_snapshot(FIXTURE)
        self.assertEqual(parsed.snapshot_timestamp_utc, "2024-01-09T12:00:00Z")
        self.assertEqual(len(parsed.events), 1)
        self.assertEqual(len(parsed.quotes), 6)
        self.assertEqual(parsed.unsupported_market_rows, 1)
        self.assertEqual(parsed.events[0].source_event_id, "test-event-1")

    def test_manifest_determinism_file_hash_and_conflict(self):
        kwargs = dict(
            source_version="v1", acquisition_timestamp_utc="2026-07-31T19:30:00Z",
            files=(FIXTURE,), raw_row_count=6, normalized_quote_count=6, event_count=1,
            capture_time_coverage=6, pre_kickoff_validation_coverage=6,
            effective_date_start="2024-01-10T18:30:00Z", effective_date_end="2024-01-10T18:30:00Z",
            competitions=("Bundesliga",), seasons=("2023",), bookmakers=("Pinnacle", "Other Book"),
            markets=("HOME_WIN", "DRAW", "AWAY_WIN"), parser_version="test-v1",
        )
        first, second = build_manifest(review(), **kwargs), build_manifest(review(), **kwargs)
        self.assertEqual(first, second)
        self.assertEqual(len(first.manifest_fingerprint), 64)
        validate_manifest_files(first, FIXTURE.parent)
        with self.assertRaises(ValueError): validate_manifest_files(first, FIXTURE.parent / "missing")

    def test_repository_replay_is_idempotent_and_conflict_safe(self):
        db = Database(":memory:")
        repo = SQLiteReviewedHistoricalOddsRepository(db)
        item = review(); repo.append_review(item); repo.append_review(item)
        self.assertEqual(db.connection.execute("SELECT COUNT(*) FROM historical_odds_source_reviews").fetchone()[0], 1)
        with self.assertRaises(ValueError): repo.append_review(replace(item, review_fingerprint="f" * 64))
        db.close()

    def test_manifest_requires_approved_persisted_review_and_rejects_version_conflict(self):
        kwargs = dict(
            source_version="v1", acquisition_timestamp_utc="2026-07-31T19:30:00Z",
            files=(FIXTURE,), raw_row_count=6, normalized_quote_count=6, event_count=1,
            capture_time_coverage=6, pre_kickoff_validation_coverage=6,
            effective_date_start="2024-01-10T18:30:00Z", effective_date_end="2024-01-10T18:30:00Z",
            competitions=("Bundesliga",), seasons=("2023",), bookmakers=("Pinnacle",),
            markets=("HOME_WIN", "DRAW", "AWAY_WIN"), parser_version="test-v1",
        )
        item = review(); manifest = build_manifest(item, **kwargs)
        db = Database(":memory:"); repo = SQLiteReviewedHistoricalOddsRepository(db)
        with self.assertRaises(PermissionError): repo.append_manifest(manifest)
        repo.append_review(item); first_id = repo.append_manifest(manifest)
        self.assertEqual(first_id, repo.append_manifest(manifest))
        with self.assertRaises(ValueError): repo.append_manifest(replace(manifest, manifest_fingerprint="e" * 64))
        db.close()

    def test_decimal_conversion_and_invalid_odds(self):
        self.assertEqual(decimal_odds("2.5", "decimal")[0], Decimal("2.5"))
        self.assertEqual(decimal_odds("150", "american")[0], Decimal("2.5"))
        self.assertEqual(decimal_odds("-200", "american")[0], Decimal("1.5"))
        self.assertEqual(decimal_odds("3/2", "fractional")[0], Decimal("2.5"))
        for value, fmt in (("1", "decimal"), ("NaN", "decimal"), ("0", "american"), ("2", "unknown")):
            with self.assertRaises(ValueError): decimal_odds(value, fmt)

    def test_timezone_normalization_requires_awareness(self):
        self.assertEqual(normalize_utc("2024-01-10T19:30:00+01:00"), "2024-01-10T18:30:00Z")
        with self.assertRaises(ValueError): normalize_utc("2024-01-10T18:30:00")

    def test_exact_and_reviewed_alias_linkage(self):
        event = SourceOddsEvent("e", "Bundesliga", "2024-01-10T18:30:00Z", "Home FC", "Away FC")
        exact = link_events((event,), (match(),), reviewed_aliases={})[0]
        alias = link_events((replace(event, home_team="Home"),), (match(),), reviewed_aliases={"home": "Home FC"})[0]
        self.assertIs(exact.status, EventLinkStatus.EXACT_MATCH)
        self.assertIs(alias.status, EventLinkStatus.REVIEWED_ALIAS_MATCH)
        self.assertTrue(alias.home_alias_used)

    def test_reversed_fixture_is_rejected(self):
        event = SourceOddsEvent("e", "Bundesliga", "2024-01-10T18:30:00Z", "Away FC", "Home FC")
        decision = link_events((event,), (match(),), reviewed_aliases={})[0]
        self.assertIs(decision.status, EventLinkStatus.CONFLICTING_MATCH)
        self.assertIn("REVERSED_HOME_AWAY", decision.reason_codes)

    def test_competition_mismatch_is_not_linked(self):
        event = SourceOddsEvent("e", "Other League", "2024-01-10T18:30:00Z", "Home FC", "Away FC")
        decision = link_events((event,), (match(),), reviewed_aliases={})[0]
        self.assertIs(decision.status, EventLinkStatus.NO_MATCH)

    def test_ambiguous_duplicate_fixture_is_rejected(self):
        event = SourceOddsEvent("e", "Bundesliga", "2024-01-10T18:30:00Z", "Home FC", "Away FC")
        decision = link_events((event,), (match(match_id="a"), match(match_id="b")), reviewed_aliases={})[0]
        self.assertIs(decision.status, EventLinkStatus.AMBIGUOUS_MATCH)
        self.assertIsNone(decision.historical_match_id)

    def test_postponed_match_requires_explicit_tolerance(self):
        event = SourceOddsEvent("e", "Bundesliga", "2024-01-10T18:30:00Z", "Home FC", "Away FC")
        delayed = match(kickoff="2024-01-10T19:30:00Z")
        self.assertIs(link_events((event,), (delayed,), reviewed_aliases={})[0].status, EventLinkStatus.NO_MATCH)
        linked = link_events((event,), (delayed,), reviewed_aliases={}, kickoff_tolerance_seconds=3600)[0]
        self.assertIs(linked.status, EventLinkStatus.TIMESTAMP_TOLERANCE_MATCH)
        self.assertEqual(linked.kickoff_delta_seconds, 3600)

    def test_quote_normalization_maps_all_1x2_selections(self):
        _, _, quotes, rejected = parsed_and_linked()
        self.assertEqual(len(quotes), 6)
        self.assertFalse(rejected)
        self.assertEqual({item.canonical_market for item in quotes}, {SupportedMarket.HOME_WIN, SupportedMarket.DRAW, SupportedMarket.AWAY_WIN})
        self.assertTrue(all(item.decimal_odds > 1 for item in quotes))
        self.assertTrue(all(len(item.quote_fingerprint) == 64 for item in quotes))

    def test_unknown_and_post_kickoff_quotes_are_non_actionable(self):
        parsed = parse_historical_snapshot(FIXTURE); links = link_events(parsed.events, (match(),), reviewed_aliases={}, reviewed_competition_aliases={"bundesliga germany": "bundesliga"})
        unknown = replace(parsed.quotes[0], captured_at_utc=None)
        post = replace(parsed.quotes[1], captured_at_utc="2024-01-10T18:30:00Z")
        quotes, rejected = normalize_quotes((unknown, post), parsed.events, links, manifest_id="m", acquisition_timestamp_utc="2026-01-01T00:00:00Z")
        self.assertFalse(quotes)
        self.assertEqual({reason for _, reason in rejected}, {"UNKNOWN_CAPTURE_TIME", "POST_KICKOFF_ODDS"})

    def test_conflicting_duplicate_quote_rejected(self):
        parsed = parse_historical_snapshot(FIXTURE); links = link_events(parsed.events, (match(),), reviewed_aliases={}, reviewed_competition_aliases={"bundesliga germany": "bundesliga"})
        first = parsed.quotes[0]; conflict = replace(first, odds_value="8.8")
        with self.assertRaises(ValueError): normalize_quotes((first, conflict), parsed.events, links, manifest_id="m", acquisition_timestamp_utc="2026-01-01T00:00:00Z")

    def test_identical_duplicate_quote_is_idempotent(self):
        parsed = parse_historical_snapshot(FIXTURE); links = link_events(parsed.events, (match(),), reviewed_aliases={}, reviewed_competition_aliases={"bundesliga germany": "bundesliga"})
        quotes, _ = normalize_quotes((parsed.quotes[0], parsed.quotes[0]), parsed.events, links, manifest_id="m", acquisition_timestamp_utc="2026-01-01T00:00:00Z")
        self.assertEqual(len(quotes), 1)

    def test_fixed_cutoff_selection_uses_only_pinnacle_without_best_price_hindsight(self):
        _, _, quotes, _ = parsed_and_linked()
        selected = select_quotes(quotes)
        by_id = {item.quote_id: item for item in quotes}
        self.assertEqual(len(selected), 3)
        self.assertTrue(all(by_id[item.selected_quote_id].canonical_bookmaker_id == "pinnacle" for item in selected))
        self.assertTrue(all(item.cutoff_timestamp_utc == "2024-01-09T18:30:00Z" for item in selected))
        self.assertTrue(all(item.policy_version == QuoteSelectionPolicy().version for item in selected))

    def test_fixed_cutoff_excludes_late_quote(self):
        _, _, quotes, _ = parsed_and_linked()
        late = replace(quotes[0], captured_at_utc="2024-01-10T12:00:00Z")
        selected = select_quotes((late,))
        self.assertFalse(selected)

    def test_coverage_is_transparent_and_partitioned(self):
        _, links, quotes, rejected = parsed_and_linked()
        report = build_coverage_report(reviewed_match_count=10, quotes=quotes, links=links, partitions={"match-1": "TEST"}, rejected=rejected)
        self.assertEqual(report.matches_with_any_odds, 1)
        self.assertEqual(report.matches_with_1x2_odds, 1)
        self.assertEqual(report.matches_with_totals_odds, 0)
        self.assertEqual(report.matches_with_btts_odds, 0)
        self.assertEqual(report.matches_with_all_11_markets, 0)
        self.assertEqual(report.valid_test_partition_odds_count, 6)
        self.assertEqual(report.valid_train_partition_odds_count, 0)

    def test_backtest_integrity_passes_for_test_only_real_quotes(self):
        _, _, quotes, _ = parsed_and_linked(); selected = select_quotes(quotes)
        report = audit_backtest_integrity(quotes=quotes, selections=selected, partitions={"match-1": "TEST"})
        self.assertIs(report.status, BacktestIntegrityStatus.BACKTEST_INTEGRITY_PASSED)
        self.assertFalse(report.blocker_codes)
        self.assertTrue(all(value for _, value in report.checks))

    def test_backtest_integrity_blocks_train_synthetic_and_side_effects(self):
        _, _, quotes, _ = parsed_and_linked(); selected = select_quotes(quotes)
        report = audit_backtest_integrity(quotes=quotes, selections=selected, partitions={"match-1": "TRAIN"}, synthetic_odds=True, bankroll_isolated=False, production_side_effects=1)
        self.assertIs(report.status, BacktestIntegrityStatus.BACKTEST_INTEGRITY_BLOCKED)
        for reason in ("TEST_ONLY", "NO_TRAIN_VALIDATION_LEAKAGE", "NO_SYNTHETIC_ODDS", "BANKROLL_ISOLATED", "NO_PRODUCTION_SIDE_EFFECTS"):
            self.assertIn(reason, report.blocker_codes)

    def test_bootstrap_confidence_interval_is_deterministic(self):
        returns = (Decimal("1"), Decimal("-1"), Decimal("0.5"))
        first = bootstrap_roi_confidence_interval(returns, iterations=100)
        self.assertEqual(first, bootstrap_roi_confidence_interval(returns, iterations=100))
        self.assertLessEqual(first[0], first[1])
        self.assertEqual(bootstrap_roi_confidence_interval(()), (None, None))

    def test_migration_34_fresh_foreign_keys_and_append_only(self):
        db = Database(":memory:"); MigrationManager(db.connection).migrate()
        self.assertEqual(db.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], 34)
        self.assertEqual(db.connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        repo = SQLiteReviewedHistoricalOddsRepository(db, migrate=False); repo.append_review(review())
        with self.assertRaises(sqlite3.IntegrityError): db.connection.execute("UPDATE historical_odds_source_reviews SET approval_status='REJECTED'")
        with self.assertRaises(sqlite3.IntegrityError): db.connection.execute("DELETE FROM historical_odds_source_reviews")
        db.close()

    def test_evidence_fingerprints_replay(self):
        _, links, quotes, _ = parsed_and_linked()
        self.assertEqual(links, link_events(parse_historical_snapshot(FIXTURE).events, (match(),), reviewed_aliases={}, reviewed_competition_aliases={"bundesliga germany": "bundesliga"}))
        self.assertEqual(quotes, parsed_and_linked()[2])

    def test_cli_human_json_and_help_are_terminal_safe(self):
        review_path = Path(__file__).parent.parent / "docs" / "data_sources" / "the_odds_api_public_sample_review_v1.json"
        for args in (("review-source", str(review_path), "--output", "human"), ("review-source", str(review_path), "--output", "json")):
            output = io.StringIO()
            with redirect_stdout(output): self.assertEqual(cli_main(list(args)), 0)
            output.getvalue().encode("ascii")
        output = io.StringIO()
        with self.assertRaises(SystemExit) as caught, redirect_stdout(output): cli_main(["--help"])
        self.assertEqual(caught.exception.code, 0)

    def test_official_policy_boundaries_are_unchanged(self):
        from app.historical_backtesting.policy import DEFAULT_HISTORICAL_BACKTEST_POLICY
        policy = DEFAULT_HISTORICAL_BACKTEST_POLICY
        self.assertEqual(policy.minimum_decimal_odds, Decimal("1.60"))
        self.assertEqual(policy.minimum_expected_value, Decimal("0.02"))
        self.assertEqual((policy.conservative_stake_percentage, policy.standard_stake_percentage, policy.maximum_stake_percentage), (Decimal("0.01"), Decimal("0.02"), Decimal("0.03")))
        self.assertNotIn("CORRECT_SCORE", {item.value for item in SupportedMarket})


if __name__ == "__main__":
    unittest.main()
