"""Decimal-safe fair odds, implied probability, edge, and EV assessment."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, localcontext

from .fingerprint import sha256_fingerprint
from .market_mapping import CANONICAL_MARKET_ORDER, probability_for
from .models import MarketAssessment, OddsMarketStatus


def assess_markets(predictions, odds_snapshots, policy, *, run_namespace=""):
    by_match = defaultdict(list)
    for item in odds_snapshots:
        if not item.closing:
            by_match[item.snapshot.historical_match_id].append(item)
    assessments = []
    for prediction in predictions:
        available = by_match[prediction.historical_match_id]
        for market in CANONICAL_MARKET_ORDER:
            candidates = tuple(item for item in available if item.market_identity is market)
            if not candidates:
                assessments.append(_missing(prediction, market, len(assessments), policy, run_namespace))
                continue
            for candidate in candidates:
                probability = probability_for(prediction.calibrated_probabilities, market)
                odds = candidate.snapshot.decimal_odds
                with localcontext() as context:
                    context.prec = 50
                    fair_odds = Decimal(1) / probability
                    implied = Decimal(1) / odds
                    edge = probability - implied
                    expected_value = probability * odds - Decimal(1)
                age = int(
                    (
                        datetime.fromisoformat(candidate.normalized_kickoff_utc.replace("Z", "+00:00"))
                        - datetime.fromisoformat(candidate.normalized_snapshot_timestamp_utc.replace("Z", "+00:00"))
                    ).total_seconds()
                )
                reasons = []
                if candidate.market_status is not OddsMarketStatus.ACTIVE:
                    reasons.append(f"MARKET_{candidate.market_status.value}")
                if odds < policy.minimum_decimal_odds:
                    reasons.append("ODDS_BELOW_1_60")
                if expected_value < policy.minimum_expected_value:
                    reasons.append("EV_BELOW_0_02")
                if policy.maximum_odds_age_seconds is not None and age > policy.maximum_odds_age_seconds:
                    reasons.append("STALE_ODDS")
                core = {
                    "prediction_fingerprint": prediction.calibrated_prediction_fingerprint,
                    "odds_snapshot_fingerprint": candidate.snapshot.source_fingerprint,
                    "market_identity": market,
                    "probability": probability,
                    "fair_odds": fair_odds,
                    "decimal_odds": odds,
                    "implied_probability": implied,
                    "expected_value": expected_value,
                    "edge": edge,
                    "eligible": not reasons,
                    "rejection_reasons": tuple(reasons),
                    "policy_versions": policy.versions,
                }
                fingerprint = sha256_fingerprint(core)
                assessments.append(
                    MarketAssessment(
                        assessment_id=f"historical-backtest-assessment-{sha256_fingerprint((run_namespace, fingerprint))}",
                        prediction_row_id=prediction.prediction_row_id,
                        odds_row_id=candidate.stored_odds_row_id,
                        historical_match_id=prediction.historical_match_id,
                        market_identity=market, calibrated_probability=probability,
                        fair_odds=fair_odds, decimal_odds=odds,
                        implied_probability=implied, expected_value=expected_value,
                        edge=edge, odds_age_seconds=age, eligible=not reasons,
                        rejection_reasons=tuple(reasons), assessment_fingerprint=fingerprint,
                        deterministic_rank=len(assessments),
                    )
                )
    return tuple(assessments)


def _missing(prediction, market, order, policy, run_namespace):
    core = {
        "prediction_fingerprint": prediction.calibrated_prediction_fingerprint,
        "market_identity": market, "eligible": False,
        "rejection_reasons": ("MISSING_ODDS",), "policy_versions": policy.versions,
    }
    fingerprint = sha256_fingerprint(core)
    return MarketAssessment(
        assessment_id=f"historical-backtest-assessment-{sha256_fingerprint((run_namespace, fingerprint))}",
        prediction_row_id=prediction.prediction_row_id, odds_row_id=None,
        historical_match_id=prediction.historical_match_id, market_identity=market,
        calibrated_probability=probability_for(prediction.calibrated_probabilities, market),
        fair_odds=None, decimal_odds=None, implied_probability=None,
        expected_value=None, edge=None, odds_age_seconds=None, eligible=False,
        rejection_reasons=("MISSING_ODDS",), assessment_fingerprint=fingerprint,
        deterministic_rank=order,
    )
