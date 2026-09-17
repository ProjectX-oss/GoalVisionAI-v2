"""Lab outcome segmentation; singles and combos remain separate."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable


SEGMENT_FIELDS = (
    "competition_profile", "candidate_lane", "market", "league", "capability_tier", "odds_band", "confidence",
    "lineup_confirmed", "pi_available", "api_prediction_relation",
    "pi_agreement", "market_consensus_relation", "ensemble_decision_class",
)


def odds_band(value: object) -> str:
    odds = Decimal(str(value))
    if odds < Decimal("1.70"):
        return "BELOW_1.70"
    if odds < Decimal("2.00"):
        return "1.70-1.99"
    if odds < Decimal("2.50"):
        return "2.00-2.49"
    if odds < Decimal("3.50"):
        return "2.50-3.49"
    return "3.50+"


def segment_results(rows: Iterable[dict]) -> dict[str, list[dict[str, object]]]:
    buckets: dict[str, dict[tuple[str, str], dict[str, object]]] = {
        "SINGLE": {}, "COMBO": {},
    }
    for row in rows:
        kind = "COMBO" if row.get("kind") == "COMBO" else "SINGLE"
        status = str(row.get("status") or "PENDING")
        for field in SEGMENT_FIELDS:
            value = str(row.get(field) or "UNKNOWN")
            key = (field, value)
            bucket = buckets[kind].setdefault(key, {
                "dimension": field, "value": value, "total": 0,
                "won": 0, "lost": 0, "void": 0, "pending": 0,
            })
            bucket["total"] += 1
            target = status.lower() if status in {"WON", "LOST", "VOID"} else "pending"
            bucket[target] += 1
    return {
        kind: [items[key] for key in sorted(items)]
        for kind, items in buckets.items()
    }
