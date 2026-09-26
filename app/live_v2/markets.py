"""Current LIVE mappings and bookmaker-wise proportional overround removal."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from .contracts import digest, fresh, integer

SIDES = {'1X2': ('1', 'X', '2'), 'TOTALS': ('OVER', 'UNDER'), 'BTTS': ('YES', 'NO')}
NAMES = {'1X2': frozenset({'Fulltime Result', 'Match Winner'}),
         'TOTALS': frozenset({'Goals Over/Under'}), 'BTTS': frozenset({'Both Teams To Score'})}


def review_catalogue(payload: dict, reviews: list[dict]) -> dict:
    """Pin operator-reviewed IDs to an actual /odds/live/bets capture and semantics."""
    if payload.get('endpoint') != '/odds/live/bets' or payload.get('errors') or not isinstance(payload.get('response'), list):
        raise ValueError('LIVE_CATALOGUE_REQUIRED')
    names = {}
    for item in payload['response']:
        if not integer(item.get('id'), 1) or item['id'] in names:
            raise ValueError('AMBIGUOUS_CATALOGUE')
        names[item['id']] = item['name']
    for review in reviews:
        family = review['family']
        if (family not in SIDES or review['name'] not in NAMES[family]
            or names.get(review['id']) != review['name'] or review.get('period') != 'REGULATION_FULL_MATCH'
            or not review.get('review_reference')):
            raise ValueError('UNREVIEWED_LIVE_SEMANTICS')
    if len({r['id'] for r in reviews}) != len(reviews):
        raise ValueError('DUPLICATE_REVIEW')
    return {'version': 'LIVE_MARKET_REVIEW_V1', 'endpoint': '/odds/live/bets', 'review_status': 'REVIEWED',
            'catalogue_fingerprint': digest(payload), 'mappings': reviews}


def selection(family: str, value: dict) -> tuple[str, str | None] | None:
    """Only full-match 1X2, BTTS, and main half-goal totals 1.5/2.5/3.5."""
    label = str(value.get('value', '')).lower()
    if family == '1X2' and value.get('handicap') is None:
        side = {'home': '1', 'draw': 'X', 'away': '2', '1': '1', 'x': 'X', '2': '2'}.get(label)
        return (side, None) if side else None
    if family == 'BTTS' and value.get('handicap') is None:
        return (label.upper(), None) if label in {'yes', 'no'} else None
    if family == 'TOTALS' and value.get('main') is True:
        line = str(value.get('handicap'))
        if label in {'over', 'under'} and line in {'1.5', '2.5', '3.5'}:
            return label.upper(), line
    return None


def normalize(payload: dict, state: dict, mapping: dict, *, retrieved_at: datetime) -> tuple[list[dict], list[str]]:
    """No invented bookmaker identities; unfamiliar provider shapes fail closed."""
    if (mapping.get('review_status') != 'REVIEWED' or not mapping.get('catalogue_fingerprint')
        or mapping.get('endpoint') != '/odds/live/bets' or mapping.get('version') != 'LIVE_MARKET_REVIEW_V1'
        or any(r.get('period') != 'REGULATION_FULL_MATCH' or r.get('name') not in NAMES.get(r.get('family'), ())
               or not r.get('review_reference') for r in mapping.get('mappings', []))):
        return [], ['LIVE_CATALOGUE_UNVERIFIED']
    if payload.get('errors') or not isinstance(payload.get('response'), list):
        return [], ['CURRENT_ODDS_UNAVAILABLE']
    reviewed = {r['id']: r for r in mapping['mappings']}
    quotes, reasons = [], []
    for row in payload['response']:
        fixture, teams, flags = row.get('fixture', {}), row.get('teams', {}), row.get('status', {})
        if (fixture.get('id') != state['fixture_id'] or fixture.get('status', {}).get('elapsed') != state['minute']
            or any(teams.get(s, {}).get('id') != state[s+'_id'] or
                   teams.get(s, {}).get('goals') != state[s+'_score'] for s in ('home', 'away'))):
            reasons.append('ODDS_STATE_IDENTITY_MISMATCH')
            continue
        if any(flags.get(k) is not False for k in ('stopped', 'blocked', 'finished')):
            reasons.append('STOPPED_OR_BLOCKED_ODDS')
            continue
        bookmaker = row.get('bookmaker', {})
        if not integer(bookmaker.get('id'), 1) or not bookmaker.get('name'):
            reasons.append('BOOKMAKER_PROVENANCE_UNAVAILABLE')
            continue
        for bet in row.get('odds', []):
            review = reviewed.get(bet.get('id'))
            if not review or bet.get('name') != review['name']:
                reasons.append('UNSUPPORTED_LIVE_BET_ID')
                continue
            for value in bet.get('values', []):
                parsed = selection(review['family'], value)
                if not parsed or value.get('suspended') is not False:
                    reasons.append('UNSUPPORTED_OR_SUSPENDED_SELECTION')
                    continue
                try:
                    price = Decimal(str(value['odd']))
                    if not price.is_finite() or not 1 < price <= 1000:
                        raise ValueError
                except (KeyError, InvalidOperation, ValueError):
                    reasons.append('INVALID_PRICE')
                    continue
                side, line = parsed
                quote = {'fixture_id': state['fixture_id'], 'bookmaker_id': bookmaker['id'],
                         'bookmaker': bookmaker['name'], 'live_bet_id': bet['id'],
                         'family': review['family'], 'side': side, 'line': line,
                         'odds': str(price), 'provider_at': row.get('update'),
                         'retrieved_at': retrieved_at.isoformat(), 'blocked': False, 'stopped': False,
                         'suspended': False, 'mapping_version': mapping['version'],
                         'catalogue_fingerprint': mapping['catalogue_fingerprint'],
                         'source_fingerprint': digest(row), 'state_fingerprint': digest(state)}
                quote['fingerprint'] = digest(quote)
                quotes.append(quote)
    return quotes, sorted(set(reasons))


def consensus(quotes: list[dict], now: datetime) -> list[dict]:
    """Require >=3 complete independent books, excluding the best-price book from fair p.

    Equal-weight mean of bookmaker fair probabilities, q_i=(1/o_i)/sum(1/o).
    Missing origin timestamps are retained evidence but ineligible for consensus.
    """
    groups: dict[tuple, dict[int, list[dict]]] = {}
    for q in quotes:
        if (not fresh(q.get('retrieved_at'), now, 30) or not fresh(q.get('provider_at'), now, 30)
            or any(q.get(k) is not False for k in ('blocked', 'stopped', 'suspended'))):
            continue
        key = (q['fixture_id'], q['family'], q['line'], q['state_fingerprint'])
        groups.setdefault(key, {}).setdefault(q['bookmaker_id'], []).append(q)
    results = []
    for (_, family, _, _), books in sorted(groups.items(), key=lambda x: str(x[0])):
        complete = {}
        names = [str(rows[0]['bookmaker']).strip().casefold() for rows in books.values()]
        for book, rows in books.items():
            if names.count(str(rows[0]['bookmaker']).strip().casefold()) != 1:
                continue
            if len(rows) != len(SIDES[family]) or {q['side'] for q in rows} != set(SIDES[family]):
                continue
            implied = {q['side']: 1/Decimal(q['odds']) for q in rows}
            overround = sum(implied.values())
            if not Decimal('1') <= overround <= Decimal('1.20'):
                continue
            complete[book] = (rows, {side: p/overround for side, p in implied.items()})
        if len(complete) < 3:
            continue
        for side in SIDES[family]:
            options = [q for rows, _ in complete.values() for q in rows if q['side'] == side]
            best = max(options, key=lambda q: (Decimal(q['odds']), -q['bookmaker_id']))
            peers = [prob[side] for book, (_, prob) in complete.items() if book != best['bookmaker_id']]
            fair = sum(peers)/len(peers)
            results.append({'quote': best, 'probability': str(fair),
                            'edge': str(fair-1/Decimal(best['odds'])),
                            'bookmakers': sorted(complete), 'consensus_bookmakers': sorted(b for b in complete if b != best['bookmaker_id']),
                            'dispersion': str(max(peers)-min(peers)),
                            'semantics': 'CURRENT_MARKET_VALUE_NOT_CALIBRATED_MODEL'})
    return results
