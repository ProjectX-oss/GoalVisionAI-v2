"""Install a reviewed PREMATCH release at an idle boundary; never run a cycle.

Usage: sudo python install_prematch_v2.py /absolute/package/manifest.json apply
Other actions: disable-data-labels, disable-new-picks, rollback.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager, nullcontext
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
from typing import Iterator

DROPIN = '90-reviewed-prematch-v2.conf'
SYSTEMD = Path('/etc/systemd/system')
RUNTIME_SYSTEMD = Path('/run/systemd/system')
START_GATE = '91-prematch-installer-quiesce.conf'
INSTALLER_LOCK = Path('/run/lock/goalvision-prematch-v2-installer.lock')
SERVICES = (
    'goalvision-lab-v2-discover.service',
    'goalvision-lab-combo-settle.service',
    'goalvision-adaptive-learning-observer.service',
    'goalvision-lab-weekly-stats.service',
)


def run(*args: str) -> str:
    """Run bounded local administrative commands; never read credential files."""
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=60).strip()


@contextmanager
def installer_lock() -> Iterator[None]:
    """Serialize every action across packages; never unlink the shared lock inode."""
    with INSTALLER_LOCK.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another PREMATCH installer operation is running.') from None
        yield


def dropin(manifest: dict, service: str, *, send: bool = True,
           observe: bool = True, labels: bool = True) -> bytes:
    """Render only the reviewed command and its three explicit capability controls."""
    content = '[Service]\nEnvironmentFile=\nEnvironmentFile=' + manifest['release_environment_file'] + '\n'
    if service == manifest['discovery_service']:
        command = [arg for arg in manifest['discovery_command'] if send or arg != '--send']
        if observe:
            command += manifest['observation_arguments']
        if labels:
            command += ['--label-v2-selections']
        content += 'ExecStart=\nExecStart=' + ' '.join(command) + '\n'
    return content.encode()


def discovery_state(manifest: dict, content: bytes) -> tuple[bool, bool, bool]:
    """Accept exact known configurations, including the old no-send/no-label state."""
    for send in (False, True):
        for observe, labels in ((False, False), (True, False), (True, True)):
            if content == dropin(manifest, manifest['discovery_service'],
                                 send=send, observe=observe, labels=labels):
                return send, observe, labels
    raise SystemExit('Unexpected discovery configuration drift; refusing to overwrite.')


def validate_manifest(manifest: dict) -> None:
    """Limit this installer to the reviewed services and literal systemd arguments."""
    if tuple(manifest['services']) != SERVICES or manifest['discovery_service'] != SERVICES[0]:
        raise SystemExit('Unexpected service scope.')
    command = manifest['discovery_command']
    observation = manifest['observation_arguments']
    if (not isinstance(command, list) or command.count('--send') != 1
            or command[1:5] != ['-P', '-m', 'app.lab_v2_shadow', 'controlled-cycle']
            or any(arg.startswith(('--football-context-', '--label-v2-selections')) for arg in command)
            or not isinstance(observation, list) or len(observation) != 4
            or observation[::2] != ['--football-context-root', '--football-context-registry']):
        raise SystemExit('Unexpected discovery command or observation arguments.')
    # The reviewed package uses literal, whitespace-free paths/arguments. Reject
    # expansions, specifiers, quoting and newlines instead of guessing systemd syntax.
    for value in [*command, *observation, manifest['release_environment_file']]:
        if not isinstance(value, str) or not re.fullmatch(r'[-/A-Za-z0-9_.:]+', value):
            raise SystemExit('Unsupported systemd argument; review required.')
    if manifest.get('regression_status') != 'PASSED':
        raise SystemExit('Offline regression gate has not passed.')


def validate_release(manifest: dict) -> None:
    """Verify clean release, reviewed installer bytes and pinned environment."""
    release = Path(manifest['release'])
    git = ('git', '-c', 'safe.directory=' + str(release), '-C', str(release))
    if run(*git, 'rev-parse', 'HEAD') != manifest['commit']:
        raise SystemExit('Release identity changed; re-audit required.')
    if run(*git, 'status', '--porcelain', '--untracked-files=all'):
        raise SystemExit('Release is dirty; re-audit required.')
    if Path(__file__).read_bytes() != (release / 'docs/operations/install_prematch_v2.py').read_bytes():
        raise SystemExit('Installer differs from the reviewed release.')
    environment = Path(manifest['release_environment_file']).read_bytes()
    if (environment != ('PYTHONPATH=' + str(release) + '\n').encode()
            or hashlib.sha256(environment).hexdigest() != manifest['release_environment_sha256']):
        raise SystemExit('Release environment changed; review required.')


def validate_configuration(manifest: dict, originals: dict[str, bytes | None],
                           *, gated: bool = False) -> None:
    """Reject base-unit, effective drop-in or owned-file drift before writing."""
    required = {str(SYSTEMD / unit) for service in SERVICES
                for unit in (service, service.removesuffix('.service') + '.timer')}
    if not required.issubset(manifest['installed_fingerprints']):
        raise SystemExit('Missing installed unit fingerprints.')
    for path, expected in manifest['installed_fingerprints'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise SystemExit('Installed configuration changed: ' + path)
    for service, original in originals.items():
        target = SYSTEMD / (service + '.d') / DROPIN
        if (target.read_bytes() if target.exists() else None) != original:
            raise SystemExit('Reviewed drop-in changed during operation: ' + service)
        if run('systemctl', 'show', service, '-p', 'LoadState', '--value') != 'loaded':
            raise SystemExit('Service is not loaded: ' + service)
        expected = {str(target)} if original is not None else set()
        if gated:
            gate = RUNTIME_SYSTEMD / (service + '.d') / START_GATE
            if gate.read_bytes() != start_gate_content():
                raise SystemExit('Rollback start gate changed: ' + service)
            expected.add(str(gate))
        if set(run('systemctl', 'show', service, '-p', 'DropInPaths', '--value').split()) != expected:
            raise SystemExit('Unexpected effective service drop-ins: ' + service)
        if run('systemctl', 'show', service, '-p', 'FragmentPath', '--value') != str(SYSTEMD / service):
            raise SystemExit('Unexpected effective service fragment: ' + service)
        timer = service.removesuffix('.service') + '.timer'
        if run('systemctl', 'show', timer, '-p', 'DropInPaths', '--value'):
            raise SystemExit('Unexpected effective timer drop-ins: ' + timer)
        if run('systemctl', 'show', timer, '-p', 'FragmentPath', '--value') != str(SYSTEMD / timer):
            raise SystemExit('Unexpected effective timer fragment: ' + timer)
    command = manifest['discovery_command']
    working = run('systemctl', 'show', manifest['discovery_service'], '-p', 'WorkingDirectory', '--value')
    ledger_argument = command[command.index('--ledger') + 1] if '--ledger' in command else 'var/lab_combo/ledger.db'
    if not Path(working).is_absolute() or (Path(working) / ledger_argument).resolve() != Path(manifest['ledger']).resolve():
        raise SystemExit('Rollback ledger does not match the discovery command.')


def start_gate_content() -> bytes:
    """Return the exact temporary condition that denies new service starts."""
    return ('[Unit]\nConditionPathExists=!' + str(INSTALLER_LOCK) + '\n').encode()


@contextmanager
def prevent_service_starts(services: list[str]) -> Iterator[None]:
    """Skip new systemd starts during rollback without stopping running sends.

    A temporary runtime condition is false while the persistent installer lock
    file exists. Unlike a runtime mask, this also works with units in /etc.
    """
    paths = [RUNTIME_SYSTEMD / (service + '.d') / START_GATE for service in services]
    if any(path.exists() for path in paths):
        raise SystemExit('Existing rollback start gate; operator recovery/review required.')
    created = []
    try:
        for path in paths:
            write_atomic(path, start_gate_content())
            created.append(path)
        run('systemctl', 'daemon-reload')
        yield
    finally:
        for path in created:
            path.unlink()
        if created:
            run('systemctl', 'daemon-reload')


@contextmanager
def rollback_guard(ledger: Path) -> Iterator[None]:
    """Fence new durable send claims until configuration/reload/restore completes.

    All reviewed single send paths commit a ledger claim before transport. Taking
    the SQLite writer reservation AFTER service drain closes the check/write race,
    including non-systemd publishers. Any labelled claim (even without a receipt)
    is potentially delivered and refuses rollback. Never alter ledger evidence.
    """
    connection = sqlite3.connect(ledger.as_uri() + '?mode=rw', uri=True, timeout=5)
    try:
        connection.execute('BEGIN IMMEDIATE')
        count = connection.execute("""SELECT count(*) FROM evidence p
            WHERE p.kind='single_prediction'
              AND json_type(p.document,'$.selection_origin') IS NOT NULL
              AND EXISTS (SELECT 1 FROM evidence e WHERE
                (e.kind IN ('receipt', 'claim', 'delivery_unknown')
                 AND e.identity='single_prediction:'||p.identity)
                OR (e.kind='economic_claim' AND json_extract(e.document,'$.publication_identity')
                    ='single_prediction:'||p.identity))""").fetchone()[0]
        if count:
            raise SystemExit('Keep compatible settlement/report code: labelled publication or unresolved claim; '
                             'use disable-new-picks or disable-data-labels.')
        yield
    finally:
        connection.rollback()
        connection.close()


def idle(services: list[str]) -> bool:
    """Treat every transitional or unknown service state as not drained."""
    return all(run('systemctl', 'show', service, '-p', 'ActiveState', '--value')
               in {'inactive', 'failed'} for service in services)


def write_atomic(path: Path, content: bytes) -> None:
    """Replace one reviewed drop-in without exposing partial content."""
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix('.new')
    temporary.write_bytes(content)
    temporary.chmod(0o644)
    temporary.replace(path)


def change_configuration(manifest: dict, action: str, targets: dict[str, Path],
                         state: tuple[bool, bool, bool]) -> None:
    """Write/reload only requested units; the caller owns fenced recovery."""
    send, observe, labels = state
    if action == 'disable-new-picks':
        send = False
    elif action == 'disable-data-labels':
        observe = labels = False
    for service, path in targets.items():
        if action == 'rollback':
            path.unlink()
        else:
            write_atomic(path, dropin(manifest, service, send=send, observe=observe, labels=labels))
    run('systemd-analyze', 'verify', *[str(SYSTEMD / service) for service in targets])
    run('systemctl', 'daemon-reload')


def restore_configuration(targets: dict[str, Path], originals: dict[str, bytes | None]) -> None:
    """Restore compatible configuration before releasing the publication fence."""
    for service, path in targets.items():
        original = originals[service]
        if original is None:
            path.unlink(missing_ok=True)
        else:
            write_atomic(path, original)
    run('systemctl', 'daemon-reload')


def install(manifest: dict, action: str) -> None:
    """Pause relevant timers, drain services, then guard and change configuration."""
    validate_manifest(manifest)
    validate_release(manifest)
    services = manifest['services'] if action in {'apply', 'rollback'} else [manifest['discovery_service']]
    targets = {service: SYSTEMD / (service + '.d') / DROPIN for service in services}
    originals = {service: path.read_bytes() if path.exists() else None for service, path in targets.items()}
    if action == 'apply' and any(value is not None for value in originals.values()):
        raise SystemExit('Reviewed drop-in already exists; do not overwrite another rollout.')
    if action != 'apply' and any(value is None for value in originals.values()):
        raise SystemExit('This rollout is not installed on every requested service.')
    state = (True, True, True)
    if action != 'apply':
        state = discovery_state(manifest, originals[manifest['discovery_service']])
        for service, original in originals.items():
            if service != manifest['discovery_service'] and original != dropin(manifest, service):
                raise SystemExit('Unexpected settlement/report configuration drift: ' + service)
    validate_configuration(manifest, originals)
    timers = [s.removesuffix('.service') + '.timer' for s in services]
    states = {timer: run('systemctl', 'show', timer, '-p', 'ActiveState', '--value') for timer in timers}
    if any(state not in {'active', 'inactive', 'failed'} for state in states.values()):
        raise SystemExit('Timer state is transitional or unknown; retry at a stable boundary.')
    active = [timer for timer, state in states.items() if state == 'active']
    try:
        if active:
            run('systemctl', 'stop', *active)
        if any(run('systemctl', 'show', timer, '-p', 'ActiveState', '--value')
               not in {'inactive', 'failed'} for timer in timers):
            raise RuntimeError('Timer triggers did not pause; configuration unchanged.')
        # Keep the ledger fence through gate cleanup and any configuration recovery.
        with ExitStack() as fence:
            changed = False
            try:
                with prevent_service_starts(services) if action == 'rollback' else nullcontext():
                    validate_configuration(manifest, originals, gated=action == 'rollback')
                    deadline = time.monotonic() + 1800
                    while not idle(services):
                        if time.monotonic() > deadline:
                            raise RuntimeError('Idle-boundary deadline exceeded; configuration unchanged.')
                        time.sleep(1)
                    # Revalidate after the potentially long drain, before the decisive guard.
                    validate_release(manifest)
                    validate_configuration(manifest, originals, gated=action == 'rollback')
                    if action == 'rollback':
                        fence.enter_context(rollback_guard(Path(manifest['ledger'])))
                    if not idle(services):
                        raise RuntimeError('Services restarted during drain; configuration unchanged.')
                    changed = True
                    try:
                        change_configuration(manifest, action, targets, state)
                    except BaseException:
                        restore_configuration(targets, originals)
                        changed = False
                        raise
            except BaseException:
                if changed:
                    restore_configuration(targets, originals)
                raise

    finally:
        if active:
            run('systemctl', 'start', *active)
    print('Configuration installed; no manual cycle started. Verify the next scheduled tick.')


def main() -> None:
    """Hold the host-wide installer lock for validation, mutation and recovery."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('action', choices=('apply', 'disable-data-labels', 'disable-new-picks', 'rollback'))
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Root is required only to install systemd drop-ins and reload units.')
    with installer_lock():
        install(json.loads(args.manifest.read_text()), args.action)


if __name__ == '__main__':
    main()
