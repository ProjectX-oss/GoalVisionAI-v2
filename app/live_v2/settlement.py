"""Regulation-only deterministic settlement and separate fixed-1u statistics."""
from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from .contracts import digest, integer, utc
from .store import Store
from .markets import SIDES


def resolve(candidate: dict, result: dict) -> dict:
    """Final-time evidence only; suspended/abandoned matches remain unresolved."""
    state, quote = candidate['state'], candidate['market']['quote']
    if (result.get('fixture_id') != state['fixture_id'] or result.get('home_id') != state['home_id']
        or result.get('away_id') != state['away_id'] or result.get('season') != state['season']
        or result.get('league_id') != state['league_id'] or not result.get('source_fingerprint')
        or utc(result['retrieved_at']) <= utc(state['retrieved_at'])):
        raise ValueError('RESULT_IDENTITY_OR_CHRONOLOGY_INVALID')
    if quote.get('family') not in SIDES or quote.get('side') not in SIDES[quote['family']]:
        raise ValueError('UNSUPPORTED_SETTLEMENT_MARKET')
    if quote['family'] == 'TOTALS' and quote.get('line') not in {'1.5', '2.5', '3.5'}:
        raise ValueError('UNSUPPORTED_SETTLEMENT_LINE')
    price = Decimal(quote['odds'])
    if not price.is_finite() or not 1 < price <= 1000:
        raise ValueError('INVALID_CAPTURED_PRICE')
    score = result.get('regulation_score')
    if result.get('status') == 'CANC' and result.get('void_review_reference'):
        outcome, score = 'VOID', None
    else:
        if result.get('status') not in {'FT', 'AET', 'PEN'} or not isinstance(score, list) or len(score) != 2 or not all(integer(x, 0, 30) for x in score):
            raise ValueError('REGULATION_RESULT_NOT_FINAL')
        home, away = score
        if home < state['home_score'] or away < state['away_score']:
            raise ValueError('RESULT_SCORE_CONTRADICTION')
        family, side = quote['family'], quote['side']
        if family == '1X2':
            won = side == ('1' if home > away else '2' if away > home else 'X')
        elif family == 'BTTS':
            won = (home > 0 and away > 0) == (side == 'YES')
        elif family == 'TOTALS' and quote['line'] in {'1.5', '2.5', '3.5'} and side in {'OVER', 'UNDER'}:
            won = (home+away > Decimal(quote['line'])) == (side == 'OVER')
        else:
            raise ValueError('UNSUPPORTED_SETTLEMENT_MARKET')
        outcome = 'WON' if won else 'LOST'
    pnl = Decimal(quote['odds'])-1 if outcome == 'WON' else Decimal('-1') if outcome == 'LOST' else Decimal('0')
    return {'economic_key': candidate['economic_key'], 'selection': candidate, 'result_evidence': result,
            'regulation_score': score, 'outcome': outcome, 'unit_result': str(pnl), 'stake': '1',
            'semantics': 'REGULATION_FULL_MATCH', 'version': 'LIVE_SETTLEMENT_V1'}


def _totals(rows: list[dict]) -> dict:
    won, lost, void = (sum(r['outcome'] == status for r in rows) for status in ('WON', 'LOST', 'VOID'))
    pnl = sum((Decimal(r['unit_result']) for r in rows), Decimal('0'))
    return {'bets': len(rows), 'WON': won, 'LOST': lost, 'VOID': void, 'pnl': str(pnl),
            'accuracy': str(Decimal(won)/(won+lost)) if won+lost else None,
            'roi': str(pnl/len(rows)) if rows else None}


def statistics(rows: list[dict]) -> dict:
    """ROI includes all fixed-1u stakes, including voids; accuracy excludes voids."""
    if len({r['economic_key'] for r in rows}) != len(rows):
        raise ValueError('DUPLICATE_LIVE_SETTLEMENT')
    groups: dict[str, dict[str, list[dict]]] = {k: {} for k in ('market', 'odds_band', 'minute_band', 'completeness_band')}
    for row in rows:
        c = row['selection']
        odds, minute = Decimal(c['market']['quote']['odds']), c['state']['minute']
        bands = {'market': c['market']['quote']['family'],
                 'odds_band': '<1.60' if odds < Decimal('1.60') else '1.60–2.49' if odds < Decimal('2.50') else '2.50+',
                 'minute_band': '10–30' if minute <= 30 else '31–60' if minute <= 60 else '61–82',
                 'completeness_band': 'COMPLETE' if c['features']['completeness'] == 1 else 'INCOMPLETE'}
        for kind, band in bands.items():
            groups[kind].setdefault(band, []).append(row)
    return {'product': 'LIVE_V2_PRIVATE', 'accounting': 'HYPOTHETICAL_FIXED_1U', 'overall': _totals(rows),
            **{kind: {band: _totals(items) for band, items in sorted(group.items())} for kind, group in groups.items()}}


def settle(store: Store, key: str, result: dict, now: datetime) -> dict:
    """Only confirmed private selections enter publication statistics."""
    preview = store.get('preview', key)
    if not preview or preview['kind'] != 'prediction' or not store.get('receipt', key):
        raise ValueError('CONFIRMED_LIVE_SELECTION_REQUIRED')
    if utc(result['retrieved_at']) > utc(now):
        raise ValueError('FUTURE_RESULT_EVIDENCE')
    candidate = store.get('candidate', preview['candidate_id'])
    document = resolve(candidate, result)
    with store.transaction():
        store.append('settlement', key, document, now, ('receipt', key))
        existing = store.get('statistics', key)
        if existing is None:
            report = statistics(store.all('settlement'))
            report['settlement_fingerprints'] = sorted(digest(r) for r in store.all('settlement'))
            store.append('statistics', key, report, now, ('settlement', key))
    return document
