"""Known proper scores, chronology, independent sampling and frozen weight gates."""
from copy import deepcopy
from datetime import timedelta
import math
import pytest
from app.dixon_coles_forward import incremental as inc
from app.dixon_coles_forward.contracts import load_plan
from app.dixon_coles_research.contracts import seal,utc

PLAN=inc.load_plan();FORWARD=load_plan()


def rows(n=300,*,phase='CALIBRATION_FIT',good_dc=True):
    start=utc('2026-10-05T01:00:00+00:00') if phase=='CALIBRATION_FIT' else utc('2026-10-11T01:00:00+00:00')
    data=[]
    for i in range(n):
        clock=start+timedelta(days=i%7 if phase!='CALIBRATION_FIT' else 0)
        data.append({'fixture_id':i+(10000 if phase!='CALIBRATION_FIT' else 1),
            'forecast_fingerprint':f'forecast-{phase}-{i}','result_fingerprint':f'result-{i}',
            'forecast_at':clock.isoformat(),'kickoff_utc':(clock+timedelta(hours=1)).isoformat(),
            'settled_at':(clock+timedelta(hours=3)).isoformat(),'partition':phase,'y':0,
            'p':{'MARKET':(.5,.25,.25),'CHAMPION':(.5,.25,.25),
                 'DIXON_COLES':(.8,.1,.1) if good_dc else (.2,.4,.4)}})
    return data


def test_multiclass_scores_and_order_are_exact():
    out=inc.scores([((.5,.25,.25),0)])
    assert out['rps']==pytest.approx((.5**2+.25**2)/2)
    assert out['brier']==pytest.approx(.375)
    assert out['log_loss']==pytest.approx(math.log(2))
    assert out['draw_calibration']['brier']==pytest.approx(.0625)
    assert out['fixtures']==1


@pytest.mark.parametrize('p',[(0,.5,.5),(.5,.5,.5),(.5,float('nan'),.5),(.5,.5)])
def test_bad_probability_is_not_clamped_or_silently_renormalized(p):
    with pytest.raises(ValueError):inc.vector(p)


def test_log_pool_endpoints_and_geometric_mean():
    a=(.5,.25,.25);b=(.2,.4,.4)
    assert inc.pool(a,b,0)==pytest.approx(a)
    assert inc.pool(a,b,1)==pytest.approx(b)
    assert inc.pool(a,b,.5)==pytest.approx((1/3,1/3,1/3))


def test_zero_weight_when_dc_adds_no_information_and_ties_prefer_zero():
    data=rows(good_dc=False)
    fit=inc.fit_pool(data,base='MARKET',plan=PLAN,forward=FORWARD,now=utc('2026-10-10T01:00:00+00:00'))
    assert fit['dc_weight']==0
    for r in data:r['p']['DIXON_COLES']=r['p']['MARKET']
    assert inc.fit_pool(data,base='MARKET',plan=PLAN,forward=FORWARD,now=utc('2026-10-10T01:00:00+00:00'))['dc_weight']==0


@pytest.mark.parametrize('bad',['open','short','duplicate','validation','holdout','predeclaration'])
def test_fit_readiness_and_leakage_fail_closed(bad):
    data=rows();clock=utc('2026-10-10T01:00:00+00:00')
    if bad=='open':clock=utc('2026-10-06T00:00:00+00:00')
    if bad=='short':data.pop()
    if bad=='duplicate':data[-1]['fixture_id']=data[0]['fixture_id']
    if bad in ('validation','holdout'):data[-1]['partition']='VALIDATION_EVALUATION' if bad=='validation' else 'SEALED_HOLDOUT'
    if bad=='predeclaration':data[-1]['forecast_at']='2026-10-03T18:00:00+00:00'
    with pytest.raises(ValueError):inc.fit_pool(data,base='MARKET',plan=PLAN,forward=FORWARD,now=clock)


def test_positive_incremental_value_can_only_advance_research_planning():
    data=rows();fit=inc.fit_pool(data,base='MARKET',plan=PLAN,forward=FORWARD,now=utc('2026-10-10T01:00:00+00:00'))
    result=inc.validate_pool(data,rows(140,phase='VALIDATION_EVALUATION'),fit,plan=PLAN,forward=FORWARD,now=utc('2026-10-18T01:00:00+00:00'))
    assert result['dc_weight']==1
    assert result['verdict']=='CONTINUE_HOLDOUT_PLANNING_ONLY'
    assert result['promotion_eligibility'].startswith('BLOCKED') and not result['holdout_read']
    assert not result['automatic_promotion']
    assert result==inc.validate_pool(data,rows(140,phase='VALIDATION_EVALUATION'),fit,plan=PLAN,forward=FORWARD,now=utc('2026-10-18T01:00:00+00:00'))


def test_resealed_weight_tamper_and_validation_overlap_are_rejected():
    data=rows();fit=inc.fit_pool(data,base='MARKET',plan=PLAN,forward=FORWARD,now=utc('2026-10-10T01:00:00+00:00'))
    forged={k:v for k,v in fit.items() if k!='fingerprint'};forged['dc_weight']=.3
    with pytest.raises(ValueError,match='REPRODUCTION'):
        inc.validate_pool(data,rows(140,phase='VALIDATION_EVALUATION'),seal(forged),plan=PLAN,forward=FORWARD,now=utc('2026-10-18T01:00:00+00:00'))
    val=rows(140,phase='VALIDATION_EVALUATION');val[0]['fixture_id']=data[0]['fixture_id']
    with pytest.raises(ValueError,match='DEPENDENCE'):
        inc.validate_pool(data,val,fit,plan=PLAN,forward=FORWARD,now=utc('2026-10-18T01:00:00+00:00'))


def test_report_cannot_fit_or_consume_holdout(monkeypatch):
    monkeypatch.setattr(inc,'fit_pool',lambda *a,**k:pytest.fail('report fitted weights'))
    result=inc.report([],plan=PLAN,forward=FORWARD,now=utc('2026-10-04T12:00:00+00:00'))
    assert result['optimal_forward_dc_weight'] is None and result['comparisons']['MARKET']['baseline']['fixtures']==0
    assert not result['holdout_read'] and not result['fit_invoked']
    data=rows(1);data[0]['partition']='SEALED_HOLDOUT'
    with pytest.raises(ValueError,match='HOLDOUT'):inc.report(data,plan=PLAN,forward=FORWARD,now=utc('2026-10-27T00:00:00+00:00'))


def test_real_forward_schema_is_filtered_before_label_read():
    # Genuine frozen forward record shape: input_as_of, not an invented adapter key.
    record={'fixture_id':999999,'forecast_at':'2026-10-04T09:00:00+00:00',
        'input_as_of':'2026-10-04T08:59:00+00:00','kickoff_utc':'2026-10-04T13:00:00+00:00',
        'comparisons':{k:{} for k in inc.ORDER}}
    selected,counts=inc.eligible_forecasts([seal(record)],plan=PLAN,forward=FORWARD,now=utc('2026-10-04T12:00:00+00:00'))
    assert selected==[] and counts=={'predeclaration':1}
    record.update(forecast_at='2026-10-19T12:00:00+00:00',input_as_of='2026-10-19T12:00:00+00:00',kickoff_utc='2026-10-19T13:00:00+00:00')
    selected,counts=inc.eligible_forecasts([seal(record)],plan=PLAN,forward=FORWARD,now=utc('2026-10-20T12:00:00+00:00'))
    assert selected==[] and counts=={'sealed_holdout':1}


def test_adapter_reproduces_real_forecast_and_never_fabricates_champion(monkeypatch):
    from tests import test_dixon_coles_research as fixture
    from app.dixon_coles_forward import model,service
    clock=utc(PLAN['declared_at'])+timedelta(minutes=1)
    monkeypatch.setattr(fixture,'START',clock)
    source=fixture.item();artifact=model.fit(source['training_results'],league_id=71,as_of=clock,plan=FORWARD)
    frozen=service.forecast(source,artifact=artifact,plan=FORWARD,now=clock)
    actual,diagnostic=inc.prepare([frozen],{artifact['fingerprint']:artifact},[fixture.result()],
        plan=PLAN,forward=FORWARD,now=clock+timedelta(days=1))
    assert len(actual)==1 and set(actual[0]['p'])=={'MARKET','DIXON_COLES'}
    assert actual[0]['partition']=='CALIBRATION_FIT'
    assert diagnostic['filter_counts']['champion_identity_missing']==1
    forged={k:deepcopy(v) for k,v in frozen.items() if k!='fingerprint'}
    forged['comparisons']['HOME_WIN']['DIXON_COLES']=.99
    with pytest.raises(ValueError,match='REPRODUCTION'):
        inc.prepare([seal(forged)],{artifact['fingerprint']:artifact},[fixture.result()],
            plan=PLAN,forward=FORWARD,now=clock+timedelta(days=1))
