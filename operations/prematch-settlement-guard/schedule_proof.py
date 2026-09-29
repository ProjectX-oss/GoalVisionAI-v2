"""Enumerate every normal settlement tick using installed systemd/tzdata."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent/'vendor'))
from calendar_proof import NAMES, TARGET, evaluate


def proof() -> dict:
    """Prove horizon eligibility; discovery-active checks remain independent."""
    zone = Path('/etc/timezone').read_text().strip()
    windows = []
    for label, date in (('current', '2026-09-29'), ('spring_dst', '2026-03-28'),
                        ('autumn_dst', '2026-10-24')):
        start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
        end = start + timedelta(hours=48)
        discovery = evaluate(TARGET[NAMES[0]], start-timedelta(seconds=1), 100, zone)
        ticks = evaluate(TARGET[NAMES[1]], start-timedelta(seconds=1), 320, zone)
        rows = []
        for tick in ticks:
            if tick >= end:
                break
            following = next(t for t in discovery if t > tick)
            gap = int((following-tick).total_seconds())
            rows.append({'settlement_utc': tick.isoformat(),
                         'settlement_host': tick.astimezone(ZoneInfo(zone)).isoformat(),
                         'next_discovery_utc': following.isoformat(),
                         'seconds_to_discovery': gap, 'outside_guard': gap > 180})
        assert rows and ticks[-1] >= end and all(r['outside_guard'] for r in rows)
        edges = [r for r in rows if datetime.fromisoformat(r['settlement_host']).minute in (25,55)]
        windows.append({'label': label, 'start_utc': start.isoformat(), 'end_utc': end.isoformat(),
                        'ticks': rows, 'tick_count': len(rows),
                        'minimum_seconds_to_discovery': min(r['seconds_to_discovery'] for r in rows),
                        'minimum_25_55_seconds': min(r['seconds_to_discovery'] for r in edges)})
    return {'evaluator': 'systemd-analyze calendar', 'host_timezone': zone,
            'systemd_version': subprocess.check_output(['/usr/bin/systemd-analyze', '--version'], text=True).splitlines()[0],
            'tzdata_version': Path('/usr/share/zoneinfo/tzdata.zi').read_text().splitlines()[0],
            'zoneinfo_sha256': {z: hashlib.sha256((Path('/usr/share/zoneinfo')/z).read_bytes()).hexdigest()
                               for z in (zone, 'Europe/Riga')},
            'schedules': TARGET, 'guard_seconds': 180, 'windows': windows,
            'all_normal_ticks_outside_horizon': True,
            'limits': 'Nominal calendar proof. AccuracySec=60s leaves at least 240s before discovery. Catch-up/late starts use actual runtime deadline; active discovery can defer any tick.'}


if __name__ == '__main__':
    print(json.dumps(proof(), indent=2))
