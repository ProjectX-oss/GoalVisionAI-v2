"""Independent Official-aligned single selection and disagreement classification."""

from decimal import Decimal

from .fingerprint import sha256_fingerprint
from .models import (
    DisagreementSeverity, DisagreementType, PreMatchOutcome, ShadowComparison,
    ShadowSelection,
)


def select_one(role, assessments, policy, *, namespace=""):
    eligible = tuple(item for item in assessments if item.eligible)
    ranked = sorted(eligible, key=lambda item: (
        -item.expected_value, -item.calibrated_probability, -item.edge,
        -item.decimal_odds, item.deterministic_rank, item.assessment_id,
    ))
    winner = ranked[0] if ranked else None
    core = {
        "role": role, "assessments": tuple(item.assessment_fingerprint for item in assessments),
        "selected": winner.assessment_fingerprint if winner else None,
        "policy": policy.selection_policy_version,
    }
    fingerprint = sha256_fingerprint(core)
    return ShadowSelection(
        selection_id=f"shadow-selection-{sha256_fingerprint((namespace, role, fingerprint))}",
        model_role=role, selected_assessment_id=winner.assessment_id if winner else None,
        market_identity=winner.market_identity if winner else None,
        probability=winner.calibrated_probability if winner else None,
        decimal_odds=winner.decimal_odds if winner else None,
        expected_value=winner.expected_value if winner else None,
        outcome=PreMatchOutcome.EVALUATED if winner else PreMatchOutcome.NO_SELECTION,
        reason_codes=() if winner else ("NO_ELIGIBLE_SINGLE",),
        selection_fingerprint=fingerprint,
    )


def compare(champion_inference, challenger_inference, champion_selection, challenger_selection, policy, *, namespace=""):
    champion = {item.target.value: item.probability for item in champion_inference.calibrated_probabilities.ordered_probabilities}
    challenger = {item.target.value: item.probability for item in challenger_inference.calibrated_probabilities.ordered_probabilities}
    deltas = tuple((name, abs(challenger[name] - champion[name])) for name in champion)
    maximum = max(value for _, value in deltas)
    mean = sum((value for _, value in deltas), Decimal(0)) / Decimal(len(deltas))
    if champion_selection.market_identity is None and challenger_selection.market_identity is None:
        kind = DisagreementType.BOTH_NO_SELECTION
    elif champion_selection.market_identity is None:
        kind = DisagreementType.CHALLENGER_ONLY_SELECTION
    elif challenger_selection.market_identity is None:
        kind = DisagreementType.CHAMPION_ONLY_SELECTION
    elif champion_selection.market_identity != challenger_selection.market_identity:
        kind = DisagreementType.DIFFERENT_MARKET
    elif maximum == 0 and champion_selection.expected_value == challenger_selection.expected_value:
        kind = DisagreementType.EXACT_AGREEMENT
    elif champion_selection.outcome != challenger_selection.outcome:
        kind = DisagreementType.SAME_MARKET_DIFFERENT_ELIGIBILITY
    else:
        kind = DisagreementType.SAME_MARKET_DIFFERENT_PROBABILITY
    if kind in (DisagreementType.EXACT_AGREEMENT, DisagreementType.BOTH_NO_SELECTION):
        severity = DisagreementSeverity.NONE
    elif maximum < policy.probability_delta_low:
        severity = DisagreementSeverity.LOW
    elif maximum < policy.probability_delta_moderate:
        severity = DisagreementSeverity.MODERATE
    elif maximum < policy.probability_delta_high:
        severity = DisagreementSeverity.HIGH
    else:
        severity = DisagreementSeverity.CRITICAL
    selected_fair_delta = None
    selected_ev_delta = None
    confidence_delta = None
    if champion_selection.probability is not None and challenger_selection.probability is not None:
        confidence_delta = challenger_selection.probability - champion_selection.probability
        selected_ev_delta = challenger_selection.expected_value - champion_selection.expected_value
        selected_fair_delta = Decimal(1) / challenger_selection.probability - Decimal(1) / champion_selection.probability
    core = {
        "champion": champion_inference.calibrated_inference_fingerprint,
        "challenger": challenger_inference.calibrated_inference_fingerprint,
        "champion_selection": champion_selection.selection_fingerprint,
        "challenger_selection": challenger_selection.selection_fingerprint,
        "kind": kind, "severity": severity, "deltas": deltas, "policy": policy.comparison_policy_version,
    }
    fingerprint = sha256_fingerprint(core)
    return ShadowComparison(
        comparison_id=f"shadow-comparison-{sha256_fingerprint((namespace, fingerprint))}", disagreement_type=kind,
        severity=severity, target_probability_deltas=deltas,
        maximum_probability_delta=maximum, mean_probability_delta=mean,
        result_distribution_delta=sum((value for name, value in deltas if name in ("HOME_WIN", "DRAW", "AWAY_WIN")), Decimal(0)) / Decimal(3),
        totals_delta=sum((value for name, value in deltas if name.startswith(("OVER_", "UNDER_"))), Decimal(0)) / Decimal(6),
        btts_delta=sum((value for name, value in deltas if name.startswith("BTTS_")), Decimal(0)) / Decimal(2),
        fair_odds_delta=selected_fair_delta, expected_value_delta=selected_ev_delta,
        eligibility_changed=champion_selection.outcome != challenger_selection.outcome,
        selection_changed=champion_selection.market_identity != challenger_selection.market_identity,
        confidence_delta=confidence_delta, reason_codes=(kind.value,), comparison_fingerprint=fingerprint,
    )
