"""Lab-only settlement using the existing fixture policy and single-market rules."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from math import prod

from app.current_odds_forward_test.service import _won
from app.results.policy import DEFAULT_FIXTURE_STATUS_POLICY
from app.real_match_lab_analysis.fingerprint import fingerprint

from .repository import ComboRepository


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
    status = 'LOST' if 'LOST' in outcomes else 'VOID' if all(s == 'VOID' for s in outcomes) else 'WON'
    net = Decimal(-1) if status == 'LOST' else Decimal(0) if status == 'VOID' else effective - 1
    return {'prediction_id': combo['prediction_id'], 'legs': results, 'status': status,
            'partial_void': 0 < outcomes.count('VOID') < 3, 'effective_combined_odds': str(effective),
            'unit_result': str(net), 'settled_at_utc': now.isoformat()}


def statistics(repository: ComboRepository, *, published_only: bool = False) -> dict:
    """Count every immutable outcome, including all losses and all voids."""
    values = repository.all('settlement')
    if published_only:
        values = [v for v in values if repository.get('receipt', 'prediction:' + v['prediction_id'])]
    return {**{status: sum(v['status'] == status for v in values) for status in ('WON', 'LOST', 'VOID')},
            'units': str(sum((Decimal(v['unit_result']) for v in values), start=Decimal(0)))}


def settlement_message(value: dict, stats: dict) -> str:
    """Prepare transparent experimental result notification for wins and losses."""
    lines = ['🧪 GoalVision AI Lab Combo — settlement', 'LAB / experimental', f"Prediction ID: {value['prediction_id']}"]
    lines.extend(f"Fixture {leg['fixture_id']} · {leg['market']}: {leg['outcome']}" for leg in value['legs'])
    lines.extend([f"Final: {value['status']} | partial void: {value['partial_void']}",
                  f"Effective combined odds: {value['effective_combined_odds']}",
                  f"Hypothetical unit result: {value['unit_result']}",
                  f"Published Lab Combo: {stats['WON']} W / {stats['LOST']} L / {stats['VOID']} VOID"])
    return '\n'.join(lines)
