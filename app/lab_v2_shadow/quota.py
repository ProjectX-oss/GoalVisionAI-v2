"""Adaptive API-Football discovery budgeting for the Lab V2 path."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo


MAX_DISCOVERY_CALLS_PER_CYCLE = 400
SETTLEMENT_RESULT_RESERVE = 100
DAILY_SAFETY_RESERVE = SETTLEMENT_RESULT_RESERVE
ODDS_BASE_CYCLE_FRACTION = Decimal("0.58")
ODDS_RELEASED_RESERVE_CYCLE_FRACTION = Decimal("0.70")
MINIMUM_ENRICHMENT_CALLS = 12
DISCOVERY_CYCLES_PER_DAY_30_MINUTES = 28
RIGA = ZoneInfo("Europe/Riga")
PRIORITY_EXACT_RETRIES_PER_CYCLE = 20


def discovery_cycles_remaining(now: datetime) -> int:
    """Count the current half-hour slot and remaining slots in Riga's day."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("DISCOVERY_TIME_REQUIRES_OFFSET")
    local = now.astimezone(RIGA)
    if not 9 <= local.hour < 23:
        return 0
    return (23 - local.hour) * 2 - int(local.minute >= 30)


def discovery_state(now: datetime) -> str:
    """Authoritative application guard, including manual discovery commands."""
    return "DAYTIME_DISCOVERY" if discovery_cycles_remaining(now) else "NIGHT_DISCOVERY_PAUSED"


@dataclass(frozen=True, slots=True)
class AdaptiveQuotaBudget:
    requested_maximum: int
    effective_cycle_maximum: int
    already_consumed: int
    additional_calls_available: int
    daily_remaining_observed: int | None
    minute_remaining_observed: int | None
    daily_safety_reserve: int
    reserve_headroom: int | None
    status: str
    remaining_discovery_cycles: int = 0
    base_cycle_budget: int = 0

    def document(self) -> dict[str, object]:
        return asdict(self)


def adaptive_quota_budget(
    quota: dict[str, object], *, requested_maximum: int,
    already_consumed: int, now: datetime, daily_safety_reserve: int = DAILY_SAFETY_RESERVE,
) -> AdaptiveQuotaBudget:
    """Pace remaining daylight slots using provider quota, keeping 100 result calls."""
    if not 1 <= requested_maximum <= MAX_DISCOVERY_CALLS_PER_CYCLE:
        raise ValueError("LAB_V2_MAXIMUM_CALLS_MUST_BE_BETWEEN_1_AND_400")
    if daily_safety_reserve != SETTLEMENT_RESULT_RESERVE:
        raise ValueError("LAB_V2_USE_SETTLEMENT_RESULT_RESERVE_100")
    daily = _integer(quota.get("daily_remaining"))
    minute = _integer(quota.get("minute_remaining"))
    normalized = quota.get("interpretation_status") == "NORMALIZED"
    if not normalized or daily is None or minute is None:
        return AdaptiveQuotaBudget(
            requested_maximum, already_consumed, already_consumed, 0,
            daily, minute, daily_safety_reserve, None,
            "QUOTA_UNAVAILABLE_STOP_AFTER_STATUS",
        )
    reserve_headroom = max(0, daily - daily_safety_reserve)
    hard_remaining = max(0, requested_maximum - already_consumed)
    cycles = discovery_cycles_remaining(now)
    base = reserve_headroom // cycles if cycles else 0
    additional = min(hard_remaining, base, minute)
    status = "FULL_MAXIMUM_SAFE" if already_consumed + additional == requested_maximum else "REDUCED_TO_PRESERVE_QUOTA"
    return AdaptiveQuotaBudget(
        requested_maximum, already_consumed + additional, already_consumed,
        additional, daily, minute, daily_safety_reserve, reserve_headroom,
        status if cycles else "NIGHT_DISCOVERY_PAUSED", cycles, base,
    )


def projected_daily_usage(*, maximum_per_cycle: int, cycles_per_day: int = DISCOVERY_CYCLES_PER_DAY_30_MINUTES,
                          operational_reserve: int = DAILY_SAFETY_RESERVE) -> dict[str, int | bool]:
    if maximum_per_cycle < 0 or cycles_per_day < 0 or operational_reserve < 0:
        raise ValueError("PROJECTED_USAGE_INPUT_INVALID")
    discovery = maximum_per_cycle * cycles_per_day
    total = discovery + operational_reserve
    return {
        "discovery_cycles": cycles_per_day,
        "maximum_calls_per_cycle": maximum_per_cycle,
        "maximum_discovery_calls": discovery,
        "final_review_settlement_result_retry_reserve": operational_reserve,
        "projected_worst_case_total": total,
        "daily_provider_limit": 7500,
        "within_daily_limit": total <= 7500,
    }


def _integer(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None
