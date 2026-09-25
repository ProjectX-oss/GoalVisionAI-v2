"""Lab-only settlement using the existing fixture policy and single-market rules."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from math import prod

from app.current_odds_forward_test.service import _won
from app.results.policy import DEFAULT_FIXTURE_STATUS_POLICY
from app.real_match_lab_analysis.fingerprint import fingerprint

from .repository import ComboRepository
from .experimental import SETTLEMENT_RELEVANCE_AFTER_KICKOFF
from .presentation import combo_result_message, single_result_message


def resolve_leg(leg: dict, payload: dict, now: datetime) -> dict | None:
    """Use regulation-time scores, leave postponed/malformed results unresolved."""
    rows = payload.get('response')
    if payload.get('errors') or not isinstance(rows, list) or len(rows) != 1:
        return None
    row = rows[0]
    fixture = row.get('fixture') or {}
    if str(fixture.get('id')) != str(leg['fixture_id']):
        return None
    if now < datetime.fromisoformat(leg['kickoff_utc']):
        return None
    status = (fixture.get('status') or {}).get('short')
    nonplayable = DEFAULT_FIXTURE_STATUS_POLICY.classify_non_playable(status or '')
    score = (row.get('score') or {}).get('fulltime') or {}
    home, away = score.get('home'), score.get('away')
    if nonplayable and nonplayable[0].value == 'VOID':
        outcome = 'VOID'
    elif status in {'FT', 'AET', 'PEN'} and all(type(x) is int and 0 <= x <= 30 for x in (home, away)):
        outcome = 'WON' if _won(leg['market'], home, away) else 'LOST'
    else:
        return None
    return {'observation_id': leg['observation_id'], 'fixture_id': leg['fixture_id'],
            'outcome': outcome, 'market': leg['market'], 'captured_odds': leg['odds'],
            'home_team': leg.get('home_team'), 'away_team': leg.get('away_team'),
            'provider_status': status, 'fulltime_home': home, 'fulltime_away': away,
            'retrieved_at_utc': now.isoformat(), 'provider': 'API_FOOTBALL',
            'source_fingerprint': fingerprint(payload), 'rule_version': 'lab-combo-regulation-v1'}


def aggregate(combo: dict, results: list[dict], now: datetime) -> dict:
    """Settle only a complete set; void legs contribute decimal odds of one."""
    if len(results) != 3 or {r['observation_id'] for r in results} != {l['observation_id'] for l in combo['legs']}:
        raise ValueError('All three immutable leg results are required')
    by_id = {r['observation_id']: r for r in results}
    results = [by_id[leg['observation_id']] for leg in combo['legs']]
    if any(r['outcome'] not in {'WON', 'LOST', 'VOID'} for r in results):
        raise ValueError('Unresolved combo leg')
    effective = prod((Decimal(leg['odds']) if result['outcome'] != 'VOID' else Decimal(1)
                      for leg, result in zip(combo['legs'], results)), start=Decimal(1))
    outcomes = [r['outcome'] for r in results]
    status = ('LOST' if 'LOST' in outcomes else 'VOID' if all(s == 'VOID' for s in outcomes)
              else 'PARTIAL_VOID' if 'VOID' in outcomes else 'WON')
    net = Decimal(-1) if status == 'LOST' else Decimal(0) if status == 'VOID' else effective - 1
    return {'prediction_id': combo['prediction_id'], 'legs': results, 'status': status,
            'partial_void': 0 < outcomes.count('VOID') < 3, 'effective_combined_odds': str(effective),
            'unit_result': str(net), 'settled_at_utc': now.isoformat()}


def statistics(repository: ComboRepository, *, published_only: bool = False) -> dict:
    """Count every immutable outcome, including all losses and all voids."""
    published = [value for value in repository.all('prediction')
                 if (repository.get('receipt', 'combo_prediction:' + value['prediction_id'])
                     or repository.get('receipt', 'prediction:' + value['prediction_id']))]
    values = repository.all('settlement')
    if published_only:
        published_ids = {value['prediction_id'] for value in published}
        values = [value for value in values if value['prediction_id'] in published_ids]
    outcomes = {status: sum(v['status'] == status for v in values)
                for status in ('WON', 'LOST', 'VOID', 'PARTIAL_VOID')}
    units = sum((Decimal(v['unit_result']) for v in values), start=Decimal(0))
    odds = [Decimal(value['combined_odds']) for value in published]
    decided = outcomes['WON'] + outcomes['LOST'] + outcomes['PARTIAL_VOID']
    return {**outcomes, 'total_published': len(published), 'total_settled': len(values),
            'pending': len(published) - len(values),
            'win_rate': _ratio(outcomes['WON'] + outcomes['PARTIAL_VOID'], decided),
            'average_combined_odds': str(sum(odds, Decimal(0)) / len(odds)) if odds else None,
            'hypothetical_units_wagered': str(len(published)), 'hypothetical_profit_loss': str(units),
            'roi_yield': _ratio(units, len(values)), 'units': str(units)}


def single_statistics(repository: ComboRepository) -> dict:
    published = [value for value in repository.all('single_prediction')
                 if repository.get('receipt', 'single_prediction:' + value['prediction_id'])]
    published_ids = {value['prediction_id'] for value in published}
    settled = [value for value in repository.all('single_settlement')
               if value['prediction_id'] in published_ids]
    outcomes = {status: sum(value['status'] == status for value in settled)
                for status in ('WON', 'LOST', 'VOID')}
    profit = sum((Decimal(value['unit_result']) for value in settled), Decimal(0))
    odds = [Decimal(value['captured_odds']) for value in published]
    decided = outcomes['WON'] + outcomes['LOST']
    return {**outcomes, 'total_published': len(published), 'total_settled': len(settled),
            'pending': len(published) - len(settled), 'win_rate': _ratio(outcomes['WON'], decided),
            'average_odds': str(sum(odds, Decimal(0)) / len(odds)) if odds else None,
            'hypothetical_units_staked': str(len(published)),
            'hypothetical_units_won': str(sum((Decimal(v['unit_result']) for v in settled if v['status'] == 'WON'), Decimal(0))),
            'hypothetical_units_lost': str(sum((Decimal(v['unit_result']) for v in settled if v['status'] == 'LOST'), Decimal(0))),
            'hypothetical_profit_loss': str(profit), 'roi_yield': _ratio(profit, len(settled))}


def resolve_single(prediction: dict, payload: dict, now: datetime) -> dict | None:
    if now < datetime.fromisoformat(prediction['kickoff_utc']) + SETTLEMENT_RELEVANCE_AFTER_KICKOFF:
        return None
    leg = {**prediction, 'observation_id': prediction['prediction_id'],
           'odds': prediction['captured_odds']}
    result = resolve_leg(leg, payload, now)
    if result is None:
        return None
    odds = Decimal(prediction['captured_odds'])
    unit = Decimal(-1) if result['outcome'] == 'LOST' else Decimal(0) if result['outcome'] == 'VOID' else odds - 1
    return {'prediction_id': prediction['prediction_id'], 'fixture_id': prediction['fixture_id'],
            **({'selection_origin': prediction['selection_origin']} if 'selection_origin' in prediction else {}),
            'market': prediction['market'], 'captured_odds': prediction['captured_odds'],
            'home_team': prediction.get('home_team'), 'away_team': prediction.get('away_team'),
            'status': result['outcome'], 'fulltime_home': result['fulltime_home'],
            'fulltime_away': result['fulltime_away'], 'provider_status': result['provider_status'],
            'unit_result': str(unit), 'settled_at_utc': now.isoformat(),
            'source_fingerprint': result['source_fingerprint']}


def single_settlement_message(value: dict, stats: dict) -> str:
    return single_result_message(value, stats)


def settlement_message(value: dict, stats: dict) -> str:
    """Prepare a compact public result while retaining full ledger evidence."""
    return combo_result_message(value, stats)


def _ratio(numerator, denominator) -> str | None:
    if not denominator:
        return None
    return str(Decimal(numerator) / Decimal(denominator))
