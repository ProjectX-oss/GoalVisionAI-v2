"""Conservative Lab publication review; research admission remains unchanged."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.real_match_lab_analysis.fingerprint import fingerprint
from .ensemble import EnsembleSignal, evaluate_ensemble, _independence_group, _market_weight, _FAMILY
from .ensemble import MAX_MARKET_EDGE, MAX_MODEL_MARKET_DIFFERENCE
from .forward_evidence import current_quote
from .global_evaluation import SOFT_ENSEMBLE
from .api_prediction import NORMALIZATION_VERSION, _probability

PUBLICATION_POLICY_VERSION = 'LAB_SEVERE_DISAGREEMENT_PUBLICATION_V1'
SEVERE_FINDINGS = frozenset({'ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE',
                            'SEVERE_MODEL_MARKET_CONTRADICTION'})


def review_publication(candidate: dict, *, now: datetime) -> dict:
    """Replay retained, already profile-weighted signals before any new Lab claim.

    Warning lists alone are insufficient. Missing/invalid evidence fails closed;
    no provider calls, probability blending, data deletion or threshold fitting.
    """
    reasons = set(candidate.get('soft_findings') or ()) & SEVERE_FINDINGS
    reasons.update(set(candidate.get('rejection_reasons') or ()) & SEVERE_FINDINGS)
    try:
        from .runner import FINAL_REVIEW_MAX_AGE
        review = datetime.fromisoformat(candidate['final_review_completed_at_utc'])
        if (not current_quote(candidate, now) or not 0 <= (now - review).total_seconds()
                <= FINAL_REVIEW_MAX_AGE.total_seconds()):
            reasons.add('PUBLICATION_DECISION_EVIDENCE_STALE')
        market = candidate['market']
        odds = Decimal(str(candidate['captured_odds']))
        probability = _probability(candidate['ensemble_probability'], unit='probability')
        if probability is None or not 0 < probability < 1 or not odds.is_finite() or odds <= 1:
            raise ValueError('invalid probability or odds')
        signals = [EnsembleSignal(**{**s,
                    'probability': _probability(s['probability'], unit='probability') if s['probability'] is not None else None,
                    'reliability': Decimal(str(s['reliability']))}) for s in candidate['signals']]
        if any((raw['probability'] is not None and signal.probability is None) or not signal.provenance
               for raw, signal in zip(candidate['signals'], signals)):
            raise ValueError('invalid signal')
        decision = evaluate_ensemble(market, odds, signals)
        reasons.update(set(decision.rejection_reasons) - SOFT_ENSEMBLE)
        reasons.update(set(decision.rejection_reasons) & SEVERE_FINDINGS)
        predictive = [s for s in decision.signals if s.name != 'CURRENT_MARKET_CONSENSUS'
                      and _independence_group(s) != 'CURRENT_MARKET_CONSENSUS'
                      and s.probability is not None and s.provenance]
        families = {_independence_group(s) for s in predictive}
        consensus = [s.probability for s in decision.signals
                     if s.name == 'CURRENT_MARKET_CONSENSUS' and s.probability is not None]
        if not families or len(consensus) != 1:
            raise ValueError('missing independent/market evidence')
        replay = decision.ensemble_probability
        if len(families) == 1:
            weights = [_market_weight(s, _FAMILY.get(market)) for s in predictive]
            replay = sum((s.probability * w for s, w in zip(predictive, weights)), Decimal(0)) / sum(weights)
            if abs(replay - consensus[0]) > MAX_MODEL_MARKET_DIFFERENCE:
                reasons.add('SEVERE_MODEL_MARKET_CONTRADICTION')
        if probability - Decimal(1) / odds > MAX_MARKET_EDGE:
            reasons.add('ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE')
        if replay is None or abs(probability - replay) > Decimal('1e-25'):
            reasons.add('PUBLICATION_PROBABILITY_REPLAY_MISMATCH')
        # Bind the frozen quote to fixture, selection, bookmaker and timestamps.
        quote = dict(provider='API_FOOTBALL', fixture_id=candidate['fixture_id'],
                     bookmaker_id=candidate['bookmaker_id'], bookmaker=candidate['bookmaker'],
                     market=market, odds=odds,
                     provider_updated=datetime.fromisoformat(candidate['provider_origin_timestamp_utc']),
                     retrieved_at=datetime.fromisoformat(candidate['goalvision_retrieved_at_utc']))
        if fingerprint(quote) != candidate['quote_provenance_fingerprint']:
            reasons.add('PUBLICATION_QUOTE_IDENTITY_MISMATCH')
        metadata = candidate['provider_metadata']
        if (metadata['fixture']['id'] != candidate['fixture_id']
                or any(metadata['teams'][side]['id'] != candidate[side + '_team_id'] for side in ('home', 'away'))
                or candidate['home_team_id'] == candidate['away_team_id']):
            reasons.add('PUBLICATION_FIXTURE_IDENTITY_MISMATCH')
        if any(s.name == 'API_FOOTBALL_PREDICTION' for s in predictive):
            api = candidate.get('api_prediction_normalization') or {}
            if (api.get('normalization_version') != NORMALIZATION_VERSION or not api.get('available')
                    or not api.get('source_fingerprint') or api.get('fixture_id') != candidate['fixture_id']
                    or any(api.get(side + '_team_id') != candidate[side + '_team_id'] for side in ('home', 'away'))):
                reasons.add('PUBLICATION_API_NORMALIZATION_EVIDENCE_REQUIRED')
            else:
                distribution = {k: _probability(v, unit='probability') for k, v in api['probabilities'].items()}
                if (set(distribution) != {'HOME_WIN', 'DRAW', 'AWAY_WIN'}
                        or any(v is None for v in distribution.values())
                        or abs(sum(distribution.values()) - 1) > Decimal('1e-25')
                        or any(s.probability != distribution.get(market) for s in predictive
                               if s.name == 'API_FOOTBALL_PREDICTION')):
                    reasons.add('PUBLICATION_API_PROBABILITY_INVALID')
    except (KeyError, TypeError, ValueError, InvalidOperation, ZeroDivisionError, AttributeError):
        reasons.add('PUBLICATION_DECISION_EVIDENCE_INVALID_OR_MISSING')
    return {'version': PUBLICATION_POLICY_VERSION, 'eligible': not reasons,
            'rejection_reasons': sorted(reasons)}
