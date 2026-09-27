"""One bounded no-send projection on an isolated snapshot; never modifies live state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import signal
import sys
import tempfile
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.admin_alerts.activation import prepare_epoch
from app.admin_alerts.correlation import groups
from app.admin_alerts.model import DISCOVERY, Event, coverage
from app.admin_alerts.sources import scan_page
from app.admin_alerts.store import Store


def project(raw: bytes, now: float, invocation: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='goalvision-admin-alerts-v13-projection-') as name:
        root = Path(name)
        (root/'admin.sqlite').write_bytes(raw)
        store = Store(root)
        try:
            attempts_before = list(map(tuple, store.db.execute('SELECT * FROM attempts')))
            old_outbox = store.db.execute('SELECT count(*) FROM outbox').fetchone()[0]
            invalidated = store.invalidate_scan_progress(now)
            store.enqueue(now)
            episodes = [g for g in groups(store.db) if g['invocation'] == invocation and g['service'] == DISCOVERY]
            suppressed = prepare_epoch(store.db, now+1)
            store.enqueue(now+2)
            state = {}
            progress_events = scan_page(state, [(f'{i:06}',) for i in range(128)], now, 'ledger')
            return {'mode':'ISOLATED_SNAPSHOT_NO_SEND','legacy_scan_invalidated':invalidated,
                'scan_progress_status':state['status'],'scan_progress_faults':len(progress_events),
                'historical_crash_group_count':len(episodes),
                'historical_crash_groups':[{'correlation_id':g['correlation_id'],
                    'primary_rule':g['members'][0]['rule'], 'rules':[r['rule'] for r in g['members']],
                    'associations':g['associations']} for g in episodes],
                'activation_policy':store.db.execute('SELECT policy FROM notification_epochs').fetchone()[0],
                'activation_snapshot_rows':store.db.execute('SELECT count(*) FROM epoch_incidents').fetchone()[0],
                'activation_snapshot_complete':not store.db.execute('''SELECT 1 FROM epoch_incidents
                    WHERE episode_at_activation IS NULL OR generation_at_activation IS NULL''').fetchone(),
                'existing_outbox_rows':old_outbox, 'would_suppress_at_activation':suppressed,
                'attempt_history_preserved':attempts_before==list(map(tuple,store.db.execute('SELECT * FROM attempts'))),
                'telegram_sends':0,'football_api_calls':0,'live_mutations':0}
        finally:
            store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic', action='store_true')
    parser.add_argument('--invocation', required=True)
    args = parser.parse_args()
    now = time.time()
    def expired(signum: int, frame: object) -> None:
        raise TimeoutError('REHEARSAL_DEADLINE')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(40)
    try:
        if args.synthetic:
            with tempfile.TemporaryDirectory(prefix='goalvision-admin-alerts-v13-fixture-') as name:
                root=Path(name); store=Store(root)
                events=[Event(DISCOVERY,'SERVICE_FAILURE','pipeline',args.invocation,now-200,'journal',invocation=args.invocation),
                        Event(DISCOVERY,'MISSING_OUTPUT',args.invocation,args.invocation,now-100,'stdout-window',invocation=args.invocation),
                        Event(DISCOVERY,'ANALYSIS_FAILURE','pipeline','health-one',now-195,'health-one'),
                        coverage('ledger',now-100,'UNRESOLVED_SCAN_IN_PROGRESS')]
                store.ingest(events,{},now-100); store.enqueue(now-100);store.close()
                result=project((root/'admin.sqlite').read_bytes(),now,args.invocation)
                result.update(evidence_origin='SYNTHETIC_CONTRACT_FIXTURE_NOT_LIVE',sender_enabled=False)
        else:
            import control_v1_3 as control
            review=control.inspect(Path(__file__).resolve().parent,installed='v1.2')
            if review['sender_enabled'] is not False:
                raise ValueError('SENDER_MUST_BE_FALSE')
            with control.snapshot() as db:
                raw=db.serialize()
            result=project(raw,now,args.invocation)
            result.update(evidence_origin='LIVE_ADMIN_READ_ONLY_SNAPSHOT',sender_enabled=False,
                          configured_identity_ready=review['identity_configured'])
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0
    except Exception:
        print(json.dumps({'status':'HOST_REHEARSAL_BLOCKED','reason':'READABLE_LIVE_ADMIN_STATE_REQUIRED',
                          'live_mutations':0,'telegram_sends':0,'football_api_calls':0}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
