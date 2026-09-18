"""PREMATCH-only settlement observer; no transport, provider client, or training."""
from __future__ import annotations
from datetime import datetime
from .contracts import digest,utc
from .coordinator import LearningCoordinator
from .metrics import metrics


def observe(repository: object, ledger: object, *, now: datetime) -> dict:
    """Recover immutable settlements and shadow labels from existing result evidence."""
    coordinator=LearningCoordinator(repository)
    from .observations import import_prematch
    linkage=import_prematch(ledger,repository,now=utc(now).isoformat())
    results={}
    for kind in ('single_settlement','leg_result'):
        for r in ledger.all(kind):
            if r.get('provider_status') and r.get('source_fingerprint'):
                key=str(r['fixture_id'])
                value={'response':[{'fixture':{'id':int(key),'status':{'short':r['provider_status']}},
                       'score':{'fulltime':{'home':r.get('fulltime_home'),'away':r.get('fulltime_away')}}}],
                       'original_result_fingerprint':r['source_fingerprint']}
                if key in results and results[key]['response']!=value['response']:
                    raise ValueError('CONFLICTING_FIXTURE_RESULTS')
                results[key]=value
    for pred in repository.all('shadow_predictions','PREMATCH'):
        if repository.get('shadow_settlements',pred['prediction_id']):
            continue
        payload=results.get(str(pred['frozen_opportunity']['fixture_id']))
        if payload:
            coordinator.governance.settle_shadow_result(pred['prediction_id'],payload,now=now)
    state=coordinator.after_settlement('PREMATCH',now=now,train=False)
    value={'created_at':utc(now).isoformat(),'stream':'PREMATCH','linkage':linkage,
           'state':state,'metrics':metrics(repository.all('learning_observations','PREMATCH'),'PREMATCH'),
           'LIVE':'DISABLED','api_calls':0,'telegram_sends':0,'heavy_training':False}
    repository.append('observer_runs',digest(value),'PREMATCH',value,value['created_at'])
    return value


async def settle_pending_shadow(repository: object, client: object, *, now: datetime,
                                maximum_calls: int = 5) -> dict:
    """Bounded fallback within the existing settlement worker, never observer polling."""
    from .governance import Governance
    if not 0<=maximum_calls<=20:
        raise ValueError('SHADOW_SETTLEMENT_CALL_BOUND')
    start=client.request_count;cache={};done=[]
    for pred in repository.all('shadow_predictions','PREMATCH'):
        identity=pred['prediction_id'];row=pred['frozen_opportunity']
        if repository.get('shadow_settlements',identity) or (utc(now)-utc(row['kickoff_utc'])).total_seconds()<7200:
            continue
        fid=int(row['fixture_id'])
        if fid not in cache:
            if client.request_count-start>=maximum_calls:
                continue
            cache[fid]=await client.fixture(fid)
        if Governance(repository).settle_shadow_result(identity,cache[fid],now=now):
            done.append(identity)
    return {'settled':done,'api_calls':client.request_count-start}
