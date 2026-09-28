"""Read-only bounded journal report; missing evidence can never become success."""
from datetime import datetime, timedelta, timezone
import json
import os
import re
from pathlib import Path
import stat
import subprocess
from typing import Any
from calendar_proof import NAMES, TARGET, evaluate

RULES = ('QUOTA_DB_CONTENTION_RETRY', 'QUOTA_DB_CONTENTION_EXHAUSTED',
         'SERVICE_FAILURE', 'DATABASE_LOCK', 'MISSING_OUTPUT')
REQUIRED = dict(zip((u.replace('.timer', '.service') for u in NAMES[:3]), (2, 3, 2)))
DISCOVERY_LOG = Path('/var/log/goalvision-prematch/discovery-output.log')
MAX_DISCOVERY_BYTES = 64 * 1024 * 1024
MAX_DISCOVERY_RECORDS = 100_000
DISCOVERY_SCHEMA = 'goalvision-lab-v2-operator-cycle-v1'


def read_discovery_file(path: Path, byte_budget: int, record_budget: int
                        ) -> tuple[list[tuple[datetime, dict[str, Any]]], int, int]:
    """Read one regular, uncompressed JSONL file within the shared budgets."""
    if path.suffix == '.gz' or path.is_symlink():
        raise ValueError('DISCOVERY_ROTATION_REQUIRES_OPERATOR_REVIEW:' + str(path))
    rows = []
    used_bytes = used_records = 0
    try:
        # Refuse symlink swaps and non-regular files without blocking on a FIFO.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > byte_budget:
                raise ValueError('DISCOVERY_OUTPUT_UNAVAILABLE_OR_EXCEEDS_64M_REVIEW_WINDOW')
            while line := stream.readline(byte_budget - used_bytes + 1):
                used_bytes += len(line)
                used_records += 1
                if used_bytes > byte_budget:
                    raise ValueError('DISCOVERY_OUTPUT_UNAVAILABLE_OR_EXCEEDS_64M_REVIEW_WINDOW')
                if used_records > record_budget:
                    raise ValueError('DISCOVERY_OUTPUT_RECORD_LIMIT_EXCEEDED')
                try:
                    doc = json.loads(line)
                except (ValueError, UnicodeError):
                    # As before, unrelated/malformed lines never supply evidence.
                    continue
                if not isinstance(doc, dict) or doc.get('schema_version') != DISCOVERY_SCHEMA:
                    continue
                try:
                    stamp = datetime.fromisoformat(doc['evaluated_at_utc'].replace('Z', '+00:00'))
                    if stamp.tzinfo is None:
                        raise ValueError('TIMEZONE_REQUIRED')
                except (ValueError, KeyError, TypeError, AttributeError) as exc:
                    raise ValueError('DISCOVERY_OUTPUT_MALFORMED_TIMESTAMP:' + str(path)) from exc
                rows.append((stamp, doc))
    except OSError as exc:
        raise ValueError('DISCOVERY_OUTPUT_UNAVAILABLE:' + str(path)) from exc
    if not rows:
        raise ValueError('DISCOVERY_OUTPUT_NO_VALID_CYCLE_TIMESTAMP:' + str(path))
    return rows, used_bytes, used_records


def discovery_evidence(current: Path, since: datetime, until: datetime
                       ) -> tuple[list[tuple[datetime, dict[str, Any]]], dict[str, Any]]:
    """Use current then consecutive numbered rotations only until since is covered.

    Filename order establishes rotation continuity; scheduled journal/output
    matching in summarize additionally rejects missing cycles within the window.
    Older rotations are inventoried by name only, never opened or size-counted.
    """
    files_read: list[str] = []
    ranges: list[dict[str, Any]] = []
    outputs: list[tuple[datetime, dict[str, Any]]] = []
    byte_budget, record_budget = MAX_DISCOVERY_BYTES, MAX_DISCOVERY_RECORDS
    path = current
    rotations: dict[int, list[Path]] = {}
    index = 0
    while True:
        rows, used_bytes, used_records = read_discovery_file(path, byte_budget, record_budget)
        byte_budget -= used_bytes
        record_budget -= used_records
        first, last = min(t for t, _ in rows), max(t for t, _ in rows)
        files_read.append(str(path))
        ranges.append({'path': str(path), 'earliest_valid_timestamp': first.isoformat(),
                       'latest_valid_timestamp': last.isoformat(), 'bytes_read': used_bytes,
                       'records_read': used_records})
        outputs.extend((t, doc) for t, doc in rows if since <= t <= until)
        if index == 0:
            # Inventory names only after the current log has been validated.
            for candidate in current.parent.iterdir():
                match = re.fullmatch(re.escape(current.name) + r'\.([1-9][0-9]*)(\.gz)?', candidate.name)
                if match:
                    rotations.setdefault(int(match[1]), []).append(candidate)
        if first <= since:
            break
        index += 1
        candidates = rotations.get(index, [])
        if len(candidates) != 1:
            raise ValueError('DISCOVERY_ROTATION_GAP_OR_AMBIGUOUS:' + str(index))
        path = candidates[0]
    ignored = [str(p) for number in sorted(rotations) if number > index
               for p in sorted(rotations[number])]
    return sorted(outputs, key=lambda row: row[0]), {
        'discovery_output_files_read': files_read,
        'discovery_output_files_ignored_outside_window': ignored,
        'discovery_output_file_ranges': ranges,
        'discovery_output_coverage_since': first.isoformat(),
        'discovery_output_rotation_policy': 'CURRENT_THEN_CONSECUTIVE_ROTATIONS_UNTIL_SINCE_COVERED',
    }


def utc(microseconds):
    return datetime.fromtimestamp(int(microseconds)/1_000_000, timezone.utc).isoformat()


def summarize(records, since, until, discovery_outputs=()):
    services = {}
    for service, minimum in REQUIRED.items():
        rows = [r for r in records if r.get('_SYSTEMD_UNIT') == service or r.get('UNIT') == service or r.get('OBJECT_SYSTEMD_UNIT') == service]
        rows.sort(key=lambda r: int(r['__REALTIME_TIMESTAMP']))
        runs, current = [], None
        for r in rows:
            message = r.get('MESSAGE', '')
            if not isinstance(message, str):
                continue
            manager = r.get('_PID') == '1'
            invocation = r.get('_SYSTEMD_INVOCATION_ID') if not manager else r.get('INVOCATION_ID') or r.get('OBJECT_SYSTEMD_INVOCATION_ID')
            if manager and message.startswith('Starting '):
                current = {'invocation_id': invocation, 'actual_trigger_timestamp': utc(r['__REALTIME_TIMESTAMP']),
                           'trigger_source': 'systemd service Starting journal entry', 'exit_status': None,
                           'completed_at': None, 'counts': dict.fromkeys(RULES, 0), 'output_records': 0,
                           'expected_output_seen': False}
                runs.append(current)
            if current is None:
                # A cycle already running at --since does not satisfy minimums.
                continue
            if invocation:
                if current['invocation_id'] and current['invocation_id'] != invocation:
                    continue
                current['invocation_id'] = invocation
            for rule in RULES:
                if re.search(r'(?<![A-Z_])'+rule+r'(?![A-Z_])', message):
                    current['counts'][rule] += 1
            if re.search(r'database (?:is )?locked|sqlite_busy|sqlite_locked|DATABASE_LOCKED', message, re.I) and not re.search(r'(?<![A-Z_])DATABASE_LOCK(?![A-Z_])', message):
                current['counts']['DATABASE_LOCK'] += 1
            if not manager:
                current['output_records'] += 1
                try:
                    doc = json.loads(message)
                except ValueError:
                    doc = None
                if service == NAMES[2].replace('.timer', '.service') and isinstance(doc, dict):
                    if (doc.get('stream') == 'PREMATCH' and doc.get('created_at')
                            and all(isinstance(doc.get(k), dict) for k in ('linkage', 'state', 'metrics'))
                            and doc.get('LIVE') == 'DISABLED' and doc.get('heavy_training') is False
                            and doc.get('api_calls') == 0 and doc.get('telegram_sends') == 0):
                        current['expected_output_seen'] = True
            if manager and 'Main process exited,' in message:
                match = re.search(r'code=(\w+), status=(\d+)', message)
                current['exit_status'] = int(match[2]) if match and match[1] == 'exited' else 'SIGNAL_OR_UNKNOWN'
            if manager and ('Failed with result' in message or message.startswith('Failed to start ')):
                current['counts']['SERVICE_FAILURE'] = max(1, current['counts']['SERVICE_FAILURE'])
                current['completed_at'] = utc(r['__REALTIME_TIMESTAMP'])
                if current['exit_status'] is None:
                    current['exit_status'] = 'FAILED_WITHOUT_NUMERIC_STATUS'
            if manager and ('Deactivated successfully.' in message or message.startswith('Finished ')):
                if current['exit_status'] is None:
                    current['exit_status'] = 0
                current['completed_at'] = utc(r['__REALTIME_TIMESTAMP'])
        timer = service.replace('.service', '.timer')
        expected = evaluate(TARGET[timer], since-timedelta(seconds=1), 2000)
        expected = [t for t in expected if since <= t < until]
        # Explicit matching prevents manual/out-of-window cycles satisfying the
        # scheduled minimum. This is calendar alignment, not proof of causation.
        matched = set()
        for run in runs:
            actual = datetime.fromisoformat(run['actual_trigger_timestamp'])
            candidates = [t for t in expected if 0 <= (actual-t).total_seconds() <= 65 and t not in matched]
            run['scheduled_timestamp'] = candidates[-1].isoformat() if candidates else None
            if candidates:
                matched.add(candidates[-1])
            if timer == NAMES[0]:
                end = datetime.fromisoformat(run['completed_at']) if run['completed_at'] else until
                outputs = [d for t,d in discovery_outputs if actual <= t <= end]
                run['expected_output_seen'] = bool(outputs)
                run['output_association'] = 'TIME_WINDOW_ONLY_NO_INVOCATION_ID_IN_FILE'
                for doc in outputs:
                    text = json.dumps(doc)
                    for rule in RULES:
                        if rule in text:
                            run['counts'][rule] += 1
            elif timer == NAMES[1]:
                run['output_association'] = 'NOT_ASSESSABLE_STDOUT_NULL'
            else:
                run['output_association'] = 'EXACT_JOURNAL_INVOCATION'
            if run['completed_at'] and not run['expected_output_seen'] and timer != NAMES[1]:
                run['counts']['MISSING_OUTPUT'] = max(1, run['counts']['MISSING_OUTPUT'])
        complete = [r for r in runs if r['completed_at'] and r['invocation_id'] and r['scheduled_timestamp']]
        missing = [t.isoformat() for t in expected if t not in matched and (until-t).total_seconds() > 120]
        totals = {rule: sum(r['counts'][rule] for r in runs) for rule in RULES}
        totals['MISSING_OUTPUT'] += len(missing)
        enough = len(complete) >= minimum
        failed = any(r['exit_status'] != 0 or r['counts']['QUOTA_DB_CONTENTION_EXHAUSTED'] or
                     r['counts']['DATABASE_LOCK'] or r['counts']['SERVICE_FAILURE'] or r['counts']['MISSING_OUTPUT'] for r in complete)
        incomplete = any(not r['completed_at'] or not r['invocation_id'] or not r['scheduled_timestamp'] for r in runs)
        services[service] = {'required_completed_cycles': minimum, 'completed_scheduled_cycles': len(complete),
            'invocations': runs, 'counts': totals, 'missing_scheduled_starts': missing,
            'verdict': 'FAIL' if failed or missing else 'PASS' if enough and not incomplete else 'WAIT_OR_INCOMPLETE_EVIDENCE'}
    verdicts = {r['verdict'] for r in services.values()}
    return {'since': since.isoformat(), 'until': until.isoformat(), 'services': services,
            'verdict': 'FAIL' if 'FAIL' in verdicts else 'PASS' if verdicts == {'PASS'} else 'WAIT_OR_INCOMPLETE_EVIDENCE',
            'limits': 'Starting journal timestamps are actual service activations; calendar alignment does not prove timer causation. Journal rule counts are records, not ADMIN incident totals. Missing starts/output or missing invocation IDs prevent PASS.'}


def evidence(host, since):
    start = datetime.fromisoformat(since.replace('Z', '+00:00'))
    if start.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    until = datetime.now(timezone.utc)
    if not start < until or until-start > timedelta(days=7):
        raise ValueError('EVIDENCE_WINDOW_MUST_BE_PAST_AND_AT_MOST_7_DAYS')
    args = ['/usr/bin/journalctl', '--no-pager', '--output=json', '--since='+start.isoformat(), '--until='+until.isoformat()]
    for unit in REQUIRED:
        args.extend(['--unit', unit])
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=60)
    if 'permission' in result.stderr.lower() or 'not seeing messages' in result.stderr.lower():
        raise ValueError('JOURNAL_ACCESS_INCOMPLETE_USE_ROOT')
    outputs, discovery_report = discovery_evidence(DISCOVERY_LOG, start, until)
    report = summarize([json.loads(line) for line in result.stdout.splitlines()], start, until, outputs)
    report['current_service_state'] = {}
    for unit in REQUIRED:
        state = host.show(unit)
        report['current_service_state'][unit] = {k: state.get(k) for k in ('ActiveState', 'InvocationID', 'ExecMainStatus', 'Result')}
    report.update(discovery_report)
    return report
