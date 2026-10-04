"""Bounded read-only candidate, quota and journal diagnostics. No service invocation."""
import argparse
from collections import Counter
from datetime import datetime,timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import time


def connect(path):
    db=sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True,timeout=.1)
    db.execute('PRAGMA query_only=ON')
    return db


def candidates(path,as_of):
    db=connect(path);deadline=time.monotonic()+40
    db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    try:
        cycles=db.execute("SELECT identity,created_at_utc,json_extract(document_json,'$.candidate_ids') FROM lab_v2_shadow_evidence WHERE kind='rehearsal' AND created_at_utc<=? ORDER BY rowid DESC LIMIT 12",(as_of,)).fetchall()
        ids=list(dict.fromkeys(i for _,_,v in cycles for i in json.loads(v or '[]')))
        if len(ids)>50000:raise ValueError('CANDIDATE_CAP')
        counts={k:Counter() for k in ('rejections','readiness','hard_failures','soft_findings','missing_features','decision','producer','raw_zero','calibration')}
        invalid=[];fixtures=set();ready=0
        for identity in ids:
            if time.monotonic()>deadline:raise TimeoutError('AUDIT_BUDGET')
            row=db.execute("SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='candidate' AND identity=?",(identity,)).fetchone()
            if row is None:raise ValueError('CANDIDATE_MISSING')
            v=json.loads(row[0]);fixtures.add(v['fixture_id']);ready+=v.get('readiness_lane') in {'READY','STANDARD_READY','STRONG_READY','EXPERIMENTAL_READY'}
            for out,key in (('rejections','rejection_reasons'),('readiness','readiness_reasons'),('hard_failures','hard_failures'),('soft_findings','soft_findings'),('missing_features','missing_features')):
                counts[out].update(v.get(key,[]))
            counts['decision'].update([v.get('decision','UNKNOWN')])
            if 'INVALID_MODEL_PROBABILITY' in v.get('rejection_reasons',[]):
                trace=v.get('invalid_model_probability_evidence',{})
                detail={k:v.get(k) for k in ('candidate_id','fixture_id','market','ensemble_probability','baseline_probability','model_generation','model_artifact_identity','calibration_status','api_prediction_normalization','invalid_model_probability_evidence','predictive_families')}
                detail['signals']=[{k:s.get(k) for k in ('name','probability','availability','independence_group','provenance')} for s in v.get('signals',[])]
                invalid.append(detail)
                counts['calibration'].update([v.get('calibration_status','UNKNOWN')])
                for s in detail['signals']:counts['producer'].update([s.get('name') or 'UNKNOWN'])
        return {'scope':'LATEST_12_COMPLETED_REHEARSALS_AS_OF_CUTOFF','cycles':len(cycles),'cycle_ids':[r[0] for r in cycles], 'earliest':min(r[1] for r in cycles),'latest':max(r[1] for r in cycles),'candidates':len(ids),'independent_fixtures':len(fixtures),'ready_candidates':ready,'counts':{k:dict(v) for k,v in counts.items()},'invalid_count':len(invalid),'invalid_fixtures':len({v['fixture_id'] for v in invalid}),'invalid_incidents':invalid}
    finally:db.close()


def runtime(path,as_of):
    cutoff=datetime.fromisoformat(as_of);since=(cutoff-timedelta(hours=24)).isoformat();db=connect(path)
    deadline=time.monotonic()+10;db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    try:
        columns={r[1] for r in db.execute('PRAGMA table_info(cycle_health)')}
        payload='document_json' if 'document_json' in columns else 'document'
        # Repository uses payload JSON; choose only observed schema names.
        if payload not in columns:payload='payload'
        if payload not in columns:raise ValueError('HEALTH_SCHEMA:'+','.join(sorted(columns)))
        rows=db.execute('SELECT '+payload+" FROM cycle_health WHERE stream='PREMATCH' AND created_at>=? AND created_at<=? ORDER BY created_at",(since,as_of)).fetchall()
        keep={'started_at','completed_at','result','failure','evidence_at','provider_calls','provider_rows','fixtures','fixtures_considered','fixtures_evaluated','odds_fixtures','markets','lanes','tracking','readiness_lanes','ready','published','rejections','fixture_blockers','readiness_blockers','quota','quota_remaining','LIVE'}
        health=[{k:v for k,v in json.loads(r[0]).items() if k in keep} for r in rows]
        quota=db.execute("SELECT count(*) FROM quota_claims WHERE created_at>=? AND created_at<=?",(cutoff.replace(hour=0,minute=0,second=0,microsecond=0).isoformat(),as_of)).fetchone()[0]
        aggregate={'cycles':len(health),'result_counts':dict(Counter(v['result'] for v in health)),**{k:sum(v.get(k,0) or 0 for v in health) for k in ('provider_calls','fixtures','fixtures_considered','fixtures_evaluated','markets','ready','published')}}
        return {'since':since,'cycle_health':health,'utc_day_quota_claims':quota,'aggregate':aggregate}
    finally:db.close()


def journals(as_of):
    end=datetime.fromisoformat(as_of);start=end-timedelta(hours=24)
    units=['goalvision-lab-v2-discover.service','goalvision-lab-combo-settle.service','goalvision-adaptive-learning-observer.service','goalvision-dixon-coles-forward.service']
    codes=['database is locked','database table is locked','QUOTA_DB_CONTENTION_EXHAUSTED','QUOTA_DB_CONTENTION_RETRY','PROTECTED_QUOTA_RESERVE','FileNotFoundError','Failed with result','timed out','PARTIAL','DISCOVERY_ACTIVE']
    result={}
    for unit in units:
        # These are system units; no sudo needed on this operator account.
        r=subprocess.run(['journalctl','--no-pager','-u',unit,'--since',start.isoformat(),'--until',end.isoformat(),'-o','cat'],capture_output=True,text=True,timeout=15)
        result[unit]={'exit':r.returncode,'lines':len(r.stdout.splitlines()),'counts':{c:r.stdout.count(c) for c in codes},'truncated':False}
    return {'since':start.isoformat(),'until':end.isoformat(),'units':result,'coverage':'OPERATOR_ACCESSIBLE_JOURNAL; ZERO_MATCHES_DOES_NOT_PROVE_NO_FAILURES; CROSS_CHECK_OPERATOR_ADMIN_EXPORT_AND_RUN_LEDGER'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--as-of',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path('/home/arvis/GoalVisionAI/var')
    for name,fn in [('candidates',lambda:candidates(root/'lab_v2/shadow.db',a.as_of)),('runtime',lambda:runtime(root/'adaptive_lab/audit.db',a.as_of)),('journals',lambda:journals(a.as_of))]:
        try:value=fn()
        except Exception as e:value={'status':'BLOCKED','error':str(e)}
        (a.output/(name+'.json')).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
        print(name,{k:v for k,v in value.items() if k not in ('cycle_health','invalid_incidents','cycle_ids')},flush=True)
if __name__=='__main__':main()
