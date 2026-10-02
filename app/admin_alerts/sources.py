"""Bounded read adapters. No runner imports, producer writes, or repair commands."""
from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import selectors
import sqlite3
import subprocess
import time
from typing import Callable

from .model import DISCOVERY, UNITS, SCHEMA, Event, coverage, digest, epoch, identity
from .rules import compact, completed_health, code_events
from .output_contracts import CONTRACTS, expected_document

MAX_LINE = 131072
MAX_READ = 1048576
MAX_ROWS = 128
# Bound raw JSON independently of the 128 KiB monitor projection.
MAX_HEALTH_SOURCE = 4 * MAX_READ
DISCOVERY_OUTPUT_WINDOW_SLOP_SECONDS = 10


def command(args: list[str], timeout: float = 3, limit: int = MAX_READ) -> str:
    """Kill a child on deadline or byte limit; never use shell or retain stderr."""
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env={**os.environ, 'LC_ALL': 'C', 'TZ': 'UTC'})
    data = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as poll:
            poll.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('SOURCE_DEADLINE')
                if not poll.select(remaining):
                    raise TimeoutError('SOURCE_DEADLINE')
                chunk = os.read(process.stdout.fileno(), min(65536, limit + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError('SOURCE_BYTE_LIMIT')
        if process.wait(timeout=max(.01, deadline - time.monotonic())):
            raise OSError('SOURCE_UNAVAILABLE')
        return data.decode('utf-8', errors='replace')
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def tail(path: Path, previous: dict, now: float, *, running: bool,
         grace: float = 180) -> tuple[list[tuple[dict, str]], list[Event], dict, int]:
    """Keep offsets, not unsanitized trailing bytes. Re-read a bounded partial line.

    Reviewed delaycompress rotation drains the .1 inode before the replacement.
    First start reads at most the last MiB. Old unresolved delivery is read separately.
    """
    state = dict(previous)
    records: list[tuple[dict, str]] = []
    issues: list[Event] = []
    total = 0
    serial = previous.get("rotation_serial", 0)
    serial = serial if type(serial) is int and serial >= 0 else 0
    def rotation_issue(reason: str) -> None:
        nonlocal serial
        serial += 1
        occurrence = "rotation-v2-" + digest((serial, reason, previous.get("file"),
            previous.get("offset"), previous.get("anchor"), current_id))
        issues.append(Event("monitor", "MONITORING_COVERAGE_DEGRADED", "stdout-rotation",
            occurrence, now, "stdout", facts={"reason": reason, "occurrence_version": 2}))
    try:
        current = path.stat()
        current_id = [current.st_dev, current.st_ino]
        selected = path
        if state and state.get('file') != current_id:
            # Reviewed logrotate uses delaycompress: only .1 is an eligible
            # uncompressed predecessor, also used by discovery_output_window.
            # File read/traverse ACLs do not imply directory-list permission.
            rotated = Path(str(path) + '.1')
            try:
                old = rotated.stat()
                if [old.st_dev, old.st_ino] == state.get('file'):
                    selected = rotated
            except FileNotFoundError:
                pass
            if selected == path:
                rotation_issue("ROTATED_INODE_LOST")
                state = {}
        stat = selected.stat()
        fid = [stat.st_dev, stat.st_ino]
        if not state:
            start = max(0, stat.st_size - MAX_READ)
            state = {'file': fid, 'offset': start, 'discard': start > 0}
            if start:
                issues.append(coverage('stdout', now, 'INITIAL_WINDOW_BOUNDED', object_id='stdout-history'))
        if stat.st_size < state.get('offset', 0):
            rotation_issue("FILE_TRUNCATED")
            state = {'file': fid, 'offset': 0}
        with selected.open('rb') as handle:
            if [os.fstat(handle.fileno()).st_dev, os.fstat(handle.fileno()).st_ino] != fid:
                raise OSError('ROTATION_RACE')
            if state.get('anchor') and state['offset'] >= state.get('anchor_size', 0):
                handle.seek(state['offset'] - state['anchor_size'])
                if digest(handle.read(state['anchor_size']).hex()) != state['anchor']:
                    rotation_issue("FILE_REWRITTEN")
                    state = {'file': fid, 'offset': 0}
            handle.seek(state['offset'])
            count = 0
            while total < MAX_READ and count < 512:
                start = handle.tell()
                line = handle.readline(min(MAX_LINE + 1, MAX_READ - total))
                total += len(line)
                if not line:
                    break
                ended = line.endswith(b'\n')
                if state.get('discard'):
                    state['offset'] = handle.tell()
                    state['discard'] = not ended
                    continue
                if len(line) > MAX_LINE:
                    issues.append(coverage('stdout', now, 'OVERSIZED_RECORD', object_id='stdout-size'))
                    state.update(offset=handle.tell(), discard=not ended)
                    continue
                if not ended:
                    # The scan byte budget can also split a perfectly valid line.
                    state['offset'] = start
                    if total < MAX_READ:
                        marker = digest(line.hex())
                        if state.get('partial_hash') != marker:
                            state.update(partial_hash=marker, partial_since=now)
                        if not running and now - state.get('partial_since', now) >= grace:
                            issues.append(coverage('stdout', now, 'INCOMPLETE_AFTER_EXIT', object_id='stdout-partial'))
                    break
                state.pop('partial_hash', None)
                state.pop('partial_since', None)
                state['offset'] = handle.tell()
                count += 1
                if not line.strip():
                    continue
                reference = 'stdout:' + ':'.join(str(n) for n in (*fid, start))
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError()
                    records.append((value, reference))
                except (ValueError, RecursionError):
                    issues.append(coverage('stdout', now, 'MALFORMED_RECORD', object_id='stdout-format'))
            if state['offset']:
                state['anchor_size'] = min(64, state['offset'])
                handle.seek(state['offset'] - state['anchor_size'])
                state['anchor'] = digest(handle.read(state['anchor_size']).hex())
        if selected != path and state.get('partial_hash') and not running and now - state.get('partial_since', now) >= grace:
            state['offset'] = stat.st_size
            state.pop('partial_hash', None)
        if selected != path and state['offset'] >= stat.st_size and not state.get('partial_hash'):
            state = {'file': current_id, 'offset': 0}
        if total >= MAX_READ or count >= 512:
            issues.append(coverage('stdout', now, 'SCAN_BACKLOG', object_id='stdout-backlog'))
    except OSError:
        issues.append(coverage('stdout', now, 'READ_UNAVAILABLE'))
    if state and serial:
        state["rotation_serial"] = serial
    return records, issues, state, total


def discovery_output_window(path: Path, start: float, end: float) -> tuple[dict | None, bool]:
    """Bounded direct proof for discovery's TIME_WINDOW_ONLY stdout contract.

    This deliberately bypasses the streaming cursor when deciding absence: a
    cursor/rotation/access hiccup must not manufacture MISSING_OUTPUT. Current
    and previous uncompressed log files are enough for the latest invocation.
    """
    if not start or not end or end < start:
        return None, False
    available = False
    lower = start - DISCOVERY_OUTPUT_WINDOW_SLOP_SECONDS
    upper = end + DISCOVERY_OUTPUT_WINDOW_SLOP_SECONDS
    for selected in (path, Path(str(path) + '.1')):
        if not selected.exists():
            continue
        try:
            stat = selected.stat()
            available = True
            with selected.open('rb') as handle:
                offset = max(0, stat.st_size - MAX_READ)
                handle.seek(offset)
                if offset:
                    handle.readline(MAX_LINE + 1)  # discard partial first line
                count = 0
                while count < 512:
                    line = handle.readline(MAX_LINE + 1)
                    if not line:
                        break
                    count += 1
                    if len(line) > MAX_LINE or not line.endswith(b'\n'):
                        continue
                    try:
                        doc = json.loads(line)
                    except (ValueError, RecursionError):
                        continue
                    if not isinstance(doc, dict) or not expected_document(DISCOVERY, doc):
                        continue
                    stamp = epoch(doc.get('evaluated_at_utc'))
                    if lower <= stamp <= upper:
                        return ({'association': 'TIME_WINDOW_ONLY', 'contract_version': 1,
                                 'output_timestamp': stamp,
                                 'output_reference': 'stdout-window-' + digest((selected.name, stamp, doc.get('cycle_id')))},
                                True)
        except OSError:
            return None, False
    return None, available


PROPERTIES = ('Id', 'LoadState', 'Result', 'ExecMainCode', 'ExecMainStatus', 'ActiveState', 'SubState',
              'InvocationID', 'ExecMainStartTimestampMonotonic', 'ExecMainExitTimestampMonotonic',
              'StandardOutput', 'TimeoutStartUSec', 'UnitFileState', 'TimersCalendar', 'LastTriggerUSec',
              'NextElapseUSecRealtime', 'AccuracyUSec', 'RandomizedDelayUSec', 'NeedDaemonReload')


def systemd(read: Callable = command) -> dict[str, dict]:
    units = [*UNITS, *(u.replace('.service', '.timer') for u in UNITS)]
    output = read(['systemctl', 'show', *units, '--property=' + ','.join(PROPERTIES)])
    result = {}
    for block in output.strip().split('\n\n'):
        value = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        if value.get('Id') in units and value.get('LoadState') == 'loaded':
            result[value['Id']] = value
    return result


def duration(value: str) -> float:
    """systemd's human durations, including minute and millisecond components."""
    import re
    factors = {'us': .000001, 'ms': .001, 's': 1, 'min': 60, 'h': 3600, 'd': 86400}
    parts = re.findall(r'([0-9.]+)(us|ms|min|s|h|d)', value)
    return sum(float(n) * factors[u] for n, u in parts) if parts else 0


def system_stamp(value: str) -> float:
    try:
        return datetime.strptime(value, '%a %Y-%m-%d %H:%M:%S UTC').replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0


def service_rules(properties: dict, previous: dict, now: float, boot_time: float,
                  start_time: float, maintenance: dict) -> tuple[list[Event], dict]:
    """Use observed timer deadlines. systemd resolves calendars, timezone and DST.

    No guessed cadence: missed starts can be proven only after a deadline was observed.
    """
    events = []
    state = {}
    grace = now - max(boot_time, start_time) < 180
    for unit in UNITS:
        service = properties.get(unit)
        timer = properties.get(unit.replace('.service', '.timer'))
        suppressed = any(m.get('scope') in ('all', unit) and m.get('until', 0) > now
                         for m in maintenance.values())
        if not service or not timer:
            events.append(coverage('systemd', now, 'UNIT_UNAVAILABLE', object_id=unit))
            continue
        start = boot_time + int(service.get('ExecMainStartTimestampMonotonic') or 0) / 1e6
        end = boot_time + int(service.get('ExecMainExitTimestampMonotonic') or 0) / 1e6
        invocation = identity(service.get('InvocationID') or None)
        running = service.get('ActiveState') in ('activating', 'active', 'deactivating')
        result = service.get('Result', 'unknown')
        failed = not running and (result not in ('success', 'unknown', '') or service.get('ExecMainStatus', '0') != '0')
        deadline = system_stamp(timer.get('NextElapseUSecRealtime', ''))
        last_trigger = system_stamp(timer.get('LastTriggerUSec', ''))
        old = previous.get(unit, {})
        due = old.get('next', 0)
        state[unit] = {'next': deadline or due, 'invocation': invocation, 'start': start, 'end': end,
                       'running': running, 'failed': failed, 'standard_output': service.get('StandardOutput', 'UNKNOWN'),
                       'next_unknown_since': old.get('next_unknown_since', now) if not deadline else 0,
                       'schedule_evidence': 'AVAILABLE' if deadline else 'UNKNOWN'}
        if suppressed:
            continue

        def add(rule: str, occurrence: str, healthy: bool = False, severity: int = 2) -> None:
            events.append(Event(unit, rule, 'pipeline', occurrence, now, 'systemd', severity,
                                invocation, facts={'running': running, 'exit_status': int(service.get('ExecMainStatus') or 0),
                                'result': result if result in ('success', 'exit-code', 'signal', 'timeout', 'oom-kill', 'core-dump', 'resources') else 'UNKNOWN'},
                                healthy=healthy))
        if failed:
            add('SERVICE_FAILURE', invocation, severity=3 if result == 'oom-kill' else 2)
        elif not running and result == 'success' and end > boot_time and end >= start:
            add('SERVICE_FAILURE', invocation, healthy=True)
        timeout = duration(service.get('TimeoutStartUSec', ''))
        if running and timeout and now - start > timeout + 60:
            add('RUNNING_LONG', invocation)
        elif not running and end >= start and end > boot_time:
            add('RUNNING_LONG', invocation, healthy=True)
        if not grace:
            if timer.get('ActiveState') != 'active' or timer.get('UnitFileState') in ('disabled', 'masked'):
                add('TIMER_INACTIVE', digest((timer.get('ActiveState'), timer.get('UnitFileState'))))
            else:
                add('TIMER_INACTIVE', 'active-enabled', healthy=True)
            slack = duration(timer.get('AccuracyUSec', '')) + duration(timer.get('RandomizedDelayUSec', '')) + 180
            if due and now > due + slack and last_trigger < due and start < due and not running:
                add('MISSING_START', str(due))
                state[unit]['next'] = due  # retain unmet deadline despite a future NextElapse
            elif due and (start >= due or last_trigger >= due):
                add('MISSING_START', invocation, healthy=True)
        if service.get('NeedDaemonReload') == 'yes' or timer.get('NeedDaemonReload') == 'yes':
            events.append(coverage('systemd', now, 'LOADED_CONFIGURATION_DRIFT', object_id=unit + '-configuration'))
        if not deadline and not running and not grace and now - state[unit]['next_unknown_since'] >= 180:
            events.append(coverage('systemd', now, 'NEXT_ELAPSE_UNKNOWN', object_id=unit + '-schedule'))
        elif deadline:
            events.append(Event('monitor', 'MONITORING_COVERAGE_DEGRADED', unit + '-schedule',
                'schedule-available', now, 'systemd', healthy=True))
    return events, state


def journal(previous: dict, now: float, read: Callable = command) -> tuple[list[Event], dict]:
    """Read only allowlisted units, including systemd's UNIT manager fields."""
    args = ['journalctl', '--quiet', '--no-pager', '--all', '-o', 'json', '--output-fields=__CURSOR,__REALTIME_TIMESTAMP,_BOOT_ID,_SYSTEMD_INVOCATION_ID,INVOCATION_ID,_SYSTEMD_UNIT,UNIT,MESSAGE_ID,MESSAGE,RESULT,EXIT_CODE,EXIT_STATUS', '-n', '+256']
    for unit in UNITS:
        args.extend(['-u', unit])
    if previous.get('cursor'):
        args.extend(['--after-cursor', previous['cursor']])
    else:
        args.extend(['--since', '@' + str(int(now - 900))])
    events = []
    state = deepcopy(previous)
    if read is command:
        readable = False
        try:
            for root in (Path('/var/log/journal'), Path('/run/log/journal')):
                for index, path in enumerate(root.glob('*/system*.journal')):
                    if index >= 128:
                        break
                    if os.access(path, os.R_OK):
                        readable = True
                        break
        except OSError:
            pass
        if not readable:
            return [coverage('journal', now, 'SYSTEM_JOURNAL_ACCESS_UNPROVEN')], state
    state.setdefault('outputs', {})
    state.setdefault('frames', {})
    state.setdefault('output_proofs_v1', {})
    proofs = {}
    try:
        output = read(args)
        lines = output.splitlines()
        if len(lines) >= 256:
            # Do not advance past unprocessed entries.
            lines = lines[:256]
            events.append(coverage('journal', now, 'JOURNAL_BACKLOG'))
        for line in lines:
            value = json.loads(line)
            unit = value.get('_SYSTEMD_UNIT') or value.get('UNIT')
            if unit not in UNITS:
                unit = value.get('UNIT')
            if unit not in UNITS:
                continue
            inv = identity(value.get('_SYSTEMD_INVOCATION_ID') or value.get('INVOCATION_ID'))
            stamp = int(value.get('__REALTIME_TIMESTAMP', 0)) / 1e6
            cursor = value.get('__CURSOR', '')
            if not isinstance(cursor, str) or not re.fullmatch(r'[a-zA-Z0-9_=;:-]{1,2048}', cursor):
                raise ValueError('JOURNAL_CURSOR_INVALID')
            proofs['journal-' + digest(cursor)] = {'journal_cursor': cursor, 'boot_id': identity(value.get('_BOOT_ID'))}
            state.update(cursor=cursor, boot=identity(value.get('_BOOT_ID')))
            message = value.get('MESSAGE', '')
            if isinstance(message, str) and inv != 'UNKNOWN':
                frame = re.search(r'File "[^"\n]*/app/((?:lab_v2_shadow|lab_combo|adaptive_lab|football)/[a-zA-Z0-9_/]+\.py)", line ([0-9]{1,6}), in ([a-zA-Z_][a-zA-Z0-9_]{0,63})', message)
                if frame:
                    previous_frames = state['frames'].get(unit, {})
                    frames = previous_frames.get('frames', []) if previous_frames.get('invocation') == inv else []
                    state['frames'][unit] = {'invocation': inv, 'frames': (frames + [
                        {'module': frame[1], 'line': int(frame[2]), 'function': frame[3]}])[-5:]}
                trace = state['frames'].get(unit, {})
                if trace.get('invocation') == inv:
                    proofs['journal-' + digest(cursor)]['stack_frames'] = trace['frames']
            # Recognize explicit systemd facts, never retain arbitrary exception text.
            result = value.get('RESULT')
            if not result and isinstance(message, str):
                for needle, normalized in (("Failed with result 'timeout'", 'timeout'),
                    ("Failed with result 'exit-code'", 'exit-code'), ("Failed with result 'signal'", 'signal'),
                    ("Failed with result 'oom-kill'", 'oom-kill'), ('killed by the OOM killer', 'oom-kill')):
                    if needle in message:
                        result = normalized
                        break
            if result in ('exit-code', 'signal', 'timeout', 'oom-kill', 'core-dump'):
                events.append(Event(unit, 'SERVICE_FAILURE', 'pipeline', inv if inv != 'UNKNOWN' else digest(cursor),
                    stamp, 'journal-' + digest(cursor), 3 if result == 'oom-kill' else 2, inv, facts={'result': result}))
            if isinstance(message, str) and len(message.encode('utf-8')) <= MAX_LINE:
                try:
                    doc = json.loads(message)
                except ValueError:
                    doc = None
                if isinstance(doc, dict):
                    # Only a service's final artifact with trusted journal attribution is proof.
                    if (CONTRACTS[unit].source == 'STRUCTURED_JOURNAL_JSON'
                            and value.get('_SYSTEMD_UNIT') == unit
                            and value.get('_SYSTEMD_INVOCATION_ID') == inv and inv != 'UNKNOWN'
                            and expected_document(unit, doc)):
                        proof = {'contract_version': CONTRACTS[unit].version,
                                 'output_timestamp': stamp, 'journal_cursor': cursor,
                                 'association': 'EXACT_INVOCATION'}
                        outputs = state['output_proofs_v1'].setdefault(unit, {})
                        outputs[inv] = proof
                        state['output_proofs_v1'][unit] = dict(list(outputs.items())[-32:])
                        events.append(Event(unit, 'MISSING_OUTPUT', inv, inv, now,
                            'journal-' + digest(cursor), invocation=inv, healthy=True, facts=proof))
                    # The discovery compact schema belongs to the dedicated stdout contract.
                    # Do not classify unrelated schema-versioned journal documents as stdout faults.
                    if unit == DISCOVERY and doc.get('schema_version') == SCHEMA:
                        events.extend(compact(doc, 'journal-' + digest(cursor), now, invocation=inv))
                    else:
                        events.extend(code_events(doc.get('code') or doc.get('status'), unit, inv, stamp, 'journal-' + digest(cursor), invocation=inv))
                        if doc.get('status') == 'DELIVERY_UNKNOWN_RECONCILIATION_REQUIRED':
                            events.append(Event(unit, 'DELIVERY_UNCERTAIN', identity(doc.get('report_id') or doc.get('prediction_id') or inv),
                                inv, stamp, 'journal-' + digest(cursor), 3, inv))
                        observation = doc.get('football_context_observation') or {}
                        if not isinstance(observation, dict):
                            events.append(coverage('journal', now, 'INVALID_RECORD_SHAPE'))
                            continue
                        for key in ('CONSTRUCTION_FAILED', 'FINISH_FAILED'):
                            if observation.get(key):
                                events.extend(code_events('OBSERVATION_' + key, unit, inv, stamp, 'journal-' + digest(cursor), invocation=inv))
                else:
                    known = None
                    for needle, code in (('database is locked', 'DATABASE_LOCKED'),
                        ('QUOTA_DB_CONTENTION_EXHAUSTED', 'QUOTA_DB_CONTENTION_EXHAUSTED'),
                        ('OBSERVATION_CONSTRUCTION_FAILED', 'OBSERVATION_CONSTRUCTION_FAILED'),
                        ('OBSERVATION_FINISH_FAILED', 'OBSERVATION_FINISH_FAILED')):
                        if needle in message:
                            known = code
                    events.extend(code_events(known, unit, inv, stamp, 'journal-' + digest(cursor), invocation=inv))
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired):
        # Journal vacuum/cursor loss does not mean an application failure.
        events.append(coverage('journal', now, 'READ_OR_CURSOR_UNAVAILABLE'))
        state = {'output_proofs_v1': state.get('output_proofs_v1', {})}  # retain verified evidence on cursor loss
    events = [replace(e, facts={**e.facts, **proofs.get(e.source, {})}) for e in events]
    return events, state


def invocation_output(unit: str, invocation: str, now: float, read: Callable = command) -> list[Event]:
    """At most 100 entries for one exact unresolved invocation; no global cursor change."""
    if (unit not in CONTRACTS or CONTRACTS[unit].source != 'STRUCTURED_JOURNAL_JSON'
            or not re.fullmatch(r'[a-f0-9]{32}', invocation)):
        return []

    def exact_read(unused: list[str]) -> str:
        output = read(['journalctl', '--quiet', '--no-pager', '--all', '-o', 'json', '-n', '100',
                       '_SYSTEMD_UNIT=' + unit, '_SYSTEMD_INVOCATION_ID=' + invocation])
        # Validate even injected readers, and bound parser work independently of journalctl.
        entries = [json.loads(line) for line in output.splitlines()[:100]]
        return '\n'.join(json.dumps(v) for v in entries if
            v.get('_SYSTEMD_UNIT') == unit and v.get('_SYSTEMD_INVOCATION_ID') == invocation)

    events, _ = journal({}, now, exact_read)
    return [e for e in events if e.rule == 'MISSING_OUTPUT' and e.healthy]


def readonly(path: Path) -> sqlite3.Connection:
    """Fail closed unless WAL access cannot create or modify producer sidecars.

    Deploy with a read-only bind mount (ReadOnlyPaths). A writable development WAL
    mount is deliberately skipped; mode=ro alone does not guarantee SHM immutability.
    """
    with path.open('rb') as handle:
        header = handle.read(100)
    if len(header) != 100 or header[:16] != b'SQLite format 3\x00':
        raise ValueError('DATABASE_HEADER_INVALID')
    if header[18] == 2:
        if not (os.statvfs(path).f_flag & os.ST_RDONLY):
            raise PermissionError('WAL_REQUIRES_READONLY_MOUNT')
        if not Path(str(path) + '-shm').exists():
            raise PermissionError('WAL_SHM_UNAVAILABLE')
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=.1)
    connection.execute('PRAGMA query_only=ON')
    connection.execute('PRAGMA busy_timeout=100')
    until = time.monotonic() + .3
    connection.set_progress_handler(lambda: int(time.monotonic() > until), 1000)
    return connection


def health_rows(path: Path, previous: dict, now: float) -> tuple[list[Event], dict]:
    """Read bounded health projections; persisted performance evidence is untouched.

    PERFORMANCE is not consumed by completed_health. Only that root key may be
    omitted from an oversized, valid document. All failure/publication facts
    retain the existing 128 KiB limit; raw source JSON is capped at 4 MiB.
    """
    state = dict(previous)
    events = []
    connection = None
    try:
        connection = readonly(path)
        for table, service in (('cycle_health', DISCOVERY), ('observer_runs', UNITS[2])):
            last = state.get(table, [datetime.fromtimestamp(now - 900, timezone.utc).isoformat(), ''])
            query = f'''WITH batch AS MATERIALIZED (
                SELECT id,created_at,
                    CASE WHEN length(CAST(document AS BLOB))<=? THEN document ELSE NULL END AS document
                FROM {table} INDEXED BY {table}_stream_time WHERE stream='PREMATCH'
                AND (created_at,id)>(?,?) ORDER BY created_at,id LIMIT ?
            ), projected AS MATERIALIZED (
                SELECT id,created_at,
                    CASE WHEN length(CAST(document AS BLOB))>? AND json_valid(document)
                         THEN json_remove(document,'$.PERFORMANCE') ELSE document END AS document
                FROM batch
            )
            SELECT id,created_at,
                CASE WHEN length(CAST(document AS BLOB))<=? THEN document ELSE NULL END
            FROM projected ORDER BY created_at,id'''
            rows = connection.execute(query, (MAX_HEALTH_SOURCE, *last, MAX_ROWS,
                                               MAX_LINE, MAX_LINE)).fetchall()
            for key, stamp, document in rows:
                state[table] = [stamp, key]
                if document is None:
                    events.append(coverage('health', now, 'OVERSIZED_RECORD'))
                    continue
                value = json.loads(document)
                if not isinstance(value, dict):
                    events.append(coverage('health', now, 'INVALID_RECORD_SHAPE'))
                    continue
                events.extend(completed_health(value, service, identity(key), now, 'health-' + identity(key)))
            if len(rows) == MAX_ROWS:
                events.append(coverage('health', now, 'SCAN_BACKLOG'))
    except (OSError, ValueError, sqlite3.Error):
        events.append(coverage('health', now, 'READ_SCHEMA_OR_WAL_ACCESS_UNAVAILABLE'))
    finally:
        if connection:
            connection.close()
    return events, state


def unresolved(path: Path, previous: dict, now: float) -> tuple[list[Event], dict]:
    """Page ALL claims using the existing (kind,identity) primary key.

    Exact receipt lookups include old unresolved sends on first installation.
    Each scan processes one bounded page; a completed pass starts again on next poll.
    """
    events = []
    state = dict(previous)
    connection = None
    try:
        validate_scan_cursor(state)
        connection = readonly(path)
        rows = connection.execute('''SELECT identity FROM evidence WHERE kind='claim' AND identity>?
                                     ORDER BY identity LIMIT ?''', (state.get('after', ''), MAX_ROWS)).fetchall()
        for (key,) in rows:
            receipt = connection.execute("SELECT 1 FROM evidence WHERE kind='receipt' AND identity=?", (key,)).fetchone()
            # A claim without a receipt is uncertainty, not proof that a send occurred.
            events.append(Event(DISCOVERY, 'DELIVERY_UNCERTAIN', identity(key.split(':', 1)[-1]),
                'ledger-' + digest((key, bool(receipt))), now, 'ledger-' + digest(key), 3,
                facts={'claim_exists': True, 'receipt_persisted': bool(receipt)}, healthy=bool(receipt)))
        events.extend(scan_page(state, rows, now, 'ledger'))
    except (OSError, ValueError, sqlite3.Error):
        state.update(version=2, read_available=False, status='SCAN_UNAVAILABLE', processed_this_page=0, progress=False)
        events.append(coverage('ledger', now, 'READ_SCHEMA_OR_CURSOR_UNAVAILABLE'))
    finally:
        if connection:
            connection.close()
    return events, state


def weekly_unresolved(path: Path, previous: dict, now: float) -> tuple[list[Event], dict]:
    """Read weekly claim/receipt identities through existing primary keys."""
    events = []
    state = dict(previous)
    connection = None
    try:
        validate_scan_cursor(state)
        connection = readonly(path)
        rows = connection.execute("SELECT id FROM weekly_claims WHERE id>? AND stream='PREMATCH' ORDER BY id LIMIT ?",
                                  (state.get('after', ''), MAX_ROWS)).fetchall()
        for (key,) in rows:
            receipt = connection.execute("SELECT 1 FROM weekly_receipts WHERE id=? AND stream='PREMATCH'", (key,)).fetchone()
            events.append(Event(UNITS[4], 'DELIVERY_UNCERTAIN', identity(key), 'weekly-' + digest((key, bool(receipt))),
                now, 'weekly-' + digest(key), 3, facts={'claim_exists': True, 'receipt_persisted': bool(receipt)}, healthy=bool(receipt)))
        events.extend(scan_page(state, rows, now, 'weekly'))
    except (OSError, ValueError, sqlite3.Error):
        state.update(version=2, read_available=False, status='SCAN_UNAVAILABLE', processed_this_page=0, progress=False)
        events.append(coverage('weekly', now, 'READ_SCHEMA_OR_CURSOR_UNAVAILABLE'))
    finally:
        if connection:
            connection.close()
    return events, state


SCAN_STALL_SECONDS = 1200


def validate_scan_cursor(state: dict) -> None:
    if (state.get('version', 2) != 2 or not isinstance(state.get('after', ''), str)
            or not isinstance(state.get('last_progress_at', 0), (float, int))):
        raise ValueError('SCAN_CURSOR_CORRUPT')


def scan_page(state: dict, rows: list, now: float, source: str) -> list[Event]:
    """A bounded page is healthy. Stall is measured since the last advancement.

    A migrated v1 cursor starts its 20-minute observation window now. Producer
    activity does not defer scans; readonly access failures remain explicit.
    """
    before = state.get('after', '')
    after = rows[-1][0] if len(rows) == MAX_ROWS else ''
    fingerprint = digest(rows)
    completed = len(rows) < MAX_ROWS
    advancing = (not rows and completed) or (all(isinstance(r[0], str) for r in rows)
                 and rows[0][0] > before and all(a[0] < b[0] for a, b in zip(rows, rows[1:]))
                 and (completed or after != before) and fingerprint != state.get('page_fingerprint'))
    last = state.get('last_progress_at', now)
    stalled = not advancing and now - last >= SCAN_STALL_SECONDS
    state.update(version=2, read_available=True,
                 status='SCAN_STALLED' if stalled else 'SCAN_COMPLETED' if completed and advancing else 'SCAN_IN_PROGRESS',
                 processed_this_page=len(rows), progress=advancing,
                 last_progress_at=now if advancing else last, page_fingerprint=fingerprint if not completed else None)
    if advancing:
        state['after'] = after
    return [coverage(source, now, 'SCAN_STALLED_NO_ADVANCEMENT')] if stalled else []
