"""Global universe, profile evaluation, persistence and forward evidence regressions."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import asyncio
import json
from pathlib import Path
import sqlite3

import pytest

from test_lab_v2_shadow import NOW, FakeClient, coverage, odds_payload
from app.lab_v2_shadow.capability import LeagueCapabilityCache
from app.lab_v2_shadow.runner import LabV2ShadowRunner, _fixture_rows_with_evidence, _readiness
from app.lab_v2_shadow.profiles import classify, fallback_capability, policy_for
from app.lab_v2_shadow.global_evaluation import evaluate_profile, next_refresh
from app.lab_v2_shadow.ensemble import EnsembleSignal
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.scheduling import fair_order, record_service
from app.lab_v2_shadow.forward_evidence import capture_selection, capture_result, performance


CASES = [(f'U{age} League', 'YOUTH_U17_U18' if age<=18 else 'YOUTH_U19_U20' if age<=20 else 'YOUTH_U21_U23') for age in (17,18,19,20,21,23)] + [
    ('Women League','SENIOR_WOMEN_PRO'), ('Reserve League','RESERVE_OR_B_TEAM'),
    ('Regional Division 4','LOWER_DIVISION_OR_SEMIPRO'), ('World Cup U20','INTERNATIONAL_YOUTH'),
    ('World Cup','INTERNATIONAL_SENIOR'), ('Domestic Cup','DOMESTIC_CUP'),
    ('Champions League','INTERNATIONAL_CLUB'), ('Friendlies','FRIENDLY'), ('New Competition','UNKNOWN')]


def fixture(name='New Competition', identity=7):
    return {'fixture': {'id': identity, 'date': (NOW+timedelta(hours=4)).isoformat(), 'status': {'short':'NS'}},
            'league': {'id':identity+1000, 'name':name, 'season':2026, 'country':'Testland',
                       'type':'Cup' if name=='Domestic Cup' else 'League'},
            'teams': {'home':{'id':identity*2,'name':'Home'}, 'away':{'id':identity*2+1,'name':'Away'}}}


def discovered(row):
    cache = LeagueCapabilityCache.from_api_payload({'response':[]}, retrieved_at=NOW)
    return _fixture_rows_with_evidence({'response':[row]}, cache, NOW)


@pytest.mark.parametrize('name,profile', CASES)
def test_every_category_survives_without_capability(name, profile):
    accepted, rejected = discovered(fixture(name))
    assert not rejected and len(accepted)==1
    assert accepted[0]['competition_profile']==profile
    assert accepted[0]['classification_fingerprint'] == discovered(fixture(name))[0][0]['classification_fingerprint']


def test_neutral_second_leg_qualifier_flags_and_b_team():
    row=fixture('Qualification Cup'); row['fixture']['neutral']=True; row['league']['round']='Final - 2nd leg'
    row['teams']['home']['name']='Club B'
    item=discovered(row)[0][0]
    assert item['competition_profile']=='RESERVE_OR_B_TEAM'
    assert {'IS_NEUTRAL_VENUE','IS_SECOND_LEG','IS_QUALIFIER','IS_KNOCKOUT'} <= set(item['flags'])


def test_invalid_identity_does_not_disappear():
    row=fixture(); row['teams']['away']['id']=row['teams']['home']['id']
    accepted,rejected=discovered(row)
    assert not accepted and rejected[0]['reason']=='FIXTURE_IDENTITY_OR_DATE_INVALID'


def signals(p='0.64'):
    return [EnsembleSignal('CURRENT_MARKET_CONSENSUS','HOME_WIN',Decimal('0.60'),'HOME_WIN',Decimal('.9'),'AVAILABLE','current'),
            EnsembleSignal('CURRENT_MATCH_INTELLIGENCE','HOME_WIN',Decimal(p),'HOME_WIN',Decimal('.8'),'AVAILABLE','history')]


@pytest.mark.parametrize('missing', [('lineup',), ('advanced_stats',), ('lineup','advanced_stats','injuries')])
def test_positive_value_experimental_missing_optional_features(missing):
    d,e=evaluate_profile('HOME_WIN',Decimal('2'),signals(),policy_for('YOUTH_U17_U18'),missing)
    assert d.decision=='APPROVED' and e['candidate_lane']=='EXPERIMENTAL'
    assert not e['hard_failures'] and e['soft_penalties']


@pytest.mark.parametrize('odds,p', [('1.2','.64'), ('2','NaN'), ('2','1.1'), ('NaN','.64')])
def test_invalid_or_negative_value_fails_closed(odds,p):
    d,e=evaluate_profile('HOME_WIN',Decimal(odds),signals(p),policy_for('UNKNOWN'),())
    assert d.decision=='REJECTED' and e['hard_failures']


def test_correlated_sources_never_supply_two_independent_nonmarket_votes():
    rows=signals()[1:]
    rows.append(replace(rows[0],name='PI_RATINGS'))
    d,e=evaluate_profile('HOME_WIN',Decimal('2'),rows,policy_for('UNKNOWN'),())
    assert d.decision=='REJECTED' and 'CURRENT_MARKET_CONSENSUS_UNAVAILABLE' in e['hard_failures'] and e['predictive_family_count'] == 1


def test_profile_ready_without_lineups_and_requires_exact_refresh():
    f=discovered(fixture('U18 League'))[0][0]; f['kickoff_utc']=NOW+timedelta(minutes=40)
    d,_=evaluate_profile('HOME_WIN',Decimal('2'),signals(),policy_for('YOUTH_U17_U18'),('lineup',))
    assert _readiness(d,f,NOW,{})[0]=='FINAL_REVIEW_REQUIRED'
    review={'fixture_refreshed':True,'odds_refreshed':True,'reviewed_at_utc':NOW.isoformat(),'lineup_status':'NOT_SUPPORTED'}
    assert _readiness(d,f,NOW,review)[0]=='READY_TO_PUBLISH'
    review['odds_refreshed']=False
    assert _readiness(d,f,NOW,review)[0]=='FINAL_REVIEW_REQUIRED'


def test_fair_scheduling_youth_women_restart(tmp_path):
    path=tmp_path/'shadow.db'; repo=ShadowEvidenceRepository(path)
    rows=[]
    for i in range(100):
        rows.append({'fixture_id':i+1,'competition_profile':'SENIOR_MEN_PRO','kickoff_utc':NOW})
    rows.extend([{'fixture_id':101,'competition_profile':'YOUTH_U17_U18','kickoff_utc':NOW},
                 {'fixture_id':102,'competition_profile':'SENIOR_WOMEN_PRO','kickoff_utc':NOW}])
    assert len({r['competition_profile'] for r in fair_order(rows,repo,phase='history')[:3]})==3
    first=fair_order(rows,repo,phase='history')[0]; record_service(repo,first,NOW,'history');repo.close()
    repo=ShadowEvidenceRepository(path)
    assert fair_order(rows,repo,phase='history')[0]['competition_profile']!=first['competition_profile']
    repo.close()


class GlobalClient(FakeClient):
    async def fixtures_by_date(self,day,*,timezone_name='UTC'):
        return self._hit('/fixtures',{'date':day},{'response':[fixture(CASES[i%len(CASES)][0],i+1) for i in range(225)]})
    async def _get(self, endpoint, *, params):
        if endpoint=='/odds':
            from test_lab_v2_shadow import Response
            return Response(self._hit(endpoint,params,{'response':[], 'paging':{'current':1,'total':1}}))
        return await super()._get(endpoint,params=params)


def test_225_fixture_universe_persisted_and_restart_recovery(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);repo=ShadowEvidenceRepository(Path('var/global.db'))
    runner=LabV2ShadowRunner(GlobalClient(),repo,capability_cache_path=Path('var/cap.json'),maximum_calls=30)
    report=asyncio.run(runner.run(now=NOW,horizon_days=1))
    assert report['fixtures_discovered']==225
    states=repo.all('global_fixture_state')
    assert len(states)==225 and len(repo.all('global_discovery'))==225
    assert sum(report['competition_profile_counts'].values())==225
    assert len(repo.latest_global_fixtures(now=NOW))==225
    assert all(r['state'] in {'DISCOVERED','TRACKING','READY','EXPERIMENTAL_READY','REJECTED','UNAVAILABLE','EXPIRED'} for r in states)
    assert report['telegram_sends']==report['official_mutations']==0
    assert repo.connection.execute('PRAGMA foreign_key_check').fetchall()==[]
    repo.close()
    repo=ShadowEvidenceRepository(Path('var/global.db'))
    assert len(repo.latest_global_fixtures(now=NOW+timedelta(minutes=1)))==225
    repo.close()


def test_existing_schema_upgrade_replay_and_guards(tmp_path):
    path=tmp_path/'old.db';c=sqlite3.connect(path)
    c.execute('CREATE TABLE lab_v2_shadow_evidence (kind TEXT NOT NULL,identity TEXT NOT NULL,created_at_utc TEXT NOT NULL,content_fingerprint TEXT NOT NULL,document_json TEXT NOT NULL,PRIMARY KEY(kind,identity))');c.close()
    repo=ShadowEvidenceRepository(path)
    assert repo.append('global_discovery','one',{'fixture_id':1},created_at=NOW)
    assert not repo.append('global_discovery','one',{'fixture_id':1},created_at=NOW)
    with pytest.raises(ValueError):repo.append('global_discovery','one',{'fixture_id':2},created_at=NOW)
    for sql in ('DELETE FROM lab_v2_shadow_evidence','UPDATE lab_v2_shadow_evidence SET kind="changed"'):
        with pytest.raises(sqlite3.IntegrityError):repo.connection.execute(sql)
    assert repo.connection.execute('PRAGMA foreign_keys').fetchone()[0]==1
    assert not repo.connection.execute('PRAGMA foreign_key_check').fetchall()
    repo.close()


def test_forward_freezes_first_current_price_and_small_samples(tmp_path):
    repo=ShadowEvidenceRepository(tmp_path/'forward.db')
    row={'stage':'READY_TO_PUBLISH','decision':'APPROVED','candidate_id':'c1','fixture_id':1,'league_id':2,
         'competition_profile':'YOUTH_U17_U18','market':'HOME_WIN','candidate_lane':'EXPERIMENTAL',
         'ensemble_probability':'.65','captured_odds':'2','quote_provenance_fingerprint':'q1',
         'kickoff_utc':(NOW+timedelta(hours=1)).isoformat(),'profile_policy_version':'V1'}
    assert capture_selection(repo,row,now=NOW)
    assert not capture_selection(repo,{**row,'captured_odds':'3'},now=NOW)
    assert capture_result(repo,'1:HOME_WIN',outcome='WON',source_fingerprint='final-result',now=NOW+timedelta(hours=3))
    metrics=performance(repo)[0]
    assert metrics['hypothetical_flat_stake_roi']=='1' and metrics['sample_size']==1
    assert not metrics['eligible_for_manual_policy_review']
    with pytest.raises(ValueError):capture_result(repo,'1:HOME_WIN',outcome='LOST',source_fingerprint='other',now=NOW+timedelta(hours=3))
    repo.close()


def test_refresh_strategy_monotonic_and_profile_specific():
    kickoff=NOW+timedelta(hours=7)
    assert next_refresh(kickoff,NOW,policy_for('YOUTH_U19_U20'))>NOW
    assert policy_for('YOUTH_U19_U20').half_life_days < policy_for('SENIOR_MEN_PRO').half_life_days

@pytest.mark.parametrize('name', ['Primera B Metropolitana', 'Serie B', 'Group B Championship'])
def test_letter_b_competition_is_not_a_reserve_team(name):
    assert discovered(fixture(name))[0][0]['competition_profile'] != 'RESERVE_OR_B_TEAM'


def test_odds_pagination_continues_after_restart(tmp_path,monkeypatch):
    from test_lab_v2_shadow import PagedOddsClient
    monkeypatch.chdir(tmp_path)
    repo=ShadowEvidenceRepository(Path('var/pages.db'))
    day=NOW.date().isoformat()
    for offset,expected in [(0,[(day,1),(day,2)]),(1,[(day,1),(day,3)])]:
        client=PagedOddsClient()
        runner=LabV2ShadowRunner(client,repo,capability_cache_path=Path('var/cap.json'),maximum_calls=4)
        runner.allowed_bookmaker_ids=frozenset({3,4})
        asyncio.run(runner._date_odds([day],[{'fixture_id':7,'kickoff_utc':NOW+timedelta(hours=4)}],NOW+timedelta(minutes=offset)))
        assert client.order==expected
    repo.close()


def test_recovery_after_discovery_before_cycle_completion(tmp_path):
    repo=ShadowEvidenceRepository(tmp_path/'recovery.db')
    row=discovered(fixture('U17 League'))[0][0]
    from app.lab_v2_shadow.runner import _plain
    document={**_plain(row),'state':'DISCOVERED','reason':'PROVIDER_DATE_FIXTURE'}
    repo.append('global_discovery','interrupted',document,created_at=NOW)
    assert len(repo.latest_global_fixtures(now=NOW))==1
    assert not repo.latest_global_fixtures(now=NOW+timedelta(days=1))
    assert len(repo.latest_global_fixtures(now=NOW+timedelta(days=1),include_expired=True))==1
    repo.close()


def test_exact_identity_conflict_has_explicit_global_rejection():
    from app.lab_v2_shadow.diagnostics import global_diagnostic
    row=discovered(fixture())[0][0]
    report=global_diagnostic([row],[],{},NOW,reviews={7:{'status':'FIXTURE_INVALID','reason':'CONTRADICTORY_FIXTURE_IDENTITY'}})
    assert report['global_fixture_states'][0]['state']=='REJECTED'
    assert report['global_fixture_states'][0]['reason']=='CONTRADICTORY_FIXTURE_IDENTITY'
