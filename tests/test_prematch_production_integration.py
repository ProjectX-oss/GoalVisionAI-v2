"""Exact production-lineage integration regressions; isolated synthetic evidence."""
import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from dataclasses import replace

from test_lab_v2_prematch import BatchClient, Response
from test_lab_v2_global import fixture
from test_lab_v2_shadow import NOW, odds_payload, _controlled_ready_candidate
from app.lab_v2_shadow.runner import LabV2ShadowRunner
from app.lab_v2_shadow.repository import ShadowEvidenceRepository
from app.lab_v2_shadow.scheduling import fair_order
from app.lab_v2_shadow.competition_registry import REVIEWED_COMPETITIONS
from app.adaptive_lab.repository import AuditRepository
from app.adaptive_lab.coordinator import LearningCoordinator
from app.adaptive_lab.observer import settle_pending_shadow, observe
from app.adaptive_lab.observations import ingest


def test_incident_958_fixture_constrained_odds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('app.lab_v2_shadow.runner._history_market_probabilities',
        lambda *a: {'HOME_WIN': Decimal('.60'), 'DRAW': Decimal('.24'), 'AWAY_WIN': Decimal('.16')})
    class Incident(BatchClient):
        def quota_snapshot(self):
            return {'interpretation_status':'NORMALIZED','daily_remaining':1806-self.request_count,'minute_remaining':300-self.request_count}
        async def fixtures_by_date(self, day, *, timezone_name='UTC'):
            rows = [fixture('Regional Division 4', i) for i in range(1,959)]
            for row in rows:
                row['league']['id'] = 999
            return self._hit('/fixtures', {'date':day}, {'response':rows})
        async def _get(self, endpoint, *, params):
            if endpoint == '/odds' and 'date' in params:
                rows = [odds_payload(NOW, fixture_id=i)['response'][0] for i in range(1,4)] if params['page']==1 else []
                return Response(self._hit(endpoint,params,{'response':rows,'paging':{'current':params['page'],'total':500}}))
            return await super()._get(endpoint,params=params)
    repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
    client = Incident()
    report = asyncio.run(LabV2ShadowRunner(client,repo,capability_cache_path=tmp_path/'var/caps.json', maximum_calls=400).run(now=NOW,horizon_days=1))
    numbers = {'discovered':report['fixtures_discovered'], 'model_analysis_attempts':report['model_analysis_attempts'],
               'current_odds_evaluated':report['current_odds_fixtures'], 'waiting_for_refresh':report['waiting_odds_refresh'],
               'READY':report['ready_candidate_count'], 'provider_calls':report['api_calls_consumed']}
    print('INCIDENT_THROUGHPUT='+json.dumps(numbers,sort_keys=True))
    assert numbers['discovered'] == numbers['model_analysis_attempts'] == 958
    assert numbers['current_odds_evaluated'] == 3 and numbers['waiting_for_refresh'] == 955
    assert numbers['provider_calls'] <= 107 and numbers['READY'] == 0
    assert len(repo.all('model_analysis')) == 958
    repo.close()


def test_major_competitions_first(tmp_path):
    repo = ShadowEvidenceRepository(tmp_path/'shadow.db')
    rows = [{'fixture_id':900,'league_id':999,'country':'Unknown','competition_profile':'SENIOR_MEN_PRO','kickoff_utc':NOW}]
    for identity in (39,140,78,135,61,2,3,848):
        r = REVIEWED_COMPETITIONS['API_FOOTBALL',identity]
        rows.append({'fixture_id':identity,'league_id':identity,'country':r.country,'competition_profile':r.profile,'kickoff_utc':NOW+timedelta(hours=1)})
    assert fair_order(rows,repo,phase='history')[-1]['fixture_id'] == 900
    repo.close()


def test_canonical_shadow_uses_existing_observer_and_deduplicates(tmp_path, monkeypatch):
    repo = AuditRepository(tmp_path/'adaptive.db')
    coordinator = LearningCoordinator(repo)
    monkeypatch.setattr(coordinator.governance,'observe',lambda *a,**k: [])
    row = dict(_controlled_ready_candidate(NOW), prepared_at_utc=NOW.isoformat())
    coordinator.shadow([row],stream='PREMATCH',now=NOW)
    coordinator.shadow([dict(row,captured_odds='2.1')],stream='PREMATCH',now=NOW+timedelta(minutes=1))
    assert len(repo.all('canonical_opportunities')) == 1
    later = NOW+timedelta(hours=4)
    class Results:
        request_count = 0
        async def fixture(self, identity):
            self.request_count += 1
            return {'response':[{'fixture':{'id':identity,'status':{'short':'FT'}},'score':{'fulltime':{'home':2,'away':0}}}]}
    client = Results()
    asyncio.run(settle_pending_shadow(repo,client,now=later))
    asyncio.run(settle_pending_shadow(repo,client,now=later))
    assert client.request_count == 1
    observations = repo.all('learning_observations','PREMATCH')
    assert len(observations) == 1 and observations[0]['source_product'] == 'SHADOW'
    assert observations[0]['published_at'] is None
    result = repo.all('canonical_results')[0]
    receipt = {'status':'SENT','sent_at_utc':NOW.isoformat()}
    ingest(repo,row,receipt,result,stream='PREMATCH',publication_id='published-later')
    assert len(repo.all('learning_observations')) == 1
    assert not repo.all('combo_analytics') and not repo.all('live_publications')
    assert repo.connection.execute('PRAGMA foreign_key_check').fetchall() == []
    repo.close()


def test_shadow_published_result_reuse_and_crash_recovery(tmp_path, monkeypatch):
    from app.lab_combo.settlement import resolve_leg
    from app.adaptive_lab.observer import import_canonical
    repo = AuditRepository(tmp_path/'adaptive.db')
    coordinator = LearningCoordinator(repo)
    monkeypatch.setattr(coordinator.governance,'observe',lambda *a,**k: [])
    row = dict(_controlled_ready_candidate(NOW), prepared_at_utc=NOW.isoformat())
    coordinator.shadow([row],stream='PREMATCH',now=NOW)
    later=NOW+timedelta(hours=4)
    payload={'response':[{'fixture':{'id':row['fixture_id'],'status':{'short':'FT'}},'score':{'fulltime':{'home':2,'away':0}}}]}
    result=resolve_leg({**row,'observation_id':'public','odds':row['captured_odds']},payload,later)
    ingest(repo,row,{'status':'SENT','sent_at_utc':NOW.isoformat()},result,stream='PREMATCH',publication_id='public')
    class Ledger:
        def all(self, kind):
            return [result] if kind=='single_settlement' else []
    class Forbidden:
        request_count=0
        async def fixture(self, identity):
            raise AssertionError('Published result must be reused')
    asyncio.run(settle_pending_shadow(repo,Forbidden(),now=later,ledger=Ledger()))
    import_canonical(repo,now=later+timedelta(minutes=30))
    assert len(repo.all('learning_observations')) == 1
    assert repo.all('learning_observations')[0]['source_product'] == 'SINGLE'
    assert len(repo.all('canonical_results')) == 1
    repo.close()


def test_malformed_canonical_result_remains_pending(tmp_path, monkeypatch):
    repo=AuditRepository(tmp_path/'adaptive.db')
    coordinator=LearningCoordinator(repo)
    monkeypatch.setattr(coordinator.governance,'observe',lambda *a,**k: [])
    row=dict(_controlled_ready_candidate(NOW),prepared_at_utc=NOW.isoformat())
    coordinator.shadow([row],stream='PREMATCH',now=NOW)
    class Malformed:
        request_count=0
        async def fixture(self, identity):
            self.request_count+=1
            return {'response':[None]}
    asyncio.run(settle_pending_shadow(repo,Malformed(),now=NOW+timedelta(hours=4)))
    assert not repo.all('canonical_results') and not repo.all('learning_observations')
    repo.close()


def test_no_upcoming_demand_does_not_sweep_odds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class NoDemand(BatchClient):
        async def fixtures_by_date(self, day, *, timezone_name='UTC'):
            return self._hit('/fixtures', {'date':day}, {'response':[]})
    client=NoDemand()
    repo=ShadowEvidenceRepository(tmp_path/'shadow.db')
    report=asyncio.run(LabV2ShadowRunner(client,repo,capability_cache_path=tmp_path/'var/caps.json').run(now=NOW,horizon_days=1))
    assert report['model_analysis_attempts'] == 0
    assert not any(endpoint in {'/odds','/predictions'} for endpoint, query in client.requests)
    assert not any('league' in query for endpoint, query in client.requests)
    repo.close()
