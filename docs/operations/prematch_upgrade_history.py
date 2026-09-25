"""Bounded read-only upgrade compatibility inventory; never reconcile or send."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

RUNTIME = Path('/home/arvis/GoalVisionAI/var')
CONTEXT = Path('/home/arvis/goalvision-operations/football-context-v2')
LIMIT = 200

@contextmanager
def read(path):
    c = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)
    c.row_factory = sqlite3.Row
    deadline = time.monotonic() + 15
    c.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    c.execute('PRAGMA query_only=ON')
    c.execute('BEGIN')
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def rows(c, sql, args=()):
    result = [dict(r) for r in c.execute(sql, args).fetchmany(LIMIT + 1)]
    return {'rows': result[:LIMIT], 'truncated': len(result) > LIMIT}


def inventory():
    result = {'captured_at_utc': datetime.now(timezone.utc).isoformat(),
              'consistency': 'One mode=ro query_only transaction per database; not a simultaneous cross-database snapshot.',
              'bound': '15 second progress deadline per database; 200 rows per detail; no history writes.'}
    with read(RUNTIME / 'lab_combo/ledger.db') as c:
        result['delivery_kinds'] = rows(c, "SELECT kind,count(*) AS count FROM evidence WHERE kind IN ('claim','economic_claim','delivery_unknown','receipt','single_prediction','prediction','single_settlement','settlement') GROUP BY kind")
        result['unreceipted_claims'] = rows(c, """SELECT identity FROM evidence c WHERE c.kind='claim'
            AND NOT EXISTS (SELECT 1 FROM evidence r WHERE r.kind='receipt' AND r.identity=c.identity) ORDER BY identity LIMIT 201""")
        result['unknown_outcomes'] = rows(c, "SELECT identity FROM evidence WHERE kind='delivery_unknown' ORDER BY identity LIMIT 201")
        result['economic_claims_without_receipts'] = rows(c, """SELECT identity,json_extract(document,'$.publication_identity') AS publication_identity
            FROM evidence c WHERE kind='economic_claim' AND NOT EXISTS
            (SELECT 1 FROM evidence r WHERE r.kind='receipt' AND r.identity=json_extract(c.document,'$.publication_identity')) ORDER BY identity LIMIT 201""")
        result['confirmed_publications'] = rows(c, """SELECT substr(identity,1,instr(identity,':')-1) AS publication_kind,count(*) AS count
            FROM evidence WHERE kind='receipt' AND identity GLOB '*prediction:*'
            AND json_extract(document,'$.status')='SENT' AND json_extract(document,'$.sent')=1
            AND json_extract(document,'$.message_id')>0 GROUP BY publication_kind""")
        result['pending_settlements'] = rows(c, """SELECT p.identity,p.kind,json_extract(r.document,'$.message_id') AS message_id
            FROM evidence p JOIN evidence r ON r.kind='receipt'
            AND r.identity=(CASE p.kind WHEN 'single_prediction' THEN 'single_prediction:' ELSE 'combo_prediction:' END)||p.identity
            WHERE p.kind IN ('single_prediction','prediction') AND json_extract(r.document,'$.status')='SENT'
            AND NOT EXISTS (SELECT 1 FROM evidence s WHERE s.identity=p.identity AND s.kind=CASE p.kind
                WHEN 'single_prediction' THEN 'single_settlement' ELSE 'settlement' END) ORDER BY p.identity LIMIT 201""")
    with read(RUNTIME / 'lab_v2/shadow.db') as c:
        result['recent_publication_cycles'] = rows(c, """SELECT identity,created_at_utc,
            json_extract(document_json,'$.analysis_status') AS analysis_status,
            json_extract(document_json,'$.delivery_status') AS delivery_status,
            json_extract(document_json,'$.publication_requested') AS publication_requested,
            json_extract(document_json,'$.telegram_sends') AS telegram_sends
            FROM lab_v2_shadow_evidence WHERE kind='publication_cycle' ORDER BY created_at_utc DESC LIMIT 20""")
        # Walk only bounded recent publication-cycle JSON; select facts, never API payloads.
        evidence = []
        def inspect(value):
            if isinstance(value, dict):
                if value.get('acknowledgement_received') and not value.get('receipt_persisted'):
                    evidence.append({k:value.get(k) for k in ('prediction_id','acknowledgement_received','acknowledgement','receipt_persisted','persistence_failure','reconciliation_required')})
                for v in value.values(): inspect(v)
            elif isinstance(value,list):
                for v in value: inspect(v)
        for row in c.execute("SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='publication_cycle' ORDER BY created_at_utc DESC LIMIT 200"):
            inspect(json.loads(row[0]))
        result['acknowledged_unpersisted_in_latest_200_cycles'] = evidence
    result['stdout_evidence_limit'] = 'Installed discovery stdout=null: absent receipt/cycle output cannot prove non-delivery. No complete stdout archive is available.'
    stores = {}
    for name in ('attempts.db','sources.db','snapshots.db','reviewed-regulations.sqlite'):
        path=CONTEXT/name
        with read(path) as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 20")]
            # Names come from local schema, still validate before identifier interpolation.
            assert all(t.replace('_','').isalnum() for t in tables)
            stores[name]={'integrity':c.execute('PRAGMA quick_check(1)').fetchone()[0],
                          'tables':{t:c.execute('SELECT count(*) FROM "'+t+'"').fetchone()[0] for t in tables},
                          'mode':oct(path.stat().st_mode & 0o777)}
    result['observation_stores']=stores
    from app.prematch_football_context.regulation_registry.repository import Registry
    registry=Registry(CONTEXT/'reviewed-regulations.sqlite')
    try:
        deadline=time.monotonic()+15
        registry.connection.set_progress_handler(lambda: int(time.monotonic()>deadline),10000)
        registry.connection.execute('PRAGMA query_only=ON')
        registry.connection.execute('BEGIN')
        result['registry_validation']={'status':'VERIFIED','records':len(registry.verify())}
    finally:
        registry.connection.rollback(); registry.close()
    with read(RUNTIME/'adaptive_lab/audit.db') as c:
        result['observer_store']=rows(c,"SELECT stream,count(*) AS count,max(created_at) AS latest FROM observer_runs WHERE stream='PREMATCH' GROUP BY stream")
        result['weekly_unknown']=rows(c,"SELECT id,created_at,claim_id FROM weekly_delivery_unknown WHERE stream='PREMATCH' ORDER BY created_at DESC LIMIT 201")
        result['weekly_unreceipted_claims']=rows(c,"""SELECT q.id,q.created_at FROM weekly_claims q WHERE stream='PREMATCH'
            AND NOT EXISTS(SELECT 1 FROM weekly_receipts r WHERE r.claim_id=q.id AND r.stream=q.stream) ORDER BY created_at DESC LIMIT 201""")
    result['unresolved_delivery_observed']=any(result[k]['rows'] or result[k]['truncated'] for k in ('unreceipted_claims','unknown_outcomes','economic_claims_without_receipts','weekly_unknown','weekly_unreceipted_claims')) or bool(result['acknowledged_unpersisted_in_latest_200_cycles'])
    return result

if __name__ == '__main__':
    print(json.dumps(inventory(),indent=2,sort_keys=True))
