from __future__ import annotations
from copy import deepcopy
from datetime import timedelta
import json
import pytest
from app.adaptive_lab.policy import POLICY, eligibility
from app.adaptive_lab.datasets import chronological_dataset
from app.adaptive_lab.models import candidate_specs,train,predict,validate_spec,validate_artifact
from app.adaptive_lab.comparison import compare
from app.adaptive_lab.automl import AutoLearner
from .conftest import observation,START


@pytest.mark.parametrize('n,status,automatic',[(6,'INSUFFICIENT_SAMPLE',False),(100,'OBSERVE_ONLY',False),(200,'RESEARCH_ELIGIBLE',False),(500,'AUTO_LEARNING_ELIGIBLE',True)])
def test_eligibility_real_thresholds(n,status,automatic):
    rows=[observation(i,outcome='WON' if i%2 else 'LOST') for i in range(n)]
    e=eligibility(rows,'PREMATCH',START+timedelta(days=300))
    assert e['status']==status and e['automatic_eligible']==automatic
    assert eligibility(rows,'LIVE',START+timedelta(days=300))['resolved']==0
    assert eligibility(rows,'PREMATCH',START+timedelta(days=300),previous={'created_at':(START+timedelta(days=299)).isoformat()})['reason']=='NOT_ENOUGH_NEW_DATA' if n>=200 else True


def test_strict_chronology_fixture_grouping_and_consumed_holdout():
    rows=[observation(i,outcome='WON' if i%2 else 'LOST') for i in range(600)]
    dataset=chronological_dataset(rows,'PREMATCH',now=START+timedelta(days=300))
    parts=dataset['partitions']
    assert len(parts['SEALED_HOLDOUT'])==120
    for older,newer in [('TRAIN','VALIDATION'),('VALIDATION','SEALED_HOLDOUT')]:
        assert max(r['settled_at'] for r in parts[older])<min(r['prediction_created_at'] for r in parts[newer])
    consumed={r['observation_id'] for r in parts['SEALED_HOLDOUT']}
    second=chronological_dataset(rows,'PREMATCH',now=START+timedelta(days=300),consumed_holdout=consumed)
    assert second['partitions']['SEALED_HOLDOUT']==[]
    assert not set(r['fixture_id'] for r in parts['TRAIN']) & set(r['fixture_id'] for r in parts['SEALED_HOLDOUT'])


@pytest.mark.parametrize('family',['LOGISTIC','REGULARIZED_LOGISTIC','STUMP_ENSEMBLE','CALIBRATED_ENSEMBLE'])
def test_deterministic_registry_training_and_safe_serialization(family):
    spec=next(s for s in candidate_specs('PREMATCH') if s['family']==family and 'recent_form' in s['features'] and s['scope']=='GLOBAL')
    rows=[observation(i,outcome='WON' if i%2 else 'LOST') for i in range(320)]
    artifact=train(spec,rows)
    assert artifact==train(spec,rows)
    assert artifact==json.loads(json.dumps(artifact))
    assert 0<predict(artifact,rows[0])<predict(artifact,rows[1])<1
    corrupted=deepcopy(artifact); corrupted['bias']+=1
    with pytest.raises(ValueError,match='INTEGRITY'): validate_artifact(corrupted)
    with pytest.raises(ValueError,match='STREAM'): predict(artifact,observation(stream='LIVE'))


@pytest.mark.parametrize('change',[{'family':'EXEC_PYTHON'},{'iterations':100000},{'features':['future_score']},{'l2':100.},{'seed':19},{'scope':'OFFICIAL'}])
def test_reject_arbitrary_code_and_unbounded_search(change):
    spec={**candidate_specs('PREMATCH')[0],**change}
    with pytest.raises(ValueError): validate_spec(spec)


def test_bounded_candidate_feature_selection():
    for stream in ('PREMATCH','LIVE'):
        specs=candidate_specs(stream)
        assert len(specs)<=POLICY.candidate_limit and specs==candidate_specs(stream)
        assert len({tuple(s['features']) for s in specs})>1
        assert any(s['scope']=='PROFILE_MARKET' for s in specs)


def test_mandatory_rejection_despite_betting_result():
    rows=[observation(i,outcome='WON' if i%2 else 'LOST') for i in range(120)]
    result=compare(rows,[.6]*120,[.99 if i%2==0 else .01 for i in range(120)],minimum=100)
    assert not result['passed'] and 'brier_not_materially_worse' in result['blocked_by']
    collapsed=compare(rows,[.6]*120,[.01]*120,minimum=100)
    assert 'no_selection_collapse' in collapsed['blocked_by']


def test_tiny_sample_never_trains(repo):
    assert AutoLearner(repo).run('PREMATCH',now=START)['status']=='INSUFFICIENT_SAMPLE'
    assert repo.all('learning_cycles')==[]


def test_specialization_needs_real_diversity_and_support():
    spec=next(s for s in candidate_specs('PREMATCH') if s['scope']=='PROFILE_MARKET')
    rows=[observation(i,outcome='WON' if i%2 else 'LOST') for i in range(320)]
    for i,row in enumerate(rows):
        row['competition_profile']='SENIOR_MEN'
        row['offered_decimal_odds']=str(1.5+(i%4)*.6)
    artifact=train(spec,rows)
    assert artifact['specialists']
    assert not train(spec,rows[:100])['specialists']


def test_calibration_minimum_and_artifact_shape():
    spec=next(s for s in candidate_specs('PREMATCH') if s['family']=='CALIBRATED_ENSEMBLE')
    with pytest.raises(ValueError,match='CALIBRATION_SAMPLE'):
        train(spec,[observation(i,outcome='WON' if i%2 else 'LOST') for i in range(200)])
    spec=next(s for s in candidate_specs('PREMATCH') if s['family']=='LOGISTIC')
    artifact=train(spec,[observation(i,outcome='WON' if i%2 else 'LOST') for i in range(30)])
    artifact['preprocessing'][0]['scale']=0
    from app.adaptive_lab.contracts import digest
    artifact['artifact_fingerprint']=digest({k:v for k,v in artifact.items() if k!='artifact_fingerprint'})
    with pytest.raises(ValueError,match='SCALE'): validate_artifact(artifact)


def test_baseline_input_stays_stable_after_model_replacement():
    from app.adaptive_lab.features import features,captured_features
    row=observation()
    row['frozen_features']={'baseline_probability':.6}
    row['frozen_model_probability']='0.8'
    assert features(row)['prior_probability']==.6
    assert captured_features({'baseline_probability':'0.6'})['baseline_probability']==.6
