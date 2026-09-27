"""Finite-window Persistent compatibility, using only systemd-evaluated events.

Forecast windows assume ordinary old ticks occur. Actual installation separately
requires observed LastTriggerUSec; a forecast is never evidence of a real run.
"""
from bisect import bisect_right
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import math
import re

from calendar_proof import NAMES, OLD, TARGET, DST_WINDOWS, evaluate

CHANGED = NAMES[1:]
GUARD_SECONDS = 10
INSTALL_RESERVE_SECONDS = 60


def baseline_schedules(baseline):
    schedules = {}
    for unit in CHANGED:
        props = baseline['units'][unit]['properties']
        values = re.findall(r'OnCalendar=(.*?) ; next_elapse=', props.get('TimersCalendar', ''))
        if values != [OLD[unit]] or props.get('Persistent') != 'yes':
            raise ValueError('PERSISTENT_BASELINE_DRIFT:'+unit)
        schedules[unit] = values[0]
    return schedules


@lru_cache(maxsize=128)
def events(expression, start, end, unit, zone):
    # Bound enumeration by the fastest cadence of each allowed timer. Always
    # require an event beyond end so a truncated result cannot establish safety.
    minimum = {NAMES[1]: 600, NAMES[2]: 1800, NAMES[3]: 604800, NAMES[4]: 86400}[unit]
    count = math.ceil((end-start).total_seconds()/minimum)+4
    result = tuple(evaluate(expression, start-timedelta(seconds=1), count, zone))
    if result[-1] <= end:
        raise ValueError('PERSISTENT_ENUMERATION_TRUNCATED:'+unit)
    return result


def series(baseline, target, start, end):
    old = baseline_schedules(baseline)
    origin = start-timedelta(days=9)  # Includes preceding weekly event across DST.
    return {u: (events(old[u], origin, end, u, baseline['timezone']),
                events(target[u], origin, end, u, baseline['timezone'])) for u in CHANGED}


def prior(values, moment):
    index = bisect_right(values, moment)-1
    if index < 0:
        raise ValueError('PERSISTENT_PRIOR_EVENT_MISSING')
    return values[index]


def boundary_clear(values, moment):
    index = bisect_right(values, moment)
    return all(abs((t-moment).total_seconds()) >= GUARD_SECONDS
               for t in values[max(0,index-1):index+1])


def common_windows(baseline, target, start, end):
    evaluated = series(baseline, target, start, end)
    cuts = {start, end}
    for old, new in evaluated.values():
        for tick in (*old, *new):
            for shift in (-GUARD_SECONDS, 0, GUARD_SECONDS):
                point = tick+timedelta(seconds=shift)
                if start < point < end:
                    cuts.add(point)
    windows = []
    points = sorted(cuts)
    for left, right in zip(points, points[1:]):
        midpoint = left+(right-left)/2
        safe = all(prior(old, midpoint) >= prior(new, midpoint)
                   and boundary_clear(old, midpoint) and boundary_clear(new, midpoint)
                   for old, new in evaluated.values())
        if safe:
            if windows and windows[-1][1] == left:
                windows[-1] = (windows[-1][0], right)
            else:
                windows.append((left, right))
    return windows


def proof(baseline, target=TARGET, current_start=None):
    start = current_start or datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    reports = []
    for label, begin, days in [('current_eight_days', start, 8),
            *[(label, datetime.fromisoformat(value), 2)
              for label, value in zip(('spring_dst', 'autumn_dst'), DST_WINDOWS)]]:
        end = begin+timedelta(days=days)
        windows = common_windows(baseline, target, begin, end)
        usable = [(a,b) for a,b in windows if (b-a).total_seconds() > INSTALL_RESERVE_SECONDS]
        # Every UTC day in this evaluated horizon must offer an operator window.
        coverage = {(begin+timedelta(days=i)).date().isoformat():
            sum(a.date() == (begin+timedelta(days=i)).date() for a,b in usable) for i in range(days)}
        reports.append({'label': label, 'start_utc': begin.isoformat(), 'end_utc_exclusive': end.isoformat(),
            'window_count': len(usable), 'windows_per_utc_day': coverage,
            'recurring': all(coverage.values()),
            'windows': [{'start_utc': a.isoformat(), 'end_utc_exclusive': b.isoformat(),
                         'latest_install_start_utc_exclusive': (b-timedelta(seconds=INSTALL_RESERVE_SECONDS)).isoformat()}
                        for a,b in usable]})
    return {'evaluator': 'systemd-analyze calendar with installed tzdata',
        'host_timezone': baseline['timezone'], 'baseline_original_schedules': baseline_schedules(baseline),
        'target_schedules': {u:target[u] for u in CHANGED}, 'persistent_preserved': True,
        'boundary_guard_seconds': GUARD_SECONDS, 'install_reserve_seconds': INSTALL_RESERVE_SECONDS,
        'predicate': 'latest evaluated original tick >= latest evaluated target tick for every changed timer; outside old and target boundary guards',
        'forecast_limit': 'Conditional on normal original ticks. Actual LastTriggerUSec is mandatory at install; no forecast is a run receipt.',
        'windows': reports, 'compatible': all(r['recurring'] for r in reports)}
