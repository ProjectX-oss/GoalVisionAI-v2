"""Read-only package and PREMATCH drift check; never refresh accepted fingerprints."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


def main() -> int:
    root = Path(__file__).resolve().parent
    failures = []
    for line in (root/'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (root/name).resolve()
        if root not in path.parents or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append('PACKAGE_MISMATCH')
    baseline = json.loads((root/'host-baseline.json').read_text())
    for name, expected in baseline['protected_sha256'].items():
        try:
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != expected:
                failures.append('PREMATCH_FILE_DRIFT')
        except OSError:
            failures.append('PREMATCH_FINGERPRINT_UNREADABLE')
    try:
        listed = subprocess.run(['systemctl', 'list-units', '--all', '--plain', '--no-legend', '--type=service,timer'],
                                capture_output=True, text=True, timeout=5, check=True)
        names = [line.split()[0] for line in listed.stdout.splitlines() if line.strip()]
        loaded = subprocess.run(['systemctl', 'show', *names, '--property=Id,NeedDaemonReload'],
                                capture_output=True, text=True, timeout=5, check=True)
        if 'NeedDaemonReload=yes' in loaded.stdout:
            failures.append('PENDING_LOADED_CONFIGURATION_DRIFT')
        if not names:
            failures.append('LOADED_UNITS_UNKNOWN')
    except (OSError, subprocess.SubprocessError):
        failures.append('LOADED_DRIFT_CHECK_UNAVAILABLE')
    print(json.dumps({'check': 'BLOCKED' if failures else 'FILES_AND_LOADED_STATE_MATCH',
                      'failures': sorted(set(failures)), 'installation': 'NOT_PERFORMED',
                      'sender_validation': 'NOT_PERFORMED', 'api_calls': 0, 'telegram_sends': 0}, sort_keys=True))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
