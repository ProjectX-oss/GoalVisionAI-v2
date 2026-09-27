"""Reconstruct operator observations with actual v1 code, then scan v1.2 offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import patch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v1-package', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--invocation', action='append', required=True)
    args = parser.parse_args()
    root = args.state.resolve()
    root.mkdir(mode=0o700)  # never reuse live/existing state
    subprocess.run([sys.executable, '-I', '-B', '-c', '''
import json, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from app.admin_alerts.store import Store
from app.admin_alerts.model import Event, UNITS
root = Path(sys.argv[2]); now = time.time()
store = Store(root)
store.ingest([Event(UNITS[1], 'MISSING_OUTPUT', inv, inv, now-300,
    'journal-output', invocation=inv) for inv in json.loads(sys.argv[3])],
    {'journal': {'cursor': 'RECONSTRUCTED_V1_CURSOR'}}, now)
store.enqueue(now)
store.close()
''', str(args.v1_package.resolve()), str(root), json.dumps(args.invocation)], check=True)
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.package.resolve()))
    from app.admin_alerts.cli import scan
    from app.admin_alerts.store import Store
    from app.admin_alerts.delivery import dispatch, SenderConfig
    store = Store(root)
    originals = {r['id']: dict(r) for r in store.db.execute('SELECT * FROM incidents')}
    original_cursors = [tuple(r) for r in store.db.execute('SELECT * FROM metadata')]
    store.close()
    output = root/'fixture.log'; output.write_text('')
    config = {'stdout': str(output), 'health_database': str(root/'absent'),
              'ledger_database': str(root/'absent'), 'release_environment': str(root/'absent'),
              'sender': {'enabled': False}}
    calls = []
    def deny(*unused, **kwargs):
        calls.append('FORBIDDEN_NETWORK_OR_TELEGRAM')
        raise AssertionError('NETWORK_FORBIDDEN')
    class Transport:
        validate = deny
        send = deny
    runs = []
    with patch.object(socket.socket, 'connect', deny), patch.object(socket, 'create_connection', deny), \
         patch('app.admin_alerts.cli.Telegram', deny), \
         patch('app.admin_alerts.cli.systemd', return_value={}), \
         patch('app.admin_alerts.cli.service_rules', return_value=([], {})), \
         patch('app.admin_alerts.cli.journal', side_effect=lambda previous, now: ([], previous)), \
         patch('app.admin_alerts.cli.health_rows', return_value=([], {})):
        for _ in range(2):
            runs.append(scan(config, root, no_send=True))
        store = Store(root)
        try:
            assert store.get('journal')['cursor'] == 'RECONSTRUCTED_V1_CURSOR'
            for row in store.db.execute('SELECT * FROM incidents'):
                assert dict(row) == {**originals[row['id']], 'state': 'INVALIDATED'}
            assert store.db.execute('SELECT count(*) FROM invalidations').fetchone()[0] == len(originals)
            assert dispatch(store, SenderConfig(True, '', 99, 'AdminBot', 123, True), Transport(), 10**10) == 0
            outcomes = [dict(r) for r in store.db.execute('''SELECT i.id,i.state,o.state AS outbox_state,o.attempts
                FROM incidents i JOIN outbox o ON o.incident=i.id''')]
            assert all(r['outbox_state'] == 'SUPERSEDED' and r['attempts'] == 0 for r in outcomes)
            report = store.report('UNKNOWN')
        finally:
            store.close()
    assert not calls
    evidence = {'state_origin': 'USER_REPORTED_INCIDENTS_RECONSTRUCTED_WITH_ACTUAL_V1_CODE',
        'installed_state': 'LIVE_ADMIN_STATE_REQUIRES_OPERATOR_PREFLIGHT',
        'v1_manifest_sha256': hashlib.sha256((args.v1_package/'SHA256SUMS').read_bytes()).hexdigest(),
        'v1_2_manifest_sha256': hashlib.sha256((args.package/'SHA256SUMS').read_bytes()).hexdigest(),
        'outcomes': outcomes, 'scan_runs': runs, 'network_attempts': len(calls),
        'original_incident_fields_preserved': True, 'original_cursor_preserved': True,
        'original_cursor_count': len(original_cursors), 'audit_rows': len(originals),
        'monitoring_state': report['monitoring_state'], 'active_fault_count': report['active_fault_count'],
        'producer_source_reads': 0, 'producer_mutations': 0}
    (root/'rehearsal.json').write_text(json.dumps(evidence, indent=2, sort_keys=True)+'\n')
    print(json.dumps(evidence, indent=2))


if __name__ == '__main__':
    main()
