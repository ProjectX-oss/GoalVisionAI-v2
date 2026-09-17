"""Availability-aware, market-specific LAB_V2_SHADOW ensemble policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext


POLICY_VERSION = "LAB_V2_BROAD_COVERAGE_ENSEMBLE_V4"
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
    independence_group: str | None = None


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


def evaluate_ensemble(
    market: str,
    offered_odds: Decimal | None,
    signals: list[EnsembleSignal],
    *,
    severe_current_match_contradiction: bool = False,
) -> EnsembleDecision:
    """Evaluate independent evidence without requiring every signal to exist."""
    blockers: list[str] = []
    reasons: list[str] = []
    if market not in _FAMILY:
        blockers.append("UNSUPPORTED_MARKET")
    if severe_current_match_contradiction:
        blockers.append("SEVERE_CURRENT_MATCH_INTELLIGENCE_CONTRADICTION")
    if offered_odds is None:
        blockers.append("CURRENT_PRICE_UNAVAILABLE")
    elif not offered_odds.is_finite() or offered_odds <= Decimal(1):
        blockers.append("INVALID_CURRENT_DECIMAL_ODDS")
    invalid = any(
        item.market != market or not item.reliability.is_finite() or item.reliability < 0
        or (item.probability is not None and (not item.probability.is_finite()
            or not Decimal(0) <= item.probability <= Decimal(1))) for item in signals
    )
    if invalid:
        return EnsembleDecision(POLICY_VERSION, market, "REJECTED", "LOW", None,
                                offered_odds, None, None, 0, None, (), (),
                                ("INVALID_SIGNAL_PROBABILITY_OR_CONTRACT",))
    valid_odds = (
        offered_odds is not None
        and offered_odds.is_finite()
        and offered_odds > Decimal(1)
    )
    raw_usable = tuple(sorted((item for item in signals if item.availability in {"AVAILABLE", "LOW_SAMPLE"}
                               and item.reliability > 0 and (item.probability is not None or item.selection is not None)),
                              key=lambda item: (item.name, item.provenance)))
    duplicate_names = {item.name for item in raw_usable if sum(other.name == item.name for other in raw_usable) > 1}
    if duplicate_names:
        blockers.append("DUPLICATE_SIGNAL_SOURCE")
    # A signal source may contribute at most once even if a caller accidentally
    # supplies the same adapter twice.
    by_name: dict[str, EnsembleSignal] = {}
    for item in raw_usable:
        by_name.setdefault(item.name, item)
    usable = tuple(by_name[name] for name in sorted(by_name))
    probabilities = tuple(item for item in usable if item.probability is not None)
    names = {item.name for item in usable}
    if "CURRENT_MARKET_CONSENSUS" not in names:
        blockers.append("CURRENT_MARKET_CONSENSUS_UNAVAILABLE")
    minimum = 3
    independent_groups = {_independence_group(item) for item in probabilities}
    if len(independent_groups) < minimum:
        blockers.append("INSUFFICIENT_INDEPENDENT_SIGNALS")
    if not probabilities:
        blockers.append("ENSEMBLE_PROBABILITY_UNAVAILABLE")
        ensemble = agreement = implied = edge = None
    else:
        with localcontext() as context:
            context.prec = 28
            grouped: dict[str, list[tuple[EnsembleSignal, Decimal]]] = {}
            for item in probabilities:
                grouped.setdefault(_independence_group(item), []).append(
                    (item, _market_weight(item, _FAMILY.get(market)))
                )
            # Correlated implementations sharing one evidence family are first
            # combined inside that family. The family then receives one weight,
            # so reliability is not applied repeatedly as if the inputs were
            # independent observations.
            weighted_groups: list[tuple[Decimal, Decimal]] = []
            for group in sorted(grouped):
                members = grouped[group]
                member_weight = sum((weight for _, weight in members), Decimal(0))
                probability = sum(
                    (item.probability * weight for item, weight in members), Decimal(0)
                ) / member_weight
                weighted_groups.append((probability, max(weight for _, weight in members)))
            total_weight = sum((weight for _, weight in weighted_groups), Decimal(0))
            ensemble = sum((probability * weight for probability, weight in weighted_groups), Decimal(0)) / total_weight
            agreement_weight = sum((weight for probability, weight in weighted_groups
                                    if abs(probability - ensemble) <= Decimal("0.10")), Decimal(0))
            agreement = agreement_weight / total_weight
            implied = Decimal(1) / offered_odds if valid_odds else None
            edge = ensemble - implied if implied is not None else None
        trustworthy = [value for value in weighted_groups if value[1] >= Decimal("0.60")]
        spread = max((value[0] for value in trustworthy), default=ensemble) - min(
            (value[0] for value in trustworthy), default=ensemble
        )
        opposing_votes = {_independence_group(item) for item in usable if item.selection is not None
                          and _FAMILY.get(item.selection) == _FAMILY.get(market) and item.selection != market
                          and item.reliability >= Decimal("0.75")}
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
        ensemble, offered_odds, implied, edge, len(independent_groups), agreement, usable,
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


def _market_weight(signal: EnsembleSignal, family: str | None) -> Decimal:
    """Apply reviewed relevance by market family without mutating evidence."""
    factor = Decimal(1)
    if signal.name == "PI_RATINGS":
        factor = Decimal("1.15") if family == "1X2" else Decimal("0.35")
    elif signal.name == "CURRENT_MATCH_INTELLIGENCE":
        factor = Decimal("1.10") if family != "1X2" else Decimal("0.85")
    elif signal.name == "API_FOOTBALL_PREDICTION":
        factor = Decimal("0.95")
    elif signal.name == "CURRENT_MARKET_CONSENSUS":
        factor = Decimal("1.00")
    return signal.reliability * factor


def _independence_group(signal: EnsembleSignal) -> str:
    if signal.independence_group:
        return signal.independence_group
    if signal.name in {
        "PI_RATINGS", "CURRENT_MATCH_INTELLIGENCE", "GOALVISION_EXPERIMENTAL_MODEL",
    }:
        return "RESULT_HISTORY_MODEL_CONTEXT"
    return signal.name
