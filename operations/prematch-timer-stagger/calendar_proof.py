"""Evaluate exact calendars with the host's systemd and timezone database."""
from datetime import datetime, timedelta, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import re
import subprocess

NAMES = ('goalvision-lab-v2-discover.timer', 'goalvision-lab-combo-settle.timer',
         'goalvision-adaptive-learning-observer.timer', 'goalvision-lab-weekly-stats.timer',
         'goalvision-adaptive-learning.timer')
OLD = dict(zip(NAMES, ('*-*-* 09..22:00,30:00 Europe/Riga', '*-*-* *:00/10:00',
                      '*-*-* *:00/30:00', 'Sun *-*-* 22:30:00 Europe/Riga', '*-*-* 04:15:00')))
TARGET = {**OLD, NAMES[1]: '*-*-* *:05,15,25,35,45,55:00',
          NAMES[2]: '*-*-* *:08,38:00', NAMES[3]: 'Sun *-*-* 22:48:00 Europe/Riga',
          NAMES[4]: '*-*-* 04:20:00'}
# The first window is regenerated at runtime, including operator preflight.
DST_WINDOWS = ('2026-03-28T00:00:00+00:00', '2026-10-24T00:00:00+00:00')


def evaluate(expression, start, count=320, local_zone='Europe/Berlin'):
    """UTC output parsing; systemd, not arithmetic offsets, resolves local time/DST."""
    result = subprocess.run(['/usr/bin/systemd-analyze', 'calendar',
        '--base-time=' + start.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
        '--iterations=' + str(count), expression], check=True, text=True,
        capture_output=True, timeout=30, env={**os.environ, 'LC_ALL': 'C', 'TZ': local_zone})
    stamps = re.findall(r'\(in UTC\):\s+\w+ (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) UTC', result.stdout)
    # With UTC as the host zone systemd omits its redundant '(in UTC)' line.
    if local_zone == 'UTC':
        stamps = re.findall(r'(?:Next elapse|Iteration #\d+):\s+\w+ (\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) UTC', result.stdout)
    if not stamps:
        raise ValueError('SYSTEMD_CALENDAR_NO_TIMESTAMPS')
    return [datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc) for s in stamps]


def proof(target=TARGET, local_zone='Europe/Berlin', current_start=None):
    if set(target) != set(NAMES):
        raise ValueError('ALL_FIVE_TIMERS_REQUIRED')
    current_start = current_start or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    windows = (current_start.isoformat(), *DST_WINDOWS)
    reports = []
    for label, value in zip(('current_48_hours', 'spring_dst', 'autumn_dst'), windows):
        start = datetime.fromisoformat(value)
        end = start + timedelta(hours=48)
        def series_for(schedules):
            result = {}
            for unit, expression in schedules.items():
                events = evaluate(expression, start-timedelta(seconds=1), local_zone=local_zone)
                if events[-1] < end:
                    raise ValueError('CALENDAR_ENUMERATION_TRUNCATED:'+unit)
                result[unit] = [t for t in events if start <= t < end]
            return result
        series, old_series = series_for(target), series_for(OLD)
        collisions = {a + ' / ' + b: [t.isoformat() for t in sorted(set(series[a]) & set(series[b]))]
                      for a, b in itertools.combinations(NAMES, 2)}
        def gaps(events):
            return [int((b-a).total_seconds()) for a, b in zip(events, events[1:])]
        cadence = {u: sorted(set(gaps(series[u]))) for u in NAMES}
        old_gaps = {u: sorted(set(gaps(old_series[u]))) for u in NAMES}
        weekly_old = evaluate(OLD[NAMES[3]], start-timedelta(days=7), 3, local_zone)
        weekly_new = evaluate(target[NAMES[3]], start-timedelta(days=7), 3, local_zone)
        weekly_cadence = gaps(weekly_old) == gaps(weekly_new)
        research_shift = series[NAMES[4]] == [t+timedelta(minutes=5) for t in old_series[NAMES[4]]]
        separation = []
        for tick in series[NAMES[4]]:
            adjacent = evaluate(target[NAMES[1]], tick-timedelta(minutes=11), 4, local_zone)
            previous = max(t for t in adjacent if t < tick)
            following = min(t for t in adjacent if t > tick)
            separation.append({'previous_settlement_local': previous.astimezone(ZoneInfo(local_zone)).isoformat(),
                'research_local': tick.astimezone(ZoneInfo(local_zone)).isoformat(),
                'next_settlement_local': following.astimezone(ZoneInfo(local_zone)).isoformat(),
                'before_seconds': int((tick-previous).total_seconds()),
                'after_seconds': int((following-tick).total_seconds())})
        reports.append({'label': label, 'start_utc': start.isoformat(), 'end_utc_exclusive': end.isoformat(),
            'counts': {u: len(v) for u, v in series.items()}, 'collisions': collisions,
            'triggers_utc': {u: [t.isoformat() for t in v] for u, v in series.items()},
            'original_triggers_utc': {u: [t.isoformat() for t in v] for u, v in old_series.items()},
            'cadence_seconds': cadence, 'original_cadence_seconds': old_gaps,
            'weekly_cadence': {'original_utc': [t.isoformat() for t in weekly_old],
                'target_utc': [t.isoformat() for t in weekly_new],
                'original_gap_seconds': gaps(weekly_old), 'target_gap_seconds': gaps(weekly_new),
                'preserved': weekly_cadence},
            'cadence_preserved': weekly_cadence and cadence == old_gaps and all(len(series[u]) == len(old_series[u]) for u in NAMES),
            'research_shift_exactly_300_seconds': research_shift,
            'research_separation': separation,
            'research_separation_passed': bool(separation) and all(r['before_seconds'] == r['after_seconds'] == 300 for r in separation),
            'discovery_unchanged': series[NAMES[0]] == old_series[NAMES[0]]})
    zonefiles = (Path('/usr/share/zoneinfo')/local_zone, Path('/usr/share/zoneinfo/Europe/Riga'))
    return {'evaluator': 'systemd-analyze calendar', 'host_timezone': local_zone,
            'systemd_version': subprocess.run(['/usr/bin/systemd-analyze', '--version'], check=True,
                text=True, capture_output=True).stdout.splitlines()[0],
            'tzdata_version': Path('/usr/share/zoneinfo/tzdata.zi').read_text().splitlines()[0],
            'zoneinfo_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in zonefiles},
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'schedules': target, 'pair_count': 10, 'windows': reports,
            'zero_collisions': all(not hits for r in reports for hits in r['collisions'].values())}


if __name__ == '__main__':
    report = proof()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report['zero_collisions'] else 2)
