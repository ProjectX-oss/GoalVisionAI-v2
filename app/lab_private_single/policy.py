"""Frozen private filter over the complete natural candidate pool."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
import os
from zoneinfo import ZoneInfo

from app.lab_combo.publication_window import publication_blocker
from app.lab_combo.presentation import market_label, public_decimal
from app.lab_v2_shadow.publication_policy import review_accuracy_publication
from app.real_match_lab_analysis.fingerprint import fingerprint

FLAG = "GOALVISION_PRIVATE_SINGLE_170"
POLICY = "PRIVATE_SINGLE_170_P70_80_20261004_V1"
MIN_ODDS = Decimal("1.70")
MIN_P = Decimal("0.70")
MAX_P = Decimal("0.80")


def enabled() -> bool:
    mode = os.environ.get(FLAG, "0")
    if mode not in {"0", "1"}:
        raise ValueError("PRIVATE_SINGLE_CONFIGURATION_INVALID")
    return mode == "1"


def review(candidate: dict, *, now: datetime) -> dict:
    """Recompute existing evidence checks; no new estimate or threshold fitting."""
    from app.lab_v2_shadow.ensemble import _independence_group, EnsembleSignal
    from app.adaptive_lab.contracts import MARKETS
    base = review_accuracy_publication(candidate, now=now)
    reasons = set(base["rejection_reasons"])
    try:
        odds, probability = (Decimal(str(candidate[k])) for k in
                             ("captured_odds", "ensemble_probability"))
        if not odds.is_finite() or odds < MIN_ODDS:
            reasons.add("PRIVATE_ODDS_BELOW_1_70")
        if not probability.is_finite() or not MIN_P <= probability <= MAX_P:
            reasons.add("PRIVATE_PROBABILITY_OUTSIDE_70_80")
        kickoff = datetime.fromisoformat(candidate["kickoff_utc"])
        if (kickoff <= now or kickoff.astimezone(ZoneInfo("Europe/Riga")).date()
                != now.astimezone(ZoneInfo("Europe/Riga")).date()):
            reasons.add("PRIVATE_TODAY_PREMATCH_REQUIRED")
        blocker = publication_blocker(now, [candidate["kickoff_utc"]])
        if blocker:
            reasons.add(blocker)
        if (candidate.get("decision") != "APPROVED"
                or candidate.get("stage") != "READY_TO_PUBLISH"
                or candidate.get("candidate_lane") == "TRACKING"
                or candidate.get("market") not in MARKETS):
            reasons.add("PRIVATE_APPROVED_CANDIDATE_REQUIRED")
        signals = [EnsembleSignal(**{**s, "probability": Decimal(str(s["probability"]))
                   if s["probability"] is not None else None,
                   "reliability": Decimal(str(s["reliability"]))}) for s in candidate["signals"]]
        if not any(s.probability is not None and s.provenance
                   and s.name != "CURRENT_MARKET_CONSENSUS"
                   and _independence_group(s) != "CURRENT_MARKET_CONSENSUS" for s in signals):
            reasons.add("PRIVATE_INDEPENDENT_MODEL_EVIDENCE_REQUIRED")
    except (KeyError, ValueError, TypeError, InvalidOperation, AttributeError):
        reasons.add("PRIVATE_DECISION_EVIDENCE_INVALID")
    return {"version": POLICY, "eligible": not reasons, "rejection_reasons": sorted(reasons)}


def frozen_blocker(value: dict, *, now: datetime) -> str | None:
    if not enabled():
        return "PRIVATE_NEW_PUBLICATIONS_PAUSED"
    if (value.get("single_selection_policy") != POLICY
            or value.get("minimum_published_decimal_odds") != str(MIN_ODDS)
            or value.get("minimum_published_probability") != str(MIN_P)
            or value.get("maximum_published_probability") != str(MAX_P)
            or value.get("private_selection_review") != {
                "version": POLICY, "eligible": True, "rejection_reasons": []}):
        return "PRIVATE_FROZEN_POLICY_INVALID"
    if not review(value, now=now)["eligible"]:
        return "PRIVATE_PUBLICATION_REVIEW_REJECTED"
    return None


def prepare(report: dict, ledger, route: dict, *, now: datetime, football_context=None) -> dict:
    from .repository import PrivateSingleRepository
    from .routing import validate_route
    from app.lab_v2_shadow.publication import _leg, _single_rank
    from app.lab_v2_shadow.origin import freeze_origin
    from app.lab_v2_shadow.publication_policy import ACCURACY_PUBLICATION_POLICY_VERSION
    if not isinstance(ledger, PrivateSingleRepository):
        raise ValueError("PRIVATE_SINGLE_LEDGER_REQUIRED")
    route = validate_route(route)
    if not enabled() or now < datetime.fromisoformat(route["period_started_at"]):
        return {"status": "PAUSED", "singles": [], "eligible": 0, "rejections": {}}
    rejected, pool = Counter(), []
    for row in report.get("candidate_markets", []):
        check = review(row, now=now)
        if not check["eligible"]:
            rejected.update(check["rejection_reasons"])
        else:
            pool.append(row)
    singles = []
    for row in sorted(pool, key=_single_rank):
        if ledger.get("economic_claim", "PRIVATE_SINGLE_FIXTURE:" + str(row["fixture_id"])):
            rejected["PRIVATE_FIXTURE_ALREADY_CLAIMED"] += 1
            continue
        value = _leg(row, now)
        value.update(single_selection_policy=POLICY, minimum_published_decimal_odds=str(MIN_ODDS),
            minimum_published_probability=str(MIN_P), maximum_published_probability=str(MAX_P),
            private_selection_review={"version": POLICY, "eligible": True, "rejection_reasons": []},
            private_delivery_route=route, accounting="PRIVATE_LAB_ONLY_HYPOTHETICAL_ONE_UNIT",
            accuracy_publication_policy_version=ACCURACY_PUBLICATION_POLICY_VERSION,
            accuracy_publication_review={"version": ACCURACY_PUBLICATION_POLICY_VERSION,
                                         "eligible": True, "rejection_reasons": []},
            accuracy_review_completed_at_utc=now.isoformat())
        value["prediction_id"] = "lab-private-single-" + fingerprint((POLICY, route,
            row["fixture_id"], row["market"], row["candidate_id"], row["quote_provenance_fingerprint"]))
        value["selection_origin"] = freeze_origin(row, now=now, observer=football_context)
        existing = ledger.get("single_prediction", value["prediction_id"])
        if existing is not None:
            value = existing
        else:
            ledger.append("single_prediction", value["prediction_id"], value)
        # Recover a crash between prediction and frozen preview persistence.
        if ledger.get("single_preview", value["prediction_id"]) is None:
            ledger.append("single_preview", value["prediction_id"], {"message": message(value)})
        singles.append(value)
        break
    return {"status": "PREPARED" if singles else "NO_QUALIFYING_PICK", "singles": singles,
            "evaluated": len(report.get("candidate_markets", [])), "eligible": len(pool),
            "rejections": dict(sorted(rejected.items()))}


def message(value: dict) -> str:
    probability = Decimal(value["ensemble_probability"]) * 100
    kickoff = datetime.fromisoformat(value["kickoff_utc"]).astimezone(ZoneInfo("Europe/Riga"))
    return "\n".join([
        "🧪 GoalVision AI Lab • Privātā atlase",
        "Koef. ≥1.70 · modeļa novērtējums 70–80%",
        f"⚽ {value['home_team']} – {value['away_team']}",
        f"🎯 {market_label(value['market'])}",
        f"💰 Koef.: {public_decimal(value['captured_odds'])}",
        f"📊 Modeļa novērtējums: {probability:.1f}%",
        f"⏰ Starts: {kickoff:%d.%m.%Y %H:%M} (Latvija)",
        "Pārbaudīti aktuālie koeficienti un saglabātie modeļa signāli.",
        "Eksperimentāls, nekalibrēts novērtējums; iznākums nav garantēts.",
        "Atsevišķa privātās atlases uzskaite.",
        f"Atsauce: {value['prediction_id']}",
    ])
