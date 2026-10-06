"""Read-only PREMATCH evidence: fixed cutoff, no provider or service invocation."""
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.adaptive_lab.performance import band, finite, timing


def queue_and_odds(cycles):
    queue, quality = [], []
    seen, ever_stale, ever_missing = set(), set(), set()
    groups = defaultdict(Counter)
    for cycle in cycles:
        at = cycle['evaluated_at_utc']
        now = datetime.fromisoformat(at)
        states = {str(v['fixture_id']): v for v in cycle['global_fixture_states']}
        page = cycle['odds_pagination']
        reasons = page['fixture_coverage_reasons']
        seen.update(reasons)
        ever_stale.update(fid for fid,r in reasons.items() if r=='ODDS_STALE')
        ever_missing.update(fid for fid,r in reasons.items() if r=='ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD')
        ages = page.get('provider_quote_age_seconds_by_fixture', {})
        counts = Counter(reasons.values())
        stale = counts['ODDS_STALE']
        missing = sum(n for r, n in counts.items() if r in {
            'NO_CURRENT_ODDS', 'ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD', 'ODDS_EMPTY_BOOKMAKERS',
            'ODDS_EMPTY_RESPONSE', 'ODDS_FIXTURE_RECORD_NO_BOOKMAKERS'})
        q = cycle.get('final_review_queue')
        if q:
            attempts = q['attempted_fixture_ids']
            invalid = []
            for fid in attempts:
                row = states.get(str(fid), {})
                try:
                    kickoff = datetime.fromisoformat(row['kickoff_utc'])
                    from zoneinfo import ZoneInfo
                    local = kickoff.astimezone(ZoneInfo('Europe/Riga'))
                    lead = (kickoff-now).total_seconds()/60
                    if not (10 < lead <= 75 and local.date() == now.astimezone(ZoneInfo('Europe/Riga')).date()
                            and 9 <= local.hour < 23):
                        invalid.append(fid)
                except (KeyError, ValueError):
                    invalid.append(fid)
            reviews = {str(v['fixture_id']): v['final_review'] for v in cycle['tracked_final_reviews']
                       if v.get('final_review') and v['fixture_id'] in attempts}
            queue.append({'at': at, **q, 'unique_attempts': len(set(attempts)),
                'same_cycle_duplicates': len(attempts)-len(set(attempts)),
                'invalid_window_attempts': invalid, 'tracked_shortlist': cycle['tracked_final_review_shortlist'],
                'final_review_candidate_count': cycle['final_review_candidate_count'],
                'tracked_review_statuses': dict(Counter(r.get('odds_status', 'NO_ODDS_RESULT') for r in reviews.values())),
                'provider_calls': cycle['api_calls_consumed'],
                'cycle_ceiling': cycle['adaptive_quota_budget']['effective_cycle_maximum']})
        quality.append({'at': at, 'discovered': cycle['fixtures_discovered'],
            'odds_scope_fixtures': len(reasons), 'stale': stale, 'missing': missing,
            'stale_rate': stale/len(reasons) if reasons else None,
            'missing_rate': missing/len(reasons) if reasons else None,
            'reasons': dict(counts), 'provider_calls': cycle['api_calls_consumed'],
            'exact_odds_calls': cycle['exact_fixture_odds_refresh_calls'],
            'date_odds_calls': cycle['api_call_allocation'].get('/odds(date)', 0),
            'complete_date_sweeps': all(v['stable_complete_sweep'] for v in page['coverage_by_date'].values()),
            'provider_quote_age_buckets': dict(Counter(band(a, (900,1800,3600,12600,14400)) for a in ages.values()))})
        for fid, reason in reasons.items():
            state = states.get(str(fid), {})
            t = timing(state, selected_at=at)
            dimensions = {'league': str(state.get('league_id','MISSING')),
                          'competition': str(state.get('competition_profile','MISSING')),
                          'lead_time': t['prematch_lead_minutes_bucket'], 'provider':'API_FOOTBALL'}
            for dimension, value in dimensions.items():
                group = groups[(dimension, value)]
                group['fixture_cycle_observations'] += 1
                group[reason] += 1
    return {'population':'CURRENT_DATE_ODDS_SCOPE; REPEATED FIXTURES ACROSS CYCLES',
            'unique_fixture_exposure':{'seen':len(seen),'ever_stale':len(ever_stale),
                'ever_missing_complete_sweep':len(ever_missing),
                'ever_stale_rate':len(ever_stale)/len(seen) if seen else None},
            'quality_cycles': quality, 'queue_cycles': queue,
            'breakdown': [{'dimension':d,'value':v,**dict(c)} for (d,v),c in sorted(groups.items())],
            'limitations': ['Broad-sweep statuses precede exact-review overrides; do not sum different report counters.',
                'No bookmaker/market denominator exists for fixtures absent from the provider response.',
                'No saturated pending queue or least-recent tie is inferred from a zero final-review-candidate counter.']}


def disagreements(candidates):
    reasons = Counter()
    groups = defaultdict(list)
    zero = []
    for row in candidates:
        reasons.update(set(row.get('rejection_reasons', [])) | set(row.get('soft_findings', [])) |
                       set(row.get('hard_failures', [])) | set(row.get('readiness_reasons', [])))
        dims = {'market':row.get('market','MISSING'), 'league':str(row.get('league_id','MISSING')),
                'probability_range':band(row.get('ensemble_probability'), (.4,.5,.6,.7,.8,.9)),
                'odds_range':band(row.get('captured_odds') or row.get('odds'), (1.3,1.5,1.7,2,3,5))}
        t = timing(row, selected_at=row.get('evaluated_at_utc'))
        dims.update(lead_time=t['prematch_lead_minutes_bucket'], freshness=t['odds_age_seconds_bucket'])
        for key,value in dims.items(): groups[(key,value)].append(row)
        trace = row.get('invalid_model_probability_evidence')
        if trace:
            zero.append({'fixture_id':row['fixture_id'],'market':row['market'],
                'evaluated_at':row.get('evaluated_at_utc'), 'rejection':row.get('rejection_reasons'),
                'trace':trace})
    tracked = ('SEVERE_MODEL_MARKET_CONTRADICTION','MATERIAL_SIGNAL_DISAGREEMENT',
               'ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE')
    output = []
    for (dim,value), rows in sorted(groups.items()):
        rc = Counter(reason for row in rows for reason in set(row.get('rejection_reasons', [])) |
                     set(row.get('soft_findings', [])) | set(row.get('hard_failures', [])) |
                     set(row.get('readiness_reasons', [])))
        divergences=[]
        for row in rows:
            p,q=finite(row.get('ensemble_probability')),finite(row.get('market_fair_probability'))
            if p is not None and q is not None: divergences.append(float(abs(p-q)))
        output.append({'dimension':dim,'value':value,'candidate_rows':len(rows),
            'independent_fixtures':len({row['fixture_id'] for row in rows}),
            'reasons':{r:rc[r] for r in tracked}, 'no_pick_reasons':dict(rc),
            'mean_absolute_model_market_divergence':sum(divergences)/len(divergences) if divergences else None})
    return {'candidate_rows':len(candidates),'independent_fixtures':len({r['fixture_id'] for r in candidates}),
            'reason_counts':dict(reasons),'segments':output,'invalid_probability_traces':zero,
            'selection_effect':'NONE','population':'REPEATED EVALUATED MARKET CANDIDATES, NOT INDEPENDENT BETS'}


def run(path, *, cutoff, output):
    db=sqlite3.connect(Path(path).absolute().as_uri()+'?mode=ro',uri=True,timeout=.2)
    db.execute('PRAGMA query_only=ON')
    deadline=time.monotonic()+50
    db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
    try:
        raw=db.execute("SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='rehearsal' AND created_at_utc<=? ORDER BY rowid DESC LIMIT 12",(cutoff,)).fetchall()
        cycles=[json.loads(r[0]) for r in raw]
        ids=list(dict.fromkeys(i for c in cycles for i in c['candidate_ids']))
        if len(ids)>50000: raise ValueError('CANDIDATE_AUDIT_CAP')
        candidates=[]
        for identity in ids:
            raw,created=db.execute("SELECT document_json,created_at_utc FROM lab_v2_shadow_evidence WHERE kind='candidate' AND identity=?",(identity,)).fetchone()
            row=json.loads(raw)
            # Candidate stores cycle start externally and its own quote retrieval
            # internally. Use the later frozen time, never today's age of old odds.
            row['evaluated_at_utc']=max(created,row.get('goalvision_retrieved_at_utc') or created)
            candidates.append(row)
        fresh=[c for c in cycles if c.get('final_review_queue')]
        result=queue_and_odds(fresh)
        result['as_of']=cutoff
        result['candidate_diagnostics']=disagreements(candidates)
        result['candidate_diagnostics']['timing_basis']='MAX_PERSISTED_CYCLE_START_AND_OWN_QUOTE_RETRIEVAL; APPROXIMATE_EVALUATION_TIME'
        result['candidate_cycles']=[c['evaluated_at_utc'] for c in cycles]
        refresh=[]
        for c in fresh:
            prefix=c['evaluated_at_utc']+':'
            refresh.extend(json.loads(r[0]) for r in db.execute("SELECT document_json FROM lab_v2_shadow_evidence WHERE kind='tracked_odds_refresh' AND identity>=? AND identity<?",(prefix,prefix+'~')))
        result['tracked_refresh']={'fixture_attempts':len(refresh),'statuses':dict(Counter(r['status'] for r in refresh)),
             'available_rate':sum(r['status']=='AVAILABLE' for r in refresh)/len(refresh) if refresh else None,
             'scope':'TRACKED_EXACT_ODDS_ONLY; EXCLUDES FINAL REVIEW AND PRIORITY EXACT REQUESTS'}
    finally: db.close()
    Path(output).write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database',required=True);p.add_argument('--as-of',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=run(a.database,cutoff=a.as_of,output=a.output)
    print(json.dumps({'quality_cycles':r['quality_cycles'],'tracked_refresh':r['tracked_refresh'],
                      'candidate_rows':r['candidate_diagnostics']['candidate_rows']}))
