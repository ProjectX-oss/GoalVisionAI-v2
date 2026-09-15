"""Availability-aware, market-specific LAB_V2_SHADOW ensemble policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext


POLICY_VERSION = "LAB_V2_SHADOW_PHASE1_V1"
MIN_SINGLE_ODDS = Decimal("1.70")
MIN_COMBINED_ODDS = Decimal("2.00")
_FAMILY = {
    "HOME_WIN": "1X2", "DRAW": "1X2", "AWAY_WIN": "1X2",
    "BTTS_YES": "BTTS", "BTTS_NO": "BTTS",
    "OVER_1_5": "TOTAL_1_5", "UNDER_1_5": "TOTAL_1_5",
    "OVER_2_5": "TOTAL_2_5", "UNDER_2_5": "TOTAL_2_5",
    "OVER_3_5": "TOTAL_3_5", "UNDER_3_5": "TOTAL_3_5",
}


@dataclass(frozen=True, slots=True)
class EnsembleSignal:
    name: str
    market: str
    probability: Decimal | None
    selection: str | None
    reliability: Decimal
    availability: str
    provenance: str


@dataclass(frozen=True, slots=True)
class EnsembleDecision:
    policy: str
    market: str
    decision: str
    confidence: str
    ensemble_probability: Decimal | None
    offered_odds: Decimal | None
    offered_implied_probability: Decimal | None
    edge: Decimal | None
    available_signals: int
    weighted_agreement: Decimal | None
    signals: tuple[EnsembleSignal, ...]
    approval_reasons: tuple[str, ...]
    rejection_reasons: tuple[str, ...]


def evaluate_ensemble(market: str, offered_odds: Decimal | None, signals: list[EnsembleSignal]) -> EnsembleDecision:
    """Evaluate independent evidence without requiring every signal to exist."""
    blockers: list[str] = []
    reasons: list[str] = []
    if market not in _FAMILY:
        blockers.append("UNSUPPORTED_MARKET")
    if offered_odds is None:
        blockers.append("CURRENT_PRICE_UNAVAILABLE")
    elif offered_odds < MIN_SINGLE_ODDS:
        blockers.append("SINGLE_ODDS_BELOW_1_70")
    usable = tuple(sorted((item for item in signals if item.availability in {"AVAILABLE", "LOW_SAMPLE"}
                           and item.reliability > 0 and (item.probability is not None or item.selection is not None)),
                          key=lambda item: item.name))
    probabilities = tuple(item for item in usable if item.probability is not None)
    names = {item.name for item in usable}
    if "CURRENT_MARKET_CONSENSUS" not in names:
        blockers.append("CURRENT_MARKET_CONSENSUS_UNAVAILABLE")
    minimum = 3 if _FAMILY.get(market) == "1X2" else 3
    if len(usable) < minimum:
        blockers.append("INSUFFICIENT_INDEPENDENT_SIGNALS")
    if not probabilities:
        blockers.append("ENSEMBLE_PROBABILITY_UNAVAILABLE")
        ensemble = agreement = implied = edge = None
    else:
        with localcontext() as context:
            context.prec = 28
            total_weight = sum((item.reliability for item in probabilities), Decimal(0))
            ensemble = sum((item.probability * item.reliability for item in probabilities), Decimal(0)) / total_weight
            agreement_weight = sum((item.reliability for item in probabilities
                                    if abs(item.probability - ensemble) <= Decimal("0.10")), Decimal(0))
            agreement = agreement_weight / total_weight
            implied = Decimal(1) / offered_odds if offered_odds else None
            edge = ensemble - implied if implied is not None else None
        trustworthy = [item for item in probabilities if item.reliability >= Decimal("0.60")]
        spread = max((item.probability for item in trustworthy), default=ensemble) - min(
            (item.probability for item in trustworthy), default=ensemble
        )
        opposing_votes = [item.name for item in usable if item.selection is not None
                          and _FAMILY.get(item.selection) == _FAMILY.get(market) and item.selection != market
                          and item.reliability >= Decimal("0.75")]
        if spread > Decimal("0.22") or len(opposing_votes) >= 2:
            blockers.append("MATERIAL_SIGNAL_DISAGREEMENT")
        if agreement < Decimal("0.65"):
            blockers.append("WEIGHTED_AGREEMENT_BELOW_0_65")
        if edge is not None and edge < Decimal("0.04"):
            blockers.append("ENSEMBLE_EDGE_BELOW_0_04")
        if edge is not None and edge > Decimal("0.18"):
            blockers.append("ENSEMBLE_MARKET_DIVERGENCE_TOO_LARGE")
        if not blockers:
            reasons.extend(("AVAILABILITY_AWARE_SIGNAL_QUORUM", "CURRENT_MARKET_INCLUDED", "NO_MATERIAL_DISAGREEMENT"))
    confidence = _confidence(agreement, edge, len(usable)) if not blockers else "LOW"
    return EnsembleDecision(
        POLICY_VERSION, market, "APPROVED" if not blockers else "REJECTED", confidence,
        ensemble, offered_odds, implied, edge, len(usable), agreement, usable,
        tuple(reasons), tuple(sorted(set(blockers))),
    )


def _confidence(agreement: Decimal | None, edge: Decimal | None, count: int) -> str:
    if agreement is None or edge is None:
        return "LOW"
    if count >= 5 and agreement >= Decimal("0.85") and edge >= Decimal("0.07"):
        return "HIGH"
    if count >= 4 and agreement >= Decimal("0.75"):
        return "MEDIUM"
    return "LOW"
