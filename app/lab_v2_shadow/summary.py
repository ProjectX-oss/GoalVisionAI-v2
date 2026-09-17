"""Concise read-only operator summary over persisted Lab V2 evidence."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sqlite3

from .runner import _one_x_two_diagnostics


def latest_cycle_summary(path: Path, *, fixture_id: int | None = None) -> dict[str, object]:
    """Inspect the latest cycle without creating, migrating or mutating a database."""
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        row = connection.execute(
            """SELECT identity,created_at_utc,document_json
            FROM lab_v2_shadow_evidence WHERE kind='rehearsal'
            ORDER BY created_at_utc DESC,identity DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return {"status": "NO_LAB_V2_CYCLE_EVIDENCE"}
        report = json.loads(row[2])
        candidates = report.get("candidate_markets") or []
        readiness = Counter({
            str(key): int(value) for key, value in (report.get("readiness_reasons") or {}).items()
        }) or Counter(
            reason for candidate in candidates
            for reason in candidate.get("readiness_reasons") or ()
        )
        rejections = Counter({
            str(key): int(value) for key, value in (report.get("rejection_reasons") or {}).items()
        })
        publication = connection.execute(
            """SELECT document_json FROM lab_v2_shadow_evidence
            WHERE kind='publication_cycle' AND created_at_utc>=?
            ORDER BY created_at_utc DESC,identity DESC LIMIT 1""",
            (row[1],),
        ).fetchone()
        publication_document = json.loads(publication[0]) if publication else {}
        result: dict[str, object] = {
            "status": "AVAILABLE",
            "cycle_id": row[0],
            "created_at_utc": row[1],
            "fixtures_discovered": int(report.get("fixtures_discovered") or 0),
            "fixtures_with_current_odds": int(report.get("current_odds_fixtures") or 0),
            "fixtures_without_current_odds": int(report.get("fixtures_with_no_current_odds") or 0),
            "fixtures_with_stale_odds": int(report.get("fixtures_rejected_for_stale_current_odds") or 0),
            "fixtures_with_unnormalizable_odds": int(report.get("fixtures_with_unreliable_market_normalization") or 0),
            "fixtures_with_unsupported_markets": int(report.get("fixtures_with_unsupported_current_markets") or 0),
            "fixtures_with_incomplete_odds_page_coverage": int(report.get("fixtures_with_incomplete_odds_page_coverage") or 0),
            "markets_evaluated": int(report.get("candidate_markets_evaluated") or 0),
            "early": int(report.get("early_candidate_count") or 0),
            "final_review": int(report.get("final_review_candidate_count") or 0),
            "ready": int(report.get("ready_candidate_count") or 0),
            "top_rejection_reasons": dict(rejections.most_common(10)),
            "readiness_blockers": dict(readiness.most_common()),
            "fixture_coverage_status_counts": report.get("fixture_coverage_status_counts") or {},
            "tracked_final_review_state_counts": report.get("tracked_final_review_state_counts") or {},
            "api_calls_used": int(report.get("api_calls_consumed") or 0),
            "api_call_allocation": report.get("api_call_allocation") or {},
            "publication_attempts": int(publication_document.get("publication_attempt_count") or 0),
            "telegram_sends": int(publication_document.get("telegram_sends") or 0),
            "one_x_two_diagnostics": report.get("one_x_two_diagnostics") or _one_x_two_diagnostics(candidates),
        }
        for key in ("throughput", "competition_profile_counts", "global_state_counts", "rejection_funnel",
                    "top_global_rejection_reasons", "largest_rejection_bottleneck", "throughput_warnings",
                    "top_candidate_competitions", "top_candidate_markets", "current_remaining_daily_quota",
                    "fixtures_awaiting_near_kickoff_review"):
            result[key] = report.get(key)
        if fixture_id is not None:
            coverage = next((item for item in report.get("fixture_coverage") or ()
                             if str(item.get("fixture_id")) == str(fixture_id)), None)
            if coverage is None:
                matched = [item for item in candidates if str(item.get("fixture_id")) == str(fixture_id)]
                coverage = ({
                    "fixture_id": fixture_id,
                    "status": "FIXTURE_EVALUATED_REJECTED",
                    "markets_evaluated": len(matched),
                } if matched else {
                    "fixture_id": fixture_id,
                    "status": "FIXTURE_NOT_DISCOVERED",
                    "markets_evaluated": 0,
                })
            result["fixture"] = coverage
            result["tracked_final_reviews"] = [
                item for item in report.get("tracked_final_reviews", ())
                if str(item.get("fixture_id")) == str(fixture_id)
            ]
            if not result["tracked_final_reviews"] and connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='lab_v2_final_review_pending'"
            ).fetchone():
                result["tracked_final_reviews"] = [json.loads(item[0]) for item in connection.execute(
                    "SELECT document_json FROM lab_v2_final_review_pending WHERE fixture_id=? ORDER BY market",
                    (fixture_id,),
                )]
            # Cycle payloads refer to individual immutable candidate documents.
            if not candidates:
                candidates = [json.loads(item[0]) for item in connection.execute(
                    """SELECT c.document_json FROM json_each(?, '$.candidate_ids') ids
                    JOIN lab_v2_shadow_evidence c ON c.kind='candidate' AND c.identity=ids.value
                    WHERE json_extract(c.document_json, '$.fixture_id')=?""",
                    (row[2], fixture_id),
                )]
            result["candidate_markets"] = [
                {key: item.get(key) for key in ("candidate_id", "fixture_id", "market", "stage",
                                               "rejection_reasons", "readiness_reasons")}
                for item in candidates if str(item.get("fixture_id")) == str(fixture_id)
            ]
        return result
    finally:
        connection.close()
