"""Opt-in Lab daypart and shared account reserves; no model/publication policy."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import os
from zoneinfo import ZoneInfo

RIGA = ZoneInfo('Europe/Riga')
RESULT_ATTEMPTS_PER_RUN = 21
EVENING_DISCOVERY_ALLOCATION = 1800


def flag(name: str) -> bool:
    value = os.environ.get(name, '0')
    if value not in ('0', '1'):
        raise ValueError('INVALID_LAB_DAYPART_FLAG')
    return value == '1'


def enabled() -> bool:
    return flag('GOALVISION_LAB_EVENING_MODE')


def feed_quotes_enabled() -> bool:
    return flag('GOALVISION_LIVE_API_FEED_QUOTES')


def quote_age_diagnostic_enabled() -> bool:
    return flag('GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC')


def clock_utc(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('DAYPART_TIME_REQUIRES_OFFSET')
    return now.astimezone(timezone.utc)


def discovery_hours() -> tuple[int, int]:
    return (10, 18) if enabled() else (9, 23)


def live_window(now: datetime) -> bool:
    return 18 <= clock_utc(now).astimezone(RIGA).hour < 23


def prematch_results_reserve(now: datetime) -> int:
    """Remaining :05/:15/... result runs to UTC reset plus one in-flight run."""
    clock = clock_utc(now)
    reset = (clock + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tick = clock.replace(second=0, microsecond=0)
    slots = 0
    while tick < reset:
        if tick >= clock and tick.minute % 10 == 5:
            slots += 1
        tick += timedelta(minutes=1)
    return max(100, (slots + 1) * RESULT_ATTEMPTS_PER_RUN)


def prematch_discovery_reserve(now: datetime) -> int:
    """Keep results plus an initial evening allocation before spending daytime quota."""
    return prematch_results_reserve(now) + EVENING_DISCOVERY_ALLOCATION


def live_cycles_remaining(now: datetime) -> int:
    """Current/future five-minute slots in the 18–23 Riga discovery window."""
    local = clock_utc(now).astimezone(RIGA)
    if not live_window(now):
        return 0
    return (23 - local.hour) * 12 - local.minute // 5


def live_budget(quota: dict, now: datetime, *, consumed: int) -> int:
    """Bound a run to 80 attempts; PREMATCH reserve is also enforced per HTTP."""
    daily = quota.get('daily_remaining')
    minute = quota.get('minute_remaining')
    if quota.get('interpretation_status') != 'NORMALIZED' or any(
            type(value) is not int or value < 0 for value in (daily, minute)):
        return consumed
    headroom = max(0, daily - prematch_results_reserve(now))
    slots = max(1, live_cycles_remaining(now))
    return min(80, consumed + min(headroom // slots, minute))
