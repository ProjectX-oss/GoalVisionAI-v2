"""Pure, prospective 1X2 incremental-information research. No publication hook."""
from collections import Counter
from math import exp,log,isfinite
from pathlib import Path
import json
from app.adaptive_lab.performance import probability_metrics
from app.dixon_coles_research.contracts import seal,verify,utc,digest
from .contracts import load_plan as forward_plan,reserved
from . import service

ORDER=('HOME_WIN','DRAW','AWAY_WIN')
WEIGHTS=tuple(i/10 for i in range(11))


def load_plan():
    plan=json.loads(Path(__file__).with_name('incremental_plan_20261004.json').read_text())
    verify(plan)
    old=forward_plan()
    if (plan['forward_plan_fingerprint']!=old['fingerprint'] or plan['selection_effect']!='NONE'
            or plan['automatic_promotion'] is not False or plan['weights']!=list(WEIGHTS)
            or plan['calendar_fingerprint']!=old['protected_calendar']['plan_fingerprint']):
        raise ValueError('INCREMENTAL_PLAN_MISMATCH')
    return plan


def vector(values):
    result=tuple(float(v) for v in values)
    if len(result)!=3 or any(not isfinite(v) or not 0<v<1 for v in result):
        raise ValueError('INVALID_1X2_PROBABILITY')
    if abs(sum(result)-1)>1e-8:raise ValueError('NON_NORMALIZED_1X2')
    # Only floating point residue is removed; endpoints and incoherent vectors fail.
    return tuple(v/sum(result) for v in result)


def pool(base,dc,weight):
    if weight not in WEIGHTS:raise ValueError('UNDECLARED_WEIGHT')
    a,b=vector(base),vector(dc)
    values=[(1-weight)*log(x)+weight*log(y) for x,y in zip(a,b)]
    scale=max(values);values=[exp(v-scale) for v in values]
    return vector([v/sum(values) for v in values])


def scores(pairs):
    if not pairs:return {'fixtures':0,'rps':None,'brier':None,'log_loss':None,'ece':None}
    n=len(pairs)
    for p,y in pairs:
        vector(p)
        if type(y) is not int or y not in (0,1,2):raise ValueError('INVALID_1X2_OUTCOME')
    binary=[(p[i],int(y==i)) for p,y in pairs for i in range(3)]
    calibration=probability_metrics(binary)
    rank=lambda p,y:sum((sum(p[:i+1])-int(y<=i))**2 for i in (0,1))/2
    fav=[(p[max(range(3),key=lambda i:(p[i],-i))],int(y==max(range(3),key=lambda i:(p[i],-i)))) for p,y in pairs]
    longshot=[(p[min(range(3),key=lambda i:(p[i],i))],int(y==min(range(3),key=lambda i:(p[i],i)))) for p,y in pairs]
    return {'fixtures':n,'rps':sum(rank(p,y) for p,y in pairs)/n,
        'brier':sum(sum((p[i]-int(i==y))**2 for i in range(3)) for p,y in pairs)/n,
        'log_loss':-sum(log(p[y]) for p,y in pairs)/n,
        'ece':calibration['ece'],'mce':calibration['mce'],'reliability_bins':calibration['reliability_bins'],
        'draw_calibration':probability_metrics([(p[1],int(y==1)) for p,y in pairs]),
        'favourite_calibration':probability_metrics(fav),'longshot_calibration':probability_metrics(longshot)}


def eligible_forecasts(forecasts,*,plan,forward,now,additional_reserved=frozenset()):
    """Filter BEFORE requesting labels; holdout and predeclaration labels are not read."""
    verify(plan);excluded=reserved(forward,additional_reserved);counts=Counter();selected=[]
    end=utc(forward['protected_calendar']['windows']['SEALED_HOLDOUT'][0])
    for f in forecasts:
        verify(f)
        if f['fixture_id'] in excluded:counts['reserved']+=1;continue
        if utc(f['kickoff_utc'])>=end:counts['sealed_holdout']+=1;continue
        if min(utc(f['forecast_at']),utc(f['input_as_of']))<utc(plan['declared_at']):counts['predeclaration']+=1;continue
        if utc(f['forecast_at'])>utc(now):counts['future']+=1;continue
        if set(f['comparisons'])!=set(ORDER):counts['not_complete_1x2']+=1;continue
        selected.append(f)
    return selected,dict(counts)


def prepare(forecasts,models,results,*,plan,forward,now,additional_reserved=frozenset()):
    selected,counts=eligible_forecasts(forecasts,plan=plan,forward=forward,now=now,additional_reserved=additional_reserved)
    # Reuse immutable model verification, candidate/capture provenance and exact reproduction.
    verified=service.evaluate(selected,models,results,plan=forward,now=now,additional_reserved=additional_reserved)
    outcomes={}
    for result in results:
        if result.get('source_product') not in {'SINGLE','SHADOW'} or result.get('status')!='RESOLVED' or utc(result['settled_at'])>utc(now):continue
        fid=result['fixture_id']
        if fid not in outcomes or utc(result['settled_at'])<utc(outcomes[fid]['settled_at']):outcomes[fid]=result
    rows=[];champion=forward['protected_calendar']
    for f in selected:
        r=outcomes.get(f['fixture_id'])
        if not r:continue
        probs={}
        for out,source in (('MARKET','MULTIPLICATIVE'),('DIXON_COLES','DIXON_COLES')):
            probs[out]=vector([f['comparisons'][m][source] for m in ORDER])
        refs=f['candidate_references']
        if all(refs[m].get('model_generation')==champion['model_generation'] and
               refs[m].get('model_artifact_identity')==champion['model_artifact_identity'] for m in ORDER):
            try:probs['CHAMPION']=vector([f['comparisons'][m]['EXISTING_ENSEMBLE'] for m in ORDER])
            except (ValueError,KeyError):counts['incoherent_champion_vector']=counts.get('incoherent_champion_vector',0)+1
        else:counts['champion_identity_missing']=counts.get('champion_identity_missing',0)+1
        phase='PURGED'
        for name in ('CALIBRATION_FIT','VALIDATION_EVALUATION'):
            start,end=map(utc,champion['windows'][name])
            if start<=utc(f['forecast_at'])<=utc(f['kickoff_utc'])<utc(r['settled_at'])<end:phase=name
        h,a=r['home_goals'],r['away_goals']
        rows.append({'fixture_id':f['fixture_id'],'forecast_fingerprint':f['fingerprint'],
            'result_fingerprint':r['source_fingerprint'],'forecast_at':f['forecast_at'],
            'kickoff_utc':f['kickoff_utc'],'settled_at':r['settled_at'],'partition':phase,
            'p':probs,'y':0 if h>a else 2 if h<a else 1})
    return rows,{'filter_counts':counts,'verified_forward_fingerprint':verified['fingerprint'],
                 'eligible_forecasts':len(selected),'resolved_paired_fixtures':len(rows)}


def fit_pool(rows,*,base,plan,forward,now):
    """Explicit research fit only; never called by report or a runtime timer."""
    verify(plan)
    if base not in ('MARKET','CHAMPION'):raise ValueError('INVALID_POOL_BASE')
    start,end=map(utc,forward['protected_calendar']['windows']['CALIBRATION_FIT'])
    if utc(now)<end:raise ValueError('CALIBRATION_WINDOW_OPEN')
    if any(r['partition']!='CALIBRATION_FIT' or not start<=utc(r['forecast_at'])<=utc(r['kickoff_utc'])<utc(r['settled_at'])<end
           or utc(r['forecast_at'])<utc(plan['declared_at']) for r in rows):raise ValueError('FIT_PARTITION_LEAKAGE')
    if len({r['fixture_id'] for r in rows})!=len(rows):raise ValueError('FIXTURE_DEPENDENCE')
    subset=[r for r in rows if base in r['p']]
    if len(subset)<plan['minimum_fit_fixtures']:raise ValueError('INSUFFICIENT_FIT_FIXTURES')
    losses={str(w):scores([(pool(r['p'][base],r['p']['DIXON_COLES'],w),r['y']) for r in subset])['log_loss'] for w in WEIGHTS}
    best=min(losses.values());weight=next(w for w in WEIGHTS if losses[str(w)]<=best+1e-12)
    dataset=sorted([[r['fixture_id'],r['forecast_fingerprint'],r['result_fingerprint']] for r in subset])
    return seal({'version':'DC_INCREMENTAL_POOL_V1','plan_fingerprint':plan['fingerprint'],'base':base,
        'dc_weight':weight,'fit_losses':losses,'created_at':utc(now).isoformat(),
        'dataset':dataset,'dataset_fingerprint':digest(dataset),
        'model_generation':forward['protected_calendar']['model_generation'],
        'partition':'CALIBRATION_FIT','selection_effect':'NONE','automatic_promotion':False})


def report(rows,*,plan,forward,now,diagnostics=None):
    """Descriptive paired metrics. No fit, holdout read, recommendation or activation."""
    verify(plan);seen=set()
    for r in rows:
        if r['fixture_id'] in seen:raise ValueError('FIXTURE_DEPENDENCE')
        seen.add(r['fixture_id'])
        if r['partition'] not in ('CALIBRATION_FIT','VALIDATION_EVALUATION','PURGED'):raise ValueError('HOLDOUT_FORBIDDEN')
    comparisons={}
    for base in ('MARKET','CHAMPION'):
        subset=[r for r in rows if base in r['p'] and r['partition']!='PURGED']
        comparisons[base]={'baseline':scores([(r['p'][base],r['y']) for r in subset]),
            'dixon_coles_paired':scores([(r['p']['DIXON_COLES'],r['y']) for r in subset]),
            'fixed_half_pool':scores([(pool(r['p'][base],r['p']['DIXON_COLES'],.5),r['y']) for r in subset]),
            'mean_total_variation_disagreement':sum(sum(abs(a-b) for a,b in zip(r['p'][base],r['p']['DIXON_COLES']))/2 for r in subset)/len(subset) if subset else None}
    fit_n=len([r for r in rows if r['partition']=='CALIBRATION_FIT'])
    end=utc(forward['protected_calendar']['windows']['CALIBRATION_FIT'][1])
    blockers=[]
    if utc(now)<end:blockers.append('CALIBRATION_WINDOW_OPEN')
    if fit_n<plan['minimum_fit_fixtures']:blockers.append('INSUFFICIENT_PAIRED_FIT_FIXTURES')
    blockers.append('NO_FROZEN_WEIGHT_VALIDATED_ON_UNSEEN_VALIDATION')
    common=[r for r in rows if 'CHAMPION' in r['p'] and r['partition']!='PURGED']
    model_market_disagreement=sum(sum(abs(a-b) for a,b in zip(r['p']['CHAMPION'],r['p']['MARKET']))/2 for r in common)/len(common) if common else None
    return seal({'version':'DC_INCREMENTAL_INFORMATION_V1','as_of':utc(now).isoformat(),
        'plan_fingerprint':plan['fingerprint'],'diagnostics':diagnostics or {},'comparisons':comparisons,
        'partition_fixtures':dict(Counter(r['partition'] for r in rows)),
        'champion_market_mean_total_variation_disagreement':model_market_disagreement,
        'paired_fit_fixtures':{base:sum(r['partition']=='CALIBRATION_FIT' and base in r['p'] for r in rows) for base in ('MARKET','CHAMPION')},
        'optimal_forward_dc_weight':None,'weight_status':blockers,
        'fixed_pool_weight':.5,'fixed_pool_is_diagnostic_only':True,
        'market_definition':'FIRST_COMPLETE_BOOK_MULTIPLICATIVE_DEVIG_FROZEN_BY_FORWARD_PLAN',
        'rps_outcome_order':list(ORDER),'brier_definition':'SUM_OF_THREE_SQUARED_ERRORS_PER_FIXTURE',
        'ece_definition':'TEN_EQUAL_WIDTH_BINS_ON_3_CLASS_INDICATORS; NOT_3_INDEPENDENT_FIXTURES',
        'promotion_eligibility':'BLOCKED_NEEDS_MORE_EVIDENCE','holdout_read':False,'fit_invoked':False,
        'holdout_capture_blocker':'CURRENT_FORWARD_PLAN_ENDS_AT_HOLDOUT_START',
        'selection_effect':'NONE','automatic_promotion':False,'provider_calls':0,'telegram_sends':0})


def validate_pool(fit_rows,validation_rows,artifact,*,plan,forward,now):
    """Reproduce the frozen fit, then score independent unseen validation only."""
    import random
    from collections import defaultdict
    verify(artifact)
    if artifact!=fit_pool(fit_rows,base=artifact['base'],plan=plan,forward=forward,now=utc(artifact['created_at'])):
        raise ValueError('POOL_ARTIFACT_REPRODUCTION')
    start,end=map(utc,forward['protected_calendar']['windows']['VALIDATION_EVALUATION'])
    if utc(now)<end:raise ValueError('VALIDATION_WINDOW_OPEN')
    if utc(artifact['created_at'])>=start:raise ValueError('WEIGHT_NOT_FROZEN_BEFORE_VALIDATION')
    if any(r['partition']!='VALIDATION_EVALUATION' or not start<=utc(r['forecast_at'])<=utc(r['kickoff_utc'])<utc(r['settled_at'])<end for r in validation_rows):raise ValueError('VALIDATION_PARTITION_LEAKAGE')
    ids=[r['fixture_id'] for r in validation_rows]
    if len(set(ids))!=len(ids) or set(ids)&{r['fixture_id'] for r in fit_rows}:raise ValueError('FIXTURE_DEPENDENCE')
    base=artifact['base'];subset=[r for r in validation_rows if base in r['p']]
    days={r['kickoff_utc'][:10] for r in subset}
    if len(subset)<plan['minimum_validation_fixtures'] or len(days)<plan['minimum_validation_dates']:raise ValueError('INSUFFICIENT_VALIDATION')
    weight=artifact['dc_weight'];before=[];after=[];by_date=defaultdict(list)
    for r in subset:
        a=vector(r['p'][base]);b=pool(a,r['p']['DIXON_COLES'],weight);y=r['y']
        before.append((a,y));after.append((b,y));by_date[r['kickoff_utc'][:10]].append(log(a[y])-log(b[y]))
    rng=random.Random(plan['bootstrap_seed']);dates=sorted(by_date);replicates=[]
    for _ in range(plan['bootstrap_samples']):
        sample=[v for date in rng.choices(dates,k=len(dates)) for v in by_date[date]]
        replicates.append(sum(sample)/len(sample))
    replicates.sort();interval=[replicates[int(.025*(len(replicates)-1))],replicates[int(.975*(len(replicates)-1))]]
    split=len(dates)//2
    halves=[sum(v for d in group for v in by_date[d])/sum(len(by_date[d]) for d in group) for group in (dates[:split],dates[split:])]
    a,b=scores(before),scores(after);delta={k:b[k]-a[k] for k in ('log_loss','brier','rps')}
    stable=weight>plan['near_zero_weight_maximum'] and interval[1]<0 and max(halves)<0 and delta['brier']<=0 and delta['rps']<=0
    verdict='CONTINUE_HOLDOUT_PLANNING_ONLY' if stable else 'DO_NOT_ADVANCE_INCONCLUSIVE_OR_NO_INCREMENTAL_VALUE'
    return seal({'version':'DC_INCREMENTAL_VALIDATION_V1','plan_fingerprint':plan['fingerprint'],
        'pool_artifact_fingerprint':artifact['fingerprint'],'as_of':utc(now).isoformat(),
        'dc_weight':weight,'baseline':a,'pooled':b,'paired_delta':delta,
        'logloss_date_cluster_bootstrap_95_percent':interval,'chronological_half_deltas':halves,
        'verdict':verdict,'promotion_eligibility':'BLOCKED_HOLDOUT_AND_GOVERNANCE_REQUIRED',
        'selection_effect':'NONE','automatic_promotion':False,'holdout_read':False})
