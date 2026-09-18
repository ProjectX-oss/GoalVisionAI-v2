"""Lab product publication clock; never a model feature or settlement gate."""
from __future__ import annotations
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

RIGA=ZoneInfo('Europe/Riga')
POLICY_VERSION='LAB_RIGA_PUBLICATION_V2'


def local(value: datetime | str) -> datetime:
    """Reject ambiguous naive clocks instead of assuming the host timezone."""
    stamp=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('TIMEZONE_AWARE_TIMESTAMP_REQUIRED')
    return stamp.astimezone(RIGA)


def publication_blocker(now: datetime, kickoffs: list[datetime | str]) -> str | None:
    """Allow decisions and fixture kickoffs only within the Riga daytime window."""
    if not 9 <= local(now).hour < 23:
        return 'LAB_PUBLICATION_WINDOW_CLOSED'
    if any(not 9 <= local(k).hour < 23 for k in kickoffs):
        return 'FIXTURE_AFTER_LAB_CUTOFF'
    return None


def window_status(now: datetime) -> dict:
    clock=local(now)
    opening=clock.replace(hour=9,minute=0,second=0,microsecond=0)
    closing=clock.replace(hour=23,minute=0,second=0,microsecond=0)
    if clock>=opening:opening+=timedelta(days=1)
    if clock>=closing:closing+=timedelta(days=1)
    return {'window':'09:00–23:00 Europe/Riga',
            'state':'OPEN' if 9 <= clock.hour < 23 else 'CLOSED',
            'timezone':'Europe/Riga','next_open':opening.isoformat(),
            'next_close':closing.isoformat(),'next_cutoff':closing.isoformat(),
            'policy_version':POLICY_VERSION}
