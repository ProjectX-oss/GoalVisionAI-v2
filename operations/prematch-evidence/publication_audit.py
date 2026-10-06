"""Sanitized read-only delivery/settlement evidence; never sends or retries."""
from collections import Counter
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import time


def connect(path):
    db=sqlite3.connect(Path(path).absolute().as_uri()+'?mode=ro',uri=True,timeout=.2)
    db.execute('PRAGMA query_only=ON')
    deadline=time.monotonic()+20
    db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    return db


def ledger_audit(path, cutoff):
    now=datetime.fromisoformat(cutoff); since=(now-timedelta(hours=24)).isoformat()
    db=connect(path)
    try:
        kinds=('claim','receipt','delivery_unknown','single_prediction','prediction','single_settlement','settlement')
        data={k:{i:json.loads(v) for i,v in db.execute('SELECT identity,document FROM evidence WHERE kind=?',(k,))} for k in kinds}
        missing=set(data['claim'])-set(data['receipt'])
        missing_details=[]
        for key in sorted(missing):
            kind,identity=key.split(':',1)
            pred=data['single_prediction' if kind.startswith('single') else 'prediction'].get(identity,{})
            missing_details.append({'kind':kind,'prediction_id':identity,
                'prepared_at':pred.get('prepared_at_utc') or pred.get('created_at_utc'),
                'unknown_marker_present':key in data['delivery_unknown']})
        recent_receipts=Counter(v.get('status','MISSING') for v in data['receipt'].values()
                               if since <= (v.get('sent_at_utc') or '') <= cutoff)
        pending=[];duplicates={};published={};duplicate_details=[]
        for product,kind,result,prefixes in [('SINGLE','single_prediction','single_settlement',('single_prediction:',)),
                                            ('COMBO','prediction','settlement',('combo_prediction:','prediction:'))]:
            confirmed=[]
            for identity,pred in data[kind].items():
                receipt=next((data['receipt'].get(p+identity) for p in prefixes
                              if data['receipt'].get(p+identity,{}).get('status')=='SENT'),None)
                if not receipt or not (receipt.get('sent_at_utc') or 'z')<=cutoff:continue
                confirmed.append(pred)
                settlement=data[result].get(identity)
                if settlement and settlement['settled_at_utc']<=cutoff:continue
                kickoffs=[leg.get('kickoff_utc') for leg in pred.get('legs',[])] if product=='COMBO' else [pred.get('kickoff_utc')]
                kickoffs=[k for k in kickoffs if k]
                last=max(kickoffs) if kickoffs else None
                age=(now-datetime.fromisoformat(last)).total_seconds()/3600 if last else None
                pending.append({'product':product,'prediction_id':identity,'last_kickoff_utc':last,
                                'hours_after_last_kickoff':age,'older_than_6h':age is not None and age>6})
            published[product]=len(confirmed)
            keys=Counter((p.get('single_selection_policy') or 'LEGACY',str(p.get('fixture_id'))) for p in confirmed) if product=='SINGLE' else Counter(tuple(sorted(str(l['fixture_id'])+':'+l['market'] for l in p.get('legs',[]))) for p in confirmed)
            duplicates[product]=sum(n-1 for n in keys.values() if n>1)
            if product=='SINGLE':
                for (policy,fixture),n in keys.items():
                    if n<=1:continue
                    members=[p for p in confirmed if (p.get('single_selection_policy') or 'LEGACY')==policy and str(p.get('fixture_id'))==fixture]
                    duplicate_details.append({'policy':policy,'fixture_id':fixture,'count':n,
                        'prepared_at':[p.get('prepared_at_utc') for p in members],
                        'markets':[p.get('market') for p in members]})
        diagnostics=[]
        for _,raw in db.execute("SELECT identity,document FROM evidence WHERE kind='settlement_diagnostic' ORDER BY rowid DESC LIMIT 180"):
            value=json.loads(raw)
            if since <= value.get('observed_at_utc','') <= cutoff:
                diagnostics.append(value)
        return {'as_of':cutoff,'receipts_last_24h':dict(recent_receipts),
            'current_claims_without_receipt':len(missing),'current_missing_receipt_details':missing_details,
            'current_delivery_unknown_markers':len(data['delivery_unknown']),
            'claim_inventory_is_current_not_historical_asof':True,
            'confirmed_publications_asof':published,'duplicate_confirmed_fixture_within_single_policy_or_exact_combo':duplicates,
            'historical_single_fixture_repeat_details':duplicate_details,
            'pending':pending,'pending_older_than_6h':sum(p['older_than_6h'] for p in pending),
            'settlement_diagnostic_samples':len(diagnostics),
            'last_settlement_diagnostic':diagnostics[0] if diagnostics else None,
            'delay_limitation':'Kickoff age is a review flag, not measured delay from provider result availability.'}
    finally:db.close()


def publication_cycles(path,cutoff):
    now=datetime.fromisoformat(cutoff);since=(now-timedelta(hours=24)).isoformat();db=connect(path)
    try:
        raw=db.execute("SELECT created_at_utc,document_json FROM lab_v2_shadow_evidence WHERE kind='publication_cycle' AND created_at_utc>=? AND created_at_utc<=? ORDER BY rowid DESC LIMIT 40",(since,cutoff)).fetchall()
        rows=[]
        for at,doc in raw:
            v=json.loads(doc);p=v.get('controlled_publication',{});deliveries=p.get('deliveries',[])
            counters=Counter()
            for d in deliveries:
                counters['status:'+str(d.get('status'))]+=1
                counters['stage:'+str(d.get('stage'))]+=1
                for k in ('transport_attempted','receipt_persisted','reconciliation_required'):
                    counters[k]+=d.get(k) is True
                if d.get('transport_failure_kind'):counters['transport_failure:'+str(d['transport_failure_kind'])]+=1
                if d.get('status')!='SENT' and not d.get('transport_attempted'):counters['rejected_before_transport']+=1
            rows.append({'at':at,'delivery_status':v.get('delivery_status'), 'failure':p.get('failure'),
                'delivery_counts':dict(counters),'singles_sent':p.get('singles_sent',0),'combos_sent':p.get('combos_sent',0),
                'private_singles_sent':p.get('private_singles_sent',0),
                'single_blockers':dict(Counter(p.get('single_publication_blockers',{}).values())),
                'combo_blockers':dict(Counter(p.get('publication_blockers',{}).values()))})
        total=Counter()
        for row in rows:total.update(row['delivery_counts'])
        return {'since':since,'as_of':cutoff,'cycles':rows,'delivery_counts':dict(total)}
    finally:db.close()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--as-of',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();root=Path('/home/arvis/GoalVisionAI/var')
    out={'public_ledger':ledger_audit(root/'lab_combo/ledger.db',a.as_of),
         'private_ledger':ledger_audit(root/'lab_combo/private-single-170.db',a.as_of),
         'publication_cycles':publication_cycles(root/'lab_v2/shadow.db',a.as_of)}
    Path(a.output).write_text(json.dumps(out,sort_keys=True,indent=2)+'\n')
    print(json.dumps({k:{x:y for x,y in v.items() if x not in ('pending','cycles','last_settlement_diagnostic')} for k,v in out.items()},sort_keys=True))
