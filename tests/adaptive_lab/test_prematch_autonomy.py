"""PREMATCH-only production integration, baseline equivalence and automatic ticks."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from decimal import Decimal
import asyncio
import pytest
from app.adaptive_lab.baseline import artifact,context,infer
from app.adaptive_lab.governance import Governance
from app.adaptive_lab.coordinator import LearningCoordinator,opportunity
from app.adaptive_lab.models import predict
from app.adaptive_lab.policy import eligibility
from app.adaptive_lab.observer import observe
from app.adaptive_lab.automl import AutoLearner
from app.lab_v2_shadow.ensemble import EnsembleSignal
from app.lab_v2_shadow.global_evaluation import evaluate_profile
from app.lab_v2_shadow.profiles import policy_for,CompetitionProfile
from app.adaptive_lab.contracts import MARKETS,utc
from .conftest import START,frozen,observation


def signals(market,p='0.6'):
    return [EnsembleSignal('CURRENT_MARKET_CONSENSUS',market,Decimal('.45'),None,Decimal('.9'),'AVAILABLE','test-market','CURRENT_MARKET_CONSENSUS'),
            EnsembleSignal('CURRENT_MATCH_INTELLIGENCE',market,Decimal(p),None,Decimal('.8'),'AVAILABLE','test-history','RESULT_HISTORY_MODEL_CONTEXT')]


@pytest.mark.parametrize('profile',[p.value for p in CompetitionProfile])
@pytest.mark.parametrize('market',sorted(MARKETS))
def test_baseline_exact_equivalence_and_registry_lane(repo,profile,market):
    raw=signals(market);odds=Decimal('2');missing=('lineup','advanced_stats')
    old,evidence=evaluate_profile(market,odds,raw,policy_for(profile),missing)
    assert infer(context(raw,profile,missing,market,odds))==old.ensemble_probability
    gen=Governance(repo).bootstrap(artifact(),now=START)
    adapted,provenance=LearningCoordinator(repo).prematch_signals(raw,old,evidence,
        {'fixture_id':1,'competition_profile':profile},market,odds,now=START,quote_fingerprint='q',missing=missing)
    new,new_evidence=evaluate_profile(market,odds,adapted,policy_for(profile),missing)
    assert new==old and new_evidence==evidence
    assert provenance['model_generation']==gen['generation_id']
    assert repo.champion('LIVE') is None


def test_baseline_context_required_and_artifact_tamper(repo):
    from app.adaptive_lab.models import validate_artifact
    a=artifact();a['accepted_commit']='unreviewed'
    with pytest.raises(ValueError):validate_artifact(a)
    with pytest.raises(ValueError,match='FROZEN_CONTEXT'):
        predict(artifact(),observation())
    with pytest.raises(ValueError,match='STREAM'):
        predict(artifact(),observation(stream='LIVE'))


def test_existing_prematch_bootstrap_survives_light_safety_integration(repo) -> None:
    """Keep the pre-integration artifact compatible through publication resolution."""
    from app.adaptive_lab.contracts import digest

    accepted = {
        'family': 'EXISTING_PREMATCH_BASELINE_V1', 'stream': 'PREMATCH',
        'accepted_commit': '0c4f316248e55f504b780cdef4e25165b800a779',
        'ensemble_policy': 'LAB_V2_BROAD_COVERAGE_ENSEMBLE_V4',
        'profile_policy': 'LAB_COMPETITION_POLICY_V2',
        'probability_contract': 'FINITE_OPEN_UNIT_INTERVAL',
        'rollback_identity': 'EXISTING_PREMATCH_BASELINE_V1',
        'registry_version': 'LAB_MODEL_REGISTRY_V1',
    }
    accepted['artifact_fingerprint'] = digest(accepted)
    generation = Governance(repo).bootstrap(accepted, now=START)
    raw = signals('HOME_WIN')
    policy = policy_for('SENIOR_MEN_PRO')
    baseline, evidence = evaluate_profile('HOME_WIN', Decimal('2'), raw, policy, ())
    adapted, provenance = LearningCoordinator(repo).prematch_signals(
        raw, baseline, evidence, {'fixture_id': 1, 'competition_profile': policy.profile},
        'HOME_WIN', Decimal('2'), now=START, quote_fingerprint='existing-baseline',
    )
    assert evaluate_profile('HOME_WIN', Decimal('2'), adapted, policy, ()) == (baseline, evidence)
    assert provenance['model_generation'] == generation['generation_id']
    assert repo.champion('PREMATCH') == generation
    assert repo.get('model_artifacts', generation['artifact_id']) == accepted


@pytest.mark.parametrize('n,stage',[(0,'LEARNING_AND_OBSERVING'),(99,'LEARNING_AND_OBSERVING'),
  (100,'EARLY_RESEARCH'),(199,'EARLY_RESEARCH'),(200,'CHALLENGER_RESEARCH'),
  (499,'CHALLENGER_RESEARCH'),(500,'FULL_AUTO_LEARNING_ELIGIBLE')])
def test_stages_do_not_lower_promotion_gate(n,stage):
    rows=[observation(i) for i in range(n)]
    e=eligibility(rows,'PREMATCH',START+timedelta(days=300))
    assert e['stage']==stage and e['automatic_eligible']==(n>=500)
    assert e['research_due']==(n>=100)


class Ledger:
    def __init__(self):self.records={}
    def all(self,kind):return [v for (k,_),v in self.records.items() if k==kind]
    def get(self,kind,identity):return self.records.get((kind,identity))
    def add(self,index):
        p,r,s=frozen(index,outcome='WON' if index%2 else 'LOST')
        p['competition_profile']=('SENIOR_MEN_PRO','SENIOR_WOMEN_PRO','YOUTH_U19_U20')[index%3]
        p['adaptive_features']['baseline_context']=context(signals(p['market']),p['competition_profile'],[],p['market'],Decimal(p['captured_odds']))
        self.records['single_prediction',p['prediction_id']]=p
        self.records['receipt','single_prediction:'+p['prediction_id']]=r
        self.records['single_settlement',p['prediction_id']]=s
        return p,r,s


def test_scheduled_ticks_complete_prematch_autonomy_without_live(repo):
    ledger=Ledger();old=Governance(repo).bootstrap(artifact(),now=START-timedelta(days=1))
    previous=0
    for count,day in ((99,26),(100,27),(200,52),(600,152)):
        for i in range(previous,count):ledger.add(i)
        now=START+timedelta(days=day)
        result=observe(repo,ledger,now=now)
        assert not result['heavy_training'] and result['api_calls']==result['telegram_sends']==0
        research=AutoLearner(repo).run('PREMATCH',now=now)
        if count==99:assert not repo.all('model_specs') or len(repo.all('model_specs'))==1
        if count==100:assert research['status']=='EARLY_RESEARCH_COMPLETE'
        if count==200:assert not repo.all('shadow_runs')
        previous=count
    assert research['status']=='SHADOW_RUNNING',research
    assert AutoLearner(repo).run('PREMATCH',now=now+timedelta(days=8))['reason']=='NOT_ENOUGH_NEW_DATA'
    coordinator=LearningCoordinator(repo)
    for i in range(610,750):
        p,r,s=ledger.add(i)
        coordinator.shadow([p],stream='PREMATCH',now=utc(p['prepared_at_utc']))
    final=observe(repo,ledger,now=START+timedelta(days=190))
    current=repo.champion('PREMATCH')
    assert current['reason']=='PROMOTION' and current['previous_generation']==old['generation_id'],final
    assert repo.champion('LIVE') is None and repo.all('learning_observations','LIVE')==[]
    repo.connection.execute('DROP TRIGGER model_artifacts_no_update')
    repo.connection.execute("UPDATE model_artifacts SET document='{}' WHERE id=?",(current['artifact_id'],))
    observe(repo,ledger,now=START+timedelta(days=191))
    assert repo.champion('PREMATCH')['reason']=='ROLLBACK'
    assert repo.champion('PREMATCH')['artifact_id']==old['artifact_id']
    assert repo.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert list(repo.connection.execute('PRAGMA foreign_key_check'))==[]


def test_observer_cannot_train_or_fetch(repo,monkeypatch):
    monkeypatch.setattr(AutoLearner,'run',lambda *a,**k:pytest.fail('observer trained'))
    result=observe(repo,Ledger(),now=START)
    assert result['LIVE']=='DISABLED' and result['api_calls']==0


def test_math_full_market_contract():
    from app.lab_v2_shadow.runner import _poisson_markets
    for h,a in ((Decimal('.15'),Decimal('6')),(Decimal('2'),Decimal('1')), (Decimal('1'),Decimal('2'))):
        ps=_poisson_markets(h,a)
        assert abs(sum(ps[k] for k in ('HOME_WIN','DRAW','AWAY_WIN'))-1)<Decimal('1e-25')
        assert ps['BTTS_YES']+ps['BTTS_NO']==1
        assert ps['OVER_1_5']>=ps['OVER_2_5']>=ps['OVER_3_5']
        for n in (1,2,3):assert ps[f'OVER_{n}_5']+ps[f'UNDER_{n}_5']==1
        for market,p in ps.items():
            odds=Decimal('2.1');implied=1/odds;edge=p-implied;ev=p*odds-1
            assert abs(ev-edge*odds)<Decimal('1e-25')
            assert abs((1/p)*p-1)<Decimal('1e-25')


def test_regulation_scores_and_conflicting_history_are_quarantined():
    from app.lab_v2_shadow.pi_ratings import parse_api_fixture_results
    row={'fixture':{'id':8,'date':START.isoformat(),'status':{'short':'AET'}},
         'league':{'id':39,'season':2025},'teams':{'home':{'id':1},'away':{'id':2}},
         'goals':{'home':3,'away':2},'score':{'fulltime':{'home':1,'away':1}}}
    matches=parse_api_fixture_results(({'response':[row]},))
    assert [(m.home_goals,m.away_goals) for m in matches]==[(1,1)]
    missing=deepcopy(row);missing.pop('score')
    assert parse_api_fixture_results(({'response':[missing]},))==()
    conflict=deepcopy(row);conflict['score']['fulltime']['home']=2
    assert parse_api_fixture_results(({'response':[row,conflict]},))==()
    malformed=deepcopy(row);malformed['score']['fulltime']['home']=True
    assert parse_api_fixture_results(({'response':[malformed]},))==()


def test_shared_status_preflight_is_reserved_before_http(repo):
    import httpx
    from app.football.client import FootballClient
    from app.adaptive_lab.quota import SharedQuota
    async def run():
        client=FootballClient(api_key='synthetic',request_limit=1)
        await client._client.aclose()
        def response(request):
            assert len(repo.all('quota_claims'))==1
            assert repo.all('quota_claims')[0]['category']=='STATUS'
            return httpx.Response(200,json={'response':[]},headers={
              'x-ratelimit-requests-limit':'7500','x-ratelimit-requests-remaining':'7400',
              'x-ratelimit-limit':'300','x-ratelimit-remaining':'299'})
        client._client=httpx.AsyncClient(base_url=client.BASE_URL,transport=httpx.MockTransport(response))
        quota=SharedQuota(repo);quota.bind(client,lambda:START,allow_status_preflight=True)
        try:await quota.call('STATUS',client.account_status)
        finally:await client.close()
    asyncio.run(run())


def test_registry_matches_golden_outputs_from_accepted_production_commit(repo):
    import json
    from pathlib import Path
    fixture=json.loads((Path(__file__).parents[1]/'fixtures/adaptive_lab/accepted_baseline.json').read_text())
    assert fixture['source_commit']=='0c4f316248e55f504b780cdef4e25165b800a779'
    Governance(repo).bootstrap(artifact(),now=START)
    for expected in fixture['cases']:
        raw=signals(expected['market']);profile=expected['profile'];market=expected['market']
        old,e=evaluate_profile(market,Decimal(2),raw,policy_for(profile),('lineup','advanced_stats'))
        adapted,_=LearningCoordinator(repo).prematch_signals(raw,old,e,{'fixture_id':1,'competition_profile':profile},market,Decimal(2),now=START,quote_fingerprint='q',missing=('lineup','advanced_stats'))
        actual,a=evaluate_profile(market,Decimal(2),adapted,policy_for(profile),('lineup','advanced_stats'))
        assert str(actual.ensemble_probability)==expected['probability']
        assert str(actual.edge)==expected['edge'] and actual.decision==expected['decision']
        assert a['candidate_lane']==expected['lane'] and a['uncertainty_penalty']==expected['uncertainty']


def test_training_does_not_hold_database_write_lock(repo,monkeypatch):
    import app.adaptive_lab.automl as module
    from app.adaptive_lab.repository import AuditRepository
    ledger=Ledger()
    for i in range(100):ledger.add(i)
    observe(repo,ledger,now=START+timedelta(days=27))
    original=module.train;calls=[]
    def checked(spec,rows):
        assert not repo.connection.in_transaction
        path=repo.connection.execute('PRAGMA database_list').fetchone()[2]
        other=AuditRepository(path)
        try:
            other.append('cycle_health','during-training','PREMATCH',{'safe':True},START.isoformat())
        finally:other.close()
        calls.append(True)
        return original(spec,rows)
    monkeypatch.setattr(module,'train',checked)
    result=AutoLearner(repo).run('PREMATCH',now=START+timedelta(days=27))
    assert result['status']=='EARLY_RESEARCH_COMPLETE' and calls
    assert list(repo.connection.execute('PRAGMA foreign_key_check'))==[]
    assert repo.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_cycle_health_does_not_call_quota_starvation_healthy():
    from app.adaptive_lab.health import cycle_health
    r={'adaptive_quota_budget':{'status':'REDUCED_TO_PRESERVE_QUOTA'},
       'global_state_counts':{'TRACKING':20},'ready_candidate_count':0,
       'candidate_markets':[{'candidate_lane':'EXPERIMENTAL'}],
       'rejection_reasons':{'NO_INDEPENDENT_NON_MARKET_EVIDENCE':1}}
    h=cycle_health(r,started=START,completed=START)
    assert h['result']=='DEGRADED' and h['tracking']==20 and h['published']==0
    assert h['lanes']=={'EXPERIMENTAL':1} and h['LIVE']=='DISABLED'
    r['terminal_error']='ValueError'
    assert cycle_health(r,started=START,completed=START)['result']=='FAILED'


def test_schema_upgrade_replay_and_new_append_guards(tmp_path):
    import sqlite3
    from app.adaptive_lab.repository import AuditRepository
    path=tmp_path/'v2.db';r=AuditRepository(path)
    r.append('cycle_health','retained','PREMATCH',{'source':'synthetic'},START.isoformat())
    r.connection.execute('DELETE FROM adaptive_schema WHERE version=3')
    r.connection.execute('INSERT OR IGNORE INTO adaptive_schema VALUES(2)')
    r.close()
    r=AuditRepository(path)
    try:
        r.migrate();r.migrate()
        assert r.get('cycle_health','retained')=={'source':'synthetic'}
        assert not r.append('cycle_health','retained','PREMATCH',{'source':'synthetic'},START.isoformat())
        for statement in ('UPDATE cycle_health SET stream="LIVE"','DELETE FROM cycle_health'):
            with pytest.raises(sqlite3.IntegrityError):r.connection.execute(statement)
        assert list(r.connection.execute('PRAGMA foreign_key_check'))==[]
        assert r.connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    finally:r.close()


@pytest.mark.parametrize('near',[False,True])
def test_valid_history_cache_survives_budget_without_skipping_final_refresh(tmp_path,near):
    from types import SimpleNamespace
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from app.lab_v2_shadow.runner import LabV2ShadowRunner
    r=ShadowEvidenceRepository(tmp_path/'shadow.db')
    try:
        r.append_cache('/fixtures(results)',{'league':39,'season':2025,'status':'FT','last':99},
                       {'response':[]},retrieved_at=START,ttl=timedelta(hours=6))
        runner=LabV2ShadowRunner(SimpleNamespace(request_count=0),r,capability_cache_path=tmp_path/'caps.json')
        runner._remaining=lambda:0
        fixture={'fixture_id':77,'league_id':39,'season':2025,'home_team_id':1,'away_team_id':2,
                 'kickoff_utc':START+timedelta(minutes=30 if near else 180),
                 'competition_profile':'SENIOR_MEN_PRO'}
        histories,_,skipped=asyncio.run(runner._histories([fixture],START,reserve_calls=12))
        assert skipped==int(near)
        assert (39 in histories)==(not near)
        assert sum(c['actual_calls'] for c in runner.calls)==0
    finally:r.close()


def test_reviewed_central_american_club_cup_is_not_domestic():
    from app.lab_v2_shadow.competition_registry import reviewed_competition
    row=reviewed_competition('API_FOOTBALL',1028,'World')
    assert row.profile=='INTERNATIONAL_CLUB' and row.gender=='men'
    assert reviewed_competition('API_FOOTBALL',1028,'England') is None


@pytest.mark.parametrize('near',[False,True])
def test_valid_prediction_cache_does_not_spend_reserved_calls(tmp_path,near):
    from types import SimpleNamespace
    from app.lab_v2_shadow.repository import ShadowEvidenceRepository
    from app.lab_v2_shadow.runner import LabV2ShadowRunner
    r=ShadowEvidenceRepository(tmp_path/'shadow.db')
    try:
        r.append_cache('/predictions',{'fixture':77},{'response':[]},retrieved_at=START,ttl=timedelta(hours=1))
        runner=LabV2ShadowRunner(SimpleNamespace(request_count=0),r,capability_cache_path=tmp_path/'caps.json')
        runner._remaining=lambda:0
        fixture={'fixture_id':77,'league_id':39,'season':2025,'home_team_id':1,'away_team_id':2,
                 'kickoff_utc':START+timedelta(minutes=30 if near else 180),
                 'competition_profile':'SENIOR_MEN_PRO','capability':SimpleNamespace(predictions=True)}
        values,skipped=asyncio.run(runner._predictions([fixture],START,reserve_calls=12))
        assert skipped==int(near) and (77 in values)==(not near)
        assert sum(c['actual_calls'] for c in runner.calls)==0
    finally:r.close()


@pytest.mark.parametrize('problem',['none','expired','missing','wrong_team','wrong_fixture','kickoff_change','future_provenance'])
def test_persisted_cmi_requires_current_expiry_and_exact_identity(problem):
    from types import SimpleNamespace as N
    from app.lab_v2_shadow.runner import _persisted_context_current
    fixture={'fixture_id':1,'home_team_id':2,'away_team_id':3,'kickoff_utc':START+timedelta(hours=2)}
    provenance=N(retrieved_at=START,provider_timestamp=START)
    freshness=[N(signal=s,status=N(value='FRESH'),expires_at=START+timedelta(hours=1),newest_retrieved_at=START)
               for s in ('fixture_context','team_statistics','team_history','injuries')]
    fields=[N(name=s+'.team_id',value=i,provenance=[provenance]) for s,i in [('home',2),('away',3)]]
    snapshot=N(fixture_id=1,kickoff_utc=fixture['kickoff_utc'],evaluated_at=START,fields=fields,freshness=freshness)
    if problem=='expired':freshness[1].expires_at=START+timedelta(minutes=10)
    if problem=='missing':freshness.pop()
    if problem=='wrong_team':fields[0].value=77
    if problem=='wrong_fixture':snapshot.fixture_id=88
    if problem=='kickoff_change':snapshot.kickoff_utc+=timedelta(hours=1)
    if problem=='future_provenance':provenance.retrieved_at+=timedelta(hours=1)
    assert _persisted_context_current(snapshot,fixture,START+timedelta(minutes=20))==(problem=='none')
