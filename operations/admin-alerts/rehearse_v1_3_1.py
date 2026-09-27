"""Offline or read-only host snapshot rehearsal of idle cleanup and existing-epoch resume."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import tempfile
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from app.admin_alerts.activation import resume_projection, resume
from app.admin_alerts.model import Event, DISCOVERY
from app.admin_alerts.store import Store


def epoch_rows(store: Store) -> dict:
    return {table: list(map(tuple, store.db.execute('SELECT * FROM '+table+' ORDER BY 1')))
            for table in ('notification_epochs','epoch_incidents')}


def project(raw: bytes, config: dict, now: float) -> dict:
    """Only disposable state changes; any transport or new activation call is an error."""
    with tempfile.TemporaryDirectory(prefix='goalvision-admin-alerts-v131-projection-') as name:
        root=Path(name)
        (root/'admin.sqlite').write_bytes(raw)
        config_path=root/'config.json';config_path.write_text(json.dumps(config))
        store=Store(root)
        try:
            epoch=epoch_rows(store)
            attempts=list(map(tuple,store.db.execute('SELECT * FROM attempts')))
            with patch('urllib.request.OpenerDirector.open', side_effect=AssertionError('NO_NETWORK')),\
                 patch('app.admin_alerts.activation.prepare_epoch', side_effect=AssertionError('NO_NEW_EPOCH')):
                count=store.invalidate_idle_delivery(now)
                review=resume_projection(store.db,config)
                db_before_resume=(root/'admin.sqlite').read_bytes()
                if review['resume_ready']:
                    resume(config_path,store.db)
                unchanged=epoch==epoch_rows(store)
                return {'mode':'ISOLATED_SNAPSHOT_NO_SEND',
                    'source_snapshot_sha256':hashlib.sha256(raw).hexdigest(),
                    'would_invalidate_idle_unknown':count,
                    'epoch_preserved':unchanged,
                    'new_epoch_rows':len(epoch_rows(store)['notification_epochs'])-len(epoch['notification_epochs']),
                    'notification_epoch':review['notification_epoch'],
                    'activation_snapshot_complete':review['activation_snapshot_complete'],
                    'activation_review_required':review['activation_review_required'],
                    'resume_ready_after_cleanup':review['resume_ready'],
                    'snapshot_sender_after_resume':json.loads(config_path.read_text())['sender']['enabled'],
                    'resume_database_bytes_unchanged':db_before_resume==(root/'admin.sqlite').read_bytes(),
                    'attempt_history_preserved':attempts==list(map(tuple,store.db.execute('SELECT * FROM attempts'))),
                    'telegram_sends':0,'football_api_calls':0,'prematch_controls':0,'live_mutations':0}
        finally:
            store.close()


def synthetic(now: float) -> dict:
    """Seed an already activated corrected v1.3 fixture, including the old defect."""
    from app.admin_alerts.activation import prepare_epoch
    with tempfile.TemporaryDirectory(prefix='goalvision-admin-alerts-v131-fixture-') as name:
        root=Path(name)
        token=root/'token';token.write_text('99:'+'x'*30);token.chmod(0o600)
        config={'sender':{'enabled':False,'token_file':str(token),'bot_id':99,
            'bot_username':'AdminBot','private_chat_id':123,'operator_confirmed_start':True}}
        store=Store(root)
        store.ingest([Event(DISCOVERY,'TIMER_INACTIVE','timer','old',now-100,'systemd')],{},now-100)
        store.enqueue(now-100);prepare_epoch(store.db,now-50)
        store.ingest([Event('monitor','ADMIN_DELIVERY_DEGRADED','admin','UNKNOWN',now-20,
                           'admin-transport',facts={'code':'UNKNOWN'})],{},now-20)
        store.enqueue(now-20);store.close()
        result=project((root/'admin.sqlite').read_bytes(),config,now)
        result['evidence_origin']='SYNTHETIC_EXISTING_EPOCH_FIXTURE_NOT_LIVE'
        return result


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic',action='store_true')
    parser.add_argument('--installed',choices=('v1.3','v1.3.1'),default='v1.3')
    args=parser.parse_args()
    def expired(signum: int, frame: object) -> None:
        raise TimeoutError('REHEARSAL_DEADLINE')
    signal.signal(signal.SIGALRM,expired);signal.alarm(40)
    try:
        if args.synthetic:
            result=synthetic(time.time())
        else:
            import control_v1_3_1 as control
            package=Path(__file__).resolve().parent
            review=control.inspect(package,installed=args.installed)
            if review['sender_enabled'] is not False or review['monitor_fenced']:
                raise ValueError('DISABLED_SENDER_UNFENCED_MONITOR_REQUIRED')
            # Repeat configuration and snapshot reads under the existing scan lock.
            with control.scan_lock():
                config=json.loads(control.CONFIG.read_text())
                with control.snapshot(locked=True) as db:
                    raw=db.serialize()
            result=project(raw,config,time.time())
            result['evidence_origin']='LIVE_ADMIN_READ_ONLY_SNAPSHOT'
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0 if (result['resume_ready_after_cleanup'] and result['epoch_preserved']
                     and result['resume_database_bytes_unchanged']) else 1
    except Exception:
        print(json.dumps({'status':'HOST_REHEARSAL_BLOCKED','reason':'ADMIN_SNAPSHOT_OR_READINESS_REVIEW_REQUIRED',
                          'live_mutations':0,'telegram_sends':0,'football_api_calls':0,'prematch_controls':0}))
        return 1
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    raise SystemExit(main())
