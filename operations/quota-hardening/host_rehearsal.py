"""One bounded, read-only host inspection. No application entrypoints or writes."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

ROOT = Path('/home/arvis/goalvision-operations/lab-v2-public-message-upgrade-v2-20260926')
DATABASE = Path('/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db')
SERVICES = ('goalvision-lab-v2-discover', 'goalvision-lab-combo-settle',
            'goalvision-adaptive-learning-observer', 'goalvision-adaptive-learning',
            'goalvision-lab-weekly-stats')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def show(unit: str, properties: str) -> dict[str, str]:
    result = subprocess.run(['systemctl', 'show', unit, '-p', properties],
                            check=True, capture_output=True, text=True, timeout=3)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    fingerprints = {**manifest['host_fingerprints'],
                    **json.loads((ROOT / 'release-files.json').read_text())}
    for service in manifest['expected_dropins']:
        proposed = ROOT / (service + '.proposed')
        expected = manifest['payload_sha256'][str(proposed)]
        if sha(proposed) != expected:
            raise ValueError('ACCEPTED_PACKAGE_DRIFT')
        fingerprints['/etc/systemd/system/' + service + '.d/90-reviewed-prematch-v2.conf'] = expected
    before = {name: sha(Path(name)) for name in fingerprints}
    drift = [name for name in fingerprints if before[name] != fingerprints[name]]
    states = {s: show(s+'.service', 'ActiveState,SubState,EnvironmentFiles,FragmentPath,DropInPaths') for s in SERVICES}
    timers = {s: show(s+'.timer', 'ActiveState,UnitFileState') for s in SERVICES}
    info = DATABASE.stat()
    needle = f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino}'
    locks = [line.split()[1:] for line in Path('/proc/locks').read_text().splitlines() if needle in line]
    result = {'started_at': started, 'configuration_drift': drift,
              'verified_files': len(fingerprints), 'services': states, 'timers': timers,
              'audit_inode_locks_at_sample': locks, 'lock_holder_proven': False,
              'admin_sender': 'OPERATOR_REPORTED_DISABLED_NOT_READABLE',
              'database': {}, 'api_calls': 0, 'telegram_sends': 0,
              'mutating_commands': 0, 'live_database_writes': 0}
    c = sqlite3.connect(DATABASE.resolve().as_uri()+'?mode=ro', uri=True, timeout=.1)
    try:
        c.execute('PRAGMA query_only=ON')
        deadline = time.monotonic()+1.0
        c.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        result['database']['journal_mode'] = c.execute('PRAGMA journal_mode').fetchone()[0]
        result['database']['schema_version'] = c.execute('SELECT max(version) FROM adaptive_schema').fetchone()[0]
        result['database']['integrity_check'] = [row[0] for row in c.execute('PRAGMA integrity_check(1)').fetchall()]
        result['database']['foreign_key_violations'] = len(c.execute('PRAGMA foreign_key_check').fetchall())
        result['database']['elapsed_ms'] = round((time.monotonic()-(deadline-1))*1000, 3)
    except sqlite3.Error as error:
        result['database']['error_code'] = getattr(error, 'sqlite_errorname', 'SQLITE_ERROR')
    finally:
        c.close()
    result['configuration_unchanged_during_rehearsal'] = all(sha(Path(n)) == h for n,h in before.items())
    result['completed_at'] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
