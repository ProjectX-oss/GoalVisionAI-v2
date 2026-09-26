"""Explicit Riga discovery opportunities, including DST-safe identities."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from .contracts import utc

RIGA = ZoneInfo('Europe/Riga')
HOURS = (8, 10, 12, 14, 16, 18, 20, 22)
VERSION = 'LIVE_RIGA_TWO_HOUR_V1'


def opportunities(day: date) -> tuple[datetime, ...]:
    """Eight wall-clock opportunities even on 23/25-hour days."""
    return tuple(datetime.combine(day, time(hour), RIGA) for hour in HOURS)


def opportunity(now: datetime) -> str | None:
    """Permit start only in the first five minutes; never catch up missed slots."""
    local = utc(now).astimezone(RIGA)
    if local.hour not in HOURS or local.minute >= 5:
        return None
    return local.replace(minute=0, second=0, microsecond=0).isoformat()


def prematch_remaining(now: datetime, *, include_current: bool = True) -> int:
    """Count future/current slots through UTC provider reset, including next Riga date."""
    clock = utc(now)
    end = (clock + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    local_day = clock.astimezone(RIGA).date()
    count = 0
    for day in (local_day, local_day + timedelta(days=1)):
        for hour in range(9, 23):
            for minute in (0, 30):
                slot = utc(datetime.combine(day, time(hour, minute), RIGA))
                # Current potentially running cycle remains fully protected.
                if (include_current and slot <= clock < slot + timedelta(minutes=30)) or clock < slot < end:
                    count += 1
    return count
