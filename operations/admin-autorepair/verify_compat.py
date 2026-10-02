"""Read-only replay of existing logs and health; no scan, job, send or provider call."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.admin_alerts.model import UNITS, identity
from app.admin_alerts.rules import completed_health
from app.admin_alerts.sources import health_rows, journal

SINCE = '2026-10-01T19:13:00+00:00'
report = {'since_utc': SINCE, 'observed_at_utc': datetime.now(timezone.utc).isoformat()}
args = ['journalctl', '--quiet', '--no-pager', '-o', 'json', '-n', '128',
        '--since', SINCE, '-u', UNITS[2]]
def read(flags):
    return subprocess.run([*args, *flags], check=True, capture_output=True, text=True, timeout=10).stdout
ordinary = [json.loads(v) for v in read([]).splitlines()]
full = read(['--all'])
records = [json.loads(v) for v in full.splitlines()]
events, state = journal({}, time.time(), lambda args: full if '--all' in args else '')
proofs = [e for e in events if e.rule == 'MISSING_OUTPUT' and e.healthy]
report['observer_journal'] = {
    'records': len(records),
    'null_messages_without_all': sum(v.get('MESSAGE') is None for v in ordinary),
    'recognized_exact_invocations': len(proofs),
    'unique_exact_invocations': len({e.invocation for e in proofs}),
    'message_bytes_min': min(len(v['MESSAGE'].encode()) for v in records if isinstance(v.get('MESSAGE'), str)),
    'message_bytes_max': max(len(v['MESSAGE'].encode()) for v in records if isinstance(v.get('MESSAGE'), str)),
}
conn = sqlite3.connect('file:/home/arvis/GoalVisionAI/var/adaptive_lab/audit.db?mode=ro', uri=True, timeout=.2)
conn.execute('PRAGMA query_only=ON')
conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
rows = {}
try:
    for table in ('cycle_health', 'observer_runs'):
        deadline = time.monotonic() + 1
        rows[table] = conn.execute(f"SELECT id,created_at,stream,document FROM {table} "
            "WHERE stream='PREMATCH' AND created_at>=? AND length(CAST(document AS BLOB))<=4194304 "
            "ORDER BY created_at,id LIMIT 128", (SINCE,)).fetchall()
finally:
    conn.close()
with tempfile.TemporaryDirectory(prefix='goalvision-admin-replay-') as temporary:
    path = Path(temporary) / 'synthetic.db'
    db = sqlite3.connect(path)
    expected = []
    report['health'] = {}
    now = time.time()
    for table, unit in (('cycle_health', UNITS[0]), ('observer_runs', UNITS[2])):
        db.execute(f'CREATE TABLE {table}(id TEXT,created_at TEXT,stream TEXT,document TEXT)')
        db.execute(f'CREATE INDEX {table}_stream_time ON {table}(stream,created_at,id)')
        db.executemany(f'INSERT INTO {table} VALUES (?,?,?,?)', rows[table])
        report['health'][table] = {
            'rows': len(rows[table]),
            'over_128kib_before_projection': sum(len(r[3].encode()) > 131072 for r in rows[table]),
            'source_document_hashes': [hashlib.sha256(r[3].encode()).hexdigest() for r in rows[table]],
        }
        for key, stamp, stream, doc in rows[table]:
            expected += completed_health(json.loads(doc), unit, identity(key), now, 'health-' + identity(key))
    db.commit()
    db.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    started = time.monotonic()
    actual, cursors = health_rows(path, {t:[SINCE, ''] for t in rows}, now)
    report['health_replay'] = {
        'elapsed_seconds': round(time.monotonic() - started, 4),
        'events_identical_to_full_documents': list(map(asdict, expected)) == list(map(asdict, actual)),
        'source_copy_unchanged': before == hashlib.sha256(path.read_bytes()).hexdigest(),
        'coverage_errors': sum(e.rule == 'MONITORING_COVERAGE_DEGRADED' for e in actual),
        'real_fault_rules': sorted({e.rule for e in actual if not e.healthy}),
    }
print(json.dumps(report, sort_keys=True, indent=2))
if not (len(proofs) == len(records) and report['health_replay']['events_identical_to_full_documents']
        and report['health_replay']['source_copy_unchanged'] and not report['health_replay']['coverage_errors']):
    raise SystemExit(1)
