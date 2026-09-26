"""Conservative Phase 1 market-value gates; PREMATCH context never supplies live p."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from . import POLICY_VERSION
from .contracts import digest, fresh
from .markets import consensus


def evaluate(state: dict, features: dict, quotes: list[dict], *, now: datetime,
             safe_quota: bool, published: frozenset[str] = frozenset(),
             prematch_context: dict | None = None) -> list[dict]:
    """Return every rejection and qualifying evaluation deterministically."""
    markets = consensus(quotes, now)
    if not markets:
        return [{'policy': POLICY_VERSION, 'qualified': False, 'reasons': ['NO_CURRENT_MULTIBOOK_CONSENSUS'],
                 'state': state, 'features': features, 'prematch_context': prematch_context}]
    evaluations = []
    for market in markets:
        quote = market['quote']
        key = digest([state['fixture_id'], quote['family'], quote['line'], quote['side'], 'REGULATION_FULL_MATCH'])
        reasons = []
        if not safe_quota:
            reasons.append('QUOTA_RESERVED_FOR_PREMATCH')
        if state['status'] not in {'1H', '2H'} or not 10 <= state['minute'] <= 82 or not fresh(state['retrieved_at'], now, 30):
            reasons.append('UNSUITABLE_OR_STALE_STATE')
        if quote['state_fingerprint'] != digest(state):
            reasons.append('QUOTE_STATE_MISMATCH')
        if features['completeness'] < 1 or features['contradictions']:
            reasons.append('INCOMPLETE_OR_CONTRADICTORY_EVIDENCE')
        # Phase 1 has no independently validated player-disadvantage model.
        if features['red_cards'] is None or any(features['red_cards'].values()):
            reasons.append('RED_CARD_STATE_UNSUITABLE')
        if Decimal(market['edge']) < Decimal('.02'):
            reasons.append('PRICE_ADVANTAGE_BELOW_2PP')
        if Decimal(market['dispersion']) > Decimal('.08'):
            reasons.append('BOOKMAKER_DISAGREEMENT')
        if key in published:
            reasons.append('ECONOMIC_DUPLICATE')
        if not _agreement(state, features, quote):
            reasons.append('GAME_STATE_PRESSURE_DISAGREEMENT')
        # Context can veto a critical identity/availability contradiction, never create p.
        if prematch_context and prematch_context.get('critical_contradiction'):
            reasons.append('PREMATCH_CONTEXT_CONTRADICTION')
        evaluations.append({'policy': POLICY_VERSION, 'minute_policy': 'LIVE_MINUTE_10_82_V1',
                            'qualified': not reasons, 'reasons': reasons, 'economic_key': key,
                            'state': state, 'features': features, 'market': market,
                            'prematch_context': prematch_context})
    return evaluations


def _agreement(state: dict, features: dict, quote: dict) -> bool:
    """Explicit score and shot gates; possession/corners are never selection triggers."""
    if features['completeness'] < 1:
        return False
    h, a = features['home'], features['away']
    hs, ass = h['Shots on Goal'], a['Shots on Goal']
    shots = h['Total Shots']+a['Total Shots']
    goals = state['home_score']+state['away_score']
    family, side = quote['family'], quote['side']
    if family == 'TOTALS':
        line = Decimal(quote['line'])
        if goals > line:
            return False  # Both sides already economically resolved.
        if side == 'OVER':
            return hs+ass >= 4 and shots >= 10
        return state['minute'] >= 30 and hs+ass <= 4 and shots <= 12
    if family == 'BTTS':
        if state['home_score'] > 0 and state['away_score'] > 0:
            return False
        return (hs >= 2 and ass >= 2 and shots >= 10) if side == 'YES' else (
            state['minute'] >= 30 and min(hs, ass) <= 1 and shots <= 12)
    diff = state['home_score']-state['away_score']
    if side == '1':
        return diff >= 0 and hs >= ass+2 and h['Total Shots'] >= a['Total Shots']
    if side == '2':
        return diff <= 0 and ass >= hs+2 and a['Total Shots'] >= h['Total Shots']
    return diff == 0 and abs(hs-ass) <= 1 and shots <= 12 and state['minute'] >= 30
