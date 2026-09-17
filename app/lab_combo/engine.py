"""Deterministic combination selection over immutable, reviewed singles."""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from itertools import combinations
from math import prod

from app.current_odds_forward_test.operations import build_publication_review
from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
from app.current_odds_forward_test.freshness import current_odds_freshness
from app.real_match_lab_analysis.fingerprint import fingerprint
from app.real_match_lab_analysis.policy import SUPPORTED_MARKETS


def load_leg(repository: SQLiteForwardTestRepository, observation_id: str, now: datetime) -> tuple[dict | None, list[str]]:
    """Reapply all existing publication gates and bind the selected captured quote."""
    review = build_publication_review(repository, observation_id, reviewed_at=now)
    if review['status'] != 'LAB_PUBLICATION_REVIEW_PASSED':
        return None, review['blocker_codes']
    observation = json.loads(repository.load_observation(observation_id)['observation_json'])
    request = json.loads(repository.connection.execute(
        'SELECT request_snapshot FROM real_match_lab_analyses WHERE analysis_id=?',
        (observation['analysis_id'],),
    ).fetchone()[0])
    odds = json.loads(repository.load_odds(observation['odds_snapshot_id'])['snapshot_json'])
    market = observation['actionable_market']
    evaluation = next(item for item in observation['market_evaluations'] if item['market'] == market)
    quote = next(item for item in odds['quotes'] if item['market'] == market)
    try:
        origin = quote.get('provider_origin_timestamp_utc')
        freshness = current_odds_freshness(
            provider_type=quote.get('provider_type', ''),
            provider_origin=datetime.fromisoformat(origin) if origin else None,
            captured=datetime.fromisoformat(quote['captured_at_utc']),
            retrieved=datetime.fromisoformat(quote['source_retrieval_timestamp_utc']), now=now)
    except (ValueError, TypeError, KeyError):
        return None, ['INVALID_CURRENT_ODDS_TIMESTAMP']
    if freshness in {'STALE', 'EXPIRED'}:
        return None, ['STALE_CURRENT_ODDS']
    if market not in SUPPORTED_MARKETS or evaluation.get('rejection_reasons') or evaluation.get('confidence') == 'LOW':
        return None, ['SINGLE_MARKET_REJECTED']
    if Decimal(str(evaluation['bookmaker_odds'])) != Decimal(quote['decimal_odds']):
        return None, ['ODDS_QUOTE_REPLACEMENT_CONFLICT']
    leg = {
        'observation_id': observation_id, 'analysis_id': observation['analysis_id'],
        'observation_fingerprint': observation['observation_fingerprint'],
        'quote': quote, 'fixture_id': request['match_id'],
        'home_team_id': request['home_team_id'], 'away_team_id': request['away_team_id'],
        'home_team': request['home_team'], 'away_team': request['away_team'],
        'competition_id': request['competition_id'], 'competition': request['competition'],
        'kickoff_utc': request['kickoff_utc'], 'market': market,
        'odds': quote['decimal_odds'], 'probability': evaluation['calibrated_probability'],
        'expected_value': evaluation['expected_value'], 'confidence': evaluation['confidence'],
        'reasoning_fingerprint': review['reasoning_fingerprint'],
        'review': review,
    }
    return leg, []


def independent(legs: tuple[dict, ...]) -> bool:
    """Conservatively exclude shared matches, teams and competition context."""
    return (len({leg['fixture_id'] for leg in legs}) == 3
            and len({str(leg[key]) for leg in legs for key in ('home_team_id', 'away_team_id')}) == 6
            and len({leg['competition_id'] for leg in legs}) == 3
            and len({leg['quote']['bookmaker_name'] for leg in legs}) == 1)


def select_combo(legs: list[dict], now: datetime) -> tuple[dict | None, list[str]]:
    """Select exactly three reviewed legs, never relaxing single-market gates."""
    if len(legs) < 3:
        return None, ['FEWER_THAN_THREE_ELIGIBLE_SINGLES']
    choices = []
    independent_count = 0
    for group in combinations(sorted(legs, key=lambda leg: leg['observation_id']), 3):
        if not independent(group):
            continue
        independent_count += 1
        prices = tuple(Decimal(leg['odds']) for leg in group)
        if any(not price.is_finite() or price <= Decimal(1) for price in prices):
            continue
        odds = prod(prices, start=Decimal(1))
        if not odds.is_finite() or odds <= Decimal(1) or odds > Decimal('3.50'):
            continue
        rank = (-min(Decimal(str(leg['probability'])) for leg in group),
                -sum(Decimal(str(leg['expected_value'])) for leg in group),
                tuple(leg['observation_id'] for leg in group))
        choices.append((rank, group, odds))
    if not choices:
        return None, ['COMBINED_ODDS_ABOVE_EXPERIMENTAL_SAFETY_LIMIT' if independent_count else 'CORRELATION_OR_BOOKMAKER_CONFLICT']
    _, group, odds = min(choices, key=lambda item: item[0])
    identity = {'policy': 'lab-combo-v2', 'legs': [leg['observation_id'] for leg in group]}
    return {'prediction_id': 'lab-combo-' + fingerprint(identity), 'policy': identity['policy'],
            'environment': 'LAB', 'created_at_utc': now.isoformat(), 'legs': list(group),
            'combined_odds': str(odds), 'accounting': 'LAB_ONLY_HYPOTHETICAL_ONE_UNIT'}, []


def prediction_message(combo: dict) -> str:
    """Render plain text so provider names cannot inject Telegram HTML."""
    lines = ['🧪 GoalVision AI Lab Combo', 'LAB / experimental — hypothetical 1 unit']
    for index, leg in enumerate(combo['legs'], 1):
        lines.extend([f"{index}. {leg['home_team']} vs {leg['away_team']} ({leg['competition']})",
                      f"{leg['market']} @ {leg['odds']} | {leg['confidence']} | P={leg['probability']}",
                      f"Kickoff: {leg['kickoff_utc']}",
                      f"Reason: reviewed positive value {leg['expected_value']}; calibration, shift and reasoning gates passed."])
    lines.extend([f"Combined odds: {combo['combined_odds']}", f"UTC: {combo['created_at_utc']}",
                  f"Prediction ID: {combo['prediction_id']}", 'Experimental evidence only. No guaranteed profit.'])
    return '\n'.join(lines)
