"""Profile-aware soft penalties layered over the existing independent ensemble."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from .ensemble import EnsembleDecision, EnsembleSignal, evaluate_ensemble
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

    Two genuinely separate families can supply an experimental observation;
    three remain necessary for standard evidence. Correlated adapters retain
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
    p, edge = decision.ensemble_probability, decision.edge
    if p is None or not p.is_finite() or not Decimal(0) < p < Decimal(1):
        hard.append('INVALID_MODEL_PROBABILITY')
    if edge is None or not edge.is_finite() or edge <= 0:
        hard.append('NON_POSITIVE_VALUE')
    if decision.available_signals < policy.experimental_independent_families:
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
        lane = ('STRONG' if decision.confidence == 'HIGH' else 'STANDARD') if (
            decision.available_signals >= policy.standard_independent_families and not decision.rejection_reasons
            and (decision.weighted_agreement or Decimal(0)) >= policy.minimum_standard_agreement
            and edge >= policy.standard_edge + uncertainty
            and policy.profile not in {'UNKNOWN', 'FRIENDLY'}
        ) else 'EXPERIMENTAL'
        decision = replace(decision, decision='APPROVED',
                           approval_reasons=(*decision.approval_reasons, 'PROFILE_' + lane), rejection_reasons=())
    else:
        decision = replace(decision, decision='REJECTED', rejection_reasons=tuple(sorted(set(hard + soft))))
    return decision, {'candidate_lane': lane, 'profile_policy_version': policy.version,
                      'uncertainty_penalty': str(uncertainty), 'soft_penalties': penalties,
                      'missing_features': list(missing), 'hard_failures': sorted(set(hard)),
                      'soft_findings': sorted(set(soft)), 'calibration_status': 'UNCALIBRATED_LAB_ENSEMBLE',
                      'minimum_required_edge': str(policy.experimental_edge + uncertainty)}


def next_refresh(kickoff: datetime, now: datetime, policy: ProfilePolicy) -> datetime | None:
    """Deterministic data-usefulness windows, invoked manually without timers."""
    return next((kickoff - timedelta(minutes=m) for m in policy.refresh_minutes
                 if kickoff - timedelta(minutes=m) > now), None)
