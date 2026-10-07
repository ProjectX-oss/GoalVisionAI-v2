"""Current API-Football LIVE adapters. PREMATCH IDs/prices are never accepted.

Strict mode requires bookmaker identity. Explicit provider-feed mode represents
missing identity as unknown and the update field as a provider snapshot timestamp.
No mode replaces source timestamps with retrieval time or relaxes freshness.
"""
from __future__ import annotations
from datetime import datetime
from app.adaptive_lab.contracts import digest, number, utc

# Reviewed current LIVE ID/name pairs. Legacy attributed-quote adapters remain
# compatible, but provider-feed mode accepts only this real LIVE catalog allowlist.
REAL_LIVE_MARKETS = {59: 'Fulltime Result', 69: 'Both Teams to Score', 36: 'Over/Under Line'}
SUPPORTED_NAMES=frozenset({'Fulltime Result','Match Winner','Both Teams To Score','Goals Over/Under', *REAL_LIVE_MARKETS.values()})
FEED_SOURCE = 'API_FOOTBALL:/odds/live'
FEED_ORIGIN = 'API_FOOTBALL_FEED_UPDATE_V1'


def feed_provenance(quote: dict) -> bool:
    """Truthful provider attribution; never a substitute/fabricated bookmaker ID."""
    fingerprint = quote.get('provider_payload_fingerprint')
    return (quote.get('source_identity') == FEED_SOURCE
            and quote.get('quote_origin_kind') == FEED_ORIGIN
            and quote.get('bookmaker') is None and quote.get('bookmaker_id') is None
            and quote.get('bookmaker_verified') is False
            and quote.get('provider_update_timestamp') == quote.get('origin_timestamp')
            and quote.get('live_market_id') in REAL_LIVE_MARKETS
            and quote.get('live_market_name') == REAL_LIVE_MARKETS.get(quote.get('live_market_id'))
            and isinstance(fingerprint, str) and len(fingerprint) == 64
            and all(c in '0123456789abcdef' for c in fingerprint))


def normalize_quotes(payload: dict, state: dict, catalog: dict, *, retrieved_at: datetime,
                     allow_provider_feed: bool = False) -> tuple[list[dict],list[str]]:
    if catalog.get('endpoint')!='/odds/live/bets' or not isinstance(catalog.get('response'),list):
        return [],['LIVE_MARKET_CATALOG_REQUIRED']
    ids={r['id']:r['name'] for r in catalog['response'] if r.get('name') in SUPPORTED_NAMES
         and (not allow_provider_feed or REAL_LIVE_MARKETS.get(r.get('id')) == r.get('name'))}
    if payload.get('errors') or not isinstance(payload.get('response'),list):
        return [],['LIVE_ODDS_PROVIDER_UNAVAILABLE']
    quotes,diagnostics=[],[]
    for row in payload['response']:
        fixture=row.get('fixture') or {}
        if fixture.get('id')!=state['fixture_id']:
            continue
        status=row.get('status') or {}
        teams=row.get('teams') or {}
        score=tuple((teams.get(k) or {}).get('goals') for k in ('home','away'))
        if score!=(state['home_score'],state['away_score']) or fixture.get('status',{}).get('elapsed')!=state['minute']:
            diagnostics.append('LIVE_STATE_QUOTE_MISMATCH'); continue
        bookmaker=row.get('bookmaker') or {}
        origin=row.get('update')
        attributed = bool(bookmaker.get('id') and bookmaker.get('name'))
        if not origin or (not attributed and not allow_provider_feed):
            diagnostics.append('LIVE_BOOKMAKER_OR_ORIGIN_UNAVAILABLE'); continue
        for bet in row.get('odds',[]):
            if bet.get('id') not in ids or bet.get('name')!=ids[bet['id']]:
                diagnostics.append('UNSUPPORTED_LIVE_MARKET'); continue
            grouped = {}
            for value in bet.get('values', []):
                market = _market(bet['name'], value)
                if market is not None:
                    grouped.setdefault(market, []).append(value)
            for market, values in grouped.items():
                # Provider docs: a unique value may have main=false/null. Only
                # duplicate values require one explicit primary; never pick a price.
                primary = [v for v in values if v.get('main') is True]
                if len(values) > 1 and len(primary) != 1:
                    diagnostics.append('AMBIGUOUS_LIVE_MAIN_VALUE'); continue
                value = primary[0] if len(values) > 1 else values[0]
                try:
                    odds=number(value['odd'],low=1,high=10000)
                    utc(origin)
                    if odds<=1:
                        continue
                except (ValueError,KeyError,TypeError):
                    diagnostics.append('LIVE_ODDS_INVALID'); continue
                quote={'fixture_id':state['fixture_id'],'state_fingerprint':state['state_fingerprint'],
                       'market':market,'decimal_odds':str(value['odd']),
                       'bookmaker_id':bookmaker['id'] if attributed else None,
                       'bookmaker':bookmaker['name'] if attributed else None,
                       'market_identity':f"live:{bet['id']}:{value.get('value')}:{value.get('handicap')}",
                       'origin_timestamp':origin,'retrieved_at':utc(retrieved_at).isoformat(),
                       'provider_type':'API_FOOTBALL_LIVE_ODDS','endpoint':'/odds/live',
                       'blocked':status.get('blocked') is not False,'stopped':status.get('stopped') is not False,
                       'finished':status.get('finished') is not False,'suspended':value.get('suspended',False) is not False,
                       'provider_payload_fingerprint':digest(payload)}
                if not attributed:
                    quote.update(source_identity=FEED_SOURCE, quote_origin_kind=FEED_ORIGIN,
                                 bookmaker_verified=False, provider_update_timestamp=origin,
                                 live_market_id=bet['id'], live_market_name=bet['name'])
                quote['quote_fingerprint']=digest(quote)
                quotes.append(quote)
    return sorted(quotes,key=lambda q:(q['market'],-float(q['decimal_odds']),q['quote_fingerprint'])),sorted(set(diagnostics))


def _market(name: str, value: dict) -> str | None:
    side=str(value.get('value','')).lower()
    if name in {'Fulltime Result','Match Winner'}:
        return {'home':'HOME_WIN','draw':'DRAW','away':'AWAY_WIN','1':'HOME_WIN','x':'DRAW','2':'AWAY_WIN'}.get(side)
    if name in {'Both Teams To Score', 'Both Teams to Score'}:
        return {'yes':'BTTS_YES','no':'BTTS_NO'}.get(side)
    if name in {'Goals Over/Under', 'Over/Under Line'} and side in {'over','under'} and str(value.get('handicap')) in {'1.5','2.5','3.5'}:
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
