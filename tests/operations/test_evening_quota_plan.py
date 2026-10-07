"""Planning and failure-boundary checks; no production fixture/credentials."""
from datetime import datetime
import importlib.util
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "operations/evening-quota/plan.py"
spec = importlib.util.spec_from_file_location("evening_quota_plan", SOURCE)
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


@pytest.mark.parametrize("instant,phase", [
    ("2026-10-07T09:59:59+03:00", "RESULTS_ONLY"),
    ("2026-10-07T10:00:00+03:00", "PREMATCH_DISCOVERY"),
    ("2026-10-07T17:59:59+03:00", "PREMATCH_DISCOVERY"),
    ("2026-10-07T18:00:00+03:00", "LIVE_DISCOVERY_IF_READY"),
    ("2026-10-07T22:59:59+03:00", "LIVE_DISCOVERY_IF_READY"),
    ("2026-10-07T23:00:00+03:00", "RESULTS_ONLY"),
    ("2026-12-01T16:00:00+00:00", "LIVE_DISCOVERY_IF_READY"),
])
def test_riga_boundaries_and_winter_offset(instant, phase):
    assert plan.planned_phase(datetime.fromisoformat(instant)) == phase


def test_evening_reserve_covers_results_until_utc_reset_not_only_live_stop():
    reserve = plan.result_reserve(datetime.fromisoformat("2026-10-07T18:00:00+03:00"))
    assert reserve["remaining_scheduled_result_runs"] == 54
    assert reserve["protected_requests"] == 1155
    assert reserve["quota_reset_utc"] == "2026-10-08T00:00:00+00:00"
    winter = plan.result_reserve(datetime.fromisoformat("2026-12-01T18:00:00+02:00"))
    assert winter["remaining_scheduled_result_runs"] == 48
    assert winter["protected_requests"] == 1029


def test_exact_timer_tick_included_and_just_started_slot_covered_by_inflight():
    exact = plan.result_reserve(datetime.fromisoformat("2026-10-07T15:05:00+00:00"))
    after = plan.result_reserve(datetime.fromisoformat("2026-10-07T15:05:00.000001+00:00"))
    assert exact["remaining_scheduled_result_runs"] == after["remaining_scheduled_result_runs"] + 1
    assert after["in_flight_run_allowance"] == 21


def test_quota_never_borrows_protected_result_reserve():
    at = datetime.fromisoformat("2026-10-07T18:00:00+03:00")
    assert plan.live_headroom(at, 2500)["remaining_for_live_discovery_refresh_and_results"] == 1345
    assert plan.live_headroom(at, 1000)["remaining_for_live_discovery_refresh_and_results"] == 0
    # Proposed arithmetic removes the old fixed 1800 ceiling; runtime still unchanged.
    assert plan.live_headroom(at, 4000)["remaining_for_live_discovery_refresh_and_results"] == 2845


@pytest.mark.parametrize("available", [-1, 7501, True, "3000", 3.5, None])
def test_invalid_capacity_fails_closed(available):
    with pytest.raises(ValueError, match="INVALID_AVAILABLE_REQUESTS"):
        plan.live_headroom(datetime.fromisoformat("2026-10-07T18:00:00+03:00"), available)


def test_minimum_reserve_at_midnight_and_naive_timestamp_rejection():
    assert plan.result_reserve(datetime.fromisoformat("2026-10-07T23:59:59+00:00"))["protected_requests"] == 100
    with pytest.raises(ValueError, match="OFFSET_REQUIRED"):
        plan.result_reserve(datetime(2026, 10, 7, 18))


def test_actual_captured_shape_blocks_identity_and_staleness():
    evidence = {"finished_at": "2026-10-07T09:06:34.474502+00:00", "live_odds_rows": [
        {"bookmaker_id_present": False, "bookmaker_name_present": False, "update_age_seconds": 36.473576},
        {"bookmaker_id_present": False, "bookmaker_name_present": False, "update_age_seconds": 35.473576},
    ]}
    report = plan.build_plan(evidence)
    assert report == plan.build_plan(evidence)
    assert report["status"] == "BLOCKED_NOT_DEPLOYED"
    assert not report["activation_allowed"]
    assert "LIVE_BOOKMAKER_IDENTITY_UNAVAILABLE" in report["blockers"]
    assert "OBSERVED_LIVE_ROW_UPDATE_OUTSIDE_20_SECOND_LIMIT" in report["blockers"]
    assert report["provider_calls_by_this_planner"] == report["telegram_sends_by_this_planner"] == 0


def test_empty_feed_is_unproven_not_ready():
    assert "LIVE_PROVIDER_COVERAGE_NOT_PROVEN" in plan.capability_blockers({"live_odds_rows": []})


def test_fresh_named_rows_alone_never_authorize_deployment():
    report = plan.build_plan({"finished_at": "2026-10-07T09:00:00+00:00", "live_odds_rows": [
        {"bookmaker_id_present": True, "bookmaker_name_present": True, "update_age_seconds": 1},
    ]})
    assert "LIVE_BOOKMAKER_IDENTITY_UNAVAILABLE" not in report["blockers"]
    assert "LIVE_BOOKMAKER_QUOTE_ORIGIN_SEMANTICS_NOT_VERIFIED" in report["blockers"]
    assert not report["activation_allowed"]
