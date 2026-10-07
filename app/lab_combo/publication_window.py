"""Lab product publication clock; never a model feature or settlement gate."""
from __future__ import annotations
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from app.adaptive_lab.daypart import discovery_hours

RIGA=ZoneInfo('Europe/Riga')
POLICY_VERSION='LAB_RIGA_SAME_DAY_PUBLICATION_V3'


def local(value: datetime | str) -> datetime:
    """Reject ambiguous naive clocks instead of assuming the host timezone."""
    stamp=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('TIMEZONE_AWARE_TIMESTAMP_REQUIRED')
    return stamp.astimezone(RIGA)


def publication_blocker(now: datetime, kickoffs: list[datetime | str]) -> str | None:
    """Allow new picks only for the same Riga date within the daytime window."""
    clock = local(now)
    start, end = discovery_hours()
    if not start <= clock.hour < end:
        return 'LAB_PUBLICATION_WINDOW_CLOSED'
    if any(not 9 <= local(k).hour < 23 for k in kickoffs):
        return 'FIXTURE_AFTER_LAB_CUTOFF'
    if any(local(k).date() != clock.date() for k in kickoffs):
        return 'FIXTURE_NOT_TODAY_RIGA'
    return None


def window_status(now: datetime) -> dict:
    clock=local(now)
    start, end = discovery_hours()
    opening=clock.replace(hour=start,minute=0,second=0,microsecond=0)
    closing=clock.replace(hour=end,minute=0,second=0,microsecond=0)
    cutoff=clock.replace(hour=23,minute=0,second=0,microsecond=0)
    if clock>=cutoff:cutoff+=timedelta(days=1)
    if clock>=opening:opening+=timedelta(days=1)
    if clock>=closing:closing+=timedelta(days=1)
    return {'window':f'{start:02d}:00–{end:02d}:00 Europe/Riga',
            'state':'OPEN' if start <= clock.hour < end else 'CLOSED',
            'timezone':'Europe/Riga','next_open':opening.isoformat(),
            'next_close':closing.isoformat(),'next_cutoff':cutoff.isoformat(),
            'policy_version':POLICY_VERSION if (start,end)==(9,23) else 'LAB_RIGA_DAYPART_PUBLICATION_V1'}
