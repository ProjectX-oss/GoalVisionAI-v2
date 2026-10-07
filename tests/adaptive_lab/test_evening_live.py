from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.adaptive_lab import daypart
from app.adaptive_lab.contracts import digest
from app.adaptive_lab.quota import SharedQuota
from app.football.quota import FootballQuotaError
from app.live_lab.engine import readiness
from app.live_lab.provider import normalize_quotes
from app.live_lab.service import LiveService
from .test_live import live_data
from .conftest import START

CLOCK = datetime.fromisoformat('2026-10-07T15:02:00+00:00')


def capacity(daily=7500, minute=300):
    return {'interpretation_status':'NORMALIZED','daily_remaining':daily,'minute_remaining':minute}


def provider_offer(age=2):
    state, _, rates = live_data()
    row = {'fixture':{'id':7,'status':{'elapsed':60}},
           'teams':{'home':{'goals':0},'away':{'goals':0}},
           'update':(START-timedelta(seconds=age)).isoformat(),
           'status':{'blocked':False,'stopped':False,'finished':False},
           'odds':[{'id':36,'name':'Over/Under Line',
                    'values':[{'value':'Over','handicap':'1.5','odd':'2.0','main':False,'suspended':False}]}]}
    catalog={'endpoint':'/odds/live/bets','response':[{'id':36,'name':'Over/Under Line'},
            {'id':59,'name':'Fulltime Result'},{'id':69,'name':'Both Teams to Score'}]}
    return state, rates, row, catalog


def test_feed_mode_is_explicit_and_never_fabricates_a_bookmaker():
    state, rates, row, catalog = provider_offer()
    assert normalize_quotes({'response':[row]},state,catalog,retrieved_at=START)[0] == []
    quotes, _ = normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)
    quote = quotes[0]
    assert quote['bookmaker'] is None and quote['bookmaker_id'] is None
    assert quote['quote_origin_kind'] == 'API_FOOTBALL_FEED_UPDATE_V1'
    assert quote['origin_timestamp'] == row['update'] != quote['retrieved_at']
    assert 'LIVE_BOOKMAKER_OR_MARKET_PROVENANCE_MISSING' in readiness(state,quote,.6,uncertainty=.07,now=START)
    assert readiness(state,quote,.6,uncertainty=.07,now=START,allow_provider_feed=True) == []


@pytest.mark.parametrize('age,blocked',[(20,False),(20.001,True),(36,True),(-1,True)])
def test_feed_keeps_exact_twenty_second_guard(age,blocked):
    state, _, row, catalog = provider_offer(age)
    quotes, _ = normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)
    assert ('STALE_LIVE_ODDS' in readiness(state,quotes[0],.6,uncertainty=.07,now=START,allow_provider_feed=True)) == blocked


@pytest.mark.parametrize('field,bad',[('source_identity','another-provider'),('provider_payload_fingerprint',''),
    ('provider_update_timestamp',None),('live_market_id',1),('bookmaker_id',99),('bookmaker','invented')])
def test_feed_provenance_failures_cannot_be_repaired_by_rehashing(field,bad):
    state, _, row, catalog = provider_offer()
    quote=normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)[0][0]
    quote[field]=bad
    quote['quote_fingerprint']=digest({k:v for k,v in quote.items() if k!='quote_fingerprint'})
    assert 'LIVE_BOOKMAKER_OR_MARKET_PROVENANCE_MISSING' in readiness(state,quote,.6,uncertainty=.07,now=START,allow_provider_feed=True)


def test_actual_names_and_ids_not_prematch_team_or_quarter_markets():
    state, _, row, catalog = provider_offer()
    row['odds'] += [{'id':59,'name':'Fulltime Result','values':[{'value':'Home','odd':'2.0'}]},
                    {'id':69,'name':'Both Teams to Score','values':[{'value':'Yes','odd':'2.0'}]},
                    {'id':5,'name':'Over/Under Line','values':[{'value':'Over','handicap':'1.5','odd':'2.0'}]}]
    row['odds'][0]['values'] += [{'value':'Under','handicap':'1.75','odd':'2.0'}]
    catalog['response'].append({'id':5,'name':'Over/Under Line'})
    quotes, reasons = normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)
    assert {q['market'] for q in quotes} == {'OVER_1_5','HOME_WIN','BTTS_YES'}
    assert 'UNSUPPORTED_LIVE_MARKET' in reasons


def test_duplicate_values_need_exactly_one_primary_but_unique_false_is_valid():
    state, _, row, catalog=provider_offer()
    values=row['odds'][0]['values']
    values.append({**values[0],'odd':'2.2'})
    quotes,reasons=normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)
    assert quotes==[] and 'AMBIGUOUS_LIVE_MAIN_VALUE' in reasons
    values[0]['main']=True
    quotes,_=normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)
    assert [q['decimal_odds'] for q in quotes] == ['2.0']


def test_feed_candidate_message_and_immutable_source(repo,monkeypatch):
    from app.adaptive_lab.governance import Governance
    from app.live_lab.presentation import prediction_message
    monkeypatch.setattr(Governance,'safe_resolve',lambda *a,**k:pytest.fail('automatic rollback resolver'))
    state,rates,row,catalog=provider_offer()
    quote=normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)[0][0]
    service=LiveService(repo,clock=lambda:START,allow_provider_feed=True)
    candidate=service.candidate(state,quote,rates,now=START)
    assert not candidate['blockers']
    message=prediction_message(candidate)
    assert 'API-Football' in message and 'bukmeikers nav norādīts' in message
    assert candidate['quote']['origin_timestamp']==row['update']
    assert candidate['bookmaker_id'] is None
    assert not repo.all('training_runs') and not repo.all('champion_generations')


@pytest.mark.parametrize('instant,slots,live',[
    ('2026-10-07T06:59:59+00:00',0,False),
    ('2026-10-07T07:00:00+00:00',16,False),
    ('2026-10-07T14:59:59+00:00',1,False),
    ('2026-10-07T15:00:00+00:00',0,True),
    ('2026-10-07T20:00:00+00:00',0,False),
    ('2026-12-01T08:00:00+00:00',16,False),
    ('2026-12-01T16:00:00+00:00',0,True),
])
def test_application_clock_uses_riga_and_excludes_eighteen(monkeypatch,instant,slots,live):
    from app.lab_v2_shadow.quota import discovery_cycles_remaining
    from app.lab_combo.publication_window import publication_blocker
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    now=datetime.fromisoformat(instant)
    assert discovery_cycles_remaining(now)==slots
    assert daypart.live_window(now)==live
    kickoff=now.astimezone(daypart.RIGA).replace(hour=21)
    assert (publication_blocker(now,[kickoff]) is None)==(slots>0)


def test_shared_quota_protects_results_even_from_live_settlement(repo,monkeypatch):
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    quota=SharedQuota(repo)
    reserve=daypart.prematch_results_reserve(CLOCK)
    assert reserve==1155
    for category in ('LIVE_ODDS','LIVE_REFRESH','LIVE_STATE','LIVE_SETTLEMENT'):
        with pytest.raises(FootballQuotaError,match='PROTECTED_QUOTA_RESERVE'):
            quota.claim(category,now=CLOCK,provider=capacity(reserve))
    # PREMATCH results retain access; LIVE cannot consume the protected allocation.
    assert quota.claim('SETTLEMENT',now=CLOCK,provider=capacity(1))['protected_reserve']==0
    for category in ('PREMATCH_DISCOVERY','PREMATCH_REVIEW','STATUS'):
        with pytest.raises(FootballQuotaError,match='PREMATCH_DISCOVERY_WINDOW_CLOSED'):
            quota.claim(category,now=CLOCK,provider=capacity())


def test_live_http_window_results_continue_after_twenty_three(repo,monkeypatch):
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    after=CLOCK.replace(hour=21)
    quota=SharedQuota(repo)
    with pytest.raises(FootballQuotaError,match='LIVE_DISCOVERY_WINDOW_CLOSED'):
        quota.claim('LIVE_ODDS',now=after,provider=capacity())
    assert quota.claim('LIVE_SETTLEMENT',now=after,provider=capacity())
    assert quota.claim('SETTLEMENT',now=after,provider=capacity())


def test_discovery_pacing_retains_evening_allocation(monkeypatch):
    from app.lab_v2_shadow.quota import adaptive_quota_budget
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    now=CLOCK.replace(hour=7,minute=0)
    result=adaptive_quota_budget(capacity(),requested_maximum=400,already_consumed=1,now=now)
    assert result.remaining_discovery_cycles==16
    assert result.daily_safety_reserve==daypart.prematch_results_reserve(now)+1800
    assert result.additional_calls_available==(7500-result.daily_safety_reserve)//16


def test_worker_accounts_status_before_http_without_automatic_learning(repo,monkeypatch):
    from app.football.client import FootballClient
    from app.adaptive_lab.coordinator import LearningCoordinator
    from app.adaptive_lab.worker import live_cycle
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    monkeypatch.setenv('GOALVISION_LIVE_API_FEED_QUOTES','1')
    monkeypatch.setattr(LearningCoordinator,'__init__',lambda *a,**k:pytest.fail('automatic learning'))
    requests=[]
    def response(request):
        requests.append(request.url.path)
        assert len(repo.all('quota_claims'))==len(requests)
        assert repo.all('quota_claims')[0]['category']=='LIVE_SETTLEMENT'
        return httpx.Response(200,json={'errors':[],'response':[]},headers={
            'x-ratelimit-requests-limit':'7500','x-ratelimit-requests-remaining':'7000',
            'x-ratelimit-limit':'300','x-ratelimit-remaining':'299'})
    original=FootballClient.__init__
    def init(self,*args,**kwargs):
        original(self,*args,api_key='synthetic-offline-key',**kwargs)
        self._client=httpx.AsyncClient(base_url=self.BASE_URL,transport=httpx.MockTransport(response))
        self._minimum_request_interval=0
    monkeypatch.setattr(FootballClient,'__init__',init)
    result=asyncio.run(live_cycle(repo,send=False,clock=lambda:CLOCK))
    assert result['api_calls']==2 and result['automatic_training'] is False
    assert requests==['/status','/fixtures']
    assert repo.all('training_runs')==repo.all('activation_events')==repo.all('rollback_events')==[]


def test_idle_worker_has_no_provider_or_telegram_capability(repo,monkeypatch):
    from app.adaptive_lab.worker import live_cycle
    from app.football.client import FootballClient
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    monkeypatch.setattr(FootballClient,'__init__',lambda *a,**k:pytest.fail('unnecessary provider construction'))
    result=asyncio.run(live_cycle(repo,send=True,clock=lambda:CLOCK.replace(hour=7)))
    assert result['status']=='LIVE_IDLE_NO_PENDING_RESULTS' and result['api_calls']==0


def test_live_settlement_never_reads_prematch_shadow(repo):
    from app.live_lab.runner import LiveRunner
    class OnlyLive:
        def all(self,table,stream=None):
            assert stream=='LIVE'
            return []
    service=SimpleNamespace(repository=OnlyLive())
    runner=LiveRunner(service,SimpleNamespace(),SharedQuota(repo),clock=lambda:CLOCK)
    assert asyncio.run(runner.settle())==[]


def test_evening_mode_removes_fixed_live_cap_but_not_account_limits(repo,monkeypatch):
    with repo.transaction():
        for i in range(1800):
            stamp=(CLOCK-timedelta(hours=3)+timedelta(seconds=i)).isoformat()
            repo.append('quota_claims',f'prior-{i}','LIVE',{'category':'LIVE_STATE','created_at':stamp},stamp)
    shared=SharedQuota(repo)
    monkeypatch.delenv('GOALVISION_LAB_EVENING_MODE',raising=False)
    with pytest.raises(FootballQuotaError,match='LIVE_DAILY_CAP'):
        shared.claim('LIVE_ODDS',now=CLOCK,provider=capacity())
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    assert shared.claim('LIVE_ODDS',now=CLOCK,provider=capacity())['remaining_daily_before']==5700
    with pytest.raises(FootballQuotaError,match='PROTECTED_QUOTA_RESERVE'):
        shared.claim('LIVE_ODDS',now=CLOCK,provider=capacity(minute=0))


def test_feed_full_refresh_claim_result_reply_and_duplicate_protection(repo):
    from app.lab_telegram.models import LabTelegramConfig
    state,rates,row,catalog=provider_offer()
    quote=normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)[0][0]
    clock=[START]
    service=LiveService(repo,clock=lambda:clock[0],allow_provider_feed=True)
    candidate=service.candidate(state,quote,rates,now=START)
    config=LabTelegramConfig(token='fake',chat_id='-1003510920417',automatic_enabled=True,official_destinations=frozenset())
    calls=[]
    class RecordingTransport:
        async def send_message_receipt(self,**kw):
            calls.append(kw)
            return SimpleNamespace(chat_id=kw['chat_id'],message_id=41+len(calls))
    async def refresh(identity):
        assert identity==7
        return state,[quote],rates
    transport=RecordingTransport()
    assert asyncio.run(service.publish(candidate['prediction_id'],config,transport,refresh=refresh))['sent']
    assert not asyncio.run(service.publish(candidate['prediction_id'],config,transport,refresh=refresh))['sent']
    clock[0]+=timedelta(hours=1)
    payload={'response':[{'fixture':{'id':7,'status':{'short':'FT'}},'score':{'fulltime':{'home':2,'away':1}}}]}
    assert service.settle(candidate['prediction_id'],payload,now=clock[0])['status']=='WON'
    assert asyncio.run(service.publish_result(candidate['prediction_id'],config,transport))['sent']
    assert len(calls)==2 and calls[-1]['reply_to_message_id']==42
    assert 'orientējošā API-Football' in calls[-1]['text']
    assert len(repo.all('learning_observations','LIVE'))==1
    assert not repo.all('learning_observations','PREMATCH')
    assert not repo.all('training_runs') and not repo.all('champion_generations')


def test_feed_stale_final_refresh_creates_no_claim_or_send(repo):
    from app.lab_telegram.models import LabTelegramConfig
    state,rates,row,catalog=provider_offer()
    quote=normalize_quotes({'response':[row]},state,catalog,retrieved_at=START,allow_provider_feed=True)[0][0]
    service=LiveService(repo,clock=lambda:START,allow_provider_feed=True)
    candidate=service.candidate(state,quote,rates,now=START)
    stale={**quote,'origin_timestamp':(START-timedelta(seconds=21)).isoformat(),
           'provider_update_timestamp':(START-timedelta(seconds=21)).isoformat()}
    stale['quote_fingerprint']=digest({k:v for k,v in stale.items() if k!='quote_fingerprint'})
    async def refresh(identity):return state,[stale],rates
    config=LabTelegramConfig(token='fake',chat_id='-1003510920417',automatic_enabled=True,official_destinations=frozenset())
    result=asyncio.run(service.publish(candidate['prediction_id'],config,None,refresh=refresh))
    assert not result['sent'] and 'STALE_LIVE_ODDS' in result['blockers']
    assert repo.all('live_claims')==repo.all('live_publications')==[]


def test_report_projection_uses_the_active_sixteen_slot_schedule(monkeypatch):
    from app.lab_v2_shadow.quota import projected_daily_usage
    monkeypatch.setenv('GOALVISION_LAB_EVENING_MODE','1')
    assert projected_daily_usage(maximum_per_cycle=400)['discovery_cycles']==16
    monkeypatch.delenv('GOALVISION_LAB_EVENING_MODE')
    assert projected_daily_usage(maximum_per_cycle=400)['discovery_cycles']==28
