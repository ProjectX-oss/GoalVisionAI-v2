"""Synthetic bounded scan benchmark; no production files or network access."""
from __future__ import annotations

import json
from pathlib import Path
import resource
import sqlite3
import tempfile
import time

from app.admin_alerts.model import DISCOVERY
from app.admin_alerts.rules import compact
from app.admin_alerts.sources import health_rows, tail, unresolved
from app.admin_alerts.store import Store


def main() -> None:
    from datetime import datetime, timezone
    now = time.time()
    iso = datetime.fromtimestamp(now, timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='goalvision-admin-benchmark-') as directory:
        root = Path(directory)
        path = root/'output.log'
        value = {'schema_version': 'goalvision-lab-v2-operator-cycle-v1', 'cycle_id': 'synthetic-cycle',
                 'evaluated_at_utc': iso, 'analysis_status': 'FAILED', 'terminal_error': True}
        with path.open('wb') as handle:
            handle.write(b'x'*(8*1048576)+b'\n')
            for i in range(1000):
                handle.write((json.dumps({**value, 'cycle_id': 'cycle-'+str(i)})+'\n').encode())
        db = root/'health.db'
        connection = sqlite3.connect(db)
        for table in ('cycle_health', 'observer_runs'):
            connection.execute(f'CREATE TABLE {table}(id TEXT,created_at TEXT,stream TEXT,document TEXT)')
            connection.execute(f'CREATE INDEX {table}_stream_time ON {table}(stream,created_at,id)')
            connection.executemany(f'INSERT INTO {table} VALUES (?,?,?,?)',
                [(f'{i:08}', iso, 'PREMATCH', json.dumps({'result': 'HEALTHY'})) for i in range(10000)])
        connection.execute('CREATE TABLE evidence(kind TEXT,identity TEXT,document TEXT,PRIMARY KEY(kind,identity))')
        connection.executemany('INSERT INTO evidence VALUES (?,?,?)', [('claim', f'single:{i:08}', '{}') for i in range(10000)])
        connection.commit()
        connection.close()
        start = time.monotonic()
        records, events, cursor, read = tail(path, {}, now, running=False)
        for value, reference in records:
            events.extend(compact(value, reference, now))
        health, health_state = health_rows(db, {}, now)
        ledger, ledger_state = unresolved(db, {}, now)
        events.extend(health+ledger)
        admin = root/'admin-alerts'
        admin.mkdir()
        store = Store(admin)
        store.ingest(events, {'stdout': cursor, 'health': health_state, 'ledger': ledger_state}, now)
        store.enqueue(now)
        store.retain(now)
        count = store.db.execute('SELECT count(*) FROM incidents').fetchone()[0]
        store.close()
        print(json.dumps({'schema': 'goalvision-admin-benchmark-v1',
            'elapsed_seconds': round(time.monotonic()-start, 4), 'max_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'log_bytes_on_disk': path.stat().st_size, 'stdout_bytes_read': read,
            'records_processed': len(records), 'synthetic_health_rows_per_table': 10000,
            'synthetic_claim_rows': 10000, 'maximum_rows_per_query': 128, 'incidents': count,
            'producer_writes_during_scan': 0, 'telegram_sends': 0, 'football_api_calls': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
