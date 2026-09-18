"""High-volume synthetic forward rehearsal with genuine registry/training/governance."""
from __future__ import annotations
from datetime import timedelta
from math import log
import pytest
from app.adaptive_lab.contracts import digest,utc
from app.adaptive_lab.models import candidate_specs,train
from app.adaptive_lab.observations import ingest
from app.adaptive_lab.automl import AutoLearner
from app.adaptive_lab.governance import Governance
from app.adaptive_lab.coordinator import opportunity
from .conftest import START,frozen,observation


def baseline(stream):
    rows=[observation(i,stream=stream,outcome='WON' if i%2 else 'LOST') for i in range(30)]
    spec=next(s for s in candidate_specs(stream) if s['family']=='LOGISTIC' and s['scope']=='GLOBAL')
    artifact=train(spec,rows)
    artifact['coefficients']=[0.]*len(artifact['coefficients'])
    artifact['bias']=log(.6/.4)
    artifact['artifact_fingerprint']=digest({k:v for k,v in artifact.items() if k!='artifact_fingerprint'})
    return artifact


@pytest.mark.parametrize('stream',['PREMATCH','LIVE'])
def test_full_synthetic_training_shadow_promotion_and_integrity_rollback(repo,stream):
    governance=Governance(repo)
    old=governance.bootstrap(baseline(stream),now=START-timedelta(days=10))
    other='LIVE' if stream=='PREMATCH' else 'PREMATCH'
    untouched=governance.bootstrap(baseline(other),now=START-timedelta(days=10))
    for i in range(600):
        p,r,s=frozen(i,stream=stream,outcome='WON' if i%2 else 'LOST')
        ingest(repo,p,r,s,stream=stream,publication_id=p['prediction_id'])
    now=START+timedelta(days=151)
    result=AutoLearner(repo).run(stream,now=now)
    assert result['status']=='SHADOW_RUNNING',result
    assert repo.champion(stream)==old
    assert governance.promote(result['shadow_id'],now=now)['status']=='PROMOTION_BLOCKED'
    for i in range(610,750):
        p,r,s=frozen(i,stream=stream,outcome='WON' if i%2 else 'LOST')
        governance.observe(stream,opportunity(p,stream),now=utc(p['prepared_at_utc']))
        obs=ingest(repo,p,r,s,stream=stream,publication_id=p['prediction_id'])
        governance.settle_shadow(obs)
    evidence=governance.evidence(result['shadow_id'])
    assert evidence['resolved']==140 and evidence['days']>=30 and evidence['passed'],evidence
    now=START+timedelta(days=190)
    new=governance.promote(result['shadow_id'],now=now)
    assert new['reason']=='PROMOTION' and new['previous_generation']==old['generation_id']
    assert governance.promote(result['shadow_id'],now=now)==new
    assert repo.champion(other)==untouched
    assert repo.get('model_artifacts',old['artifact_id']) is not None
    assert governance.rollback(stream,now=now)['status']=='INSUFFICIENT_ROLLBACK_EVIDENCE'
    # Simulate disk corruption, not an ordinary writable API: mutation triggers
    # remain enforced in all normal paths and are separately tested.
    repo.connection.execute('DROP TRIGGER model_artifacts_no_update')
    repo.connection.execute("UPDATE model_artifacts SET document='{}' WHERE id=?",(new['artifact_id'],))
    rolled=governance.rollback(stream,now=now+timedelta(minutes=1))
    assert rolled['reason']=='ROLLBACK' and rolled['artifact_id']==old['artifact_id']
    assert governance.rollback(stream,now=now+timedelta(minutes=2))['status']=='NO_ROLLBACK_REQUIRED'
    assert repo.champion(other)==untouched
    assert list(repo.connection.execute('PRAGMA foreign_key_check'))==[]
    assert repo.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_atomic_pointer_restored_on_injected_failure(repo,monkeypatch):
    gov=Governance(repo)
    original=repo.append
    def fail(table,*args,**kwargs):
        if table=='activation_events': raise RuntimeError('simulated crash')
        return original(table,*args,**kwargs)
    monkeypatch.setattr(repo,'append',fail)
    with pytest.raises(RuntimeError): gov.bootstrap(baseline('LIVE'),now=START)
    assert repo.champion('LIVE') is None and repo.all('champion_generations')==[]


def test_unpublished_shadow_settlement_does_not_contaminate_learning(repo):
    governance=Governance(repo)
    generation=governance.bootstrap(baseline('PREMATCH'),now=START-timedelta(days=1))
    run={'shadow_id':'test-shadow','artifact_id':generation['artifact_id'],'stream':'PREMATCH',
         'created_at':(START-timedelta(hours=1)).isoformat(),'champion_generation':generation['generation_id']}
    repo.append('shadow_runs','test-shadow','PREMATCH',run,run['created_at'],artifact_id=generation['artifact_id'])
    p,r,s=frozen()
    ids=governance.observe('PREMATCH',opportunity(p,'PREMATCH'),now=START)
    payload={'response':[{'fixture':{'id':1,'status':{'short':'FT'}},'score':{'fulltime':{'home':2,'away':0}}}]}
    result=governance.settle_shadow_result(ids[0],payload,now=START+timedelta(hours=3))
    assert result['target']==1 and repo.all('learning_observations')==[]
    assert governance.evidence('test-shadow')['resolved']==1
    assert not governance.evidence('test-shadow')['passed']
    assert repo.all('live_publications')==[]


def test_throughput_collapse_requires_sufficient_opportunity_evidence(repo):
    governance=Governance(repo)
    initial=governance.bootstrap(baseline('PREMATCH'),now=START-timedelta(days=1))
    # Seed a promoted generation in a synthetic transaction to isolate monitoring.
    with repo.transaction():
        active=governance._activate('PREMATCH',initial['artifact_id'],initial['generation_id'],'PROMOTION',{},START.isoformat())
    for i in range(200):
        row=opportunity(frozen(i)[0],'PREMATCH')
        governance.monitor_opportunity('PREMATCH',row,.1,opportunity_key=str(i),now=START+timedelta(hours=6*i))
        if i==3:
            assert governance.rollback('PREMATCH',now=START+timedelta(days=1))['status']=='INSUFFICIENT_ROLLBACK_EVIDENCE'
    result=governance.rollback('PREMATCH',now=START+timedelta(days=51))
    assert result['reason']=='ROLLBACK' and result['evidence']['reason']=='SELECTION_THROUGHPUT_DEGRADATION'
