"""Immutable pre-kickoff observations and explicit result capture, no optimizer."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from math import sqrt

from .repository import ShadowEvidenceRepository
from .profiles import policy_for
from app.current_odds_forward_test.freshness import API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS, RETRIEVAL_MAX_AGE_SECONDS


def capture_selection(repository: ShadowEvidenceRepository, candidate: dict, *, now: datetime) -> bool:
    """Freeze the first fresh positive-EV fixture/market, independent of publication."""
    if candidate['decision'] != 'APPROVED' or not current_quote(candidate, now):
        return False
    if datetime.fromisoformat(candidate['kickoff_utc']) <= now:
        return False
    key = f"{candidate['fixture_id']}:{candidate['market']}"
    if repository.get('forward_selection', key) is not None:
        return False
    p, odds = Decimal(candidate['ensemble_probability']), Decimal(candidate['captured_odds'])
    if not p.is_finite() or not odds.is_finite() or not 0 < p < 1 or odds <= 1 or p * odds <= 1:
        raise ValueError('INVALID_FORWARD_VALUE')
    row = {k: candidate[k] for k in ('candidate_id', 'fixture_id', 'league_id', 'competition_profile',
                                    'market', 'candidate_lane', 'ensemble_probability', 'captured_odds',
                                    'quote_provenance_fingerprint', 'kickoff_utc', 'profile_policy_version')}
    row.update(candidate)
    row.update(selection_key=key, captured_at=now.isoformat(), accounting='SHADOW_LEARNING_ONLY',
               implied_probability=str(1 / odds), edge=str(p - 1 / odds), expected_value=str(p * odds - 1),
               telegram_publication=False, bankroll_transaction=False)
    return repository.append('forward_selection', key, row, created_at=now)


def capture_result(repository: ShadowEvidenceRepository, selection_key: str, *, outcome: str,
                   source_fingerprint: str, now: datetime) -> bool:
    """Record explicit final-result evidence without any provider or send operation."""
    row = repository.get('forward_selection', selection_key)
    if row is None or outcome not in {'WON', 'LOST', 'VOID'} or not source_fingerprint:
        raise ValueError('INVALID_FORWARD_RESULT_REFERENCE')
    if datetime.fromisoformat(row['kickoff_utc']) >= now:
        raise ValueError('RESULT_BEFORE_KICKOFF')
    return repository.append('forward_result', selection_key,
                             {'selection_key': selection_key, 'outcome': outcome,
                              'source_fingerprint': source_fingerprint}, created_at=now)


def performance(repository: ShadowEvidenceRepository) -> list[dict]:
    """Joint league/profile/market/lane metrics; pending/void never count as losses."""
    outcomes = {r['selection_key']: r['outcome'] for r in repository.all('forward_result')}
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for row in repository.all('forward_selection'):
        buckets[tuple(row[k] for k in ('league_id', 'competition_profile', 'market', 'candidate_lane'))].append(row)
    result = []
    for key, rows in sorted(buckets.items()):
        settled = [r for r in rows if outcomes.get(r['selection_key']) in {'WON', 'LOST'}]
        n = len(settled)
        wins = sum(outcomes[r['selection_key']] == 'WON' for r in settled)
        policy = policy_for(key[1])
        age = (max(datetime.fromisoformat(r['captured_at']) for r in rows) -
               min(datetime.fromisoformat(r['captured_at']) for r in rows)).days
        mean = lambda values: str(sum(values, Decimal(0)) / n) if n else None
        interval = None
        if n:
            rate, z = wins / n, 1.96
            centre = (rate + z*z/(2*n))/(1+z*z/n)
            radius = z*sqrt(rate*(1-rate)/n+z*z/(4*n*n))/(1+z*z/n)
            interval = [max(0, centre-radius), min(1, centre+radius)]
        result.append(dict(zip(('league_id', 'competition_profile', 'market', 'candidate_lane'), key)) | {
            'selections': len(rows), 'wins': wins, 'losses': n-wins,
            'voids': sum(outcomes.get(r['selection_key']) == 'VOID' for r in rows),
            'pending': sum(r['selection_key'] not in outcomes for r in rows),
            'sample_size': n, 'hit_rate': str(Decimal(wins)/n) if n else None,
            'hit_rate_wilson_95': interval,
            'average_model_probability': mean([Decimal(r['ensemble_probability']) for r in settled]),
            'average_implied_probability': mean([1/Decimal(r['captured_odds']) for r in settled]),
            'average_edge': mean([Decimal(r['ensemble_probability'])-1/Decimal(r['captured_odds']) for r in settled]),
            'brier': mean([(Decimal(r['ensemble_probability'])-int(outcomes[r['selection_key']]=='WON'))**2 for r in settled]),
            'hypothetical_flat_stake_roi': mean([Decimal(r['captured_odds'])-1 if outcomes[r['selection_key']]=='WON' else Decimal(-1) for r in settled]),
            'minimum_tuning_selections': policy.minimum_tuning_selections,
            'minimum_tuning_days': policy.minimum_tuning_days,
            'eligible_for_manual_policy_review': n >= policy.minimum_tuning_selections and age >= policy.minimum_tuning_days,
            'automatic_tuning_enabled': False})
    return result


def current_quote(candidate: dict, now: datetime) -> bool:
    """Reuse existing source/retrieval age limits at capture and publication."""
    try:
        origin = datetime.fromisoformat(candidate['provider_origin_timestamp_utc'])
        retrieved = datetime.fromisoformat(candidate['goalvision_retrieved_at_utc'])
        return (origin <= retrieved <= now
                and (now - origin).total_seconds() <= API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS
                and (now - retrieved).total_seconds() <= RETRIEVAL_MAX_AGE_SECONDS
                and bool(candidate.get('quote_provenance_fingerprint')))
    except (KeyError, TypeError, ValueError):
        return False
