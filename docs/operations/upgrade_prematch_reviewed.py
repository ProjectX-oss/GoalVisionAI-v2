"""Explicit upgrade of the installed, no-send PREMATCH V2 configuration.

Reuse reviewed V2 validation, lock, atomic writes and start gates. Never apply,
remove installed release drop-ins, invoke application commands, or alter history.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import time
import install_prematch_v2 as base

JOURNAL = Path('/var/lib/goalvision-prematch-upgrade/transaction.json')
LOG_DIR = Path('/var/log/goalvision-prematch')
LOG = LOG_DIR / 'discovery-output.log'
ROTATION = Path('/etc/logrotate.d/goalvision-prematch-reviewed')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_files(fingerprints: dict) -> None:
    for name, digest in fingerprints.items():
        if sha(Path(name)) != digest:
            raise SystemExit('Configuration/package drift: ' + name)


def render(m: dict, service: str, *, previous=False, observe=True, labels=True) -> bytes:
    config = m['previous'] if previous else m['proposed']
    value = base.dropin(config, service, send=False, observe=observe, labels=labels)
    if (not previous or m.get('previous_protected_stdout', False)) and service == base.SERVICES[0]:
        value += ('StandardOutput=append:' + str(LOG) + '\n').encode()
    return value


def state(m: dict, originals: dict) -> tuple[bool, bool, bool]:
    for previous in (True, False):
        for observe, labels in ((False, False), (True, False), (True, True)):
            if all(originals[s] == render(m, s, previous=previous, observe=observe, labels=labels)
                   for s in base.SERVICES):
                return previous, observe, labels
    raise SystemExit('Unknown or mixed installed configuration; explicit recovery/review required.')


def validate(m: dict) -> None:
    for config in (m['previous'], m['proposed']):
        base.validate_manifest(config)
        release = Path(config['release'])
        git = ('git', '-c', 'safe.directory=' + str(release), '-C', str(release))
        if base.run(*git, 'rev-parse', 'HEAD') != config['commit'] or base.run(*git, 'status', '--porcelain', '--untracked-files=all'):
            raise SystemExit('Release identity or cleanliness changed.')
        if base.run(*git, 'rev-parse', 'HEAD:app') != config['application_tree']:
            raise SystemExit('Application tree changed.')
        environment = Path(config['release_environment_file'])
        if environment.read_bytes() != ('PYTHONPATH=' + str(release) + '\n').encode():
            raise SystemExit('Unexpected release environment.')
        if sha(environment) != config['release_environment_sha256']:
            raise SystemExit('Environment fingerprint changed.')
    release = Path(m['proposed']['release'])
    git = ('git', '-c', 'safe.directory=' + str(release), '-C', str(release))
    if base.run(*git, 'ls-files', '--others', '--ignored', '--exclude-standard'):
        raise SystemExit('Unexpected ignored files in isolated release.')
    check_files(m['payload_sha256'])
    check_files(m['host_fingerprints'])
    for name, expected in m.get('configuration_directories', {}).items():
        path = Path(name)
        actual = sorted(p.name for p in path.glob('*.conf')) if path.exists() else []
        actual = [n for n in actual if n != base.START_GATE]
        if actual != expected:
            raise SystemExit('Unloaded configuration drift: ' + name)
    for name, expected in m['host_metadata'].items():
        info = Path(name).stat()
        if [stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid] != expected:
            raise SystemExit('Host permissions/ownership drift: ' + name)
    # No operational argument, quota, credential or observation path changes.
    for key in ('services', 'discovery_service', 'discovery_command', 'observation_arguments', 'ledger'):
        if m['previous'][key] != m['proposed'][key]:
            raise SystemExit('Operational arguments changed: ' + key)
    if base.run('systemctl', 'show', 'logrotate.timer', '-p', 'ActiveState', '--value') != 'active':
        raise SystemExit('Existing log rotation timer is not active.')


def configuration(m: dict, originals: dict, *, gated=False) -> None:
    base.validate_configuration(m['proposed'], originals, gated=gated)
    for service, digest in m.get('effective_environment_sha256', {}).items():
        value = base.run('systemctl', 'show', service, '-p', 'Environment', '--value')
        if hashlib.sha256(value.encode()).hexdigest() != digest:
            raise SystemExit('Effective environment drift: ' + service)
    for service, expected in m['effective_static'].items():
        for key, value in expected.items():
            if base.run('systemctl', 'show', service, '-p', key, '--value') != value:
                raise SystemExit('Effective service drift: ' + service + ' ' + key)
    for service, original in originals.items():
        if not m.get('effective_commands'):
            continue
        lines = original.decode().splitlines()
        environment = [v.removeprefix('EnvironmentFile=') for v in lines if v.startswith('EnvironmentFile=')][-1]
        if base.run('systemctl', 'show', service, '-p', 'EnvironmentFiles', '--value') != environment + ' (ignore_errors=no)':
            raise SystemExit('Effective release environment drift: ' + service)
        command = m['effective_commands'][service]
        if service == base.SERVICES[0]:
            command = [v.removeprefix('ExecStart=') for v in lines if v.startswith('ExecStart=')][-1]
        loaded = base.run('systemctl', 'show', service, '-p', 'ExecStart', '--value')
        expected = '{ path=' + command.split()[0] + ' ; argv[]=' + command + ' ; ignore_errors=no ;'
        if not loaded.startswith(expected):
            raise SystemExit('Effective command drift: ' + service)
        sink = ('append' if any(v.startswith('StandardOutput=append:') for v in lines) else m['previous_stdout'][service])
        if base.run('systemctl', 'show', service, '-p', 'StandardOutput', '--value') != sink:
            raise SystemExit('Effective output sink drift: ' + service)


def output_setup(m: dict) -> None:
    """Root-owned directory/file; arvis can read but cannot alter log evidence."""
    group = pwd.getpwnam('arvis').pw_gid
    for path, mode, is_dir in ((LOG_DIR, 0o750, True), (LOG, 0o640, False)):
        if path.is_symlink():
            raise SystemExit('Output path must not be a symlink.')
        if not path.exists():
            if is_dir:
                path.mkdir(mode=mode)
            else:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
                os.close(fd)
            os.chown(path, 0, group)
        info = path.stat()
        if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (0, group, mode):
            raise SystemExit('Output permissions/ownership drift.')
    expected = Path(m['rotation_source']).read_bytes()
    if ROTATION.exists() and (ROTATION.is_symlink() or ROTATION.read_bytes() != expected):
        raise SystemExit('Rotation configuration drift.')
    if not ROTATION.exists():
        base.write_atomic(ROTATION, expected)
    info = ROTATION.stat()
    if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o644:
        raise SystemExit('Rotation ownership/permissions drift.')
    base.run('/usr/sbin/logrotate', '--debug', str(ROTATION))


def gates() -> dict:
    return {s: base.RUNTIME_SYSTEMD / (s + '.d') / base.START_GATE for s in base.SERVICES}


def write_gates() -> None:
    for path in gates().values():
        if path.exists() and path.read_bytes() != base.start_gate_content():
            raise SystemExit('Unknown start gate.')
        base.write_atomic(path, base.start_gate_content())
    base.run('systemctl', 'daemon-reload')


def clear_gates() -> None:
    for path in gates().values():
        if path.read_bytes() != base.start_gate_content():
            raise SystemExit('Start gate drift.')
        path.unlink()
    base.run('systemctl', 'daemon-reload')


def write_set(targets: dict, contents: dict) -> None:
    for service, path in targets.items():
        base.write_atomic(path, contents[service])
    base.run('systemd-analyze', 'verify', *[str(base.SYSTEMD / s) for s in targets])
    base.run('systemctl', 'daemon-reload')


def save_journal(data: dict) -> None:
    if JOURNAL.parent.is_symlink():
        raise SystemExit('Unsafe recovery journal directory.')
    if not JOURNAL.parent.exists():
        JOURNAL.parent.mkdir(mode=0o750)
        if os.geteuid() == 0:
            os.chown(JOURNAL.parent, 0, pwd.getpwnam('arvis').pw_gid)
    info = JOURNAL.parent.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o750:
        raise SystemExit('Unsafe recovery journal directory.')
    temporary = JOURNAL.with_suffix('.new')
    with temporary.open('x') as stream:
        os.chmod(temporary, 0o640)
        if os.geteuid() == 0:
            os.chown(temporary, 0, pwd.getpwnam('arvis').pw_gid)
        json.dump(data, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(JOURNAL)
    fd = os.open(JOURNAL.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def drain() -> None:
    deadline = time.monotonic() + 1800
    while not base.idle(list(base.SERVICES)):
        if time.monotonic() > deadline:
            raise RuntimeError('Service drain deadline exceeded.')
        time.sleep(1)


def restore_timers(active: list) -> None:
    if active:
        base.run('systemctl', 'start', *active)
        if any(base.run('systemctl', 'show', t, '-p', 'ActiveState', '--value') != 'active' for t in active):
            raise RuntimeError('Previously active timers did not resume.')


def operate(m: dict, action: str, manifest_digest: str) -> None:
    """Fence all four compatible services and retain recovery state on any failure."""
    validate(m)
    targets = {s: base.SYSTEMD / (s + '.d') / base.DROPIN for s in base.SERVICES}
    originals = {s: path.read_bytes() for s, path in targets.items()}
    timers = [s.removesuffix('.service') + '.timer' for s in base.SERVICES]
    emergency = JOURNAL.exists()
    if emergency:
        if action != 'recover':
            raise SystemExit('Unfinished transaction: use reviewed recover action.')
        info = JOURNAL.stat()
        if JOURNAL.is_symlink() or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o640:
            raise SystemExit('Unsafe recovery journal.')
        data = json.loads(JOURNAL.read_text())
        if data['manifest_sha256'] != manifest_digest:
            raise SystemExit('Recovery journal belongs to another manifest.')
        before = {s: value.encode() for s, value in data['before'].items()}
        after = {s: value.encode() for s, value in data['after'].items()}
        state(m, before)
        state(m, after)
        if any(originals[s] not in (before[s], after[s]) for s in targets):
            raise SystemExit('Unknown drift during interrupted upgrade; keep gates and review.')
        active = data['active_timers']
        if not set(active).issubset(timers):
            raise SystemExit('Unexpected recovery timer scope.')
        desired = before
        # A partial gate set is allowed only for this recorded interrupted operation.
        for service, path in gates().items():
            expected_paths = {str(targets[service])}
            if path.exists():
                if path.read_bytes() != base.start_gate_content():
                    raise SystemExit('Unknown recovery gate.')
                expected_paths.add(str(path))
            if set(base.run('systemctl', 'show', service, '-p', 'DropInPaths', '--value').split()) != expected_paths:
                raise SystemExit('Unknown effective recovery drop-ins.')
    else:
        previous, observe, labels = state(m, originals)
        configuration(m, originals)
        if any(path.exists() for path in gates().values()):
            raise SystemExit('Existing installer gate; review required.')
        if action == 'upgrade':
            if not previous or {s: sha(p) for s, p in targets.items()} != m['expected_dropins']:
                raise SystemExit('Upgrade requires exact reviewed installed configuration.')
            desired = {s: render(m, s, observe=observe, labels=labels) for s in targets}
        elif action == 'recover':
            if previous:
                raise SystemExit('Previous compatible release already installed.')
            desired = {s: render(m, s, previous=True, observe=observe, labels=labels) for s in targets}
        else:
            if previous:
                raise SystemExit('Upgrade controls require upgraded release; use prior reviewed controls before upgrade.')
            if action == 'disable-data-labels':
                observe = labels = False
            desired = {s: render(m, s, observe=observe, labels=labels) for s in targets}
        states = {t: base.run('systemctl', 'show', t, '-p', 'ActiveState', '--value') for t in timers}
        if any(v not in ('active', 'inactive', 'failed') for v in states.values()):
            raise SystemExit('Transitional timer state; retry at a stable boundary.')
        active = [t for t, v in states.items() if v == 'active']
        if action == 'upgrade':
            output_setup(m)
        elif not previous:
            if not LOG.exists() or not ROTATION.exists():
                raise SystemExit('Installed output configuration missing.')
            output_setup(m)
        data = {'manifest_sha256': manifest_digest, 'active_timers': active,
                'before': {s: b.decode() for s, b in originals.items()},
                'after': {s: b.decode() for s, b in desired.items()}}
        save_journal(data)
    try:
        if active:
            base.run('systemctl', 'stop', *active)
        if any(base.run('systemctl', 'show', t, '-p', 'ActiveState', '--value') not in ('inactive', 'failed') for t in timers):
            raise RuntimeError('Timer triggers did not pause.')
        write_gates()
        drain()
        validate(m)
        configuration(m, originals, gated=True)
        if not base.idle(list(base.SERVICES)):
            raise RuntimeError('Service not drained.')
        write_set(targets, desired)
        configuration(m, desired, gated=True)
        clear_gates()
        configuration(m, desired)
        restore_timers(active)
    except BaseException:
        # Restore while fenced. If recovery itself fails, gates and journal remain;
        # do not resume timers against a mixed release. Never touch ledger records.
        try:
            if active:
                base.run('systemctl', 'stop', *active)
            write_gates()
            drain()
            restored = {s: v.encode() for s, v in data['before'].items()}
            write_set(targets, restored)
            configuration(m, restored, gated=True)
            clear_gates()
            configuration(m, restored)
            restore_timers(active)
        except BaseException:
            write_gates()
            raise RuntimeError('Recovery incomplete: keep new picks disabled; retain journal and run recover after reviewing the failure.') from None
        else:
            JOURNAL.unlink()
        raise
    JOURNAL.unlink()
    print('Configuration changed; no application cycle invoked. Installation, scheduled tick and re-enable are separate states.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('action', choices=('upgrade', 'recover', 'disable-new-picks', 'disable-data-labels', 'check'))
    parser.add_argument('--sha256', required=True, help='Reviewed manifest SHA-256')
    args = parser.parse_args()
    if sha(args.manifest) != args.sha256:
        raise SystemExit('Manifest fingerprint mismatch.')
    m = json.loads(args.manifest.read_text())
    if args.action == 'check':
        validate(m)
        originals = {s: (base.SYSTEMD / (s + '.d') / base.DROPIN).read_bytes() for s in base.SERVICES}
        previous, observe, labels = state(m, originals)
        configuration(m, originals)
        print(json.dumps({'release_state': 'previous' if previous else 'upgraded', 'new_picks': False,
                          'observe': observe, 'labels': labels, 'journal_pending': JOURNAL.exists()}))
        return
    if os.geteuid() != 0:
        raise SystemExit('Operator installation requires root.')
    with base.installer_lock():
        operate(m, args.action, args.sha256)


if __name__ == '__main__':
    main()
