"""Lab throughput contracts: no networking, transports or Official state."""
import asyncio
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.lab_v2_shadow.competition_registry import REVIEWED_COMPETITIONS, REGISTRY_VERSION
from app.lab_v2_shadow.profiles import classify, fallback_capability, policy_for
from app.lab_v2_shadow.global_evaluation import evaluate_profile
from app.lab_v2_shadow.quota import adaptive_quota_budget
from app.lab_v2_shadow.odds_coverage import DateOddsCoverage
from app.lab_v2_shadow.runner import LabV2ShadowRunner, _readiness
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.diagnostics import global_diagnostic
from test_lab_v2_global import signals, fixture, discovered, GlobalClient
from test_lab_v2_shadow import NOW, FakeClient


@pytest.mark.parametrize('identity', [71,98,103,106,179,203,365,362,549,725,640,1196,736])
def test_reviewed_competition_identity_and_gender(identity):
    row = REVIEWED_COMPETITIONS['API_FOOTBALL', identity]
    league = dict(id=identity, country=row.country, name=row.name, season=2026)
    result = classify(league, {}, {}, fallback_capability(league))
    assert result.competition_profile == row.profile
    assert ('IS_WOMEN' in result.flags) == (row.gender == 'women')
    assert REGISTRY_VERSION in result.classification_reason
    assert result == classify(league, {}, {}, fallback_capability(league))
    assert result.classification_fingerprint != classify({**league, 'id': 999999}, {}, {}, fallback_capability({**league, 'id':999999})).classification_fingerprint


def test_country_and_provider_collisions_do_not_apply_registry():
    for extra in ({'country':'Elsewhere'}, {'provider':'ANOTHER_PROVIDER'}):
        league = dict(id=110, country='Wales', name='Premier League', season=2026) | extra
        assert classify(league, {}, {}, fallback_capability(league)).competition_profile == 'UNKNOWN'


@pytest.mark.parametrize('profile', ['SENIOR_MEN_PRO','SENIOR_WOMEN_PRO','YOUTH_U17_U18','YOUTH_U19_U20','YOUTH_U21_U23','RESERVE_OR_B_TEAM','LOWER_DIVISION_OR_SEMIPRO','UNKNOWN','FRIENDLY'])
def test_single_model_experimental_uses_independent_probability(profile):
    d, e = evaluate_profile('HOME_WIN',Decimal(2),signals(),policy_for(profile),('lineup','advanced_stats'))
    assert d.decision == 'APPROVED'
    assert e['candidate_lane'] == 'EXPERIMENTAL'
    assert e['predictive_family_count'] == 1
    assert e['evidence_lane'] == 'SINGLE_MODEL_EXPERIMENTAL'
    assert d.ensemble_probability == Decimal('.64')
    assert d.edge == Decimal('.14')
    changed = signals(); changed[0] = replace(changed[0], probability=Decimal('.59'))
    assert evaluate_profile('HOME_WIN',Decimal(2),changed,policy_for(profile),())[0].ensemble_probability == d.ensemble_probability


def test_market_only_never_supplies_prediction():
    d,e = evaluate_profile('HOME_WIN',Decimal(2),signals()[:1],policy_for('UNKNOWN'),())
    assert d.decision == 'REJECTED' and e['predictive_family_count'] == 0
    assert 'NO_INDEPENDENT_NON_MARKET_EVIDENCE' in e['hard_failures']


def test_same_family_duplicates_never_create_standard():
    rows = signals(); rows.append(replace(rows[1],name='PI_RATINGS'))
    d,e = evaluate_profile('HOME_WIN',Decimal(2),rows,policy_for('SENIOR_MEN_PRO'),())
    assert e['predictive_family_count'] == 1 and e['candidate_lane'] == 'EXPERIMENTAL'


@pytest.mark.parametrize('p', ['.49','.5'])
def test_nonpositive_ev_is_always_hard_failure(p):
    d,e = evaluate_profile('HOME_WIN',Decimal(2),signals(p),policy_for('SENIOR_MEN_PRO'),())
    assert d.decision == 'REJECTED' and 'NON_POSITIVE_VALUE' in e['hard_failures']


def test_severe_model_market_disagreement_rejected():
    rows = signals('.85'); rows[0] = replace(rows[0],probability=Decimal('.45'))
    d,e = evaluate_profile('HOME_WIN',Decimal('1.4'),rows,policy_for('YOUTH_U17_U18'),())
    assert d.decision == 'REJECTED'
    assert 'SEVERE_MODEL_MARKET_CONTRADICTION' in e['hard_failures']


def test_standard_and_strong_quorum_not_relaxed():
    rows = signals('.63')
    rows.append(replace(rows[1], name='API_FOOTBALL_PREDICTION'))
    d,e = evaluate_profile('HOME_WIN',Decimal(2),rows,policy_for('SENIOR_MEN_PRO'),())
    assert e['predictive_family_count'] == 2 and e['candidate_lane'] == 'STANDARD'
    for profile in ('UNKNOWN','FRIENDLY'):
        assert evaluate_profile('HOME_WIN',Decimal(2),rows,policy_for(profile),())[1]['candidate_lane'] == 'EXPERIMENTAL'


def test_adaptive_expansion_and_protected_reserves():
    quota = dict(interpretation_status='NORMALIZED',daily_remaining=4519,minute_remaining=300)
    b = adaptive_quota_budget(quota,requested_maximum=400,already_consumed=1,
        settlement_reserve=100,final_review_reserve=30,tracked_demand=10,remaining_odds_pages=120,discovery_days=3)
    assert 100 < b.additional_calls_available <= 300
    assert b.additional_calls_available <= 4519-1500-100
    assert b.final_review_reserve == 30 and b.demand_calls == 208
    for remaining in (0,1,5):
        assert adaptive_quota_budget({**quota,'minute_remaining':remaining},requested_maximum=400,already_consumed=1).additional_calls_available <= remaining
    assert adaptive_quota_budget({**quota,'daily_remaining':1500},requested_maximum=400,already_consumed=1).additional_calls_available == 0
    assert adaptive_quota_budget({},requested_maximum=400,already_consumed=1).additional_calls_available == 0


def test_pagination_restart_keeps_maximum_and_failed_pages():
    c = DateOddsCoverage(previous_maximum=5)
    c.observe(1,dict(response=[],paging=dict(current=1,total=2)))
    c.observe(2,dict(response=[],errors={'request':'ODDS_API_TIMEOUT'}))
    d=c.document()
    assert d['maximum_advertised_total']==5 and d['failed_pages']==[2]
    assert d['unrequested_pages']==[3,4,5] and d['coverage_status']=='ODDS_TIMEOUT'
    assert not d['stable_complete_sweep']


@pytest.mark.parametrize('reason,state',[('ODDS_STALE','ODDS_STALE_WAITING_REFRESH'),('ODDS_COMPLETE_SWEEP_NO_FIXTURE_RECORD','ODDS_NOT_PUBLISHED_YET_POSSIBLE'),('ODDS_DISCOVERY_BUDGET_LIMITED_PAGINATION','ODDS_PAGINATION_PENDING')])
def test_pre_kickoff_absence_retriable(reason,state):
    f=discovered(fixture())[0][0]
    report=global_diagnostic([f],[],{},NOW,odds_reasons={'7':reason})
    r=report['global_fixture_states'][0]
    assert r['state']=='TRACKING' and r['odds_retryable'] and r['odds_retry_state']==state


def test_experimental_ready_needs_exact_current_pair():
    f=discovered(fixture('U17 League'))[0][0];f['kickoff_utc']=NOW+timedelta(minutes=45)
    d,e=evaluate_profile('HOME_WIN',Decimal(2),signals(),policy_for('YOUTH_U17_U18'),('lineup',))
    review=dict(fixture_refreshed=True,odds_refreshed=True,reviewed_at_utc=NOW.isoformat())
    assert e['candidate_lane']=='EXPERIMENTAL' and _readiness(d,f,NOW,review)[0]=='READY_TO_PUBLISH'
    assert _readiness(d,f,NOW,{**review,'odds_refreshed':False})[0]=='FINAL_REVIEW_REQUIRED'
    assert _readiness(d,f,NOW,{**review,'reviewed_at_utc':(NOW-timedelta(minutes=6)).isoformat()})[0]=='FINAL_REVIEW_REQUIRED'


def test_250_mixed_fixtures_retain_states_under_pagination_limit(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    from test_lab_v2_global import CASES
    class Client(GlobalClient):
        async def fixtures_by_date(self,day,*,timezone_name='UTC'):
            return self._hit('/fixtures',{}, {'response':[fixture(CASES[i%len(CASES)][0],i+1) for i in range(250)]})
        async def current_odds_by_date(self, day, *, page=1):
            from test_lab_v2_shadow import odds_payload
            rows = [odds_payload(fixture_id=1)['response'][0],
                    odds_payload(NOW-timedelta(hours=4),fixture_id=2)['response'][0],
                    dict(fixture={'id':3},update=NOW.isoformat(),bookmakers=[])] if page == 1 else []
            return self._hit('/odds',{},dict(response=rows,paging=dict(current=page,total=50)))
    repo=ShadowEvidenceRepository(Path('var/test.db'))
    report=asyncio.run(LabV2ShadowRunner(Client(),repo,capability_cache_path=Path('var/cap.json'),maximum_calls=20).run(now=NOW,horizon_days=1))
    assert len(repo.all('global_fixture_state'))==250
    assert report['fixtures_discovered']==250 and report['fixtures_with_incomplete_odds_page_coverage']==247
    assert len({r['competition_profile'] for r in repo.all('global_fixture_state')})>5
    assert sum(r['odds_retryable'] for r in repo.all('global_fixture_state')) >= 248
    assert report['current_odds_fixtures'] == 1
    assert report['fixtures_rejected_for_stale_current_odds'] == 1
    repo.close()


def test_real_runner_pagination_can_cross_100_without_using_reserve(tmp_path):
    class Client(FakeClient):
        def quota_snapshot(self):
            return dict(interpretation_status='NORMALIZED', daily_remaining=4519-self.request_count,
                        minute_remaining=300-self.request_count)
        async def current_odds_by_date(self,day,*,page=1):
            return self._hit('/odds',{},dict(response=[],paging=dict(current=page,total=140)))
    repo=ShadowEvidenceRepository(tmp_path/'pages.db');client=Client()
    runner=LabV2ShadowRunner(client,repo,capability_cache_path=tmp_path/'cap.json',maximum_calls=400)
    _,report=asyncio.run(runner._date_odds([NOW.date().isoformat()],[],NOW,reserve_calls=30))
    assert client.request_count == 140 and runner._remaining() >= 30
    assert report['coverage_by_date'][NOW.date().isoformat()]['coverage_status']=='ODDS_COMPLETE'
    assert client.quota_snapshot()['daily_remaining'] > 1600
    repo.close()


def test_due_exact_pair_precedes_broad_pages_and_near_only_has_no_scan(tmp_path,monkeypatch):
    from test_lab_v2_shadow import LifecycleClient
    monkeypatch.chdir(tmp_path)
    repo=ShadowEvidenceRepository(Path('var/near.db'))
    kickoff=NOW+timedelta(minutes=45)
    client=LifecycleClient(NOW,kickoff,broad='missing')
    report=asyncio.run(LabV2ShadowRunner(client,repo,capability_cache_path=Path('var/cap.json'),maximum_calls=40).run(now=NOW,horizon_days=1))
    exact_index=client.requests.index(('/odds',{'fixture':7}))
    broad_index=next(i for i,r in enumerate(client.requests) if r[0]=='/odds' and 'date' in r[1])
    assert exact_index < broad_index
    client=LifecycleClient(NOW+timedelta(minutes=1),kickoff,broad='missing')
    report=asyncio.run(LabV2ShadowRunner(client,repo,capability_cache_path=Path('var/cap.json'),maximum_calls=40).run(now=NOW+timedelta(minutes=1),near_only=True))
    assert report['exact_fixture_odds_refresh_calls']==1
    assert not any('date' in query for endpoint,query in client.requests)
    assert all(c['readiness_lane']=='EXPERIMENTAL_READY' for c in report['candidate_markets'] if c['stage']=='READY_TO_PUBLISH')
    repo.close()


def test_approaching_tracked_odds_refresh_precedes_broad_pages(tmp_path, monkeypatch):
    from test_lab_v2_shadow import LifecycleClient
    monkeypatch.chdir(tmp_path)
    repo=ShadowEvidenceRepository(Path('var/tracked.db'))
    kickoff=NOW+timedelta(hours=6)
    first=LifecycleClient(NOW,kickoff)
    asyncio.run(LabV2ShadowRunner(first,repo,capability_cache_path=Path('var/cap.json'),maximum_calls=40).run(now=NOW,horizon_days=1))
    now=kickoff-timedelta(hours=2)
    client=LifecycleClient(now,kickoff,broad='missing')
    report=asyncio.run(LabV2ShadowRunner(client,repo,capability_cache_path=Path('var/cap.json'),maximum_calls=60).run(now=now,horizon_days=1))
    exact=client.requests.index(('/odds',{'fixture':7}))
    broad=next(i for i,r in enumerate(client.requests) if r[0]=='/odds' and 'date' in r[1])
    assert exact<broad and report['ready_candidate_count']==0
    assert repo.all('tracked_odds_refresh')[0]['final_review'] is False
    repo.close()
