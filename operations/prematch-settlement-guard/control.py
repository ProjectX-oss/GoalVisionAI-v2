#!/usr/bin/python3
"""Operator-only settlement routing transaction; never controls workers or timers."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterator

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import runtime_guard as guard

PACKAGE = Path(__file__).resolve().parent
UNIT_ROOT = Path('/etc/systemd/system')
SEARCH_ROOTS = (UNIT_ROOT, Path('/run/systemd/system'), Path('/usr/lib/systemd/system'))
STATE = Path('/var/lib/goalvision-prematch-settlement-guard')
RELEASE = Path('/opt/goalvision-settlement-guard-v1')
SERVICE = 'goalvision-lab-combo-settle.service'
OWNED = '99-goalvision-settlement-guard.conf'
ADMIN_CONFIG = Path('/etc/goalvision-admin-alerts/admin-alerts.json')
STAGGER_RECEIPT = Path('/var/lib/goalvision-prematch-timer-stagger/transaction.json')
# These systemd unit dependency arrays have no semantic member order.
DEPENDENCY_KEYS = frozenset(('After', 'Before', 'Requires', 'Wants', 'OnFailure', 'OnSuccess'))
PREDECESSOR_MANIFEST = 'c50abe7fc9f7f44a3c05d12fbc81fb41cf53be847d17a09b5f316f0ac85bcfb5'
PREDECESSOR_GUARD = '4ab82ae534403e2a3d8f7e1b589220b555b8f3cfac63bb7c878337eea53ea5ff'
PREDECESSOR_ROUTE = 'c78ae7eb2347d049d2b9c763d4f77316b91a566de1eaa9f642c6754db6e36d51'
PREDECESSOR_BASELINE = 'f78123f84c612e58d3d47cd1897d9afdaa0a058b805d22bc7abc6c223544374e'
RECOVERY_SCHEMA = 'settlement-guard-installing-recovery-v1'
SERVICE_KEYS = ('Type', 'User', 'Group', 'WorkingDirectory', 'StandardOutput', 'StandardError',
    'TimeoutStartUSec', 'TimeoutStopUSec', 'KillMode', 'SendSIGKILL', 'UMask',
    'NoNewPrivileges', 'ProtectSystem', 'ProtectHome', 'PrivateTmp', 'PrivateNetwork',
    'ReadOnlyPaths', 'ReadWritePaths', 'InaccessiblePaths', 'EnvironmentFiles',
    'ExecStartPre', 'ExecStartPost', 'ExecCondition', 'ExecStop', 'ExecStopPost',
    'RootDirectory', 'RootImage', 'SupplementaryGroups', 'CapabilityBoundingSet',
    'AmbientCapabilities', 'RestrictAddressFamilies', 'SystemCallFilter',
    'OnFailure', 'OnSuccess', 'Requires', 'Wants', 'After', 'Before')
UNIT_KEYS = ('Id', 'LoadState', 'FragmentPath', 'DropInPaths', 'NeedDaemonReload',
    'ActiveState', 'SubState', 'UnitFileState', 'TimersCalendar', 'AccuracyUSec',
    'RandomizedDelayUSec', 'Persistent', 'InvocationID', 'ExecMainStatus', 'Result')


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def property_equal(key: str, actual: str, expected: str) -> bool:
    """Compare only dependency arrays as exact token sets; keep all other pins exact."""
    if key in DEPENDENCY_KEYS:
        return set(actual.split()) == set(expected.split())
    return actual == expected


def regular(path: Path) -> Path:
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK_REFUSED')
    require(path.is_file(), 'FILE_UNAVAILABLE')
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(regular(path).read_bytes()).hexdigest()


def verify_package(root: Path, digest: str) -> None:
    """Require an externally reviewed manifest digest and exact file inventory."""
    require(bool(re.fullmatch('[a-f0-9]{64}', digest)), 'MANIFEST_DIGEST_REQUIRED')
    require(sha(root/'SHA256SUMS') == digest, 'MANIFEST_TAMPER')
    names = set()
    for line in (root/'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        require(name not in names and not Path(name).is_absolute() and '..' not in Path(name).parts,
                'INVALID_MANIFEST')
        require(sha(root/name) == expected, 'PACKAGE_TAMPER')
        names.add(name)
    require(names == {str(p.relative_to(root)) for p in root.rglob('*')
                      if p.is_file() and p.name != 'SHA256SUMS'}, 'PACKAGE_INVENTORY_DRIFT')


def atomic(path: Path, content: bytes, mode: int = 0o600) -> None:
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK_REFUSED')
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.guard-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            os.fchmod(stream.fileno(), mode)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def route() -> Path:
    return UNIT_ROOT/(SERVICE+'.d')/OWNED


def wrapped_argv() -> tuple[str, ...]:
    return ('/usr/bin/python3', '-I', '-S', str(RELEASE/'runtime_guard.py'))


def payload() -> bytes:
    return ('# Owned by goalvision settlement guard v1\n[Service]\nExecStart=\nExecStart='
            + ' '.join(wrapped_argv()) + '\n').encode()


def exec_argv(value: str) -> str:
    match = re.fullmatch(r'\{ path=[^;]+ ; argv\[\]=(.*?) ; ignore_errors=no ; .* \}', value)
    require(match is not None, 'EXECSTART_UNRECOGNIZED')
    return match[1]


class Host:
    """Narrow systemd adapter with daemon-reload as its only mutation."""
    def show(self, unit: str) -> dict[str, str]:
        require(unit in baseline()['units'], 'UNIT_NOT_ALLOWED')
        keys = (*UNIT_KEYS, *SERVICE_KEYS, 'ExecStart', 'Environment')
        output = subprocess.run(['/usr/bin/systemctl', 'show', unit, '--property='+','.join(keys)],
                                capture_output=True, text=True, check=True, timeout=10).stdout
        props = dict(line.split('=', 1) for line in output.splitlines() if '=' in line)
        props['Environment_sha256'] = hashlib.sha256(props.pop('Environment', '').encode()).hexdigest()
        return props

    def reload(self) -> None:
        subprocess.run(['/usr/bin/systemctl', 'daemon-reload'], check=True,
                       capture_output=True, timeout=30)

    def protected(self) -> None:
        config = json.loads(regular(ADMIN_CONFIG).read_bytes())
        require(config.get('sender', {}).get('enabled') is False, 'ADMIN_DISABLED_REQUIRED')
        receipt = json.loads(regular(STAGGER_RECEIPT).read_bytes())
        require(receipt.get('phase') == 'installed' and receipt.get('manifest') ==
                '61f3a3263cab3bf25fd064071ae8744190f6effa0f8c984f5d1aae2c3b2ba598',
                'STAGGER_V4_INSTALLED_REQUIRED')


def baseline() -> dict[str, Any]:
    return json.loads((PACKAGE/'baseline.json').read_bytes())


def require_root_owned(path: Path) -> None:
    """Installed artifacts must be root-owned and not group/world writable."""
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK_REFUSED')
    require(path.stat().st_uid == 0 and path.stat().st_mode & 0o022 == 0, 'OWNER_MODE_DRIFT')


def inspect(host: Host, installed: bool, pending: bool = False) -> dict[str, Any]:
    """Reject source, environment, sandbox, timer and foreign drop-in drift."""
    pin = baseline()
    require(Path('/etc/timezone').read_text().strip() == pin['timezone'] and
            hashlib.sha256(Path('/etc/localtime').read_bytes()).hexdigest() == pin['localtime_sha256'],
            'TIMEZONE_DRIFT')
    for unit, entry in pin['units'].items():
        props = host.show(unit)
        require(props.get('LoadState') == 'loaded', 'UNIT_NOT_LOADED')
        for path, digest in entry['files_sha256'].items():
            require(sha(Path(path)) == digest, 'UNIT_HASH_DRIFT')
        expected = set(entry['properties']['DropInPaths'].split())
        if unit == SERVICE and installed:
            expected.add(str(route()))
        actual = set(props['DropInPaths'].split())
        require(actual == expected or (pending and unit == SERVICE and
                actual - {str(route())} == expected - {str(route())}), 'DROPIN_DRIFT')
        for root in SEARCH_ROOTS:
            # Include generic and dash-prefix drop-ins, which can affect a unit.
            prefixes = [unit+'.d', unit.rsplit('.', 1)[1]+'.d']
            stem, suffix = unit.rsplit('.', 1)
            prefixes.extend(stem[:i+1]+'.'+suffix+'.d' for i,c in enumerate(stem) if c == '-')
            for directory in prefixes:
                require({str(p) for p in (root/directory).glob('*.conf')} <= expected,
                        'UNLOADED_DROPIN_DRIFT')
        if not (pending and unit == SERVICE):
            require(props['NeedDaemonReload'] == 'no', 'DAEMON_RELOAD_DRIFT')
        for key, value in entry['stable'].items():
            # systemctl show may omit empty non-dependency properties.
            require((key not in DEPENDENCY_KEYS or key in props) and
                    property_equal(key, props.get(key, ''), value), 'UNIT_PROPERTY_DRIFT_'+key)
        if unit == SERVICE and not pending:
            target = wrapped_argv() if installed else guard.SETTLEMENT_ARGV
            require(exec_argv(props['ExecStart']) == ' '.join(target), 'EXECSTART_DRIFT')
        if unit.endswith('.timer'):
            calendar = re.findall(r'OnCalendar=(.*?) ; next_elapse=', props.get('TimersCalendar', ''))
            require(calendar == [entry['calendar']], 'CALENDAR_DRIFT')
    for path, digest in pin['environment_files_sha256'].items():
        require(sha(Path(path)) == digest, 'ENVIRONMENT_FILE_DRIFT')
    if installed:
        require(set(p.name for p in RELEASE.iterdir()) == {'runtime_guard.py'}, 'RELEASE_INVENTORY_DRIFT')
        require(regular(route()).read_bytes() == payload(), 'ROUTING_TAMPER')
        require(sha(RELEASE/'runtime_guard.py') == sha(PACKAGE/'runtime_guard.py'), 'GUARD_TAMPER')
        for path in (RELEASE, RELEASE/'runtime_guard.py', route()):
            require_root_owned(path)
    elif not pending:
        require(not route().exists() and not route().is_symlink(), 'ROUTING_ALREADY_PRESENT')
    host.protected()
    return {'pins': 'PASS', 'guard_installed': installed, 'guard_seconds': 180}


def transaction() -> dict[str, Any] | None:
    path = STATE/'transaction.json'
    return json.loads(regular(path).read_bytes()) if path.exists() else None


def save(tx: dict[str, Any]) -> None:
    atomic(STATE/'transaction.json', json.dumps(tx, sort_keys=True).encode())


@contextmanager
def locked() -> Iterator[None]:
    require(os.geteuid() == 0, 'ROOT_REQUIRED')
    require(not STATE.is_symlink(), 'SYMLINK_REFUSED')
    STATE.mkdir(mode=0o700, exist_ok=True)
    require_root_owned(STATE)
    require(not (STATE/'lock').is_symlink(), 'SYMLINK_REFUSED')
    with (STATE/'lock').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def idle(host: Host) -> None:
    props = host.show(SERVICE)
    require((props['ActiveState'], props['SubState']) == ('inactive', 'dead'), 'SETTLEMENT_NOT_IDLE')
    # Refuse near a scheduled start without stopping, gating or restarting timers.
    raw = guard.command(['/usr/bin/busctl', '--system', '--json=short', 'get-property',
        'org.freedesktop.systemd1', '/org/freedesktop/systemd1/unit/goalvision_2dlab_2dcombo_2dsettle_2etimer',
        'org.freedesktop.systemd1.Timer', 'NextElapseUSecRealtime'])
    value = json.loads(raw)
    require(value.get('type') == 't' and type(value.get('data')) is int and
            60_000_000 < value['data'] - __import__('time').time_ns()//1000 < 660_000_000,
            'SETTLEMENT_INSTALL_WINDOW_UNAVAILABLE')


def predecessor(tx: dict[str, Any]) -> None:
    """Accept only the operator-identified interrupted installation."""
    require(isinstance(tx, dict), 'RECOVERY_RECEIPT_INVALID')
    require(tx.get('manifest') == PREDECESSOR_MANIFEST, 'RECOVERY_PREDECESSOR_MISMATCH')
    require(tx.get('phase') == 'installing', 'RECOVERY_INSTALLING_REQUIRED')
    require(tx.get('original_argv') == list(guard.SETTLEMENT_ARGV), 'ORIGINAL_ARGV_DRIFT')
    require('recovery' not in tx and 'installed_at' not in tx, 'RECOVERY_RECEIPT_AMBIGUOUS')


def authorize_transaction(tx: dict[str, Any], digest: str) -> None:
    """Bind normal actions to this package or its explicitly recovered predecessor."""
    require(tx.get('original_argv') == list(guard.SETTLEMENT_ARGV), 'ORIGINAL_ARGV_DRIFT')
    if tx.get('manifest') == digest:
        require('recovery' not in tx, 'RECOVERY_LINKAGE_INVALID')
        return
    require(tx.get('manifest') == PREDECESSOR_MANIFEST, 'TRANSACTION_PACKAGE_MISMATCH')
    proof = tx.get('recovery', {})
    require(isinstance(proof, dict), 'RECOVERY_LINKAGE_INVALID')
    require(proof.get('schema') == RECOVERY_SCHEMA and proof.get('manifest') == digest,
            'TRANSACTION_PACKAGE_MISMATCH')
    raw = proof.get('predecessor_receipt', '')
    require(isinstance(raw, str), 'RECOVERY_LINKAGE_INVALID')
    require(hashlib.sha256(raw.encode()).hexdigest() == proof.get('predecessor_receipt_sha256'),
            'RECOVERY_LINKAGE_INVALID')
    previous = json.loads(raw)
    predecessor(previous)
    require(tx.get('phase') in ('installed', 'rolling_back', 'rolled_back') and
            tx.get('installed_at') == proof.get('recovered_at'), 'RECOVERY_LINKAGE_INVALID')
    require(isinstance(proof.get('recovered_at'), str), 'RECOVERY_LINKAGE_INVALID')
    stamp = datetime.fromisoformat(proof['recovered_at'])
    require(stamp.tzinfo is not None, 'RECOVERY_LINKAGE_INVALID')
    require({k: v for k, v in tx.items() if k not in ('phase', 'installed_at', 'recovery')} ==
            {k: v for k, v in previous.items() if k != 'phase'}, 'RECOVERY_LINKAGE_INVALID')


def recovery_state(host: Host) -> None:
    """Read the loaded route and idle state without any systemd mutation."""
    props = host.show(SERVICE)
    require((props.get('ActiveState'), props.get('SubState')) == ('inactive', 'dead'),
            'SETTLEMENT_NOT_IDLE')
    require(props.get('NeedDaemonReload') == 'no', 'DAEMON_RELOAD_DRIFT')
    require(re.fullmatch(r'\{ path=/usr/bin/python3 ; argv\[\]=' +
            re.escape(' '.join(wrapped_argv())) + r' ; ignore_errors=no ; [^{}]* \}',
            props.get('ExecStart', '')) is not None, 'EXECSTART_DRIFT')
    for unit in baseline()['units']:
        if unit.endswith('.timer'):
            timer = host.show(unit)
            require((timer.get('ActiveState'), timer.get('SubState')) == ('active', 'waiting'),
                    'RECOVERY_TIMER_STATE_DRIFT')


def recovery_preflight(host: Host) -> tuple[dict[str, Any], str]:
    """Run full production pins plus exact predecessor checks; perform no writes."""
    raw = regular(STATE/'transaction.json').read_bytes().decode('utf-8')
    tx = json.loads(raw)
    predecessor(tx)
    for path in (STATE, STATE/'transaction.json'):
        require_root_owned(path)
    require(sha(PACKAGE/'baseline.json') == PREDECESSOR_BASELINE, 'RECOVERY_BASELINE_DRIFT')
    require(sha(PACKAGE/'runtime_guard.py') == PREDECESSOR_GUARD, 'RECOVERY_PACKAGE_GUARD_DRIFT')
    require(sha(route()) == PREDECESSOR_ROUTE, 'RECOVERY_ROUTING_TAMPER')
    require(sha(RELEASE/'runtime_guard.py') == PREDECESSOR_GUARD, 'RECOVERY_GUARD_TAMPER')
    recovery_state(host)
    inspect(host, True)  # No partial-transaction exemptions.
    recovery_state(host)
    require(regular(STATE/'transaction.json').read_bytes().decode('utf-8') == raw, 'RECOVERY_RECEIPT_CHANGED')
    return tx, raw


def recover(host: Host, digest: str, finalize: bool = False) -> dict[str, Any]:
    """Finalize only metadata under the existing lock, preserving predecessor linkage."""
    if not finalize:
        tx, raw = recovery_preflight(host)
        return {'verdict': 'PASS', 'phase': tx['phase'], 'action': 'recovery-preflight',
                'predecessor_manifest': tx['manifest'], 'recovery_manifest': digest,
                'predecessor_receipt_sha256': hashlib.sha256(raw.encode()).hexdigest()}
    with locked():
        tx, raw = recovery_preflight(host)
        now = datetime.now(timezone.utc).isoformat()
        tx.update(phase='installed', installed_at=now, recovery={
            'schema': RECOVERY_SCHEMA, 'manifest': digest, 'recovered_at': now,
            'predecessor_receipt': raw,
            'predecessor_receipt_sha256': hashlib.sha256(raw.encode()).hexdigest()})
        authorize_transaction(tx, digest)
        save(tx)
        return tx


def change(host: Host, action: str, digest: str) -> dict[str, Any]:
    """Install/rollback only owned routing and files, retaining a recovery receipt."""
    with locked():
        tx = transaction()
        if tx:
            authorize_transaction(tx, digest)
        if action == 'install':
            require(not tx or tx['manifest'] == digest, 'RECOVERED_TRANSACTION_REINSTALL_REFUSED')
            require(not tx or tx['phase'] == 'rolled_back', 'TRANSACTION_PRESENT')
            inspect(host, False)
            idle(host)
            require(not RELEASE.exists() and not RELEASE.is_symlink(), 'RELEASE_ALREADY_PRESENT')
            tx = {'phase': 'installing', 'manifest': digest, 'original_argv': list(guard.SETTLEMENT_ARGV)}
            save(tx)
            require_root_owned(RELEASE.parent)
            RELEASE.mkdir(mode=0o755)
            RELEASE.chmod(0o755)
            atomic(RELEASE/'runtime_guard.py', (PACKAGE/'runtime_guard.py').read_bytes(), 0o444)
            route().parent.mkdir(exist_ok=True)
            idle(host)
            atomic(route(), payload(), 0o644)
            host.reload()
            inspect(host, True)
            tx.update(phase='installed', installed_at=datetime.now(timezone.utc).isoformat())
            save(tx)
        else:
            require(tx is not None, 'NO_TRANSACTION')
            if tx['phase'] == 'rolled_back':
                inspect(host, False)
                return tx
            # Partial installs are recoverable only when all present artifacts match.
            installed = route().exists()
            inspect(host, installed, pending=tx['phase'] != 'installed')
            idle(host)
            if RELEASE.exists():
                require(set(p.name for p in RELEASE.iterdir()) <= {'runtime_guard.py'}, 'RELEASE_INVENTORY_DRIFT')
                if (RELEASE/'runtime_guard.py').exists():
                    require(sha(RELEASE/'runtime_guard.py') == sha(PACKAGE/'runtime_guard.py'), 'GUARD_TAMPER')
            tx['phase'] = 'rolling_back'
            save(tx)
            if installed:
                require(regular(route()).read_bytes() == payload(), 'ROUTING_TAMPER')
                route().unlink()
                host.reload()
            elif host.show(SERVICE)['NeedDaemonReload'] != 'no' or exec_argv(host.show(SERVICE)['ExecStart']) != ' '.join(guard.SETTLEMENT_ARGV):
                host.reload()
            inspect(host, False)
            if RELEASE.exists():
                (RELEASE/'runtime_guard.py').unlink(missing_ok=True)
                RELEASE.rmdir()
            tx['phase'] = 'rolled_back'
            save(tx)
        return tx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('check', 'install', 'status', 'rollback', 'evidence',
                                                   'recovery-preflight', 'recover-installing'))
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--since')
    args = parser.parse_args()
    verify_package(PACKAGE, args.manifest_sha256)
    host = Host()
    if args.action in ('recovery-preflight', 'recover-installing'):
        result = recover(host, args.manifest_sha256, args.action == 'recover-installing')
    elif args.action in ('install', 'rollback'):
        result = change(host, args.action, args.manifest_sha256)
    else:
        tx = transaction()
        if tx:
            authorize_transaction(tx, args.manifest_sha256)
        phase = tx['phase'] if tx else 'not_installed'
        require(phase in ('installed', 'not_installed', 'rolled_back'), 'PARTIAL_TRANSACTION_USE_ROLLBACK')
        result = inspect(host, phase == 'installed')
        result['phase'] = phase
        if tx:
            result['manifest'] = tx['manifest']
            if 'recovery' in tx:
                result['recovery'] = tx['recovery']
        if args.action == 'check':
            require(phase != 'installed', 'ALREADY_INSTALLED')
            idle(host)
        if args.action == 'evidence':
            require(phase == 'installed', 'INSTALLATION_REQUIRED')
            from guard_evidence import evidence
            since = args.since or tx['installed_at']
            require(datetime.fromisoformat(since.replace('Z', '+00:00')) >=
                    datetime.fromisoformat(tx['installed_at']), 'PREINSTALL_EVIDENCE_REFUSED')
            result = evidence(host, since)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if result.get('verdict', 'PASS') != 'PASS' else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        # Only our bounded single-token refusal codes may leave the process.
        code = str(exc) if isinstance(exc, ValueError) and re.fullmatch(r'[A-Z][A-Za-z0-9_]{0,100}', str(exc)) else 'GUARD_PREFLIGHT_OR_OPERATION_FAILED'
        print(json.dumps({'status': 'REFUSED', 'code': code}), file=sys.stderr)
        raise SystemExit(1)
