"""Regression for scan exhausting the cycle before the mandatory exact refresh."""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.adaptive_lab.quota import SharedQuota
from app.football.client import FootballClient, FootballRequestLimitError
from app.football.quota import FootballQuotaError
from app.live_lab.runner import LiveRunner
from app.live_lab.service import LiveService, final_refresh_failure_reason
from app.lab_telegram.models import LabTelegramConfig
from .conftest import repo

NOW = datetime.fromisoformat('2026-10-09T15:02:00+00:00')


def mock_environment(repo, monkeypatch, budget=35, retry_broad=False):
    from app.adaptive_lab import daypart
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    monkeypatch.setenv('GOALVISION_LIVE_API_FEED_QUOTES','1')
    monkeypatch.setenv('GOALVISION_LIVE_QUOTE_AGE_DIAGNOSTIC','1')
    monkeypatch.setenv('GOALVISION_LIVE_PROBABILITY_60_70','1')
    monkeypatch.setattr(daypart,'live_budget',lambda *a,**k:budget)
    monkeypatch.setattr(FootballClient,'MIN_REQUEST_INTERVAL_SECONDS',0)
    calls=[]; sends=[]; clients=[]
    def fixture(fid):
        return {'fixture':{'id':fid,'date':(NOW-timedelta(hours=1)).isoformat(),
                           'status':{'short':'2H','elapsed':60}},
                'goals':{'home':0,'away':0},'league':{'id':39},
                'teams':{'home':{'id':fid*2,'name':'Synthetic home'},
                         'away':{'id':fid*2+1,'name':'Synthetic away'}}}
    def offer(fid):
        return {'fixture':{'id':fid,'status':{'elapsed':60}},
                'teams':{'home':{'goals':0},'away':{'goals':0}},
                'update':(NOW-timedelta(seconds=40)).isoformat(),
                'status':{'blocked':False,'stopped':False,'finished':False},
                'odds':[{'id':36,'name':'Over/Under Line','values':[
                    {'value':'Under','handicap':'2.5','odd':'1.7','main':False,'suspended':False}]}]}
    def response(request):
        path=request.url.path; params=dict(request.url.params)
        calls.append((path,params))
        assert len(repo.all('quota_claims')) == len(calls)
        headers={'x-ratelimit-requests-limit':'7500','x-ratelimit-requests-remaining':'7000',
                 'x-ratelimit-limit':'300','x-ratelimit-remaining':'299'}
        if path=='/status': rows=[]
        elif path=='/fixtures' and 'live' in params: rows=[fixture(i) for i in range(100,110)]
        elif path=='/fixtures' and 'id' in params: rows=[fixture(int(params['id']))]
        elif path=='/fixtures' and 'team' in params:
            team=int(params['team'])
            rows=[{'fixture':{'id':10000+team*10+i,'date':(NOW-timedelta(days=i+1)).isoformat(),
                              'status':{'short':'FT'}},
                   'teams':{'home':{'id':team},'away':{'id':9999}},
                   'score':{'fulltime':{'home':3,'away':3}}} for i in range(10)]
        elif path=='/fixtures/events': rows=[]
        elif path=='/odds/live/bets': rows=[{'id':36,'name':'Over/Under Line'}]
        elif path=='/odds/live':
            if retry_broad and not params:
                return httpx.Response(503,json={'errors':[],'response':[]},headers=headers)
            rows=[offer(int(params['fixture']))] if params else [offer(i) for i in range(100,110)]
        else: raise AssertionError((path,params))
        return httpx.Response(200,json={'errors':[],'response':rows},headers=headers)
    original=FootballClient.__init__
    def init(self,*args,**kwargs):
        original(self,*args,api_key='synthetic-offline-key',**kwargs)
        self._client=httpx.AsyncClient(base_url=self.BASE_URL,transport=httpx.MockTransport(response))
        clients.append(self)
    monkeypatch.setattr(FootballClient,'__init__',init)
    config=LabTelegramConfig(token='fake',chat_id='-1003510920417',automatic_enabled=True,official_destinations=frozenset())
    monkeypatch.setattr('app.lab_telegram.service.load_lab_telegram_config',lambda:config)
    monkeypatch.setattr('app.lab_combo.secure_logging.install_lab_secret_redaction',lambda *a:None)
    class Transport:
        username='GoalVision_AI_Lab_Bot'
        def __init__(self,*args): self.bot=self
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def send_message_receipt(self,**kwargs):
            sends.append(kwargs)
            return SimpleNamespace(chat_id=kwargs['chat_id'],message_id=100+len(sends))
    monkeypatch.setattr('app.lab_combo.presentation.LabTelegramTransport',Transport)
    return calls,sends,clients


@pytest.mark.parametrize('budget',[35,36,37])
@pytest.mark.parametrize('reserve',[0,9])
def test_same_cycle_ceiling_before_and_after_reservation(repo,monkeypatch,budget,reserve):
    from app.adaptive_lab.worker import live_cycle
    monkeypatch.setattr('app.live_lab.runner.FINAL_REVIEW_RESERVED_ATTEMPTS',reserve)
    calls,sends,clients=mock_environment(repo,monkeypatch,budget)
    result=asyncio.run(live_cycle(repo,send=True,clock=lambda:NOW))
    assert result['api_calls']==len(calls)<=budget
    assert result['request_budget']['cycle_ceiling']==budget
    assert result['candidates']==1
    if reserve==0:
        assert len(calls)==budget and not sends
        assert result['deliveries']==[{'status':'LIVE_FINAL_REFRESH_FAILED','sent':False,
                                      'reason':'LIVE_CYCLE_REQUEST_LIMIT_REACHED'}]
    else:
        assert len(sends)==1 and result['deliveries'][0]['sent']
        assert result['discovery_evidence']['scan_stop_reason']=='FINAL_REVIEW_BUDGET_RESERVED'
        assert [p for p,_ in calls[-3:]]==['/fixtures','/fixtures/events','/odds/live']
        assert len(repo.all('live_claims'))==len(repo.all('live_publications'))==1
        assert '60–70%' in sends[0]['text'] and 'EV:' not in sends[0]['text']
        assert clients[0]._request_limit==budget
    assert not repo.all('learning_observations','PREMATCH')
    assert not repo.all('training_runs') and not repo.all('activation_events')


def test_reserve_applies_before_every_retry_without_spending_shared_slot(repo,monkeypatch):
    calls,_,_=mock_environment(repo,monkeypatch,retry_broad=True)
    service=LiveService(repo,clock=lambda:NOW,allow_provider_feed=True,quote_age_diagnostic=True,probability_band=True)
    client=FootballClient(request_limit=35)
    quota=SharedQuota(repo)
    quota.bind(client,lambda:NOW,allow_status_preflight=True,status_preflight_category='LIVE_SETTLEMENT')
    async def exercise():
        await quota.call('LIVE_SETTLEMENT',client.account_status)
        runner=LiveRunner(service,client,quota,clock=lambda:NOW)
        result=await runner.scan(request_ceiling=3)
        assert result['scan_stop_reason']=='FINAL_REVIEW_BUDGET_RESERVED'
        assert client.request_count==3 and len(repo.all('quota_claims'))==3
        # The reserve does not leak into final-refresh or settlement calls.
        await runner._live_catalog()
        assert client.request_count==4
        await client.close()
    asyncio.run(exercise())
    assert [p for p,_ in calls]==['/status','/fixtures','/odds/live','/odds/live/bets']


@pytest.mark.parametrize('budget',[1,2,8,9,10])
def test_tiny_budget_stays_fail_closed_with_no_forced_pick(repo,monkeypatch,budget):
    from app.adaptive_lab.worker import live_cycle
    calls,sends,_=mock_environment(repo,monkeypatch,budget)
    result=asyncio.run(live_cycle(repo,send=True,clock=lambda:NOW))
    assert len(calls)<=budget and not sends and not repo.all('live_claims')


@pytest.mark.parametrize('exception,reason',[
    (FootballRequestLimitError('secret must not leak'),'LIVE_CYCLE_REQUEST_LIMIT_REACHED'),
    (FootballQuotaError('secret must not leak'),'LIVE_SHARED_OR_PROVIDER_QUOTA_BLOCKED'),
    (ValueError('secret must not leak'),'LIVE_PROVIDER_OR_REVIEW_FAILURE')])
def test_failure_diagnostic_never_serializes_exception_text(exception,reason):
    assert final_refresh_failure_reason(exception)==reason


def test_reserve_never_changes_global_publication_markets_or_probability_bounds():
    from app.adaptive_lab.contracts import MARKETS
    from app.live_lab.selection import in_probability_band
    assert len(MARKETS)==11
    assert in_probability_band('.60') and in_probability_band('.70')
    assert not in_probability_band('.59999') and not in_probability_band('.70001')
