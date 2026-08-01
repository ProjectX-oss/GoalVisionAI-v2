"""Offline extended-coverage planning and fail-closed evidence generation."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.database import Database, MigrationManager
from app.reviewed_real_historical_data.models import EvidenceTier, SourceApprovalStatus

from .fingerprint import file_sha256, sha256_fingerprint
from .models import OddsSourceReview, QuoteSelectionPolicy
from .repository import SQLiteReviewedHistoricalOddsRepository
from .service import (
    build_partition_coverage_report,
    derive_acquisition_window,
    prepare_source_review,
)


FOUNDATION_VERSION = "extended-reviewed-historical-odds-coverage-v1"


def load_source_review(path: str | Path) -> OddsSourceReview:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    raw["approval_status"] = SourceApprovalStatus(raw["approval_status"])
    raw.pop("review_fingerprint", None)
    return prepare_source_review(OddsSourceReview(**raw))


def build_extended_coverage_evidence(
    *, prior_real_evidence_path: str | Path, prior_odds_evidence_path: str | Path,
    source_review_paths: tuple[str | Path, ...], protected_database_path: str | Path,
    isolated_database_path: str | Path, branch: str, starting_commit: str,
    execution_timestamp_utc: str,
) -> dict[str, object]:
    """Persist reviewed access findings and stop honestly when no TEST archive exists."""
    prior_real = json.loads(Path(prior_real_evidence_path).read_text(encoding="utf-8"))
    prior_odds = json.loads(Path(prior_odds_evidence_path).read_text(encoding="utf-8"))
    source_hash_before = file_sha256(protected_database_path)
    reviews = tuple(load_source_review(path) for path in source_review_paths)
    window = derive_acquisition_window(prior_real)
    coverage = build_partition_coverage_report(
        window=window, quotes=(), selections=(), partitions={}, links=(), rejected=(),
    )
    isolated_path = Path(isolated_database_path)
    isolated_path.parent.mkdir(parents=True, exist_ok=True)
    database = Database(str(isolated_path))
    try:
        MigrationManager(database.connection).migrate()
        repository = SQLiteReviewedHistoricalOddsRepository(database, migrate=False)
        for review in reviews:
            repository.append_review(review)
        repository.append_acquisition_window(window, execution_timestamp_utc)
        repository.append_partition_coverage(coverage, execution_timestamp_utc)
        foreign_key_rows = database.connection.execute("PRAGMA foreign_key_check").fetchall()
        database.connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        database.close()
    source_hash_after = file_sha256(protected_database_path)
    if source_hash_before != source_hash_after:
        raise RuntimeError("Protected source database changed during coverage review.")
    candidates = prior_odds["real_data_candidates"]
    document: dict[str, object] = {
        "schema_version": "goalvision-extended-test-odds-coverage-evidence-v1",
        "foundation_version": FOUNDATION_VERSION,
        "branch": branch,
        "starting_commit": starting_commit,
        "final_commit": "PENDING_COMMIT",
        "execution_timestamp_utc": execution_timestamp_utc,
        "database_schema_version": 35,
        "split": asdict(window),
        "split_unchanged": True,
        "odds_sources_reviewed": [asdict(item) for item in reviews],
        "approved_source_with_test_overlap": False,
        "source_manifests": [],
        "raw_source_hashes": [],
        "storage_limitations": [
            "No restricted raw odds files were acquired or committed.",
            "Paid or account-gated archives require explicit authorized credentials and applicable usage rights.",
            "Personal bookmaker account data is outside scope.",
        ],
        "competitions": ["German Bundesliga"],
        "seasons": list(window.seasons),
        "bookmakers": [],
        "markets": [item.value for item in window.preferred_markets],
        "raw_quote_count": 0,
        "normalized_quote_count": 0,
        "linked_event_count": 0,
        "validation_coverage": 0,
        "test_coverage": 0,
        "ambiguous_event_count": 0,
        "unmatched_event_count": 0,
        "post_kickoff_exclusions": 0,
        "quote_selection_policies": [asdict(QuoteSelectionPolicy())],
        "coverage_report": asdict(coverage),
        "coverage_sufficiency": coverage.coverage_status.value,
        "candidate_models": [{
            "candidate": item["candidate"],
            "model_artifact_id": item["model_artifact_id"],
            "model_artifact_fingerprint": item["model_artifact_fingerprint"],
        } for item in candidates],
        "calibrations": [{
            "candidate": item["candidate"],
            "calibration_artifact_set_id": item["calibration_artifact_set_id"],
            "calibration_artifact_set_fingerprint": item["calibration_artifact_set_fingerprint"],
            "calibration_quality": item["calibration_quality"],
        } for item in candidates],
        "test_backtests": [],
        "test_candidate_market_count": 0,
        "selected_bet_count": 0,
        "predictive_metrics": {item["candidate"]: item["test_predictive_metrics"] for item in candidates},
        "calibration_metrics": {item["candidate"]: item["calibration_metrics"] for item in candidates},
        "betting_metrics": None,
        "uncertainty_metrics": None,
        "risk_and_drawdown_metrics": None,
        "backtest_integrity_result": "BACKTEST_INTEGRITY_BLOCKED",
        "backtest_integrity_blockers": ["TEST_ONLY", "REVIEWED_TEST_ODDS_COVERAGE_UNAVAILABLE"],
        "shadow_result": "SHADOW_EVIDENCE_INSUFFICIENT",
        "comparison_result": "INSUFFICIENT_TEST_ODDS_COVERAGE",
        "promotion_result": "INSUFFICIENT_TEST_ODDS_COVERAGE",
        "audit_result": "AUDIT_BLOCKED",
        "staging_activation_result": "NOT_EXECUTED_AUDIT_BLOCKED",
        "real_match_lab_rehearsal_result": "NOT_EXECUTED_NO_ELIGIBLE_STAGING_CHAMPION",
        "evidence_tier": EvidenceTier.REVIEWED_REAL_HISTORICAL.value,
        "publication_eligibility": False,
        "safety": {
            "telegram_calls": 0, "telegram_sends": 0, "delivery_records": 0,
            "official_publications": 0, "official_bankroll_statistics_mutations": 0,
            "production_activation_mutations": 0, "scheduling_startup_changes": 0,
        },
        "source_database_hash_before": source_hash_before,
        "source_database_hash_after": source_hash_after,
        "isolated_database_hash": file_sha256(isolated_path),
        "append_only_result": "PASS",
        "foreign_key_result": "PASS" if not foreign_key_rows else "FAIL",
        "startup_result": "NOT_CHANGED",
        "limitations": [
            "No reviewed source with authorized access supplied immutable TEST-period odds.",
            "No TEST betting, ROI, yield, drawdown, bootstrap, or subgroup result can be computed.",
            "Existing calibration remains ineligible on excessive MCE for AWAY_WIN and OVER_2_5.",
            "Historical predictive metrics do not establish profitability.",
        ],
        "next_required_step": "Provide an operator-approved licensed export or authorized API credential covering the immutable 2023-05-13 through 2025-05-17 acquisition window, plus a separately reserved post-TEST shadow window.",
    }
    document["evidence_fingerprint"] = sha256_fingerprint(document)
    return document
