"""Symmetric, stream-isolated descriptive statistics; associations are not causes."""
from __future__ import annotations
from collections import defaultdict
from math import log, sqrt
from statistics import mean
from .contracts import number, stream_name, utc

BUCKETS = {'odds': (1.5, 2., 3., 5., 10.), 'probability': (.4, .5, .6, .7, .8, .9),
           'edge': (0., .03, .07, .12, .2), 'EV': (0., .05, .1, .2, .4),
           'uncertainty': (.03, .06, .1, .2)}
MINUTE_BANDS = ((15, '0–15'), (30, '16–30'), (45, '31–45+'), (60, '46–60'), (75, '61–75'), (150, '76–90+'))


def bucket(value: object, name: str) -> str:
    if value is None:
        return 'MISSING'
    value = number(value)
    boundaries = BUCKETS[name]
    for i, bound in enumerate(boundaries):
        if value < bound:
            return f'[{boundaries[i-1] if i else "-inf"},{bound})'
    return f'[{boundaries[-1]},inf)'


def minute_band(minute: int) -> str:
    return next(label for bound, label in MINUTE_BANDS if minute <= bound)


def wilson(wins: int, n: int) -> list[float] | None:
    if not n:
        return None
    z, p = 1.96, wins / n
    centre = (p + z*z/(2*n)) / (1+z*z/n)
    radius = z * sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0, centre-radius), min(1, centre+radius)]


def metrics(rows: list[dict], stream: str) -> dict:
    """One-unit ROI denominator includes void stakes; binary quality excludes voids."""
    stream_name(stream)
    rows = sorted((r for r in rows if r['stream'] == stream), key=lambda r: (utc(r['settled_at']), r['observation_id']))
    binary = [r for r in rows if r['target'] is not None]
    n = len(binary)
    wins = sum(r['target'] for r in binary)
    probs = [number(r['frozen_model_probability'], low=0, high=1) for r in binary]
    targets = [r['target'] for r in binary]
    pnl = sum(number(r['flat_unit_pnl']) for r in rows)
    capital = peak = drawdown = losing = winning = max_losing = max_winning = 0
    for r in rows:
        capital += number(r['flat_unit_pnl'])
        peak = max(peak, capital)
        drawdown = max(drawdown, peak - capital)
        if r['target'] is None:
            continue
        losing = losing + 1 if r['target'] == 0 else 0
        winning = winning + 1 if r['target'] == 1 else 0
        max_losing, max_winning = max(max_losing, losing), max(max_winning, winning)
    bins = []
    for i in range(10):
        idx = [j for j, p in enumerate(probs) if min(9, int(p*10)) == i]
        if idx:
            predicted, actual = mean(probs[j] for j in idx), mean(targets[j] for j in idx)
            bins.append({'lower': i/10, 'upper': (i+1)/10, 'n': len(idx), 'predicted': predicted,
                         'observed': actual, 'error': predicted-actual})
    def average(key: str) -> float | None:
        values = [number(r[key]) for r in binary if r.get(key) is not None]
        return mean(values) if values else None
    return {'stream': stream, 'selections': len(rows), 'resolved': n, 'wins': wins, 'losses': n-wins,
            'voids': len(rows)-n, 'hit_rate': wins/n if n else None, 'flat_unit_pnl': pnl,
            'flat_unit_roi': pnl/len(rows) if rows else None,
            'brier': mean((p-y)**2 for p,y in zip(probs,targets)) if n else None,
            'log_loss': mean(-y*log(max(1e-12,p))-(1-y)*log(max(1e-12,1-p)) for p,y in zip(probs,targets)) if n else None,
            'expected_flat_unit_pnl':sum(number(r['EV']) for r in binary),
            'realized_minus_expected_pnl':pnl-sum(number(r['EV']) for r in binary),
            'reliability_bins': bins, 'ece': sum(b['n']*abs(b['error']) for b in bins)/n if n else None,
            'calibration_bias': mean(probs)-wins/n if n else None,
            'overconfidence': max(0,mean(probs)-wins/n) if n else None,
            'underconfidence': max(0,wins/n-mean(probs)) if n else None,
            'maximum_drawdown': drawdown, 'maximum_losing_streak': max_losing, 'maximum_winning_streak': max_winning,
            'wilson_95': wilson(wins,n),
            **{'average_'+key: average(key) for key in ('offered_decimal_odds','frozen_model_probability',
                                                       'implied_probability','edge','EV','uncertainty')}}


def segments(rows: list[dict], stream: str, *, limit: int = 500) -> list[dict]:
    """Bounded one-dimensional groups and five useful intersections, never a Cartesian product."""
    groups = defaultdict(list)
    dimensions = ('competition_profile','league_id','market','side','lane','model_generation','policy_version',
                  'classifier_version','evidence_family_count','primary_predictive_family')
    for r in rows:
        if r['stream'] != stream:
            continue
        values = {k: str(r.get(k)) for k in dimensions}
        for name, key in (('odds','offered_decimal_odds'),('probability','frozen_model_probability'),
                          ('edge','edge'),('EV','EV'),('uncertainty','uncertainty')):
            values[name+'_bucket'] = bucket(r.get(key),name)
        if stream == 'LIVE':
            values.update(minute_band=minute_band(r['live_minute']),
                          score_state=f"{r['live_score_home']}:{r['live_score_away']}",
                          red_card_state=str(r.get('red_card_state')), prematch_favorite_state=str(r.get('prematch_favorite_state')))
        for k,v in values.items():
            groups[(k,v)].append(r)
        for a,b in (('competition_profile','market'),('competition_profile','lane'),('market','lane'),
                    ('model_generation','market'),('policy_version','competition_profile')):
            groups[(a+'×'+b,values[a]+'×'+values[b])].append(r)
    keys = sorted(groups,key=lambda k:(-len(groups[k]),k))[:limit]
    return [{'dimension':k[0],'value':k[1],**metrics(groups[k],stream)} for k in keys]


def diagnostics(row: dict) -> list[str]:
    if row['target'] is None:
        return ['VOID_EXCLUDED_FROM_BINARY_CALIBRATION']
    suffix = 'HIT' if row['target'] else 'MISS'
    flags = []
    for label, value, threshold in (('HIGH_CONFIDENCE',row['frozen_model_probability'],.7),
                                   ('HIGH_EDGE',row['edge'],.1),('HIGH_EV',row['EV'],.2),
                                   ('HIGH_UNCERTAINTY',row.get('uncertainty') or 0,.08),
                                   ('LONG_ODDS',row['offered_decimal_odds'],3.)):
        if number(value) >= threshold:
            flags.append(label+'_'+suffix)
    if row['evidence_family_count'] == 1:
        flags.append('SINGLE_MODEL_EXPERIMENTAL_'+suffix)
    for profile in ('YOUTH','WOMEN','RESERVE','LOWER','UNKNOWN'):
        if profile in str(row.get('competition_profile')):
            flags.append(profile+'_PROFILE_'+suffix)
    frozen = row.get('frozen_flags',{})
    if 'lineup' in (frozen.get('missing_features') or []):
        flags.append('LINEUP_UNAVAILABLE_AT_SELECTION')
    if str(frozen.get('calibration_status') or '').startswith('UNCALIBRATED'):
        flags.append('CALIBRATION_UNAVAILABLE_AT_SELECTION')
    if frozen.get('market_consensus_relation') == 'DISAGREEMENT':
        flags.append('MODEL_MARKET_DIVERGENCE_PRESENT')
    return sorted(flags)


def combo_record(combo: dict, result: dict) -> dict:
    """Combo outcomes never become binary calibration targets."""
    from app.lab_combo.settlement import aggregate
    reproduced = aggregate(combo,result['legs'],utc(result['settled_at_utc']))
    if reproduced != result:
        raise ValueError('CONFLICTING_COMBO_SETTLEMENT')
    return {'prediction_id':combo['prediction_id'],'outcome':result['status'],
            'partial_void':result['partial_void'],'captured_combined_odds':combo['combined_odds'],
            'flat_unit_pnl':result['unit_result'],'legs':len(combo['legs']),
            'losing_legs':sum(r['outcome']=='LOST' for r in result['legs']),
            'profile_distribution':[r.get('competition_profile') for r in combo['legs']],
            'market_distribution':[r['market'] for r in combo['legs']],
            'correlation_evidence':combo.get('correlation_review'), 'settled_at':result['settled_at_utc']}


def combo_statistics(rows: list[dict]) -> dict:
    """Separate combo aggregates, explicitly without Brier/calibration observations."""
    pnl=sum(number(r['flat_unit_pnl']) for r in rows)
    return {'stream':'COMBO','resolved':len(rows),
            **{k:sum(r['outcome']==k for r in rows) for k in ('WON','LOST','VOID','PARTIAL_VOID')},
            'partial_void_count':sum(r['partial_void'] for r in rows),'flat_unit_pnl':pnl,
            'flat_unit_roi':pnl/len(rows) if rows else None,
            'average_captured_combined_odds':mean(number(r['captured_combined_odds']) for r in rows) if rows else None,
            'total_legs':sum(r['legs'] for r in rows),'losing_legs':sum(r['losing_legs'] for r in rows),
            'predictive_calibration_observations':0}
