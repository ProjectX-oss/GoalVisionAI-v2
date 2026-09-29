"""Extend the pinned stagger reader with invocation-bound guard evidence."""
from datetime import datetime, timedelta, timezone
import json
import re
from pathlib import Path
import sys
import subprocess
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
import forward_evidence as base
from runtime_guard import ACTIVE, IMMINENT, UNAVAILABLE, EXECUTED, SCHEMA

SETTLEMENT = 'goalvision-lab-combo-settle.service'
CODES = (ACTIVE, IMMINENT, UNAVAILABLE, EXECUTED)


def summarize(records: list[dict[str, Any]], since: datetime, until: datetime,
              discovery_outputs: tuple = ()) -> dict[str, Any]:
    """Require successful scheduled executions; informational deferrals add no work."""
    result = BASE_SUMMARIZE(records, since, until, discovery_outputs)
    service = result['services'][SETTLEMENT]
    by_invocation: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        if row.get('_SYSTEMD_UNIT') != SETTLEMENT or row.get('_PID') == '1':
            continue
        try:
            doc = json.loads(row.get('MESSAGE', ''))
        except (ValueError, TypeError):
            continue
        if isinstance(doc, dict) and doc.get('schema_version') == SCHEMA:
            by_invocation.setdefault(row.get('_SYSTEMD_INVOCATION_ID', ''), []).append(doc)
    counts = dict.fromkeys(CODES, 0)
    executed = 0
    invalid = any(not identity or identity not in {run['invocation_id'] for run in service['invocations']}
                  for identity in by_invocation)
    for run in service['invocations']:
        docs = by_invocation.get(run['invocation_id'], [])
        valid = len(docs) == 1 and docs[0].get('code') in CODES
        if valid:
            doc = docs[0]
            code = doc['code']
            valid = (doc.get('guard_seconds') == 180 and
                     doc.get('status') == ('EXECUTED' if code == EXECUTED else 'DEFERRED'))
            if code != EXECUTED:
                valid = valid and all(type(doc.get(k)) is int and doc[k] == 0 for k in
                                      ('api_calls', 'telegram_sends', 'database_writes'))
        run['guard_code'] = docs[0].get('code') if valid else 'MISSING_OR_INVALID_GUARD_RECORD'
        if not valid:
            invalid = True
            continue
        counts[code] += 1
        if (code == EXECUTED and run['completed_at'] and run['scheduled_timestamp']
                and run['invocation_id'] and run['exit_status'] == 0):
            executed += 1
    service['counts'].update(counts)
    service['executed_scheduled_cycles'] = executed
    service['required_executed_cycles'] = 3
    if counts[UNAVAILABLE] or invalid:
        service['verdict'] = 'FAIL'
    elif service['verdict'] != 'FAIL' and executed < 3:
        service['verdict'] = 'WAIT_OR_INCOMPLETE_EVIDENCE'
    # Fail on errors even in unpaired/unfinished runs; retries remain informational.
    for unit, item in result['services'].items():
        # Include failure records outside paired invocations; missing starts cannot hide errors.
        messages = [row.get('MESSAGE', '') for row in records
                    if unit in (row.get('_SYSTEMD_UNIT'), row.get('UNIT'), row.get('OBJECT_SYSTEMD_UNIT'))
                    and isinstance(row.get('MESSAGE'), str)]
        for rule in base.RULES:
            raw_count = sum(bool(re.search(r'(?<![A-Z_])'+rule+r'(?![A-Z_])', message))
                            for message in messages)
            item['counts'][rule] = max(item['counts'][rule], raw_count)
        if any(item['counts'][key] for key in ('QUOTA_DB_CONTENTION_EXHAUSTED', 'DATABASE_LOCK', 'SERVICE_FAILURE')):
            item['verdict'] = 'FAIL'
    verdicts = {item['verdict'] for item in result['services'].values()}
    result['verdict'] = ('FAIL' if 'FAIL' in verdicts else 'PASS' if verdicts == {'PASS'}
                         else 'WAIT_OR_INCOMPLETE_EVIDENCE')
    result['guard_counts'] = counts
    result['limits'] += ' Guard execution markers require successful scheduled manager completion. Timer causation still requires operator review; calendar alignment alone is insufficient.'
    return result


BASE_SUMMARIZE = base.summarize


def evidence(host: Any, since: str) -> dict[str, Any]:
    """Use bounded read-only journal and rotation reader with the guarded summary."""
    start = datetime.fromisoformat(since.replace('Z', '+00:00'))
    until = datetime.now(timezone.utc)
    if start.tzinfo is None or not start < until or until-start > timedelta(days=7):
        raise ValueError('EVIDENCE_WINDOW_INVALID')
    args = ['/usr/bin/journalctl', '--no-pager', '--output=json',
            '--since='+start.isoformat(), '--until='+until.isoformat()]
    for unit in base.REQUIRED:
        args.extend(['--unit', unit])
    query = subprocess.run(args, check=True, capture_output=True, text=True, timeout=60)
    if 'permission' in query.stderr.lower() or 'not seeing messages' in query.stderr.lower():
        raise ValueError('JOURNAL_ACCESS_INCOMPLETE_USE_ROOT')
    outputs, selected = base.discovery_evidence(base.DISCOVERY_LOG, start, until)
    result = summarize([json.loads(line) for line in query.stdout.splitlines()], start, until, outputs)
    result.update(selected)
    result['current_service_state'] = {}
    for unit in base.REQUIRED:
        state = host.show(unit)
        result['current_service_state'][unit] = {k: state.get(k) for k in
                                               ('ActiveState', 'InvocationID', 'ExecMainStatus', 'Result')}
    return result
