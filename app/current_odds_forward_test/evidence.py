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


def build_api_football_discovery_evidence() -> dict:
    """Reproduce the sanitized first bounded provider discovery record."""

    value = {
        "schema_version": "goalvision-api-football-current-discovery-evidence-v1",
        "source_commit": "760eb26",
        "branch": "goalvision/live-78-fresh-calibration",
        "execution_timestamp_utc": "2026-08-01T08:49:35.063497+00:00",
        "canonical_environment_variable": "FOOTBALL_API_KEY",
        "credential_status": "CONFIGURED",
        "authentication_status": "AUTHENTICATED",
        "plan_status": "AVAILABLE",
        "quota": {
            "daily_limit": 100,
            "daily_used_at_diagnosis": 0,
            "daily_remaining_header_after_discovery": "9",
            "requests_remaining_header_after_discovery": "99",
        },
        "discovery": {
            "window_utc": ["2026-08-01", "2026-08-08"],
            "maximum_candidates": 50,
            "maximum_api_calls": 8,
            "actual_api_calls": 1,
            "candidate_fixture_count": 0,
            "fixtures_inspected": 0,
            "skipped_candidate_count": 0,
            "skip_reasons": {},
            "fixture_order": "KICKOFF_UTC_THEN_PROVIDER_FIXTURE_ID",
            "selected_fixture": None,
            "terminal_result": "NO_ELIGIBLE_CURRENT_FIXTURE",
        },
        "odds": {
            "source": "API_FOOTBALL_CURRENT_PREMATCH_ODDS",
            "request_executed": False,
            "bookmaker": None,
            "available_markets": [],
            "timestamps": None,
            "snapshot_fingerprint": None,
        },
        "forward_test": {
            "observation_id": None,
            "feature_completeness": "NOT_EVALUATED",
            "model_calibration_compatibility": "NOT_EVALUATED",
            "market_evaluation": "NOT_EXECUTED",
            "selection": "NO_SELECTION_NOT_ANALYZED",
            "preview": None,
        },
        "database_integrity": {
            "schema_version": 36,
            "foreign_key_violations": 0,
            "source_database_sha256_before": "61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0",
            "source_database_sha256_after": "61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0",
            "isolated_database_sha256": "8b58382e382690e4f339df81085cf9c02437a2baba7ca3885a56ee43a7d3287a",
        },
        "safety": {
            "telegram_sends": 0,
            "delivery_records": 0,
            "official_publications": 0,
            "bankroll_statistics_mutations": 0,
            "production_activation_mutations": 0,
            "scheduler_startup_changes": 0,
            "historical_odds_probes": 0,
            "thestatsapi_calls": 0,
        },
        "limitations": [
            "The authenticated provider returned zero fixtures in the bounded discovery window.",
            "No fixture was selected, so odds retrieval and inference correctly did not run.",
            "This run establishes configuration and bounded connectivity only, not predictive quality.",
        ],
        "next_operator_action": "Repeat the same bounded discovery command when API-Football lists an upcoming supported top-league fixture; do not run inference until fresh current odds and required baseline data pass all gates.",
    }
    value["evidence_fingerprint"] = fingerprint(value)
    return value
