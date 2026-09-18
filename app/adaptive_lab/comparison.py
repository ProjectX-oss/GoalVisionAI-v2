"""Versioned mandatory gates and deterministic fixture-clustered confidence analysis."""
from __future__ import annotations
from collections import Counter, defaultdict
from random import Random
from statistics import mean
from .contracts import number
from .metrics import metrics, bucket
from .policy import POLICY


def evaluated(rows: list[dict], probabilities: list[float]) -> list[dict]:
    if len(rows)!=len(probabilities):
        raise ValueError('COMPARISON_LENGTH_MISMATCH')
    result=[]
    for row,p in zip(rows,probabilities,strict=True):
        if not 0<p<1:
            raise ValueError('PROBABILITY_CONTRACT_VIOLATION')
        odds=number(row['offered_decimal_odds'])
        result.append({**row,'frozen_model_probability':p,'edge':p-1/odds,'EV':p*odds-1})
    return result


def selected(row: dict) -> bool:
    """Research selection proxy; actual publication still runs the stream safety shell."""
    return row['EV']>0 and row['edge']>number(row.get('uncertainty') or 0)


def paired_bootstrap(rows: list[dict], champion: list[float], challenger: list[float]) -> list[float]:
    groups=defaultdict(list)
    for r,c,p in zip(rows,champion,challenger,strict=True):
        groups[str(r['fixture_id'])].append((p-r['target'])**2-(c-r['target'])**2)
    keys=sorted(groups)
    if not keys:
        return [0.,0.]
    rng=Random(POLICY.seed)
    samples=sorted(mean(v for _ in keys for v in groups[rng.choice(keys)]) for _ in range(POLICY.bootstrap_replicates))
    return [samples[int(.025*len(samples))],samples[int(.975*len(samples))]]


def compare(rows: list[dict], champion: list[float], challenger: list[float], *, minimum: int) -> dict:
    """Evaluate matching opportunities; catastrophic subgroups veto aggregate gains."""
    if not rows or len({r['stream'] for r in rows})!=1 or any(r['target'] is None for r in rows):
        raise ValueError('COMPARISON_BINARY_STREAM_REQUIRED')
    stream=rows[0]['stream']
    old,new=evaluated(rows,champion),evaluated(rows,challenger)
    cm,nm=metrics(old,stream),metrics(new,stream)
    old_selected,new_selected=[r for r in old if selected(r)],[r for r in new if selected(r)]
    cb,nb=metrics(old_selected,stream),metrics(new_selected,stream)
    ratio=len(new_selected)/max(1,len(old_selected))
    subgroups=[]
    for key in ('competition_profile','market','league_id'):
        for value in sorted({str(r.get(key)) for r in rows}):
            idx=[i for i,r in enumerate(rows) if str(r.get(key))==value]
            if len(idx)>=POLICY.subgroup_min:
                delta=mean((challenger[i]-rows[i]['target'])**2-(champion[i]-rows[i]['target'])**2 for i in idx)
                subgroups.append({'dimension':key,'value':value,'n':len(idx),'brier_delta':delta})
    # Chronological quarters and confidence bins are evaluated independently.
    for i in range(4):
        indices=list(range(i*len(rows)//4,(i+1)*len(rows)//4))
        if len(indices)>=POLICY.subgroup_min:
            delta=mean((challenger[j]-rows[j]['target'])**2-(champion[j]-rows[j]['target'])**2 for j in indices)
            subgroups.append({'dimension':'time_quarter','value':str(i),'n':len(indices),'brier_delta':delta})
    for band in range(10):
        indices=[j for j,p in enumerate(challenger) if min(9,int(p*10))==band]
        if len(indices)>=POLICY.subgroup_min:
            delta=mean((challenger[j]-rows[j]['target'])**2-(champion[j]-rows[j]['target'])**2 for j in indices)
            subgroups.append({'dimension':'confidence_bin','value':str(band),'n':len(indices),'brier_delta':delta})
    interval=paired_bootstrap(rows,champion,challenger)
    concentration={}
    for key in ('league_id','competition_profile','market'):
        counts=Counter(str(r.get(key)) for r in new_selected)
        concentration[key]=max(counts.values(),default=0)/max(1,len(new_selected))
    concentration['odds_bucket']=max(Counter(bucket(r['offered_decimal_odds'],'odds') for r in new_selected).values(),default=0)/max(1,len(new_selected))
    gates={
        'sufficient_evidence':len(rows)>=minimum,
        'probability_contract':True,
        'brier_not_materially_worse':nm['brier']<=cm['brier']+POLICY.brier_tolerance,
        'logloss_not_materially_worse':nm['log_loss']<=cm['log_loss']+POLICY.logloss_tolerance,
        'calibration_not_materially_worse':nm['ece']<=cm['ece']+POLICY.ece_tolerance,
        'no_catastrophic_subgroup':all(g['brier_delta']<=POLICY.subgroup_brier_tolerance for g in subgroups),
        'no_selection_collapse':len(new_selected)>0 and ratio>=POLICY.selection_ratio_min,
        'no_selection_explosion':ratio<=POLICY.selection_ratio_max,
        'risk_not_materially_worse':nb['maximum_drawdown']<=max(cb['maximum_drawdown']*1.5,cb['maximum_drawdown']+5),
        'losing_streak_not_materially_worse':nb['maximum_losing_streak']<=max(cb['maximum_losing_streak']*2,cb['maximum_losing_streak']+5),
        'roi_not_materially_worse':(nb['flat_unit_roi'] or 0)>=(cb['flat_unit_roi'] or 0)-.1,
        'predictive_improvement':nm['brier']<cm['brier'] or nm['log_loss']<cm['log_loss'],
        'bootstrap_no_material_harm':interval[1]<=POLICY.brier_tolerance,
    }
    return {'policy_version':POLICY.version,'champion':cm,'challenger':nm,'champion_betting':cb,
            'challenger_betting':nb,'selection_ratio':ratio,'concentration':concentration,
            'subgroups':subgroups,'brier_delta_bootstrap_95':interval,'gates':gates,
            'passed':all(gates.values()),'blocked_by':sorted(k for k,v in gates.items() if not v)}
