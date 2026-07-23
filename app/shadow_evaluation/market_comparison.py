"""Same-odds Decimal market evaluation for each isolated model role."""

from decimal import Decimal, localcontext

from .fingerprint import sha256_fingerprint
from .models import ShadowMarketAssessment

MARKETS = (
    "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5", "OVER_2_5",
    "UNDER_2_5", "OVER_3_5", "UNDER_3_5", "BTTS_YES", "BTTS_NO",
)


def assess_inference(inference, odds_set, policy, *, namespace=""):
    values = {item.target.value: item.probability for item in inference.calibrated_probabilities.ordered_probabilities}
    odds_by_market = {}
    for item in odds_set.snapshots:
        odds_by_market.setdefault(item.market_identity, []).append(item)
    rows = []
    for rank, market in enumerate(MARKETS):
        candidates = sorted(odds_by_market.get(market, ()), key=lambda item: (item.snapshot_timestamp_utc, item.source_identity, item.odds_snapshot_id))
        candidate = candidates[-1] if candidates else None
        probability = values[market]
        reasons = []
        fair = implied = edge = expected = None
        odds = None
        if candidate is None:
            reasons.append("MISSING_ODDS")
        else:
            odds = candidate.decimal_odds
            with localcontext() as context:
                context.prec = 50
                fair = Decimal(1) / probability
                implied = Decimal(1) / odds
                edge = probability - implied
                expected = probability * odds - Decimal(1)
            if candidate.market_status != "ACTIVE":
                reasons.append(f"MARKET_{candidate.market_status}")
            if odds < policy.minimum_decimal_odds:
                reasons.append("ODDS_BELOW_1_60")
            if expected < policy.minimum_expected_value:
                reasons.append("EV_BELOW_0_02")
        core = {
            "role": inference.model_role, "inference": inference.calibrated_inference_fingerprint,
            "market": market, "odds": candidate.source_fingerprint if candidate else None,
            "probability": probability, "fair_odds": fair, "implied_probability": implied,
            "edge": edge, "expected_value": expected, "eligible": not reasons,
            "reasons": tuple(reasons), "policy": policy.market_value_policy_version,
        }
        fingerprint = sha256_fingerprint(core)
        rows.append(ShadowMarketAssessment(
            assessment_id=f"shadow-assessment-{sha256_fingerprint((namespace, inference.model_role, fingerprint))}",
            model_role=inference.model_role, market_identity=market,
            odds_snapshot_id=candidate.odds_snapshot_id if candidate else None,
            calibrated_probability=probability, fair_odds=fair, decimal_odds=odds,
            implied_probability=implied, edge=edge, expected_value=expected,
            expected_profit_per_unit=expected, eligible=not reasons,
            rejection_reasons=tuple(reasons), deterministic_rank=rank,
            assessment_fingerprint=fingerprint,
        ))
    return tuple(rows)
