"""Current API-Football LIVE adapters. PREMATCH IDs/prices are never accepted.

The live feed can omit bookmaker identity or origin time. Such rows are explicitly
unpublishable; retrieval time is not silently substituted for provider origin time.
"""
from __future__ import annotations
from datetime import datetime
from app.adaptive_lab.contracts import digest, number, utc

# Name AND live catalog ID must agree; operators can provide a reviewed catalog
# snapshot from /odds/live/bets, never the prematch /odds/bets catalog.
SUPPORTED_NAMES=frozenset({'Fulltime Result','Match Winner','Both Teams To Score','Goals Over/Under'})


def normalize_quotes(payload: dict, state: dict, catalog: dict, *, retrieved_at: datetime) -> tuple[list[dict],list[str]]:
    if catalog.get('endpoint')!='/odds/live/bets' or not isinstance(catalog.get('response'),list):
        return [],['LIVE_MARKET_CATALOG_REQUIRED']
    ids={r['id']:r['name'] for r in catalog['response'] if r.get('name') in SUPPORTED_NAMES}
    if payload.get('errors') or not isinstance(payload.get('response'),list):
        return [],['LIVE_ODDS_PROVIDER_UNAVAILABLE']
    quotes,diagnostics=[],[]
    for row in payload['response']:
        fixture=row.get('fixture') or {}
        if fixture.get('id')!=state['fixture_id']:
            continue
        status=row.get('status') or {}
        # A price must describe the same live score and minute, not a prior goal state.
        teams=row.get('teams') or {}
        score=tuple((teams.get(k) or {}).get('goals') for k in ('home','away'))
        if score!=(state['home_score'],state['away_score']) or fixture.get('status',{}).get('elapsed')!=state['minute']:
            diagnostics.append('LIVE_STATE_QUOTE_MISMATCH'); continue
        bookmaker=row.get('bookmaker') or {}
        origin=row.get('update')
        if not bookmaker.get('id') or not bookmaker.get('name') or not origin:
            diagnostics.append('LIVE_BOOKMAKER_OR_ORIGIN_UNAVAILABLE'); continue
        for bet in row.get('odds',[]):
            if bet.get('id') not in ids or bet.get('name')!=ids[bet['id']]:
                diagnostics.append('UNSUPPORTED_LIVE_MARKET'); continue
            for value in bet.get('values',[]):
                market=_market(bet['name'],value)
                if market is None or value.get('main') is False:
                    continue
                try:
                    odds=number(value['odd'],low=1,high=10000)
                    utc(origin)
                    if odds<=1:
                        continue
                except (ValueError,KeyError,TypeError):
                    diagnostics.append('LIVE_ODDS_INVALID'); continue
                quote={'fixture_id':state['fixture_id'],'state_fingerprint':state['state_fingerprint'],
                       'market':market,'decimal_odds':str(value['odd']),
                       'bookmaker_id':bookmaker['id'],'bookmaker':bookmaker['name'],
                       'market_identity':f"live:{bet['id']}:{value.get('value')}:{value.get('handicap')}",
                       'origin_timestamp':origin,'retrieved_at':utc(retrieved_at).isoformat(),
                       'provider_type':'API_FOOTBALL_LIVE_ODDS','endpoint':'/odds/live',
                       'blocked':status.get('blocked',True),'stopped':status.get('stopped',True),
                       'finished':status.get('finished',True),'suspended':value.get('suspended',False),
                       'provider_payload_fingerprint':digest(payload)}
                quote['quote_fingerprint']=digest(quote)
                quotes.append(quote)
    return sorted(quotes,key=lambda q:(q['market'],-float(q['decimal_odds']),q['quote_fingerprint'])),sorted(set(diagnostics))


def _market(name: str, value: dict) -> str | None:
    side=str(value.get('value','')).lower()
    if name in {'Fulltime Result','Match Winner'}:
        return {'home':'HOME_WIN','draw':'DRAW','away':'AWAY_WIN','1':'HOME_WIN','x':'DRAW','2':'AWAY_WIN'}.get(side)
    if name=='Both Teams To Score':
        return {'yes':'BTTS_YES','no':'BTTS_NO'}.get(side)
    if name=='Goals Over/Under' and side in {'over','under'} and str(value.get('handicap')) in {'1.5','2.5','3.5'}:
        return side.upper()+'_'+str(value['handicap']).replace('.','_')
    return None


def history_rates(state: dict, home_payload: dict, away_payload: dict, *, retrieved_at: datetime) -> dict:
    """Compute actual observed scoring/conceding rates; exclude this and later fixtures."""
    def rate(payload: dict, team: int) -> tuple[float,float,int]:
        if payload.get('errors'):
            raise ValueError('LIVE_HISTORY_UNAVAILABLE')
        scores=[]
        for row in payload.get('response',[]):
            fixture=row.get('fixture') or {}
            if (fixture.get('id')==state['fixture_id'] or (fixture.get('status') or {}).get('short')!='FT'
                or utc(fixture['date'])>=utc(state['kickoff_utc'])):
                continue
            teams=row.get('teams') or {}
            goals=(row.get('score') or {}).get('fulltime') or {}
            home=(teams.get('home') or {}).get('id')==team
            away=(teams.get('away') or {}).get('id')==team
            if not home and not away:
                continue
            a,b=goals.get('home'),goals.get('away')
            if not all(type(v) is int and 0<=v<=30 for v in (a,b)):
                continue
            scores.append((a,b) if home else (b,a))
        if not scores:
            raise ValueError('LIVE_HISTORY_UNAVAILABLE')
        return sum(s[0] for s in scores)/len(scores),sum(s[1] for s in scores)/len(scores),len(scores)
    hs,hc,hn=rate(home_payload,state['home_team_id'])
    ass,ac,an=rate(away_payload,state['away_team_id'])
    return {'home_goal_rate':(hs+ac)/2,'away_goal_rate':(ass+hc)/2,'home_sample':hn,'away_sample':an,
            'available_at':utc(retrieved_at).isoformat(),'source_fingerprint':digest([home_payload,away_payload]),
            'frozen_history_payloads':[home_payload,away_payload]}
