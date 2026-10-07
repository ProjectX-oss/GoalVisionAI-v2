"""Read-only evening quota preparation, NOT a deployment or quota enforcer.

Consumes a sanitized, already captured provider capability document. Never loads
credentials, imports app workers, opens databases, sends requests, or installs units.
The proposed LIVE stop at 23:00 is the bounded assumption discussed with the user.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

RIGA = ZoneInfo("Europe/Riga")
DAILY_LIMIT = 7500
SETTLEMENT_CALLS_PER_RUN = 21
SETTLEMENT_MINUTES = (5, 15, 25, 35, 45, 55)
QUOTE_MAX_AGE_SECONDS = 20


def utc(value: str | datetime) -> datetime:
    instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("OFFSET_REQUIRED")
    return instant.astimezone(timezone.utc)


def planned_phase(at: datetime) -> str:
    """Wall-clock schedule only; this is not an activation decision."""
    local = utc(at).astimezone(RIGA)
    if 10 <= local.hour < 18:
        return "PREMATCH_DISCOVERY"
    if 18 <= local.hour < 23:
        return "LIVE_DISCOVERY_IF_READY"
    return "RESULTS_ONLY"


def result_reserve(at: datetime) -> dict:
    """Reserve existing six/hour, <=21-call result cycles until UTC reset.

    Includes a possible in-flight run and retains the existing 100-call minimum.
    This is a conservative planning bound on the installed PREMATCH/COMBO/private
    result worker, not proof of adequate LIVE-result capacity or an enforced cap.
    """
    clock = utc(at)
    reset = (clock + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tick = clock.replace(second=0, microsecond=0)
    slots = 0
    while tick < reset:
        if tick >= clock and tick.minute in SETTLEMENT_MINUTES:
            slots += 1
        tick += timedelta(minutes=1)
    return {
        "quota_reset_utc": reset.isoformat(),
        "remaining_scheduled_result_runs": slots,
        "maximum_attempts_per_run_including_status_and_retries": SETTLEMENT_CALLS_PER_RUN,
        "in_flight_run_allowance": SETTLEMENT_CALLS_PER_RUN,
        "protected_requests": max(100, (slots + 1) * SETTLEMENT_CALLS_PER_RUN),
    }


def live_headroom(at: datetime, available: int) -> dict:
    """Scenario arithmetic; real workers must use min(provider, durable local)."""
    if type(available) is not int or not 0 <= available <= DAILY_LIMIT:
        raise ValueError("INVALID_AVAILABLE_REQUESTS")
    reserve = result_reserve(at)["protected_requests"]
    return {
        "assumed_shared_available_requests": available,
        "prematch_results_protected_requests": reserve,
        "remaining_for_live_discovery_refresh_and_results": max(0, available - reserve),
        "scenario_only_not_a_reservation": True,
    }


def capability_blockers(capability: dict) -> list[str]:
    blockers = {
        "LIVE_WORKER_REQUIRES_NO_AUTOMATIC_LEARNING_PATH",
        "LIVE_STATUS_PREFLIGHT_REQUIRES_BEFORE_HTTP_SHARED_CLAIM",
        "LIVE_MARKET_ID_NAME_PERIOD_MAPPING_REVIEW_REQUIRED",
        "LIVE_EXECUTABLE_BASELINE_PROVENANCE_REVIEW_REQUIRED",
        "DAYPART_POLICY_NOT_IMPLEMENTED_OR_DEPLOYED",
    }
    rows = capability.get("live_odds_rows")
    if not isinstance(rows, list) or not rows:
        blockers.add("LIVE_PROVIDER_COVERAGE_NOT_PROVEN")
        return sorted(blockers)
    if any(row.get("bookmaker_id_present") is not True or
           row.get("bookmaker_name_present") is not True for row in rows):
        blockers.add("LIVE_BOOKMAKER_IDENTITY_UNAVAILABLE")
    # A row update timestamp alone cannot establish bookmaker quote-origin semantics.
    blockers.add("LIVE_BOOKMAKER_QUOTE_ORIGIN_SEMANTICS_NOT_VERIFIED")
    for row in rows:
        age = row.get("update_age_seconds")
        if type(age) not in (int, float) or not 0 <= age <= QUOTE_MAX_AGE_SECONDS:
            blockers.add("OBSERVED_LIVE_ROW_UPDATE_OUTSIDE_20_SECOND_LIMIT")
    return sorted(blockers)


def build_plan(capability: dict) -> dict:
    captured = utc(capability["finished_at"])
    local = captured.astimezone(RIGA)
    evening = local.replace(hour=18, minute=0, second=0, microsecond=0)
    return {
        "version": "EVENING_QUOTA_PREPARATION_V1",
        "status": "BLOCKED_NOT_DEPLOYED",
        "read_only": True,
        "capability_as_of": captured.isoformat(),
        "proposed_timezone": "Europe/Riga",
        "proposed_prematch_discovery": "10:00 <= time < 18:00",
        "proposed_prematch_timer": "*-*-* 10..17:00,30:00 Europe/Riga",
        "proposed_live_discovery": "18:00 <= time < 23:00; only after readiness repair",
        "live_23_stop_is_bounded_planning_assumption": True,
        "prematch_single_combo_results": "existing 24-hour timer retained",
        "live_results": "must also continue after discovery stops when picks remain unresolved",
        "result_reserve_at_18": result_reserve(evening),
        "evening_scenarios": [live_headroom(evening, available) for available in (2000, 2500, 3000, 4000)],
        "scenarios_are_not_provider_remaining_at_18": True,
        "proposed_live_fixed_daily_cap": None,
        "installed_live_daily_cap_unchanged": 1800,
        "runtime_requirements": [
            "Guard both timers and each HTTP attempt at the 18:00 boundary.",
            "Pace the 16 PREMATCH slots without consuming the future LIVE allocation.",
            "Protect PREMATCH result reserve from LIVE discovery AND LIVE result requests.",
            "Use one shared durable per-attempt quota DB and exact provider headers.",
            "Keep existing 7500/day and 300/min account limits and retry accounting.",
            "Use remaining quota on demand; never spend it merely to exhaust the allowance.",
            "Keep fresh final refresh, quality gates, duplicate protection and result delivery.",
            "Exclude automatic training, calibration activation, promotion and rollback.",
        ],
        "blockers": capability_blockers(capability),
        "activation_allowed": False,
        "provider_calls_by_this_planner": 0,
        "telegram_sends_by_this_planner": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capability", required=True, type=Path)
    args = parser.parse_args()
    plan = build_plan(json.loads(args.capability.read_text()))
    print(json.dumps(plan, sort_keys=True, indent=2, allow_nan=False))
    return 2  # Deliberately cannot be mistaken for deployment readiness PASS.


if __name__ == "__main__":
    raise SystemExit(main())
