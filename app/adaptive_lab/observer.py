"""PREMATCH-only settlement observer; no transport, provider client, or training."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import os
from .contracts import digest,utc
from .coordinator import LearningCoordinator
from .metrics import metrics


def observe(repository: object, ledger: object, *, now: datetime,
            shadow_database: Path | None = None) -> dict:
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
    import_canonical(repository, now=now)
    state=coordinator.after_settlement('PREMATCH',now=now,train=False)
    from .performance import performance_snapshot
    value={'PERFORMANCE':performance_snapshot(ledger,now=now),'created_at':utc(now).isoformat(),'stream':'PREMATCH','linkage':linkage,
           'state':state,'metrics':metrics(repository.all('learning_observations','PREMATCH'),'PREMATCH'),
           'LIVE':'NOT_EVALUATED','LIVE_SCOPE':'PREMATCH_OBSERVER','api_calls':0,'telegram_sends':0,'heavy_training':False}
    if shadow_database is not None and os.environ.get("GOALVISION_LAB_DEVIG_RESEARCH", "0") == "1":
        try:
            from .devig_integration import observed_snapshot, persist_metrics
            from .devig_metrics import operator_summary
            snapshot = observed_snapshot(repository, ledger, shadow_database, now=now)
            if "snapshot_fingerprint" in snapshot:
                persist_metrics(shadow_database, snapshot, now=now)
            value["DEVIG_RESEARCH"] = operator_summary(snapshot)
        except Exception:
            value["DEVIG_RESEARCH"] = {"status": "UNAVAILABLE", "reason": "RESEARCH_EVALUATION_UNAVAILABLE",
                                       "selection_effect": "NONE", "model_learning_observations": 0}
    if os.environ.get("GOALVISION_LAB_CALIBRATION_READINESS", "0") == "1":
        try:
            from .calendar_monitor import observed_readiness
            value["CALIBRATION_READINESS"] = observed_readiness(repository, ledger, now=now)
        except Exception:
            value["CALIBRATION_READINESS"] = {
                "status": "UNAVAILABLE", "reason": "CALIBRATION_READINESS_UNAVAILABLE",
                "selection_effect": "NONE", "training_invoked": False, "promotion_allowed": False}
    repository.append('observer_runs',digest(value),'PREMATCH',value,value['created_at'])
    return value


async def settle_pending_shadow(repository: object, client: object, *, now: datetime,
                                maximum_calls: int = 5, ledger: object | None = None) -> dict:
    """Bounded fallback within the existing settlement worker, never observer polling."""
    from .governance import Governance
    if not 0<=maximum_calls<=20:
        raise ValueError('SHADOW_SETTLEMENT_CALL_BOUND')
    start=client.request_count;cache={};done=[]
    if maximum_calls and hasattr(client, 'restrict_requests'):
        client.restrict_requests(start + maximum_calls)

    if ledger is not None:
        for kind in ('single_settlement', 'leg_result'):
            for result in ledger.all(kind):
                if result.get('provider_status') and result.get('source_fingerprint'):
                    fid = int(result['fixture_id'])
                    cache[fid] = {'response': [{'fixture': {'id': fid, 'status': {'short': result['provider_status']}},
                        'score': {'fulltime': {'home': result.get('fulltime_home'), 'away': result.get('fulltime_away')}}}]}

    for pred in repository.all('shadow_predictions','PREMATCH'):
        identity=pred['prediction_id'];row=pred['frozen_opportunity']
        if repository.get('shadow_settlements',identity) or (utc(now)-utc(row['kickoff_utc'])).total_seconds()<7200:
            continue
        fid=int(row['fixture_id'])
        if fid not in cache:
            if client.request_count-start>=maximum_calls:
                continue
            cache[fid]=await _result_payload(client, fid)
        if Governance(repository).settle_shadow_result(identity,cache[fid],now=now):
            done.append(identity)
    from app.lab_combo.settlement import resolve_leg
    for row in repository.all('canonical_opportunities', 'PREMATCH'):
        key = str(row['fixture_id']) + ':' + row['market']
        if repository.get('canonical_results', key) or (utc(now)-utc(row['kickoff_utc'])).total_seconds() < 7200:
            continue
        fid = int(row['fixture_id'])
        if fid not in cache:
            if client.request_count-start >= maximum_calls:
                break
            cache[fid] = await _result_payload(client, fid)
        try:
            result = resolve_leg({**row, 'observation_id': key, 'odds': row['captured_odds']}, cache[fid], now)
        except (ValueError, TypeError, AttributeError):
            continue
        if result:
            repository.append('canonical_results', key, 'PREMATCH', result, utc(now).isoformat())
    import_canonical(repository, now=now)
    return {'settled':done,'api_calls':client.request_count-start}


def import_canonical(repository: object, *, now: datetime) -> None:
    """Join frozen non-public samples into the existing adaptive training evidence."""
    from .observations import ingest
    for result in repository.all('canonical_results', 'PREMATCH'):
        key = result['observation_id']
        row = repository.get('canonical_opportunities', key)
        if row:
            ingest(repository, row, {}, result, stream='PREMATCH', publication_id=key, source_product='SHADOW')


async def _result_payload(client: object, fixture_id: int) -> dict:
    """Leave transient failures pending while preserving client retry accounting."""
    import httpx
    from json import JSONDecodeError
    from app.football.client import FootballRequestLimitError
    from app.football.quota import FootballQuotaError
    try:
        payload = await client.fixture(fixture_id)
        return payload if isinstance(payload, dict) else {}
    except (httpx.HTTPError, OSError, TimeoutError, JSONDecodeError, FootballRequestLimitError, FootballQuotaError):
        return {}
