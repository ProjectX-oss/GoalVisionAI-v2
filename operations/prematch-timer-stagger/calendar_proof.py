"""Evaluate exact calendars with the host's systemd and timezone database."""
from datetime import datetime, timedelta, timezone
import itertools
import json
import os
import re
import subprocess

NAMES = ('goalvision-lab-v2-discover.timer', 'goalvision-lab-combo-settle.timer',
         'goalvision-adaptive-learning-observer.timer', 'goalvision-lab-weekly-stats.timer',
         'goalvision-adaptive-learning.timer')
OLD = dict(zip(NAMES, ('*-*-* 09..22:00,30:00 Europe/Riga', '*-*-* *:00/10:00',
                      '*-*-* *:00/30:00', 'Sun *-*-* 22:30:00 Europe/Riga', '*-*-* 04:15:00')))
TARGET = {**OLD, NAMES[1]: '*-*-* *:05,15,25,35,45,55:00',
          NAMES[2]: '*-*-* *:08,38:00', NAMES[3]: 'Sun *-*-* 22:45:00 Europe/Riga'}
# The requested weekly target is deliberately retained until the operator resolves
# its contradiction with settlement at :45. Collision checks block installation.
WINDOWS = ('2026-09-26T21:00:00+00:00', '2026-03-28T00:00:00+00:00',
           '2026-10-24T00:00:00+00:00')


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


def proof(target=TARGET, local_zone='Europe/Berlin'):
    reports = []
    for value in WINDOWS:
        start = datetime.fromisoformat(value)
        end = start + timedelta(hours=48)
        series = {u: [t for t in evaluate(expr, start-timedelta(seconds=1), local_zone=local_zone)
                      if start <= t < end] for u, expr in target.items()}
        collisions = {a + ' / ' + b: [t.isoformat() for t in sorted(set(series[a]) & set(series[b]))]
                      for a, b in itertools.combinations(NAMES[:4], 2)}
        cadence = {u: sorted({int((b-a).total_seconds()) for a, b in zip(series[u], series[u][1:])})
                   for u in NAMES[1:3]}
        old_series = {u: [t for t in evaluate(OLD[u], start-timedelta(seconds=1), local_zone=local_zone) if t < end] for u in NAMES[1:3]}
        old_gaps = {u: sorted({int((b-a).total_seconds()) for a,b in zip(v,v[1:])}) for u,v in old_series.items()}
        old_research = [t for t in evaluate(OLD[NAMES[4]], start-timedelta(seconds=1), local_zone=local_zone) if t < end]
        reports.append({'start_utc': start.isoformat(), 'end_utc_exclusive': end.isoformat(),
            'counts': {u: len(v) for u, v in series.items()}, 'collisions': collisions,
            'cadence_seconds': cadence, 'original_cadence_seconds': old_gaps,
            'cadence_preserved': cadence == old_gaps and all(len(series[u]) == len(old_series[u]) for u in old_series), 'research_unchanged': series[NAMES[4]] == old_research,
            'discovery_unchanged': target[NAMES[0]] == OLD[NAMES[0]]})
    return {'evaluator': 'systemd-analyze calendar', 'host_timezone': local_zone,
            'schedules': target, 'windows': reports,
            'zero_collisions': all(not hits for r in reports for hits in r['collisions'].values())}


if __name__ == '__main__':
    print(json.dumps(proof(), indent=2))
