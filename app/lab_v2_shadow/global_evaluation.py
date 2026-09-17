"""Profile-aware soft penalties layered over the existing independent ensemble."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from .ensemble import EnsembleDecision, EnsembleSignal, evaluate_ensemble, _independence_group, _market_weight
from .profiles import ProfilePolicy

SOFT_ENSEMBLE = frozenset({'INSUFFICIENT_INDEPENDENT_SIGNALS', 'ENSEMBLE_EDGE_BELOW_0_04',
                           'WEIGHTED_AGREEMENT_BELOW_0_65', 'MATERIAL_SIGNAL_DISAGREEMENT',
                           'ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE'})
FEATURES = {'PI_RATINGS': 'long_term_strength', 'CURRENT_MATCH_INTELLIGENCE': 'recent_form',
            'GOALVISION_EXPERIMENTAL_MODEL': 'recent_form', 'API_FOOTBALL_PREDICTION': 'opponent_strength',
            'CURRENT_MARKET_CONSENSUS': 'current_odds'}


def evaluate_profile(market: str, odds: Decimal, signals: list[EnsembleSignal], policy: ProfilePolicy,
                     missing: tuple[str, ...], *, contradiction: bool = False) -> tuple[EnsembleDecision, dict]:
    """Never fabricate sources or change output probabilities to improve value.

    One non-market family can supply an experimental observation;
    two remain necessary for standard evidence. Correlated adapters retain
    the original shared-family aggregation. Uncertainty is a required edge
    margin, not a probability adjustment disguised as calibrated inference.
    """
    weighted = [replace(s, reliability=s.reliability * policy.weight(FEATURES.get(s.name, 'recent_form')))
                for s in signals]
    decision = evaluate_ensemble(market, odds, weighted, severe_current_match_contradiction=contradiction)
    penalties = {feature: str(policy.weight(feature) * Decimal('0.005')) for feature in missing}
    uncertainty = policy.uncertainty + sum((Decimal(x) for x in penalties.values()), Decimal(0))
    hard = [r for r in decision.rejection_reasons if r not in SOFT_ENSEMBLE]
    soft = [r for r in decision.rejection_reasons if r in SOFT_ENSEMBLE]
    predictive = [s for s in decision.signals if s.name != 'CURRENT_MARKET_CONSENSUS'
                  and _independence_group(s) != 'CURRENT_MARKET_CONSENSUS'
                  and s.probability is not None and s.provenance]
    families = sorted({_independence_group(s) for s in predictive})
    # A single-family experiment uses only that family's predictive probability.
    # Current prices remain validation/comparison evidence, never model inputs.
    if len(families) == 1 and odds.is_finite() and odds > 1:
        from .ensemble import _FAMILY
        weights = [_market_weight(s, _FAMILY.get(market)) for s in predictive]
        probability = sum((s.probability * w for s, w in zip(predictive, weights)), Decimal(0)) / sum(weights)
        implied = Decimal(1) / odds
        decision = replace(decision, ensemble_probability=probability, edge=probability-implied,
                           offered_implied_probability=implied)
        market_probabilities = [s.probability for s in decision.signals
                                if s.name == 'CURRENT_MARKET_CONSENSUS' and s.probability is not None]
        if any(abs(probability - value) > Decimal('0.22') for value in market_probabilities):
            hard.append('SEVERE_MODEL_MARKET_CONTRADICTION')
        if probability - implied > Decimal('0.18'):
            hard.append('ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE')
    p, edge = decision.ensemble_probability, decision.edge
    if p is None or not p.is_finite() or not Decimal(0) < p < Decimal(1):
        hard.append('INVALID_MODEL_PROBABILITY')
    if edge is None or not edge.is_finite() or edge <= 0:
        hard.append('NON_POSITIVE_VALUE')
    if len(families) < policy.experimental_independent_families:
        hard.append('NO_INDEPENDENT_NON_MARKET_EVIDENCE')
    # Keep disagreement/correlation safeguards; uncertainty never excuses a veto.
    for reason in ('MATERIAL_SIGNAL_DISAGREEMENT', 'ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE',
                   'WEIGHTED_AGREEMENT_BELOW_0_65'):
        if reason in soft:
            hard.append(reason)
    if edge is not None and edge.is_finite() and edge < policy.experimental_edge + uncertainty:
        soft.append('VALUE_BELOW_PROFILE_THRESHOLD')
    eligible = not hard and 'VALUE_BELOW_PROFILE_THRESHOLD' not in soft
    lane = 'REJECTED'
    if eligible:
        lane = ('STRONG' if decision.confidence == 'HIGH' and len(families) >= policy.strong_independent_families else 'STANDARD') if (
            len(families) >= policy.standard_independent_families and not decision.rejection_reasons
            and (decision.weighted_agreement or Decimal(0)) >= policy.minimum_standard_agreement
            and edge >= policy.standard_edge + uncertainty
            and policy.profile not in {'UNKNOWN', 'FRIENDLY'}
        ) else 'EXPERIMENTAL'
        decision = replace(decision, decision='APPROVED',
                           approval_reasons=(*decision.approval_reasons, 'PROFILE_' + lane), rejection_reasons=())
    else:
        decision = replace(decision, decision='REJECTED', rejection_reasons=tuple(sorted(set(hard + soft))))
    return decision, {'candidate_lane': lane, 'predictive_family_count': len(families),
                      'predictive_families': families,
                      'evidence_lane': 'SINGLE_MODEL_EXPERIMENTAL' if len(families) == 1 else 'MULTI_FAMILY' if families else 'NO_PREDICTIVE_FAMILY', 'profile_policy_version': policy.version, 'home_advantage_basis': policy.home_advantage_basis,
                      'uncertainty_penalty': str(uncertainty), 'soft_penalties': penalties,
                      'missing_features': list(missing), 'hard_failures': sorted(set(hard)),
                      'soft_findings': sorted(set(soft)), 'calibration_status': 'UNCALIBRATED_LAB_ENSEMBLE',
                      'minimum_required_edge': str(policy.experimental_edge + uncertainty)}


def next_refresh(kickoff: datetime, now: datetime, policy: ProfilePolicy) -> datetime | None:
    """Deterministic data-usefulness windows, invoked manually without timers."""
    return next((kickoff - timedelta(minutes=m) for m in policy.refresh_minutes
                 if kickoff - timedelta(minutes=m) > now), None)
