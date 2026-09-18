from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
import pytest
from app.adaptive_lab.contracts import digest
from app.live_lab.engine import state_snapshot,attach_events,readiness,remaining_goal_probabilities
from app.live_lab.service import LiveService
from app.live_lab.provider import normalize_quotes
from app.live_lab.presentation import prediction_message,settlement_message
from app.lab_telegram.models import LabTelegramConfig
from .conftest import START


def live_data():
    row={'fixture':{'id':7,'date':(START-timedelta(hours=1)).isoformat(),'status':{'short':'2H','elapsed':60}},
         'goals':{'home':0,'away':0},'league':{'id':39},
         'teams':{'home':{'id':1,'name':'Home'},'away':{'id':2,'name':'Away'}}}
    state=attach_events(state_snapshot(row,retrieved_at=START),{'response':[]},retrieved_at=START)
    quote={'fixture_id':7,'state_fingerprint':state['state_fingerprint'],'market':'OVER_1_5','decimal_odds':'2.0',
           'bookmaker_id':1,'bookmaker':'Fictional Test Bookmaker','market_identity':'live:25:over:1.5',
           'origin_timestamp':(START-timedelta(seconds=2)).isoformat(),'retrieved_at':START.isoformat(),
           'provider_type':'API_FOOTBALL_LIVE_ODDS','endpoint':'/odds/live','blocked':False,'stopped':False,
           'finished':False,'suspended':False}
    quote['quote_fingerprint']=digest(quote)
    rates={'home_goal_rate':3.,'away_goal_rate':3.,'home_sample':10,'away_sample':10,
           'source_fingerprint':'test-history','available_at':START.isoformat()}
    return state,quote,rates


@pytest.mark.parametrize('field,value,expected',[
    ('status','NS','FIXTURE_NOT_CONFIRMED_LIVE'),
    ('retrieved_at',(START-timedelta(seconds=31)).isoformat(),'STALE_LIVE_RETRIEVED_AT'),
    ('score_retrieved_at',(START-timedelta(seconds=31)).isoformat(),'STALE_LIVE_SCORE_RETRIEVED_AT'),
    ('minute_retrieved_at',(START-timedelta(seconds=31)).isoformat(),'STALE_LIVE_MINUTE_RETRIEVED_AT'),
    ('event_retrieved_at',(START-timedelta(seconds=31)).isoformat(),'STALE_EVENT_STATE')])
def test_live_freshness_and_status(field,value,expected):
    state,q,r=live_data();state[field]=value
    assert expected in readiness(state,q,.6,uncertainty=.07,now=START)


@pytest.mark.parametrize('field,value,expected',[
    ('provider_type','API_FOOTBALL_CURRENT_ODDS','GENUINE_LIVE_ODDS_REQUIRED'),
    ('origin_timestamp',(START-timedelta(seconds=21)).isoformat(),'STALE_LIVE_ODDS'),
    ('market','NEXT_GOAL','UNSUPPORTED_MARKET'),('blocked',True,'LIVE_MARKET_SUSPENDED'),
    ('bookmaker_id',None,'LIVE_BOOKMAKER_OR_MARKET_PROVENANCE_MISSING')])
def test_live_quote_gates(field,value,expected):
    state,q,r=live_data();q[field]=value
    assert expected in readiness(state,q,.6,uncertainty=.07,now=START)


@pytest.mark.parametrize('probability',[.5,.4,0.,1.,float('nan')])
def test_nonpositive_ev_or_probability_contract_rejected(probability):
    s,q,r=live_data()
    assert readiness(s,q,probability,uncertainty=.07,now=START)


def test_baseline_optional_missing_market_resolved_and_transitions():
    state,q,r=live_data()
    p=remaining_goal_probabilities(state,r)['OVER_1_5']
    assert p==pytest.approx(1-3*__import__('math').exp(-2))
    assert readiness(state,q,p,uncertainty=.07,now=START)==[]
    prior={'fixture_id':7,'market':'OVER_1_5','state':deepcopy(state),'captured_odds':'2.0'}
    assert 'DUPLICATE_LIVE_OPPORTUNITY' in readiness(state,q,p,uncertainty=.07,now=START,previous=[prior])
    state['home_score']=1
    assert 'DUPLICATE_LIVE_OPPORTUNITY' not in readiness(state,q,p,uncertainty=.07,now=START,previous=[prior])
    state['home_score']=0;state['red_cards_home']=1
    assert 'DUPLICATE_LIVE_OPPORTUNITY' not in readiness(state,q,p,uncertainty=.07,now=START,previous=[prior])
    state['home_score']=2
    assert 'MARKET_ALREADY_RESOLVED' in readiness(state,q,p,uncertainty=.07,now=START)


def test_live_bookmaker_missing_never_invented():
    s,q,r=live_data()
    payload={'response':[{'fixture':{'id':7,'status':{'elapsed':60}},'teams':{'home':{'goals':0},'away':{'goals':0}},
                          'status':{'blocked':False,'stopped':False,'finished':False},'odds':[]}]}
    quotes,reasons=normalize_quotes(payload,s,{'endpoint':'/odds/live/bets','response':[]},retrieved_at=START)
    assert quotes==[] and reasons==['LIVE_BOOKMAKER_OR_ORIGIN_UNAVAILABLE']


def test_live_fake_publication_settlement_and_no_official(repo):
    state,q,rates=live_data()
    clock=[START]
    service=LiveService(repo,clock=lambda:clock[0])
    candidate=service.candidate(state,q,rates,now=START)
    message=prediction_message(candidate)
    assert all(t in message for t in ('GOALVISION LIVE',"60'",'0–0','LIVE odds','EXPERIMENTAL'))
    config=LabTelegramConfig(token='fake',chat_id='-1003510920417',automatic_enabled=True,official_destinations=frozenset())
    class Transport:
        sends=[]
        async def send_message_receipt(self,**kw):
            self.sends.append(kw)
            clock[0]=START+timedelta(seconds=1)
            return SimpleNamespace(chat_id=kw['chat_id'],message_id=1)
    async def refresh(identity): return state,[q],rates
    transport=Transport()
    receipt=asyncio.run(service.publish(candidate['prediction_id'],config,transport,refresh=refresh))
    assert receipt['sent'] and len(transport.sends)==1
    assert transport.sends[0]['chat_id']=='-1003510920417'
    assert repo.all('combo_analytics')==[] and repo.all('learning_observations','PREMATCH')==[]
    result={'response':[{'fixture':{'id':7,'status':{'short':'FT'}},'score':{'fulltime':{'home':2,'away':1}}}]}
    clock[0]=START+timedelta(hours=1)
    settled=service.settle(candidate['prediction_id'],result,now=clock[0])
    assert settled['status']=='WON' and len(repo.all('learning_observations','LIVE'))==1
    assert service.settle(candidate['prediction_id'],result,now=clock[0])==settled
    result_receipt=asyncio.run(service.publish_result(candidate['prediction_id'],config,transport))
    assert result_receipt['sent'] and '✅ LIVE WON' in transport.sends[-1]['text']


def test_official_config_rejected_before_refresh(repo):
    service=LiveService(repo,clock=lambda:START)
    config=LabTelegramConfig(token='fake',chat_id='@goalvisionai',automatic_enabled=True,official_destinations=frozenset({'@goalvisionai'}))
    async def refresh(identity): raise AssertionError('must not refresh')
    result=asyncio.run(service.publish('unknown',config,None,refresh=refresh))
    assert result['status']=='LAB_CONFIGURATION_REJECTED'


def test_current_live_market_mapping_not_prematch_ids():
    state,quote,rates=live_data()
    catalog={'endpoint':'/odds/live/bets','response':[{'id':25,'name':'Goals Over/Under'}]}
    row={'fixture':{'id':7,'status':{'elapsed':60}},'teams':{'home':{'goals':0},'away':{'goals':0}},
         'bookmaker':{'id':1,'name':'Fictional'},'update':START.isoformat(),
         'status':{'blocked':False,'stopped':False,'finished':False},
         'odds':[{'id':25,'name':'Goals Over/Under','values':[{'value':'Over','handicap':'1.5','odd':'2.0','main':True}]}]}
    quotes,reasons=normalize_quotes({'response':[row]},state,catalog,retrieved_at=START)
    assert len(quotes)==1 and quotes[0]['market']=='OVER_1_5'
    assert readiness(state,quotes[0],.6,uncertainty=.07,now=START)==[]
    catalog['endpoint']='/odds/bets'
    assert normalize_quotes({'response':[row]},state,catalog,retrieved_at=START)[0]==[]


def test_material_time_and_price_rebet_and_max_fixture_bound():
    state,q,r=live_data()
    old={'fixture_id':7,'market':'OVER_1_5','state':deepcopy(state),'captured_odds':'2.0'}
    state['minute']=75
    state['state_fingerprint']=digest({k:v for k,v in state.items() if k!='state_fingerprint'})
    q['state_fingerprint']=state['state_fingerprint'];q['decimal_odds']='2.4'
    q['quote_fingerprint']=digest({k:v for k,v in q.items() if k!='quote_fingerprint'})
    assert readiness(state,q,.6,uncertainty=.07,now=START,previous=[old])==[]
    assert 'LIVE_FIXTURE_SELECTION_LIMIT' in readiness(state,q,.6,uncertainty=.07,now=START,previous=[old]*3)


def test_rate_retrieval_must_precede_prediction_not_initial_live_snapshot():
    state,q,rates=live_data()
    rates['available_at']=(START+timedelta(seconds=2)).isoformat()
    with pytest.raises(ValueError,match='PROVENANCE'):
        remaining_goal_probabilities(state,rates)
    assert remaining_goal_probabilities(state,rates,as_of=START+timedelta(seconds=3))['OVER_1_5']>0


def test_runner_refresh_accepts_real_client_history_list(repo):
    """Exercise FootballClient's actual list-returning history API, without HTTP."""
    import httpx
    from app.football.client import FootballClient
    from app.adaptive_lab.quota import SharedQuota
    from app.live_lab.runner import LiveRunner

    requests=[]
    fixture={'fixture':{'id':7,'date':(START-timedelta(hours=1)).isoformat(),
                        'status':{'short':'2H','elapsed':60}},
             'goals':{'home':0,'away':0},'league':{'id':39},
             'teams':{'home':{'id':1,'name':'Home'},'away':{'id':2,'name':'Away'}}}

    def response(request):
        path=request.url.path
        params=dict(request.url.params)
        requests.append((path,params))
        rows=[]
        if path=='/fixtures' and 'team' in params:
            team=int(params['team'])
            rows=[{'fixture':{'id':100+team*10+i,'date':(START-timedelta(days=i+2)).isoformat(),
                             'status':{'short':'FT'}},
                   'teams':{'home':{'id':team},'away':{'id':99}},
                   'score':{'fulltime':{'home':2,'away':1}}} for i in range(10)]
        elif path=='/fixtures':
            rows=[fixture]
        elif path=='/odds/live/bets':
            rows=[{'id':59,'name':'Fulltime Result'}]
        elif path=='/odds/live':
            # Missing genuine bookmaker/origin evidence must remain fail-closed.
            rows=[{'fixture':{'id':7,'status':{'elapsed':60}},
                   'teams':{'home':{'goals':0},'away':{'goals':0}},'odds':[]}]
        return httpx.Response(200,json={'response':rows,'errors':[]},headers={
            'x-ratelimit-requests-limit':'7500','x-ratelimit-requests-remaining':'7400',
            'x-ratelimit-limit':'300','x-ratelimit-remaining':'299'})

    async def run():
        client=FootballClient(api_key='synthetic-test-key',request_limit=7)
        await client._client.aclose()
        client._client=httpx.AsyncClient(base_url=client.BASE_URL,transport=httpx.MockTransport(response))
        try:
            await client.account_status()
            service=LiveService(repo,clock=lambda:START)
            state,quotes,rates=await LiveRunner(service,client,SharedQuota(repo),clock=lambda:START).refresh(7)
            assert state['fixture_id']==7 and state['events']==[]
            assert rates['home_sample']==rates['away_sample']==10
            assert rates['home_goal_rate']==rates['away_goal_rate']==1.5
            assert len(rates['frozen_history_payloads'][0]['response'])==10
            assert remaining_goal_probabilities(state,rates)['OVER_1_5']>0
            assert quotes==[]
            assert repo.all('live_diagnostics','LIVE')[0]['reasons']==['LIVE_BOOKMAKER_OR_ORIGIN_UNAVAILABLE']
            assert len(repo.all('quota_claims'))==6
            assert client.request_count==7
            assert not repo.all('live_publications')
        finally:
            await client.close()

    asyncio.run(run())
    assert requests[-2:]==[('/odds/live/bets',{}),('/odds/live',{'fixture':'7'})]
