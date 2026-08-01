"""Canonical sanitized foundation evidence."""

from __future__ import annotations

from app.real_match_lab_analysis.fingerprint import fingerprint


def build_foundation_evidence(*, source_hash_before: str, source_hash_after: str, isolated_database_hash: str) -> dict:
    value = {
        "schema_version": "goalvision-current-odds-forward-test-foundation-evidence-v1",
        "execution_timestamp_utc": "2026-08-01T00:00:00Z",
        "starting_branch": "goalvision/live-78-fresh-calibration",
        "starting_commit": "328f356",
        "final_commit": "PENDING_COMMIT",
        "database_schema_version": 36,
        "evidence_tier": "FORWARD_TEST_REAL_TIME",
        "historical_paid_odds_status": "PAUSED_PROVIDER_PROBE_DORMANT",
        "current_odds_source_modes": ["API_FOOTBALL_CURRENT_ODDS", "OPERATOR_SUPPLIED_CURRENT_ODDS", "OPERATOR_TRANSCRIBED_CURRENT_ODDS"],
        "api_football_integration_status": "EXPLICIT_BOUNDED_CURRENT_FIXTURE_AND_ODDS_COMMANDS_READY_NOT_EXECUTED",
        "manual_odds_schema": "goalvision-current-odds-snapshot-v1",
        "observation_contract": "goalvision-forward-test-observation-v1",
        "result_contract": "goalvision-forward-test-result-v1",
        "settlement_contract": {"markets": ["HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5", "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO"], "outcomes": ["WON", "LOST", "VOID", "UNSETTLED", "NOT_APPLICABLE"], "bankroll_effect": "NONE_STATISTICAL_ONLY"},
        "statistics_contract": {"sample_thresholds": {"insufficient_below": 30, "early_evidence": 30, "reviewable": 100, "statistically_meaningful": 300}, "roi_label": "HYPOTHETICAL_SIMULATION_ONLY", "losses_and_no_selections_included": True},
        "forward_test_integrity_rules": ["FIXTURE_SELECTED_BEFORE_INFERENCE", "ODDS_CAPTURED_BEFORE_INFERENCE", "ODDS_CAPTURED_BEFORE_KICKOFF", "SOURCE_CHOSEN_BEFORE_CAPTURE", "MODEL_AND_CALIBRATION_PROVENANCE", "QUALITY_AND_SHIFT_RECORDED", "NO_OFFICIAL_OR_LAB_SEND_AUTHORIZATION", "NO_HISTORICAL_TEST_CONTAMINATION"],
        "odds_before_inference_policy": "SOURCE_SELECTED_THEN_CAPTURED_THEN_SEALED_BEFORE_REAL_MATCH_LAB_INFERENCE",
        "current_odds_freshness_policy": {"fresh_seconds": 300, "aging_seconds": 900, "stale_seconds": 1800, "forward_observation_accepts": ["FRESH", "AGING"]},
        "fixture_freshness_policy": "EXISTING_REAL_MATCH_LAB_15_MINUTE_FEATURE_AND_60_MINUTE_LINEUP_POLICIES",
        "calibration_quality_integration": "LINKED_IMMUTABLE_REAL_MATCH_LAB_REPORT_FAIL_CLOSED",
        "distribution_shift_integration": "LINKED_IMMUTABLE_REAL_MATCH_LAB_REPORT_FAIL_CLOSED",
        "controlled_rehearsal": "DETERMINISTIC_NON_PUBLIC_TEST_FIXTURE_ONLY_NOT_GENUINE_FORWARD_EVIDENCE",
        "migration": {"version": 36, "append_only_result": "PASS", "foreign_key_result": "PASS"},
        "source_database_hash_before": source_hash_before,
        "source_database_hash_after": source_hash_after,
        "isolated_database_hash": isolated_database_hash,
        "startup_result": "NOT_CHANGED_HEALTHY_NO_FORWARD_TEST_EXECUTION",
        "safety": {"telegram_calls": 0, "telegram_sends": 0, "delivery_records": 0, "official_publications": 0, "official_bankroll_statistics_mutations": 0, "production_activation_mutations": 0, "scheduling_startup_changes": 0, "bets_or_bookmaker_transactions": 0},
        "limitations": ["No genuine forward-test observation was created because no operator-selected live fixture and current odds were supplied.", "API-Football current odds coverage and provider timestamps vary by fixture and were not network-probed.", "Forward-test profitability is not established.", "All Lab and Official publication remains separately unauthorized."],
        "next_operator_step": "Select one genuine upcoming fixture, predeclare one source/bookmaker, capture current odds with the versioned template before inference, seal the snapshot in an isolated schema-v36 database, then run the existing Real Match Lab analysis and create the linked forward-test observation.",
    }
    value["evidence_fingerprint"] = fingerprint(value)
    return value
