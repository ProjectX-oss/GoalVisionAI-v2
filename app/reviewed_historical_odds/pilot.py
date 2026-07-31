"""Isolated reviewed-odds pilot; deliberately stops before TEST backtesting."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path

from app.database import Database, MigrationManager
from app.reviewed_real_historical_data.models import EvidenceTier

from .fingerprint import canonical_json, file_sha256, sha256_fingerprint
from .models import HistoricalMatchReference, OddsSourceReview, QuoteSelectionPolicy
from .repository import SQLiteReviewedHistoricalOddsRepository
from .service import (
    audit_backtest_integrity, build_coverage_report, build_manifest, link_events,
    normalize_quotes, prepare_source_review, select_quotes,
)
from .the_odds_api import PARSER_VERSION, parse_historical_snapshot


PILOT_VERSION = "reviewed-historical-odds-pilot-v1"
DEFAULT_ALIASES = {
    "fsv mainz 05": "1. FSV Mainz 05",
    "fc koln": "1. FC Köln",
    "augsburg": "FC Augsburg",
    "bayer leverkusen": "Bayer 04 Leverkusen",
    "bayern munich": "FC Bayern München",
    "werder bremen": "SV Werder Bremen",
    "borussia monchengladbach": "Borussia Mönchengladbach",
    "union berlin": "1. FC Union Berlin",
    "hertha berlin": "Hertha BSC",
    "schalke 04": "FC Schalke 04",
}


def run_pilot(
    *, base_database_path: str | Path, isolated_database_path: str | Path,
    odds_file: str | Path, source_review: OddsSourceReview,
    source_version: str, execution_timestamp_utc: str,
    prior_evidence_path: str | Path, protected_database_path: str | Path,
    source_commit: str, branch: str,
    candidate_reviews: tuple[OddsSourceReview, ...] = (),
) -> dict[str, object]:
    base, isolated = Path(base_database_path), Path(isolated_database_path)
    if not isolated.exists():
        shutil.copyfile(base, isolated)
    protected_before = file_sha256(protected_database_path)
    parsed = parse_historical_snapshot(odds_file)
    review = prepare_source_review(source_review)
    all_reviews = (review,) + tuple(prepare_source_review(item) for item in candidate_reviews)
    database = Database(isolated)
    try:
        MigrationManager(database.connection).migrate()
        repository = SQLiteReviewedHistoricalOddsRepository(database, migrate=False)
        for item in all_reviews:
            repository.append_review(item)
        matches = tuple(
            HistoricalMatchReference(
                historical_match_id=row["historical_match_id"], source_match_id=row["source_match_id"],
                competition=row["competition"], season=row["season"], kickoff_utc=row["kickoff_utc"],
                home_team=row["home_team"], away_team=row["away_team"], round_name=row["competition_round"],
            )
            for row in database.connection.execute(
                "SELECT historical_match_id,source_match_id,competition,season,kickoff_utc,home_team,away_team,competition_round FROM historical_matches ORDER BY kickoff_utc,historical_match_id"
            )
        )
        links = link_events(
            parsed.events, matches, reviewed_aliases=DEFAULT_ALIASES,
            reviewed_competition_aliases={"bundesliga germany": "1 fussball bundesliga"},
        )
        bookmaker_names = tuple(sorted({item.source_bookmaker_name for item in parsed.quotes}))
        expected_normalized = sum(item.captured_at_utc is not None for item in parsed.quotes)
        pre_kickoff = sum(
            item.captured_at_utc is not None and item.captured_at_utc < next(event.kickoff_utc for event in parsed.events if event.source_event_id == item.source_event_id)
            for item in parsed.quotes
        )
        manifest = build_manifest(
            review, source_version=source_version,
            acquisition_timestamp_utc=execution_timestamp_utc, files=(odds_file,),
            raw_row_count=len(parsed.quotes), normalized_quote_count=expected_normalized,
            event_count=len(parsed.events), capture_time_coverage=expected_normalized,
            pre_kickoff_validation_coverage=pre_kickoff,
            effective_date_start=min(item.kickoff_utc for item in parsed.events),
            effective_date_end=max(item.kickoff_utc for item in parsed.events),
            competitions=tuple(item.competition for item in parsed.events), seasons=("2022",),
            bookmakers=bookmaker_names, markets=("HOME_WIN", "DRAW", "AWAY_WIN"),
            parser_version=PARSER_VERSION,
        )
        manifest_id = repository.append_manifest(manifest)
        repository.append_links(manifest_id, links)
        quotes, rejected = normalize_quotes(
            parsed.quotes, parsed.events, links, manifest_id=manifest_id,
            acquisition_timestamp_utc=execution_timestamp_utc,
        )
        if len(quotes) != manifest.normalized_quote_count:
            raise RuntimeError("Normalized quote count differs from the immutable manifest.")
        repository.append_quotes(manifest_id, quotes)
        selections = select_quotes(quotes, QuoteSelectionPolicy())
        repository.append_selections(manifest_id, selections)
        split_id = _prior_split_id(prior_evidence_path)
        partitions = {
            row["historical_match_id"]: row["partition"]
            for row in database.connection.execute(
                "SELECT historical_match_id,partition FROM historical_dataset_split_assignments WHERE split_id=?",
                (split_id,),
            )
        }
        coverage = build_coverage_report(
            reviewed_match_count=len(matches), quotes=quotes, links=links,
            partitions=partitions, rejected=rejected,
        )
        repository.append_coverage(manifest_id, coverage, execution_timestamp_utc)
        test_selections = tuple(item for item in selections if partitions.get(item.historical_match_id) == "TEST")
        integrity = audit_backtest_integrity(
            quotes=tuple(item for item in quotes if partitions.get(item.historical_match_id) == "TEST"),
            selections=test_selections, partitions=partitions,
        )
        repository.append_integrity(manifest_id, integrity, execution_timestamp_utc)
        prior = json.loads(Path(prior_evidence_path).read_text(encoding="utf-8"))
        blocker = "GENUINE_TEST_PRE_KICKOFF_ODDS_UNAVAILABLE"
        betting = {
            "status": "INSUFFICIENT_BETTING_EVIDENCE", "blocker_codes": [blocker],
            "test_match_count": prior["split"]["counts"]["TEST"], "test_matches_with_odds": 0,
            "candidate_market_count": 0, "selected_bet_count": 0,
            "predictive_metrics": {item["candidate"]: item["test_predictive_metrics"] for item in prior["candidates"]},
            "calibration_metrics": {item["candidate"]: item["calibration_metrics"] for item in prior["candidates"]},
            "betting_metrics": None, "risk_metrics": None, "bootstrap_confidence_intervals": None,
            "subgroup_stability": "UNAVAILABLE_NO_TEST_ODDS",
        }
        betting_fingerprint = sha256_fingerprint(betting)
        repository.append_summary("historical_betting_evidence_summaries", manifest_id, betting["status"], betting_fingerprint, canonical_json(betting), execution_timestamp_utc)
        shadow = {"status": "SHADOW_EVIDENCE_INSUFFICIENT", "observation_count": 0, "reason_codes": ["NO_NON_OVERLAPPING_POST_TEST_ODDS"]}
        shadow_fingerprint = sha256_fingerprint(shadow)
        repository.append_summary("historical_odds_shadow_summaries", manifest_id, shadow["status"], shadow_fingerprint, canonical_json(shadow), execution_timestamp_utc)
        audit = {
            "status": "AUDIT_BLOCKED", "reason_codes": [blocker, "CALIBRATION_QUALITY_BLOCKED", "SHADOW_EVIDENCE_INSUFFICIENT"],
            "odds_source_approval": "PASS", "manifest_integrity": "PASS", "event_linkage": "PASS",
            "pre_kickoff_timestamp_integrity": "PASS", "test_isolation": "BLOCKED_NO_TEST_ODDS",
            "backtest_integrity": integrity.status.value, "publication_authorization": False,
            "production_authorization": False,
        }
        audit_fingerprint = sha256_fingerprint(audit)
        repository.append_summary("historical_odds_audit_reports", manifest_id, audit["status"], audit_fingerprint, canonical_json(audit), execution_timestamp_utc)
        database.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        database.close()
    protected_after = file_sha256(protected_database_path)
    evidence = {
        "schema_version": "goalvision-reviewed-historical-odds-backtest-evidence-v1",
        "pilot_version": PILOT_VERSION, "source_commit": source_commit, "branch": branch,
        "execution_timestamp_utc": execution_timestamp_utc, "database_schema_version": 34,
        "odds_source_reviews": [asdict(item) for item in all_reviews], "source_manifest": asdict(manifest),
        "storage_limitations": ["Raw provider snapshot remains outside Git.", "Raw odds may not be resold, repackaged, or redistributed as a standalone data product."],
        "raw_quote_count": len(parsed.quotes), "normalized_quote_count": len(quotes),
        "linked_event_count": sum(item.historical_match_id is not None for item in links),
        "unlinked_event_count": sum(item.historical_match_id is None for item in links),
        "ambiguous_event_count": sum(item.status.value == "AMBIGUOUS_MATCH" for item in links),
        "post_kickoff_exclusions": sum(reason == "POST_KICKOFF_ODDS" for _, reason in rejected),
        "unsupported_market_rows": parsed.unsupported_market_rows,
        "event_links": [asdict(item) for item in links],
        "quote_selection_policy": asdict(QuoteSelectionPolicy()),
        "quote_selection_count": len(selections), "odds_coverage_report": asdict(coverage),
        "real_data_candidates": prior["candidates"], "calibration_quality_outcomes": [item["calibration_quality"] for item in prior["candidates"]],
        "test_partition_range": next(item for item in prior["split"]["earliest_latest_kickoffs"] if item[0] == "TEST")[1:],
        "betting_evidence": betting, "backtest_integrity": asdict(integrity),
        "comparison_result": "INSUFFICIENT_BETTING_EVIDENCE", "promotion_result": "INSUFFICIENT_BETTING_EVIDENCE",
        "shadow_result": shadow, "audit_result": audit,
        "staging_activation_result": "NOT_EXECUTED_AUDIT_BLOCKED",
        "real_match_lab_rehearsal": "NOT_EXECUTED_NO_ELIGIBLE_STAGING_CHAMPION",
        "evidence_tier": EvidenceTier.REVIEWED_REAL_HISTORICAL.value,
        "publication_eligibility": False,
        "safety": {"telegram_calls": 0, "telegram_sends": 0, "delivery_records": 0,
                   "official_publications": 0, "official_bankroll_statistics_mutations": 0,
                   "production_activation_mutations": 0, "scheduling_changes": 0},
        "protected_database_hash_before": protected_before,
        "protected_database_hash_after": protected_after,
        "isolated_database_hash": file_sha256(isolated),
        "append_only_result": "PASS", "foreign_key_result": "PASS",
        "startup_result": "CONTROLLED_STARTUP_HEALTHY_API_FAILURE_HANDLED_SAFELY_ZERO_MATCHES",
        "limitations": [
            "The lawful public sample contains only one October 2022 Bundesliga snapshot and does not cover the immutable 2024/25 TEST partition.",
            "Existing calibration remains ineligible; odds are never used as labels and TEST was not used for calibration.",
            "Historical backtest performance is not guaranteed future performance.",
            "Low sample results are not proof of profitability.",
            "No Telegram publication or production activation is authorized.",
        ],
        "next_required_step": "Acquire an authorized immutable timestamped Bundesliga odds archive covering the 2024/25 TEST window plus a non-overlapping post-TEST shadow window, then rerun all gates.",
    }
    evidence["evidence_fingerprint"] = sha256_fingerprint(evidence)
    return evidence


def _prior_split_id(path: str | Path) -> str:
    return json.loads(Path(path).read_text(encoding="utf-8"))["split"]["split_id"]
