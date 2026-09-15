"""Explicit Lab-only V2 publication handoff to the existing settlement ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from itertools import combinations

from app.lab_combo.presentation import latvia_time, market_label, public_decimal
from app.lab_combo.repository import ComboRepository
from app.real_match_lab_analysis.fingerprint import fingerprint


MAX_SINGLES_PER_CYCLE = 3
MAX_COMBOS_PER_CYCLE = 3


def prepare_v2_publications(report: dict[str, object], ledger: ComboRepository, *, now: datetime) -> dict[str, object]:
    """Persist only final-reviewed V2 READY singles and independent triples."""
    clock = now.astimezone(timezone.utc)
    ready = [
        dict(item) for item in report.get("candidate_markets", [])
        if item.get("decision") == "APPROVED" and item.get("stage") == "READY_TO_PUBLISH"
    ]
    ready.sort(key=lambda item: (
        -Decimal(str(item.get("edge") or "-99")),
        item["kickoff_utc"], item["fixture_id"], item["market"],
    ))
    consumed_keys = {
        value.get("publication_key") for value in ledger.all("single_prediction")
        if (
            ledger.get("claim", "single_prediction:" + value["prediction_id"])
            or ledger.get("receipt", "single_prediction:" + value["prediction_id"])
        )
    }
    consumed_combo_keys = {
        tuple(sorted(leg["publication_key"] for leg in value["legs"]))
        for value in ledger.all("prediction")
        if (
            ledger.get("claim", "combo_prediction:" + value["prediction_id"])
            or ledger.get("receipt", "combo_prediction:" + value["prediction_id"])
        )
    }
    singles = []
    used_fixtures: set[int] = set()
    for candidate in ready:
        key = f"{candidate['fixture_id']}:{candidate['market']}"
        if key in consumed_keys or int(candidate["fixture_id"]) in used_fixtures:
            continue
        value = _leg(candidate, clock)
        value["prediction_id"] = "lab-v2-single-" + fingerprint((candidate["policy"], key, candidate["quote_provenance_fingerprint"]))
        value["accounting"] = "LAB_ONLY_HYPOTHETICAL_ONE_UNIT"
        if ledger.append("single_prediction", value["prediction_id"], value):
            ledger.append("single_preview", value["prediction_id"], {"message": v2_single_message(value)})
            ledger.append("v2_segmentation", value["prediction_id"], _segmentation(value, "SINGLE"))
        singles.append(value)
        used_fixtures.add(int(candidate["fixture_id"]))
        if len(singles) == MAX_SINGLES_PER_CYCLE:
            break

    combos = []
    remaining = [_leg(candidate, clock) for candidate in ready]
    consumed_fixtures: set[int] = set()
    consumed_teams: set[str] = set()
    for group in combinations(remaining, 3):
        fixtures = {int(item["fixture_id"]) for item in group}
        teams = {str(item[key]) for item in group for key in ("home_team_id", "away_team_id")}
        if len(fixtures) != 3 or len(teams) != 6 or fixtures & consumed_fixtures or teams & consumed_teams:
            continue
        combined = Decimal(1)
        for leg in group:
            combined *= Decimal(leg["odds"])
        if combined < Decimal("2.00"):
            continue
        key = tuple(sorted(item["publication_key"] for item in group))
        if key in consumed_combo_keys:
            continue
        combo = {
            "prediction_id": "lab-v2-combo-" + fingerprint(("LAB_V2", key)),
            "policy": "LAB_V2_BROAD_COVERAGE_COMBO_V1",
            "created_at_utc": clock.isoformat(),
            "legs": [dict(item) for item in group],
            "combined_odds": str(combined),
            "accounting": "LAB_ONLY_HYPOTHETICAL_ONE_UNIT",
            "correlation_review": "PASSED_DISTINCT_FIXTURES_TEAMS_AND_DISJOINT_BATCH",
        }
        if ledger.append("prediction", combo["prediction_id"], combo):
            ledger.append("preview", combo["prediction_id"], {"message": v2_combo_message(combo, len(combos) + 1)})
            ledger.append("v2_segmentation", combo["prediction_id"], {"kind": "COMBO", "legs": [_segmentation(item, "SINGLE") for item in group]})
        combos.append(combo)
        consumed_fixtures.update(fixtures)
        consumed_teams.update(teams)
        if len(combos) == MAX_COMBOS_PER_CYCLE:
            break
    return {"singles": singles, "combos": combos, "ready_input_count": len(ready)}


def v2_single_message(value: dict) -> str:
    lines = [
        "🧪 GoalVision AI Lab",
        f"⚽ Mačs: {value['home_team']} – {value['away_team']}",
        f"🎯 Likme: {market_label(value['market'])}",
        f"💰 Koef.: {public_decimal(value['captured_odds'])}",
        f"⏰ Starts: {latvia_time(value['kickoff_utc'])}",
    ]
    if value.get("confidence") == "HIGH":
        lines.append("⭐ Confidence: HIGH")
    return "\n".join(lines)


def v2_combo_message(value: dict, number: int) -> str:
    lines = [f"🧪 GoalVision AI Lab Combo #{number}"]
    for symbol, leg in zip(("1️⃣", "2️⃣", "3️⃣"), value["legs"], strict=True):
        lines.extend((
            f"{symbol} {leg['home_team']} – {leg['away_team']}",
            f"🎯 Likme: {market_label(leg['market'])}",
            f"💰 Koef.: {public_decimal(leg['captured_odds'])}",
        ))
    first = min(datetime.fromisoformat(leg["kickoff_utc"]) for leg in value["legs"])
    lines.extend((
        f"🔥 Kopējais koef.: {public_decimal(value['combined_odds'])}",
        f"⏰ Pirmais starts: {latvia_time(first.isoformat())}",
    ))
    return "\n".join(lines)


def _leg(candidate: dict, now: datetime) -> dict:
    key = f"{candidate['fixture_id']}:{candidate['market']}"
    return {
        **candidate,
        "observation_id": candidate["candidate_id"],
        "publication_key": key,
        "odds": candidate["captured_odds"],
        "probability": candidate.get("ensemble_probability"),
        "expected_value": candidate.get("edge"),
        "prepared_at_utc": now.isoformat(),
    }


def _segmentation(value: dict, kind: str) -> dict[str, object]:
    return {
        "kind": kind, "market": value.get("market"), "league": value.get("league"),
        "capability_tier": value.get("capability_tier"), "odds_band": value.get("odds_band"),
        "confidence": value.get("confidence"), "pi_available": value.get("pi_available"),
        "pi_agreement": value.get("pi_agreement"),
        "api_prediction_relation": value.get("api_prediction_relation"),
        "market_consensus_relation": value.get("market_consensus_relation"),
        "lineup_confirmed": value.get("lineup_confirmed"),
        "ensemble_decision_class": value.get("ensemble_decision_class"),
    }
