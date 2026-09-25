"""Apply a reviewed, service-specific release at an idle boundary; never run a cycle.

Usage: sudo python install_prematch_v2.py /absolute/package/manifest.json apply
Other actions: disable-data-labels, disable-new-picks, rollback.
The manifest is generated after tests and identifies a clean immutable worktree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

DROPIN = '90-reviewed-prematch-v2.conf'


def run(*args: str) -> str:
    """Run bounded local administrative commands; never read credential files."""
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=60).strip()


def labelled_receipts(ledger: Path) -> int:
    """Block incompatible rollback after any confirmed new attributed selection."""
    with sqlite3.connect(ledger.as_uri() + '?mode=ro', uri=True, timeout=5) as connection:
        return connection.execute("""SELECT count(*) FROM evidence p JOIN evidence r
            ON r.kind='receipt' AND r.identity='single_prediction:'||p.identity
            WHERE p.kind='single_prediction' AND json_type(p.document,'$.selection_origin') IS NOT NULL
              AND json_extract(r.document,'$.sent')=1""").fetchone()[0]


def main() -> None:
    """Change only reviewed drop-ins, preserve timers and never interrupt a transaction."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('action', choices=('apply', 'disable-data-labels', 'disable-new-picks', 'rollback'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Root is required only to install systemd drop-ins and reload units.')
    manifest = json.loads(args.manifest.read_text())
    release = Path(manifest['release'])
    if run('git', '-c', 'safe.directory=' + str(release), '-C', str(release), 'rev-parse', 'HEAD') != manifest['commit']:
        raise SystemExit('Release identity changed; re-audit required.')
    if run('git', '-c', 'safe.directory=' + str(release), '-C', str(release), 'status', '--porcelain'):
        raise SystemExit('Release is dirty; re-audit required.')
    if manifest.get('regression_status') != 'PASSED':
        raise SystemExit('Offline regression gate has not passed.')
    for path, expected in manifest['installed_fingerprints'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise SystemExit('Installed configuration changed: ' + path)
    if args.action == 'rollback' and labelled_receipts(Path(manifest['ledger'])):
        raise SystemExit('Keep compatible settlement/report code; use disable-new-picks or disable-data-labels.')
    services = manifest['services'] if args.action in {'apply', 'rollback'} else [manifest['discovery_service']]
    targets = {service: Path('/etc/systemd/system') / (service + '.d') / DROPIN for service in services}
    originals = {service: path.read_bytes() if path.exists() else None for service, path in targets.items()}
    if args.action == 'apply' and any(value is not None for value in originals.values()):
        raise SystemExit('Reviewed drop-in already exists; do not overwrite another rollout.')
    if args.action != 'apply' and any(value is None for value in originals.values()):
        raise SystemExit('This rollout is not installed on every requested service.')
    timers = [s.removesuffix('.service') + '.timer' for s in services]
    active = [timer for timer in timers if run('systemctl', 'show', timer, '-p', 'ActiveState', '--value') == 'active']
    changed = False
    try:
        # Pause timer triggers only. Already running oneshots finish normally.
        if active:
            run('systemctl', 'stop', *active)
        deadline = time.monotonic() + 1800
        while any(run('systemctl', 'show', service, '-p', 'ActiveState', '--value') not in {'inactive', 'failed'} for service in services):
            if time.monotonic() > deadline:
                raise RuntimeError('Idle-boundary deadline exceeded; configuration unchanged.')
            time.sleep(1)
        for service, path in targets.items():
            path.parent.mkdir(exist_ok=True)
            changed = True
            if args.action == 'rollback':
                path.unlink()
                continue
            content = '[Service]\nEnvironmentFile=\nEnvironmentFile=' + manifest['release_environment_file'] + '\n'
            if service == manifest['discovery_service']:
                command = list(manifest['discovery_command'])
                if args.action == 'apply':
                    command += manifest['observation_arguments'] + ['--label-v2-selections']
                elif args.action == 'disable-new-picks':
                    command.remove('--send')
                    command += manifest['observation_arguments']
                content += 'ExecStart=\nExecStart=' + ' '.join(command) + '\n'
            temporary = path.with_suffix('.new')
            temporary.write_text(content)
            temporary.chmod(0o644)
            temporary.replace(path)
        run('systemd-analyze', 'verify', *[str(Path('/etc/systemd/system') / service) for service in services])
        run('systemctl', 'daemon-reload')
    except BaseException:
        if changed:
            for service, path in targets.items():
                original = originals[service]
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            run('systemctl', 'daemon-reload')
        raise
    finally:
        if active:
            run('systemctl', 'start', *active)
    print('Configuration installed; no manual cycle started. Verify the next scheduled tick.')


if __name__ == '__main__':
    main()
