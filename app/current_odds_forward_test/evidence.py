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


def build_adaptive_fixture_discovery_evidence() -> dict:
    """Canonical sanitized evidence for the adaptive provider correction."""

    value = {
        "schema_version": "goalvision-api-football-fixture-discovery-fix-evidence-v1",
        "starting_branch": "goalvision/live-78-fresh-calibration",
        "starting_commit": "ad1cfd7",
        "final_commit": "PENDING_COMMIT",
        "execution_timestamp_utc": "2026-08-01T10:40:45.536973+00:00",
        "previous_zero_result_cause": {
            "code": "PROVIDER_QUERY_REJECTED_ERRORS_DISCARDED",
            "endpoint": "/fixtures",
            "method": "GET",
            "query": {"from": "2026-08-01", "to": "2026-08-08"},
            "league_filter": None,
            "season_filter": None,
            "timezone": None,
            "status_filter": None,
            "pagination": None,
            "http_status": 200,
            "errors": {"from": "The From field need another parameter.", "to": "The To field need another parameter."},
            "results": 0,
            "paging": {"current": 1, "total": 1},
            "parser_defect": "NON_EMPTY_PROVIDER_ERRORS_WERE_INTERPRETED_AS_EMPTY_FIXTURE_DATA",
        },
        "endpoint_correction": {
            "endpoint": "/fixtures",
            "method": "GET",
            "query_mode": "DATE_ONLY_WITH_UTC",
            "canonical_query": {"date": "2026-08-01", "timezone": "UTC"},
            "http_status": 200,
            "errors": [],
            "results": 967,
            "paging": {"current": 1, "total": 1},
        },
        "provider_capability": {
            "authentication": "AUTHENTICATED",
            "plan": "AVAILABLE_WITH_DATE_COVERAGE_LIMIT",
            "accessible_fixture_dates": ["2026-07-31", "2026-08-02"],
            "later_date_result": "API_FOOTBALL_PLAN_RESTRICTED",
            "league_results": 1234,
            "odds_coverage_source": "/leagues season.coverage.odds",
            "invalid_odds_metadata_endpoint_rejected": "/odds/leagues",
        },
        "competition_resolver": {
            "status": "CURRENT_PROVIDER_CHRONOLOGY_ENFORCED",
            "priority_competitions": 14,
            "resolved_current": [179, 2, 3, 848, 253],
            "stale_current_season_rejected": [39, 78, 140, 135, 61, 88, 94, 144, 203],
            "source": "/leagues?current=true",
            "ordering": "EARLIEST_SAFE_KICKOFF_THEN_COMPETITION_PRIORITY_THEN_PROVIDER_FIXTURE_ID",
        },
        "canonical_discovery": {
            "stages_attempted": ["COMPETITION_RESOLUTION", "PRIORITY_24_TO_72_HOURS"],
            "date_queries": ["2026-08-01"],
            "provider_fixture_rows": 967,
            "candidate_fixture_count": 4,
            "fixtures_inspected": 4,
            "skip_reasons": {"ALREADY_STARTED": 9, "API_FOOTBALL_QUOTA_INSUFFICIENT": 1, "EXCLUDED_FIXTURE_CLASS": 248, "INSUFFICIENT_REQUIRED_DATA": 3, "KICKOFF_TOO_CLOSE": 45, "NOT_UPCOMING_OR_POSTPONED": 164, "UNSUPPORTED_COMPETITION_TYPE": 20},
            "selected_fixture": None,
            "terminal_result": "NO_ELIGIBLE_CURRENT_FIXTURE",
            "odds_requests": 0,
            "reason_odds_not_requested": "BASELINE_BEFORE_ODDS_GATE_FAILED_FOR_THREE_CANDIDATES_AND_REMAINING_MINUTE_CAPACITY_COULD_NOT_FUND_ANOTHER_COMPLETE_CANDIDATE",
        },
        "api_usage": {
            "diagnostic_calls": 6,
            "fixture_and_odds_discovery_calls_across_bounded_correction_runs": 37,
            "canonical_run_calls": 8,
            "task_total_calls": 43,
            "diagnostic_limit": 20,
            "discovery_limit": 40,
            "daily_reserve": 20,
        },
        "quota": {
            "interpretation_status": "NORMALIZED",
            "exact_headers": {"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "83", "x-ratelimit-limit": "10", "x-ratelimit-remaining": "8"},
            "daily_limit": 100,
            "daily_remaining": 83,
            "minute_limit": 10,
            "minute_remaining_at_last_header": 8,
            "semantics": {"x-ratelimit-requests-*": "DAILY_SUBSCRIPTION", "x-ratelimit-*": "PER_MINUTE"},
        },
        "selected_fixture": None,
        "kickoff_utc": None,
        "bookmaker": None,
        "available_markets": [],
        "odds_capture_timestamps": None,
        "forward_test": {"observation_id": None, "feature_completeness": "NOT_EVALUATED", "model_id": None, "model_fingerprint": None, "calibration_id": None, "calibration_fingerprint": None, "calibration_quality": "NOT_EVALUATED", "distribution_shift": "NOT_EVALUATED", "market_evaluations": [], "selection": "NO_SELECTION_NOT_ANALYZED", "preview": None, "preview_fingerprint": None},
        "database_integrity": {"migration_changed": False, "schema_version": 36, "append_only_status": "PASS", "foreign_key_violations": 0, "source_database_sha256_before": "61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0", "source_database_sha256_after": "61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0", "isolated_database_sha256": "aabcec4e111e407ec93ec4934e8b25408f731856831d88033a96ed36999a5b6e"},
        "startup_result": "HEALTHY_ZERO_FORWARD_TEST_EXECUTION",
        "safety": {"telegram_calls": 0, "telegram_sends": 0, "delivery_records": 0, "official_publications": 0, "bankroll_statistics_mutations": 0, "production_activation_mutations": 0, "scheduling_startup_changes": 0, "bookmaker_transactions": 0, "historical_odds_probes": 0, "thestatsapi_calls": 0},
        "limitations": ["No fixture passed the required baseline-before-odds gate during the canonical minute-bounded run.", "No odds snapshot, inference, model output, calibration result, market evaluation, observation or preview was created.", "The run validates adaptive provider discovery and safety, not predictive quality."],
        "next_operator_action": "After the API-Football per-minute window resets, rerun the same bounded discovery command; the next deterministic candidate must still pass baseline, fresh odds and every existing quality gate before inference.",
    }
    value["evidence_fingerprint"] = fingerprint(value)
    return value


def build_discovery_efficiency_evidence() -> dict:
    """Canonical sanitized evidence for quota-efficient current discovery."""

    candidate_ids = (1556629, 1556630, 1490362, 1490363, 1490364, 1490365)
    value = {
        "schema_version": "goalvision-api-football-discovery-efficiency-evidence-v1",
        "source_branch": "goalvision/live-78-fresh-calibration",
        "source_commit": "5a49aa71d226bc2fece3033b7deb0003eaa5a244",
        "final_commit": "PENDING_COMMIT",
        "execution_timestamp_utc": "2026-08-01T11:14:03.780639+00:00",
        "request_cost_findings": {
            "previous_candidate_cost": {"team_history": 2, "odds": 1, "total": 3},
            "exact_bottleneck": "EACH_CANDIDATE_REQUESTED_BOTH_TEAM_HISTORIES_BEFORE_CHECKING_THE_FIRST_RESPONSE",
            "provider_blocker": {
                "endpoint": "/fixtures",
                "query_shape": {"team": "REDACTED_NUMERIC_ID", "last": 5, "league": 179, "season": 2026},
                "http_status": 200,
                "errors": {"plan": "Free plans do not have access to this season, try from 2022 to 2024."},
                "result": "API_FOOTBALL_PLAN_RESTRICTED",
            },
            "optimized_failed_candidate_cost": {"team_history": 1, "odds": 0, "total": 1},
            "fixture_list_call_cost": 1,
            "competition_metadata_or_quota_refresh_cost": 1,
            "retries": 0,
        },
        "optimizations": [
            "FIXTURE_RESPONSE_ONLY_COVERAGE_AND_IDENTITY_PREFILTER",
            "HOME_BASELINE_SHORT_CIRCUIT_BEFORE_AWAY_BASELINE",
            "CONTEXT_BOUND_TEAM_HISTORY_REUSE",
            "LEAGUE_SEASON_CAPABILITY_CACHE_WITH_SIX_HOUR_EXPIRY",
            "FULL_MANDATORY_COST_PLANNED_BEFORE_CANDIDATE_START",
            "REQUIRED_BASELINE_BEFORE_OPTIONAL_DATA_AND_ODDS",
            "COMPETITION_PRIORITY_AND_CACHE_REUSE_ORDERING_WITHOUT_MODEL_OUTPUT",
        ],
        "cache_strategy": {
            "status": "REFRESHED",
            "record_count": 1235,
            "retrieved_at_utc": "2026-08-01T11:14:03.780639+00:00",
            "expires_at_utc": "2026-08-01T17:14:03.780639+00:00",
            "cache_fingerprint": "ea16d9816da2f19e44ca96a92cd3d0b85f9a844d113b8258b8a4fccca7e1f128",
            "credentials_present": False,
            "team_cache_scope": "TEAM+LEAGUE+SEASON+EVALUATION_CUTOFF",
            "team_cache_ttl_minutes": 15,
            "standings_cache_scope": "LEAGUE+SEASON",
            "season_aggregate_cache_scope": "TEAM+LEAGUE+SEASON",
            "injury_cache_scope": "FIXTURE+TEAM_WITH_FOUR_HOUR_TTL",
            "lineup_cache_scope": "FIXTURE_WITH_ONE_HOUR_TTL",
            "startup_network_calls": 0,
        },
        "batching_findings": {
            "fixtures_ids": "SUPPORTED_UP_TO_20_IDS_BUT_NOT_USEFUL_FOR_UNKNOWN_RECENT_TEAM_FIXTURE_IDS",
            "injuries_ids": "SUPPORTED_UP_TO_20_FIXTURE_IDS_OPTIONAL_AND_NOT_CALLED_BEFORE_BASELINE",
            "team_season_reuse": "SUPPORTED_AND_CONTEXT_BOUND",
            "standings_reuse": "ONE_LEAGUE_SEASON_RESPONSE_CAN_SERVE_ALL_CANDIDATES_BUT_EXISTING_REQUIRED_BASELINE_DOES_NOT_REQUIRE_IT",
            "date_odds": "SUPPORTED_WITH_TEN_RESULTS_PER_PAGE_BUT_EXACT_FIXTURE_QUERY_IS_SMALLER_AND_IDENTITY_SAFE",
            "odds_fixture_ids_batch": "NOT_DOCUMENTED",
            "bookmaker_filter": "SUPPORTED_BUT_NO_PREDECLARED_SINGLE_BOOKMAKER_POLICY",
            "bet_filter": "SUPPORTED_BUT_ONE_FILTER_CANNOT_RETURN_ALL_CANONICAL_MARKETS",
        },
        "canonical_run": {
            "provider_fixtures_returned": 967,
            "candidates_prefiltered": 620,
            "candidates_planned": 7,
            "candidates_with_deep_network_call": 6,
            "per_candidate_request_costs": [
                {"provider_fixture_id": identifier, "team_history_calls": 1, "odds_calls": 0, "retries": 0, "result": "CANDIDATE_SKIPPED_BASELINE", "reason": "API_FOOTBALL_PLAN_RESTRICTED"}
                for identifier in candidate_ids
            ] + [
                {"provider_fixture_id": 1490366, "team_history_calls": 0, "odds_calls": 0, "retries": 0, "result": "CANDIDATE_SKIPPED_QUOTA", "reason": "FULL_THREE_CALL_BUDGET_UNAVAILABLE"}
            ],
            "skip_reasons": {"ALREADY_STARTED": 4, "API_FOOTBALL_PLAN_RESTRICTED": 6, "API_FOOTBALL_QUOTA_INSUFFICIENT": 1, "EXCLUDED_FIXTURE_CLASS": 222, "KICKOFF_TOO_CLOSE": 42, "NOT_UPCOMING_OR_POSTPONED": 207, "NO_FIXTURE_COVERAGE": 90, "NO_ODDS_CAPABILITY": 36, "UNSUPPORTED_COMPETITION_TYPE": 19},
            "odds_requests": 0,
            "selected_fixture": None,
            "terminal_result": "DISCOVERY_QUOTA_INSUFFICIENT",
        },
        "api_usage": {
            "canonical_run_calls": 8,
            "supplemental_exact_plan_error_call": 1,
            "total_calls": 9,
            "maximum_calls_per_discovery_run": 10,
            "daily_reserve": 20,
        },
        "quota_after_canonical_run": {
            "interpretation_status": "NORMALIZED",
            "daily_limit": 100,
            "daily_remaining": 81,
            "minute_limit": 10,
            "minute_remaining_at_last_normalized_header": 8,
            "exact_headers": {"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "81", "x-ratelimit-limit": "10", "x-ratelimit-remaining": "8"},
        },
        "odds": {"request_count": 0, "bookmaker": None, "markets": [], "snapshot_fingerprint": None},
        "forward_test": {"observation_id": None, "feature_completeness": "REQUIRED_BASELINE_INCOMPLETE", "model_id": None, "model_fingerprint": None, "calibration_id": None, "calibration_fingerprint": None, "calibration_quality": "NOT_EVALUATED", "distribution_shift": "NOT_EVALUATED", "market_evaluations": [], "selection": "NO_SELECTION_NOT_ANALYZED", "preview": None, "preview_fingerprint": None},
        "database_integrity": {"migration_changed": False, "source_database_schema": 7, "source_database_sha256_before": "61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0", "source_database_sha256_after": "61ff2a843abba8c616d7617dc7e22f671d655f580ef10ec0d4cf10625bf76bc0", "source_database_foreign_key_violations": 0, "isolated_database_created": False, "reason": "NO_ODDS_SNAPSHOT_OR_FORWARD_OBSERVATION_TO_PERSIST"},
        "safety": {"telegram_calls": 0, "telegram_sends": 0, "delivery_records": 0, "official_publications": 0, "bankroll_statistics_mutations": 0, "production_activation_mutations": 0, "scheduling_startup_changes": 0, "bookmaker_transactions": 0, "thestatsapi_calls": 0},
        "limitations": ["The configured free plan exposes current fixture listings but rejects current-season team history, so required baseline features cannot be constructed without fabricating or mixing incompatible seasons.", "No candidate reached current odds, inference, calibration, distribution-shift review, market evaluation or forward-test persistence."],
        "next_operator_action": "Use an API-Football plan that permits 2026 team-history access, then rerun the same bounded discovery command after the capability cache expires or is explicitly refreshed; do not run inference until the exact current-season baseline and fresh odds pass.",
    }
    value["evidence_fingerprint"] = fingerprint(value)
    return value
