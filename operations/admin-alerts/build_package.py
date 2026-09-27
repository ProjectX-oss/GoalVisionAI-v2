"""Prepare a standalone reviewed payload. No installation or systemctl mutation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    destination = args.output.resolve()
    if destination.exists():
        raise SystemExit('Output already exists; inspect it before rebuilding.')
    destination.mkdir(mode=0o755, parents=True)
    (destination/'app/admin_alerts').mkdir(parents=True)
    (destination/'app/__init__.py').write_text('"""Standalone ADMIN package namespace."""\n')
    for source in (repo/'app/admin_alerts').glob('*.py'):
        shutil.copyfile(source, destination/'app/admin_alerts'/source.name)
    for name in ('run.py', 'admin-alerts.json', 'goalvision-admin-alerts.service',
                 'goalvision-admin-alerts.timer', 'disable-admin-alerts', 'package_check.py', 'install_package.py'):
        shutil.copyfile(Path(__file__).parent/name, destination/name)
    shutil.copyfile(repo/'docs/operations/PREMATCH_ADMIN_ALERTS_V1_HOST.json', destination/'host-baseline.json')
    entries = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination/'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name,digest in entries.items()))
    print(json.dumps({'package': str(destination), 'files': len(entries),
                      'checksums_sha256': hashlib.sha256((destination/'SHA256SUMS').read_bytes()).hexdigest()}, sort_keys=True))


if __name__ == '__main__':
    main()
