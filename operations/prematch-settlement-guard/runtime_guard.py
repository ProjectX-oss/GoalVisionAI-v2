#!/usr/bin/python3
"""Settlement service boundary. Standard library only; no business imports."""
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

SETTLEMENT_PRE_DISCOVERY_GUARD_SECONDS = 180
SCHEMA = 'goalvision-settlement-runtime-guard-v1'
DISCOVERY = 'goalvision-lab-v2-discover.service'
TIMER = 'goalvision-lab-v2-discover.timer'
SETTLEMENT_ARGV = (
    '/home/arvis/GoalVisionAI/.venv/bin/python', '-P', '-m', 'app.lab_combo',
    'settle', '--send', '--adaptive-database',
    '/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db',
)
ACTIVE = 'SETTLEMENT_DEFERRED_DISCOVERY_ACTIVE'
IMMINENT = 'SETTLEMENT_DEFERRED_DISCOVERY_IMMINENT'
UNAVAILABLE = 'SETTLEMENT_DEFERRED_DISCOVERY_STATE_UNAVAILABLE'
EXECUTED = 'SETTLEMENT_EXECUTED'
PROPERTIES = ('Id', 'LoadState', 'ActiveState', 'SubState', 'InvocationID', 'NeedDaemonReload')


def command(argv: list[str]) -> str:
    """Read systemd with bounded waits; never forward command errors or stderr."""
    return subprocess.run(argv, check=True, capture_output=True, text=True,
                          timeout=2).stdout


def show(unit: str) -> dict[str, str]:
    """Read only the allowlisted service/timer properties."""
    if unit not in (DISCOVERY, TIMER):
        raise ValueError('UNIT_NOT_ALLOWED')
    text = command(['/usr/bin/systemctl', 'show', unit,
                    '--property=' + ','.join(PROPERTIES)])
    result = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
    if (set(result) != set(PROPERTIES) or result['Id'] != unit
            or result['LoadState'] != 'loaded' or result['NeedDaemonReload'] != 'no'):
        raise ValueError('STATE_UNAVAILABLE')
    return result


def next_elapse_us() -> int:
    """Read systemd's actual realtime deadline as integer microseconds via D-Bus."""
    state = show(TIMER)
    if (state['ActiveState'], state['SubState']) != ('active', 'waiting'):
        raise ValueError('TIMER_UNAVAILABLE')
    raw = command(['/usr/bin/busctl', '--system', '--json=short', 'get-property',
                   'org.freedesktop.systemd1',
                   '/org/freedesktop/systemd1/unit/goalvision_2dlab_2dv2_2ddiscover_2etimer',
                   'org.freedesktop.systemd1.Timer', 'NextElapseUSecRealtime'])
    value = json.loads(raw)
    deadline = value.get('data')
    if value.get('type') != 't' or type(deadline) is not int or not 0 < deadline < 2**63:
        raise ValueError('TIMER_DEADLINE_UNAVAILABLE')
    return deadline


def invocation(value: str) -> str:
    """Return only a journal invocation identifier, never arbitrary state text."""
    return value if re.fullmatch('[a-f0-9]{32}', value or '') else ''


def emit(code: str, identity: str, delta_us: int | None = None) -> None:
    """Write one small sanitized JSON record to the service's journal stderr."""
    record: dict[str, Any] = {
        'schema_version': SCHEMA,
        'status': 'EXECUTED' if code == EXECUTED else 'DEFERRED',
        'code': code, 'discovery_invocation': invocation(identity),
        'guard_seconds': SETTLEMENT_PRE_DISCOVERY_GUARD_SECONDS,
    }
    if code != EXECUTED:
        record.update(api_calls=0, telegram_sends=0, database_writes=0)
    if delta_us is not None:
        record['seconds_to_discovery'] = max(-86400, min(86400, delta_us / 1_000_000))
    print(json.dumps(record, sort_keys=True, separators=(',', ':')), file=sys.stderr, flush=True)


def run(read_state: Callable[[], dict[str, str]] | None = None,
        read_next: Callable[[], int] = next_elapse_us,
        clock_ns: Callable[[], int] = time.time_ns,
        execute: Callable[..., Any] = os.execv,
        report: Callable[..., None] = emit) -> int:
    """Observe twice, then replace this wrapper with the pinned settlement argv.

    This is a best-effort boundary check, not an atomic lock with discovery.
    A final kernel scheduling race and runs exceeding the horizon remain possible.
    """
    read_state = read_state or (lambda: show(DISCOVERY))
    identity = ''
    previous = None
    for _ in range(2):
        try:
            state = read_state()
            identity = invocation(state.get('InvocationID', ''))
            active, sub = state['ActiveState'], state['SubState']
            if active in ('activating', 'active', 'deactivating'):
                report(ACTIVE, identity)
                return 0
            if (active, sub) != ('inactive', 'dead'):
                raise ValueError('UNSAFE_DISCOVERY_STATE')
            if state.get('InvocationID', '') and not identity:
                raise ValueError('INVALID_INVOCATION')
            snapshot = (active, sub, identity)
            if previous is not None and snapshot != previous:
                raise ValueError('DISCOVERY_CHANGED_BETWEEN_OBSERVATIONS')
            deadline = read_next()
            if type(deadline) is not int or not 0 < deadline < 2**63:
                raise ValueError('INVALID_DEADLINE')
            delta = deadline - clock_ns() // 1000
            if delta <= SETTLEMENT_PRE_DISCOVERY_GUARD_SECONDS * 1_000_000:
                report(IMMINENT, identity, delta)
                return 0
            # A normal next discovery is always within 24h; reject corrupt data.
            if delta > 86400 * 1_000_000:
                raise ValueError('DEADLINE_OUT_OF_BOUNDS')
            previous = snapshot
        except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
            report(UNAVAILABLE, identity)
            return 0
    report(EXECUTED, identity)
    try:
        execute(SETTLEMENT_ARGV[0], list(SETTLEMENT_ARGV))
    except OSError:
        # Marker alone never satisfies execution evidence: completion must succeed.
        return 126
    return 0


if __name__ == '__main__':
    raise SystemExit(run())
