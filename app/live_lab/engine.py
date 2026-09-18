"""Pure in-play state, remaining-goals prediction and immutable opportunity gates."""
from __future__ import annotations
from datetime import datetime
from math import exp, factorial
from app.adaptive_lab.contracts import MARKETS, digest, number, utc
from .policy import POLICY


def state_snapshot(row: dict, *, retrieved_at: datetime) -> dict:
    """Provider retrieval timestamps remain explicit, never presented as origin times."""
    fixture=row.get('fixture') or {}
    status=fixture.get('status') or {}
    goals=row.get('goals') or {}
    if status.get('short') not in POLICY.active_statuses:
        raise ValueError('FIXTURE_NOT_CONFIRMED_LIVE')
    minute=status.get('elapsed')
    if type(minute) is not int or not 0<=minute<=120:
        raise ValueError('LIVE_MINUTE_INVALID')
    if not all(type(goals.get(k)) is int and 0<=goals[k]<=30 for k in ('home','away')):
        raise ValueError('LIVE_SCORE_MISSING')
    if type(fixture.get('id')) is not int or not fixture.get('date'):
        raise ValueError('FIXTURE_IDENTITY_INVALID')
    stamp=utc(retrieved_at).isoformat()
    if utc(fixture['date'])>utc(retrieved_at):
        raise ValueError('FIXTURE_NOT_CONFIRMED_LIVE')
    value={'fixture_id':fixture['id'],'kickoff_utc':fixture['date'],'status':status['short'],
           'minute':minute,'added_time':status.get('extra'),'home_score':goals['home'],'away_score':goals['away'],
           'retrieved_at':stamp,'score_retrieved_at':stamp,'minute_retrieved_at':stamp,
           'provider':'API_FOOTBALL','source_fingerprint':digest(row),
           'league_id':(row.get('league') or {}).get('id'),
           'home_team':((row.get('teams') or {}).get('home') or {}).get('name'),
           'away_team':((row.get('teams') or {}).get('away') or {}).get('name'),
           'home_team_id':((row.get('teams') or {}).get('home') or {}).get('id'),
           'away_team_id':((row.get('teams') or {}).get('away') or {}).get('id'),
           'competition_profile':row.get('competition_profile','UNKNOWN'),
           'events':None,'event_retrieved_at':None,'red_cards_home':None,'red_cards_away':None,
           'optional_features':{}}
    value['state_fingerprint']=digest(value)
    return value


def attach_events(state: dict, payload: dict, *, retrieved_at: datetime) -> dict:
    """Fresh empty event arrays are valid evidence; absent arrays are not invented zeros."""
    events=payload.get('response')
    if payload.get('errors') or not isinstance(events,list):
        raise ValueError('LIVE_EVENT_STATE_UNAVAILABLE')
    red={state['home_team_id']:0,state['away_team_id']:0}
    for event in events:
        elapsed=(event.get('time') or {}).get('elapsed')
        if type(elapsed) is not int or elapsed>state['minute']:
            raise ValueError('FUTURE_EVENT_STATE_CONFLICT')
        if event.get('type')=='Card' and event.get('detail') in {'Red Card','Second Yellow card'}:
            team=(event.get('team') or {}).get('id')
            if team not in red:
                raise ValueError('EVENT_FIXTURE_IDENTITY_CONFLICT')
            red[team]+=1
    value={k:v for k,v in state.items() if k!='state_fingerprint'}
    value.update(events=events,event_retrieved_at=utc(retrieved_at).isoformat(),
                 event_source_fingerprint=digest(payload),red_cards_home=red[state['home_team_id']],
                 red_cards_away=red[state['away_team_id']])
    value['state_fingerprint']=digest(value)
    return value


def remaining_goal_probabilities(state: dict, rates: dict, *, as_of: datetime | None = None) -> dict[str,float]:
    """Reviewed independent LIVE Poisson baseline from frozen pre-snapshot team rates.

    Rates must originate from observed team history, never default league averages.
    Red-card context reduces certainty at readiness; no invented effect multiplier.
    """
    if not rates.get('source_fingerprint') or utc(rates['available_at'])>utc(as_of or state['retrieved_at']):
        raise ValueError('LIVE_RATE_PROVENANCE_MISSING')
    if min(rates['home_sample'],rates['away_sample'])<POLICY.minimum_history:
        raise ValueError('LIVE_RATE_SAMPLE_INSUFFICIENT')
    remaining=max(0,90-state['minute'])/90
    home_rate=number(rates['home_goal_rate'],low=.01,high=6)*remaining
    away_rate=number(rates['away_goal_rate'],low=.01,high=6)*remaining
    # Finite Poisson tail is normalized; at these bounded rates residual is negligible.
    hp=[exp(-home_rate)*home_rate**i/factorial(i) for i in range(32)]
    ap=[exp(-away_rate)*away_rate**i/factorial(i) for i in range(32)]
    hp=[v/sum(hp) for v in hp]; ap=[v/sum(ap) for v in ap]
    result={k:0. for k in MARKETS}
    from app.current_odds_forward_test.service import _won
    for h,p in enumerate(hp):
        for a,q in enumerate(ap):
            for market in MARKETS:
                if _won(market,h+state['home_score'],a+state['away_score']):
                    result[market]+=p*q
    return {k:max(0,min(1,v)) for k,v in result.items()}


def resolved_market(market: str, state: dict) -> bool:
    total=state['home_score']+state['away_score']
    if market.startswith(('OVER_','UNDER_')):
        return total>float(market.split('_')[1]+'.'+market.split('_')[2])
    if market.startswith('BTTS_'):
        return state['home_score']>0 and state['away_score']>0
    return False


def readiness(state: dict, quote: dict, probability: float, *, uncertainty: float, now: datetime,
              previous: list[dict] = ()) -> list[str]:
    """All hard gates operate outside model artifacts and cannot be optimized away."""
    reasons=[]
    if state.get('state_fingerprint') != digest({k:v for k,v in state.items() if k!='state_fingerprint'}):
        reasons.append('LIVE_STATE_INTEGRITY_FAILURE')
    if quote.get('quote_fingerprint') != digest({k:v for k,v in quote.items() if k!='quote_fingerprint'}):
        reasons.append('LIVE_QUOTE_INTEGRITY_FAILURE')
    def fresh(value: str | None, seconds: int) -> bool:
        if not value:
            return False
        try:
            return 0<=(utc(now)-utc(value)).total_seconds()<=seconds
        except (ValueError,TypeError):
            return False
    if state['status'] not in POLICY.active_statuses:
        reasons.append('FIXTURE_NOT_CONFIRMED_LIVE')
    for name in ('retrieved_at','score_retrieved_at','minute_retrieved_at'):
        if not fresh(state.get(name),POLICY.state_age_seconds):
            reasons.append('STALE_LIVE_'+name.upper())
    if state.get('events') is None or not fresh(state.get('event_retrieved_at'),POLICY.event_age_seconds):
        reasons.append('STALE_EVENT_STATE')
    if quote.get('provider_type')!='API_FOOTBALL_LIVE_ODDS' or quote.get('endpoint')!='/odds/live':
        reasons.append('GENUINE_LIVE_ODDS_REQUIRED')
    if not fresh(quote.get('origin_timestamp'),POLICY.quote_age_seconds) or not fresh(quote.get('retrieved_at'),POLICY.quote_age_seconds):
        reasons.append('STALE_LIVE_ODDS')
    try:
        if utc(quote['origin_timestamp'])>utc(quote['retrieved_at']):
            reasons.append('LIVE_QUOTE_TIME_ORDER_INVALID')
    except (KeyError,ValueError,TypeError):
        reasons.append('STALE_LIVE_ODDS')
    if quote.get('fixture_id')!=state['fixture_id'] or quote.get('state_fingerprint')!=state['state_fingerprint']:
        reasons.append('LIVE_STATE_QUOTE_MISMATCH')
    market=quote.get('market')
    if market not in MARKETS:
        reasons.append('UNSUPPORTED_MARKET')
    elif resolved_market(market,state):
        reasons.append('MARKET_ALREADY_RESOLVED')
    if not quote.get('bookmaker_id') or not quote.get('bookmaker') or not quote.get('market_identity'):
        reasons.append('LIVE_BOOKMAKER_OR_MARKET_PROVENANCE_MISSING')
    if quote.get('blocked') or quote.get('stopped') or quote.get('finished') or quote.get('suspended'):
        reasons.append('LIVE_MARKET_SUSPENDED')
    try:
        p=number(probability,low=0,high=1); odds=number(quote['decimal_odds'],low=1,high=10000)
        if not 0<p<1 or odds<=1:
            reasons.append('PROBABILITY_OR_ODDS_CONTRACT')
        elif p*odds<=1:
            reasons.append('NON_POSITIVE_EV')
        if abs(p-1/odds)>POLICY.max_market_divergence:
            reasons.append('SEVERE_MODEL_MARKET_CONTRADICTION')
        if number(uncertainty,low=0,high=1)>POLICY.max_uncertainty:
            reasons.append('UNCERTAINTY_TOO_HIGH')
    except (ValueError,KeyError,TypeError):
        reasons.append('PROBABILITY_OR_ODDS_CONTRACT')
    prior=[r for r in previous if r['fixture_id']==state['fixture_id']]
    if len(prior)>=POLICY.selections_per_fixture:
        reasons.append('LIVE_FIXTURE_SELECTION_LIMIT')
    for old in prior:
        # Same normalized market family, including its opposing side.
        if market_family(old['market'])!=market_family(market):
            continue
        previous_state=old['state']
        changed_score=(previous_state['home_score'],previous_state['away_score'])!=(state['home_score'],state['away_score'])
        changed_cards=(previous_state['red_cards_home'],previous_state['red_cards_away'])!=(state['red_cards_home'],state['red_cards_away'])
        progressed=state['minute']-previous_state['minute']>=POLICY.rebet_minutes
        moved=abs(number(quote['decimal_odds'])/number(old['captured_odds'])-1)>=POLICY.rebet_relative_price
        if not (changed_score or changed_cards or (progressed and moved)):
            reasons.append('DUPLICATE_LIVE_OPPORTUNITY')
    return sorted(set(reasons))


def market_family(market: str | None) -> str:
    if market in {'HOME_WIN','DRAW','AWAY_WIN'}:
        return '1X2'
    if market and market.startswith('BTTS'):
        return 'BTTS'
    return 'TOTAL_'+str(market).split('_',1)[-1]
