from __future__ import annotations
from copy import deepcopy
from datetime import timedelta
import sqlite3
import pytest
from app.adaptive_lab.observations import ingest, freeze_observation, import_prematch
from app.adaptive_lab.metrics import metrics, segments, diagnostics, wilson, bucket, combo_record
from app.adaptive_lab.contracts import digest
from .conftest import frozen, observation, START


@pytest.mark.parametrize('outcome',['WON','LOST','VOID'])
@pytest.mark.parametrize('stream',['PREMATCH','LIVE'])
def test_exact_frozen_linkage_and_replay(repo,outcome,stream):
    pred,receipt,result=frozen(stream=stream,outcome=outcome)
    row=ingest(repo,pred,receipt,result,stream=stream,publication_id=pred['prediction_id'])
    assert row['frozen_model_probability']==pred['ensemble_probability']
    assert row['offered_decimal_odds']==pred['captured_odds']
    assert row==ingest(repo,pred,receipt,result,stream=stream,publication_id=pred['prediction_id'])
    assert len(repo.all('learning_observations',stream))==1
    assert row['target']==(None if outcome=='VOID' else int(outcome=='WON'))
    changed={**result,'source_fingerprint':'changed'}
    with pytest.raises(ValueError,match='CONFLICTING_SETTLEMENT'):
        ingest(repo,pred,receipt,changed,stream=stream,publication_id=pred['prediction_id'])


@pytest.mark.parametrize('mutation,reason',[
    ('fixture','AMBIGUOUS_SELECTION_IDENTITY'),('odds','CONFLICTING_SETTLEMENT'),
    ('probability','INVALID_NUMBER'),('after_kickoff','POST_KICKOFF_LEAKAGE'),
    ('no_receipt_time','MISSING_FROZEN_EVIDENCE'),('late_quote','MISSING_FROZEN_EVIDENCE'),
    ('wrong_score','CONFLICTING_SETTLEMENT')])
def test_bad_linkage_fails_closed(repo,mutation,reason):
    p,r,s=frozen()
    if mutation=='fixture': s['fixture_id']=99
    if mutation=='odds': s['captured_odds']='3.0'
    if mutation=='probability': p['ensemble_probability']='NaN'
    if mutation=='after_kickoff': r['sent_at_utc']=(START+timedelta(hours=2)).isoformat()
    if mutation=='no_receipt_time': del r['sent_at_utc']
    if mutation=='late_quote': p['provider_origin_timestamp_utc']=(START+timedelta(days=1)).isoformat()
    if mutation=='wrong_score': s['fulltime_home']=0; s['fulltime_away']=1
    with pytest.raises(ValueError,match=reason):
        ingest(repo,p,r,s,stream='PREMATCH',publication_id=p['prediction_id'])
    assert repo.all('learning_observations')==[]


def test_combo_leg_and_single_same_prediction_learn_once(repo):
    p,r,s=frozen()
    one=ingest(repo,p,r,s,stream='PREMATCH',publication_id='single')
    two=ingest(repo,p,r,s,stream='PREMATCH',publication_id='combo',source_product='COMBO_LEG')
    assert one==two and len(repo.all('learning_observations'))==1
    assert repo.all('learning_observations')[0]['source_product']=='SINGLE'


def test_unlinked_settlement_is_diagnostic(repo):
    class Ledger:
        def get(self,kind,identity): return None
        def all(self,kind): return [frozen()[2]] if kind=='single_settlement' else []
    result=import_prematch(Ledger(),repo,now=START.isoformat())
    assert result['diagnostics'][0]['status']=='UNLINKED_SETTLEMENT'


def test_metrics_exact_values_void_and_stream_isolation():
    rows=[observation(0),observation(1,outcome='LOST'),observation(2,outcome='VOID'),observation(3,stream='LIVE')]
    m=metrics(rows,'PREMATCH')
    assert (m['resolved'],m['wins'],m['losses'],m['voids'])==(2,1,1,1)
    assert m['hit_rate']==.5 and m['brier']==pytest.approx(.26)
    assert m['flat_unit_pnl']==pytest.approx(-.1) and m['flat_unit_roi']==pytest.approx(-.1/3)
    assert m['maximum_drawdown']==1 and m['maximum_losing_streak']==1
    assert m['maximum_winning_streak']==1
    assert m['log_loss']==pytest.approx(.7135581778)
    assert m['ece']==pytest.approx(.1)
    assert m['wilson_95'][0]<.5<m['wilson_95'][1]
    assert metrics(rows,'LIVE')['resolved']==1
    assert wilson(0,0) is None and metrics([],'LIVE')['brier'] is None


@pytest.mark.parametrize('name,value,expected',[('odds',2.,'[2.0,3.0)'),('probability',.6,'[0.6,0.7)'),('edge',.07,'[0.07,0.12)'),('EV',None,'MISSING')])
def test_metric_buckets(name,value,expected):
    assert bucket(value,name)==expected


def test_bounded_segments_and_symmetric_associations():
    rows=[observation(i,outcome='WON' if i%2 else 'LOST') for i in range(20)]
    assert len(segments(rows,'PREMATCH',limit=7))==7
    assert 'SINGLE_MODEL_EXPERIMENTAL_HIT' in diagnostics(rows[1])
    assert 'SINGLE_MODEL_EXPERIMENTAL_MISS' in diagnostics(rows[0])
    assert 'LINEUP_UNAVAILABLE_AT_SELECTION' in diagnostics(rows[0])


@pytest.mark.parametrize('outcomes,status',[(['WON']*3,'WON'),(['WON','LOST','VOID'],'LOST'),(['VOID']*3,'VOID'),(['WON','WON','VOID'],'PARTIAL_VOID')])
def test_combo_statistics_have_no_predictive_target(outcomes,status):
    from app.lab_combo.settlement import aggregate
    legs=[]; results=[]
    for i,outcome in enumerate(outcomes):
        p,r,s=frozen(i,outcome=outcome)
        p['odds']=p['captured_odds']; legs.append(p)
        results.append({**s,'observation_id':p['observation_id'],'outcome':outcome})
    combo={'prediction_id':'combo-1','legs':legs,'combined_odds':'7.98','correlation_review':'DISTINCT_FIXTURES'}
    result=aggregate(combo,results,START+timedelta(days=2))
    row=combo_record(combo,result)
    assert row['outcome']==status and 'target' not in row
    assert row['losing_legs']==outcomes.count('LOST')
    if status=='PARTIAL_VOID': assert float(row['flat_unit_pnl'])==pytest.approx(1.9*2.-1)


def test_missing_legacy_diagnostic_provenance_stays_explicit():
    row=observation(outcome='LOST')
    row['frozen_flags']={'calibration_status':None,'missing_features':None,'market_consensus_relation':None}
    flags=diagnostics(row)
    assert 'SINGLE_MODEL_EXPERIMENTAL_MISS' in flags
    assert 'CALIBRATION_UNAVAILABLE_AT_SELECTION' not in flags
