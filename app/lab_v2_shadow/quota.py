"""Adaptive API-Football discovery budgeting for the Lab V2 path."""

from __future__ import annotations

from dataclasses import asdict, dataclass


QUOTA_POLICY_VERSION = "LAB_ADAPTIVE_QUOTA_V2"
MAX_DISCOVERY_CALLS_PER_CYCLE = 400
SETTLEMENT_RESERVE = 100
DAILY_SAFETY_RESERVE = 1500
MINIMUM_ENRICHMENT_CALLS = 12
DISCOVERY_CYCLES_PER_DAY_30_MINUTES = 48


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
    policy_version: str = QUOTA_POLICY_VERSION
    settlement_reserve: int = 0
    final_review_reserve: int = 0
    demand_calls: int | None = None

    def document(self) -> dict[str, object]:
        return asdict(self)


def adaptive_quota_budget(
    quota: dict[str, object], *, requested_maximum: int,
    already_consumed: int, daily_safety_reserve: int = DAILY_SAFETY_RESERVE,
    settlement_reserve: int = 0, final_review_reserve: int = 0,
    tracked_demand: int = 0, remaining_odds_pages: int | None = None, discovery_days: int = 3,
) -> AdaptiveQuotaBudget:
    """Bound a cycle by exact provider quota without spending into reserve."""
    if not 1 <= requested_maximum <= MAX_DISCOVERY_CALLS_PER_CYCLE:
        raise ValueError("LAB_V2_MAXIMUM_CALLS_MUST_BE_BETWEEN_1_AND_400")
    if daily_safety_reserve < DAILY_SAFETY_RESERVE:
        raise ValueError("LAB_V2_DAILY_SAFETY_RESERVE_CANNOT_BE_LOWERED")
    daily = _integer(quota.get("daily_remaining"))
    minute = _integer(quota.get("minute_remaining"))
    normalized = quota.get("interpretation_status") == "NORMALIZED"
    if not normalized or daily is None or minute is None:
        return AdaptiveQuotaBudget(
            requested_maximum, already_consumed, already_consumed, 0,
            daily, minute, daily_safety_reserve, None,
            "QUOTA_UNAVAILABLE_STOP_AFTER_STATUS",
        )
    if min(settlement_reserve, final_review_reserve, tracked_demand, already_consumed) < 0 or not 1 <= discovery_days <= 7:
        raise ValueError('INVALID_QUOTA_DEMAND')
    reserve_headroom = max(0, daily - daily_safety_reserve - settlement_reserve)
    demand = None if remaining_odds_pages is None else (
        max(0, remaining_odds_pages) + final_review_reserve + tracked_demand + discovery_days * 16)

    hard_remaining = max(0, requested_maximum - already_consumed)
    additional = min(hard_remaining, reserve_headroom, minute)
    if requested_maximum > 100:
        # At most one quarter of safely spendable daily capacity in one cycle.
        additional = min(additional, max(0, (reserve_headroom + already_consumed) // 4 - already_consumed))
    if demand is not None:
        additional = min(additional, demand)
    status = "FULL_MAXIMUM_SAFE" if already_consumed + additional == requested_maximum else "REDUCED_TO_PRESERVE_QUOTA"
    return AdaptiveQuotaBudget(
        requested_maximum, already_consumed + additional, already_consumed,
        additional, daily, minute, daily_safety_reserve, reserve_headroom, status,
        QUOTA_POLICY_VERSION, settlement_reserve, final_review_reserve, demand,
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
