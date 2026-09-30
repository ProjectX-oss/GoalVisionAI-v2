"""Explicit Lab-only V2 publication handoff to the existing settlement ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from itertools import combinations
from zoneinfo import ZoneInfo

from app.lab_combo.presentation import latvia_time, market_label, public_decimal
from app.lab_combo.repository import ComboRepository
from app.lab_combo.publication_window import publication_blocker
from app.real_match_lab_analysis.fingerprint import fingerprint


from .forward_evidence import current_quote
from .publication_policy import (review_publication, review_accuracy_publication,
    PUBLICATION_POLICY_VERSION, ACCURACY_PUBLICATION_POLICY_VERSION)


MAX_SINGLES_PER_CYCLE = 3
MAX_COMBOS_PER_CYCLE = 3
MIN_PUBLISHED_MARKET_PROBABILITY = Decimal("0.55")
MIN_PUBLISHED_DECIMAL_ODDS = Decimal("1.30")
SINGLE_SELECTION_POLICY = "LAB_SINGLE_ACCURACY_FIRST_PER_FIXTURE_V1"


def _single_rank(item: dict[str, object]) -> tuple:
    return (
        -Decimal(str(item["ensemble_probability"])),
        {"STRONG": 0, "STANDARD": 1, "EXPERIMENTAL": 2}.get(item.get("candidate_lane"), 3),
        -Decimal(str(item.get("edge") or "-99")),
        item.get("kickoff_utc", ""),
        int(item["fixture_id"]),
        str(item["market"]),
    )


def _probability_first_single_candidates(ready: list[dict[str, object]]) -> list[dict[str, object]]:
    """Choose one highest-probability eligible market per fixture, then rank fixtures by probability."""
    best_by_fixture: dict[int, dict[str, object]] = {}
    for item in ready:
        fixture_id = int(item["fixture_id"])
        previous = best_by_fixture.get(fixture_id)
        if previous is None or _single_rank(item) < _single_rank(previous):
            best_by_fixture[fixture_id] = item
    return sorted(best_by_fixture.values(), key=_single_rank)


def prepare_v2_publications(report: dict[str, object], ledger: ComboRepository, *, now: datetime,
                            label_origin: bool = False, football_context: object | None = None) -> dict[str, object]:
    """Persist only final-reviewed V2 READY singles and independent triples."""
    clock = now.astimezone(timezone.utc)
    combo_ready = []
    single_pool = []
    publication_blockers = {}
    publication_reviews = {}
    single_publication_blockers = {}
    single_publication_reviews = {}
    for item in report.get("candidate_markets", []):
        candidate_id = str(item.get("candidate_id", item.get("fixture_id", "UNKNOWN")))
        try:
            blocker = publication_blocker(clock, [item["kickoff_utc"]])
            if blocker:
                publication_blockers[candidate_id] = blocker
                single_publication_blockers[candidate_id] = blocker
                continue
            if datetime.fromisoformat(item["kickoff_utc"]) <= clock or not current_quote(item, clock):
                continue
            odds = Decimal(str(item["captured_odds"]))
            probability = Decimal(str(item["ensemble_probability"]))
        except (KeyError, ValueError, TypeError, InvalidOperation):
            continue
        if (not odds.is_finite() or odds <= Decimal(1)
                or not probability.is_finite() or not Decimal(0) < probability < Decimal(1)):
            continue

        # SINGLE: accuracy-first. EV is diagnostic only. A candidate rejected
        # solely for NON_POSITIVE_VALUE may still qualify if all identity,
        # freshness, replay and severe-contradiction checks pass.
        if probability < MIN_PUBLISHED_MARKET_PROBABILITY:
            single_publication_blockers[candidate_id] = "LAB_PUBLICATION_PROBABILITY_BELOW_0_55"
        elif odds < MIN_PUBLISHED_DECIMAL_ODDS:
            single_publication_blockers[candidate_id] = "LAB_PUBLICATION_ODDS_BELOW_1_30"
        elif item.get("stage") in {"READY_TO_PUBLISH", "REJECTED"} and item.get("candidate_lane") != "TRACKING":
            accuracy_gate = review_accuracy_publication(item, now=clock)
            single_publication_reviews[candidate_id] = accuracy_gate
            if accuracy_gate["eligible"]:
                single_pool.append({
                    **item,
                    "accuracy_publication_policy_version": ACCURACY_PUBLICATION_POLICY_VERSION,
                    "accuracy_publication_review": accuracy_gate,
                })
            else:
                single_publication_blockers[candidate_id] = "LAB_ACCURACY_PUBLICATION_POLICY_REJECTED"

        # COMBO: unchanged positive-EV path.
        if (item.get("decision") == "APPROVED" and item.get("stage") == "READY_TO_PUBLISH"
                and item.get("candidate_lane") != "TRACKING"):
            gate = review_publication(item, now=clock)
            publication_reviews[candidate_id] = gate
            if not gate["eligible"]:
                publication_blockers[candidate_id] = "LAB_PUBLICATION_POLICY_REJECTED"
                continue
            if probability * odds <= 1:
                continue
            combo_ready.append({
                **item,
                "publication_policy_version": PUBLICATION_POLICY_VERSION,
                "publication_review": gate,
            })
    single_ready = _probability_first_single_candidates(single_pool)
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
    for candidate in single_ready:
        key = f"{candidate['fixture_id']}:{candidate['market']}"
        if key in consumed_keys or int(candidate["fixture_id"]) in used_fixtures:
            continue
        value = _leg(candidate, clock)
        value["single_selection_policy"] = SINGLE_SELECTION_POLICY
        value["minimum_published_probability"] = str(MIN_PUBLISHED_MARKET_PROBABILITY)
        value["minimum_published_decimal_odds"] = str(MIN_PUBLISHED_DECIMAL_ODDS)
        value["prediction_id"] = "lab-v2-single-" + fingerprint((
            candidate["policy"], key, candidate["candidate_id"],
            candidate["quote_provenance_fingerprint"],
        ))
        value["accounting"] = "LAB_ONLY_HYPOTHETICAL_ONE_UNIT"
        existing = ledger.get('single_prediction', value['prediction_id'])
        if existing is not None:
            # Retain old previews and attribution exactly, even on a new-label replay.
            from .origin import is_labelled
            if label_origin and not is_labelled(existing):
                publication_blockers[candidate['candidate_id']] = 'HISTORICAL_PREVIEW_REQUIRES_NEW_DECISION'
                continue
            value = existing
        elif label_origin:
            from .origin import freeze_origin
            value['selection_origin'] = freeze_origin(candidate, now=clock, observer=football_context)
            from .public_presentation import VERSION
            from .statistics import public_single_snapshot
            value['public_presentation'] = {
                'version': VERSION, 'statistics': public_single_snapshot(ledger, as_of=clock)}
        if ledger.append("single_prediction", value["prediction_id"], value):
            ledger.append("single_preview", value["prediction_id"], {"message": v2_single_message(value)})
            ledger.append("v2_segmentation", value["prediction_id"], _segmentation(value, "SINGLE"))
        singles.append(value)
        used_fixtures.add(int(candidate["fixture_id"]))
        if len(singles) == MAX_SINGLES_PER_CYCLE:
            break

    combos = []
    remaining = sorted(
        (_leg(candidate, clock) for candidate in combo_ready),
        key=lambda item: (
            -Decimal(str(item.get("edge") or "-99")), item["kickoff_utc"],
            item["fixture_id"], item["market"], item["candidate_id"],
        ),
    )
    consumed_fixtures: set[int] = set()
    consumed_teams: set[str] = set()
    while len(combos) < MAX_COMBOS_PER_CYCLE:
        choices = []
        for group in combinations(remaining, 3):
            fixtures = {int(item["fixture_id"]) for item in group}
            teams = {str(item[key]) for item in group for key in ("home_team_id", "away_team_id")}
            if len(fixtures) != 3 or len(teams) != 6 or fixtures & consumed_fixtures or teams & consumed_teams:
                continue
            publication_keys = tuple(sorted(item["publication_key"] for item in group))
            if publication_keys in consumed_combo_keys:
                continue
            rank = (
                -min(Decimal(str(item["edge"])) for item in group),
                -sum((Decimal(str(item["edge"])) for item in group), Decimal(0)),
                tuple(item["publication_key"] for item in group),
            )
            choices.append((rank, group, fixtures, teams, publication_keys))
        if not choices:
            break
        _, group, fixtures, teams, key = min(choices, key=lambda item: item[0])
        combined = Decimal(1)
        for leg in group:
            combined *= Decimal(leg["odds"])
        combo = {
            "prediction_id": "lab-v2-combo-" + fingerprint((
                "LAB_V2", key, tuple(item["candidate_id"] for item in group),
                tuple(item["quote_provenance_fingerprint"] for item in group),
            )),
            "policy": "LAB_V2_BROAD_COVERAGE_COMBO_V2",
            "publication_policy_version": PUBLICATION_POLICY_VERSION,
            "created_at_utc": max(item["prepared_at_utc"] for item in group),
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
        remaining = [item for item in remaining
                     if int(item["fixture_id"]) not in consumed_fixtures
                     and not consumed_teams.intersection({str(item["home_team_id"]), str(item["away_team_id"])})]
    return {"publication_reviews": publication_reviews, "publication_policy_version": PUBLICATION_POLICY_VERSION,
            "single_publication_reviews": single_publication_reviews,
            "single_accuracy_publication_policy_version": ACCURACY_PUBLICATION_POLICY_VERSION,
            "single_selection_policy": SINGLE_SELECTION_POLICY,
            "minimum_published_probability": str(MIN_PUBLISHED_MARKET_PROBABILITY),
            "minimum_published_decimal_odds": str(MIN_PUBLISHED_DECIMAL_ODDS),
            "single_publication_blockers": single_publication_blockers,
            "publication_blockers":publication_blockers,"singles": singles, "combos": combos,
            "ready_input_count": len(combo_ready), "accuracy_single_input_count": len(single_pool)}


def v2_single_message(value: dict) -> str:
    from .origin import LABEL, is_labelled
    if is_labelled(value) and 'public_presentation' in value:
        from .public_presentation import prediction_message
        return prediction_message(value)
    if is_labelled(value):
        # Historical version: replay and delivery validation retain exact bytes.
        origin = value['selection_origin']
        families = ', '.join(origin['predictive_families']) or 'saglabātā atlases politika'
        lines = [LABEL, 'Eksperimentāla atlase; nekalibrēts novērtējums.',
            f"⚽ Mačs: {value['home_team']} – {value['away_team']}",
            f"🎯 Likme: {market_label(value['market'])}",
            f"💰 Koef.: {public_decimal(value['captured_odds'])}",
            f"⏰ Starts: {datetime.fromisoformat(value['kickoff_utc']).astimezone(ZoneInfo('Europe/Riga')):%d.%m.%Y %H:%M} (Latvija)",
            f"Novērtētā varbūtība: {Decimal(value['ensemble_probability']) * 100:.1f}%",
            f"Pamatojums: {families}; vērtības pārsvars {Decimal(value['edge']) * 100:.1f} procentpunkti.",
            'Noslēguma pārbaude pabeigta; iznākums nav garantēts.',
            f"Atsauce: {value['prediction_id']}"]
        if origin['context'] is not None:
            lines.append(f"V2 futbola konteksts: {origin['context']['available_features']}/7 pazīmes — novērošanai")
        return '\n'.join(lines)
    lines = [
        "🧪 GoalVision AI Lab",
        f"⚽ Mačs: {value['home_team']} – {value['away_team']}",
        f"🎯 Likme: {market_label(value['market'])}",
        f"💰 Koef.: {public_decimal(value['captured_odds'])}",
        f"⏰ Starts: {latvia_time(value['kickoff_utc'])}",
    ]
    if value.get("candidate_lane"):
        lines.append(f"Lab lane: {value['candidate_lane']}")
        lines.append(f"Profile: {value.get('competition_profile', 'UNKNOWN')}")
        lines.append("Experimental uncalibrated estimate; no guaranteed outcome.")
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
    probability = Decimal(str(candidate["ensemble_probability"]))
    odds = Decimal(str(candidate["captured_odds"]))
    return {
        **candidate,
        "observation_id": candidate["candidate_id"],
        "publication_key": key,
        "odds": candidate["captured_odds"],
        "probability": candidate.get("ensemble_probability"),
        "expected_value": str(probability * odds - Decimal(1)),
        "prepared_at_utc": (
            candidate.get("final_review_completed_at_utc")
            or candidate.get("goalvision_retrieved_at_utc")
            or now.isoformat()
        ),
    }


def _segmentation(value: dict, kind: str) -> dict[str, object]:
    return {
        "kind": kind, "market": value.get("market"), "league": value.get("league"),
        "competition_profile": value.get("competition_profile"), "candidate_lane": value.get("candidate_lane"),
        "capability_tier": value.get("capability_tier"), "odds_band": value.get("odds_band"),
        "confidence": value.get("confidence"), "pi_available": value.get("pi_available"),
        "pi_agreement": value.get("pi_agreement"),
        "api_prediction_relation": value.get("api_prediction_relation"),
        "market_consensus_relation": value.get("market_consensus_relation"),
        "lineup_confirmed": value.get("lineup_confirmed"),
        "ensemble_decision_class": value.get("ensemble_decision_class"),
    }
