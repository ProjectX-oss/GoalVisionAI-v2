"""Lab product publication clock; never a model feature or settlement gate."""
from __future__ import annotations
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

RIGA=ZoneInfo('Europe/Riga')
POLICY_VERSION='LAB_RIGA_PUBLICATION_V1'


def local(value: datetime | str) -> datetime:
    """Reject ambiguous naive clocks instead of assuming the host timezone."""
    stamp=datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('TIMEZONE_AWARE_TIMESTAMP_REQUIRED')
    return stamp.astimezone(RIGA)


def publication_blocker(now: datetime, kickoffs: list[datetime | str]) -> str | None:
    """Daily 23:00 cutoff; no unrequested morning opening threshold is inferred."""
    if local(now).hour>=23:
        return 'LAB_PUBLICATION_TIME_CUTOFF'
    if any(local(k).hour>=23 for k in kickoffs):
        return 'FIXTURE_AFTER_LAB_CUTOFF'
    return None


def window_status(now: datetime) -> dict:
    clock=local(now);cutoff=clock.replace(hour=23,minute=0,second=0,microsecond=0)
    if clock>=cutoff:cutoff+=timedelta(days=1)
    return {'state':'CLOSED' if clock.hour>=23 else 'OPEN','timezone':'Europe/Riga',
            'next_cutoff':cutoff.isoformat(),'policy_version':POLICY_VERSION}
