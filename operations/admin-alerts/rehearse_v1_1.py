"""One read-only source rehearsal; writes only a new isolated ADMIN evidence directory."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import socket
import sqlite3
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.admin_alerts.cli import scan
from app.admin_alerts.model import Event, UNITS
from app.admin_alerts.output_contracts import contract_report
from app.admin_alerts.sources import command, journal, readonly
from app.admin_alerts.store import Store


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--invocation', action='append', required=True)
    parser.add_argument('--v1-package', type=Path, required=True)
    args = parser.parse_args()
    if len(args.invocation) != 2 or not all(re.fullmatch('[a-f0-9]{32}', i) for i in args.invocation):
        raise ValueError('TWO_EXACT_INVOCATIONS_REQUIRED')
    root = args.state.resolve()
    if 'admin-alerts' not in root.name or root.exists():
        raise ValueError('NEW_ISOLATED_ADMIN_STATE_REQUIRED')
    root.mkdir(mode=0o700)
    baseline = json.loads((args.v1_package/'host-baseline.json').read_text())
    protected = set(baseline['protected_sha256'])
    release_roots = ('/home/arvis/GoalVisionAI-prematch-release-public-message-v2-20260926',
                     '/home/arvis/GoalVisionAI-prematch-release-363f567')
    for release in release_roots:
        protected.update(str(p) for p in (Path(release)/'app').rglob('*.py'))
    before = {n: sha(Path(n)) for n in sorted(protected)}
    installed_before = {str(p): sha(p) for p in Path('/opt/goalvision-admin-alerts').rglob('*')
                        if p.is_file() and '__pycache__' not in p.parts}
    live_config_readable = True
    try:
        config = json.loads(Path('/etc/goalvision-admin-alerts/admin-alerts.json').read_text())
    except PermissionError:
        live_config_readable = False
        config = json.loads((args.v1_package/'admin-alerts.json').read_text())
    if config.get('sender', {}).get('enabled') is not False:
        raise ValueError('SENDER_NOT_DISABLED')
    copied_state = True
    try:
        source = readonly(Path('/var/lib/goalvision-admin-alerts/admin.sqlite'))
    except PermissionError:
        copied_state = False
    else:
        try:
            destination = sqlite3.connect(root/'admin.sqlite')
            try:
                source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()
    now = time.time()
    store = Store(root)
    if not copied_state:
        # Explicitly reconstructed from the user's supplied OPEN/PENDING observations.
        # This is isolated test state, never claimed to be a live database snapshot.
        store.ingest([Event(UNITS[1], 'MISSING_OUTPUT', inv, inv, now-300,
                           'journal-output', invocation=inv) for inv in args.invocation], {}, now)
        store.enqueue(now)
    prior_journal = store.get('journal', {})
    store.close()
    rows = []
    findings = []
    for inv in args.invocation:
        raw = command(['journalctl', '--quiet', '--no-pager', '-o', 'json', '-n', '94',
            '_SYSTEMD_UNIT='+UNITS[1], '_SYSTEMD_INVOCATION_ID='+inv,
            '+', 'UNIT='+UNITS[1], 'INVOCATION_ID='+inv,
            '+', 'UNIT='+UNITS[1], 'OBJECT_SYSTEMD_INVOCATION_ID='+inv])
        values = [json.loads(line) for line in raw.splitlines()]
        rows.extend(values)
        final_json = []
        for value in values:
            try:
                doc = json.loads(value.get('MESSAGE', ''))
            except (ValueError, TypeError):
                doc = None
            if isinstance(doc, dict):
                final_json.append(value)
        findings.append({'invocation': inv, 'finding': 'OUTPUT_CONTRACT_NOT_APPLICABLE',
            'journal_entries': len(values), 'bounded_at': 94, 'json_objects': len(final_json),
            'exact_trusted_invocation_entries': sum(v.get('_SYSTEMD_INVOCATION_ID') == inv for v in values),
            'first_entry_utc': datetime.fromtimestamp(int(values[0]['__REALTIME_TIMESTAMP'])/1e6, timezone.utc).isoformat() if values else None,
            'last_entry_utc': datetime.fromtimestamp(int(values[-1]['__REALTIME_TIMESTAMP'])/1e6, timezone.utc).isoformat() if values else None,
            'historical_systemd_result': 'UNKNOWN', 'historical_exec_main_status': 'UNKNOWN',
            'historical_start_exit_timestamps': 'UNKNOWN',
            'admin_cursor_observed_final_output': 'UNKNOWN' if not copied_state else 'NO_FINAL_OUTPUT_IN_BOUNDED_EVIDENCE',
            'output_after_180_second_grace': 'NOT_PROVEN',
            'incident_assessment': 'UNSUPPORTED_OUTPUT_CONTRACT; producer outcome unresolved; retain OPEN',
            'journal_cursor_references': [v.get('__CURSOR') for v in values]})
    # The only journal evidence for this rehearsal is these two exact historical invocations.
    raw = '\n'.join(json.dumps(v) for v in rows)
    journal_events, journal_state = journal(prior_journal, now, lambda _: raw)
    calls = {'network_attempts': 0}
    def deny_network(*unused, **kwargs):
        calls['network_attempts'] += 1
        raise AssertionError('NETWORK_FORBIDDEN_IN_REHEARSAL')
    def scoped_journal(previous, stamp):
        return journal_events, journal_state
    with patch.object(socket.socket, 'connect', side_effect=deny_network), \
         patch('app.admin_alerts.cli.Telegram', side_effect=deny_network), \
         patch('app.admin_alerts.cli.journal', side_effect=scoped_journal):
        result = scan(config, root, no_send=True)
    after = {n: sha(Path(n)) for n in sorted(protected)}
    installed_after = {n: sha(Path(n)) for n in installed_before}
    report = json.loads((root/'incident-report.json').read_text())
    store = Store(root)
    outcomes = [dict(r) for r in store.db.execute("""SELECT i.id,i.invocation,i.state,o.state AS outbox_state,o.attempts
        FROM incidents i LEFT JOIN outbox o ON o.incident=i.id WHERE i.rule='MISSING_OUTPUT' AND i.service=?""", (UNITS[1],))]
    store.close()
    evidence = {'captured_at': datetime.now(timezone.utc).isoformat(), 'scan': result,
        'findings': findings, 'output_contracts': contract_report(), 'outcomes': outcomes,
        'isolated_sender_enabled': False, 'installed_sender_verified_disabled': live_config_readable,
        'state_origin': 'READ_ONLY_INSTALLED_SNAPSHOT' if copied_state else 'USER_REPORTED_INCIDENTS_RECONSTRUCTED',
        'installed_admin_state_readable': copied_state, 'journal_scope': 'ONLY_TWO_REQUESTED_INVOCATIONS',
        'network_attempts': calls['network_attempts'], 'protected_file_count': len(before),
        'protected_file_hash_changes': [n for n in before if before[n] != after[n]],
        'protected_sha256': before, 'installed_admin_hash_changes': [n for n in installed_before if installed_before[n] != installed_after[n]],
        'monitoring_state': report['monitoring_state'], 'source_access': report['source_access'],
        'limitations': [] if live_config_readable and copied_state else [
            'Live ADMIN configuration/database access denied; sudo -n requires a password.',
            'Historical systemd manager result/exit timestamps unavailable in readable journal.',
            'Live ADMIN cursor/outbox and sender-disabled status not independently verified.',
            'Source databases used the existing mode=ro/query_only adapter; no private mount was created.']}
    (root/'rehearsal.json').write_text(json.dumps(evidence, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k:v for k,v in evidence.items() if k not in ('protected_sha256','findings','source_access','output_contracts')}, indent=2))


if __name__ == '__main__':
    main()
