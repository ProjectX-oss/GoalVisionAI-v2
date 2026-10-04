"""Opt-in second Lab COMBO policy over already captured current bookmaker quotes."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
import os
from statistics import median

from app.adaptive_lab.devig_research import capture
from app.dixon_coles_research.contracts import seal, verify, utc
from .combo_agreement import binding

POLICY = "LAB_COMBO_MULTI_BOOK_MARKET_V1"
COHORT = "COMBO_MARKET_20261004_V1"
FLAG = "GOALVISION_COMBO_MARKET_PARALLEL"
MAX_COMBOS = 1
MIN_BOOKMAKERS = 2
METHODS = ("MULTIPLICATIVE", "POWER")


def requested() -> bool:
    return os.environ.get(FLAG, "0") != "0"


def mode_blocker(policy: str) -> str | None:
    mode = os.environ.get(FLAG, "0")
    if mode not in {"0", "1"}:
        return "COMBO_MARKET_CONFIGURATION_INVALID"
    if policy == POLICY and mode != "1":
        return "COMBO_MARKET_SELECTION_DISABLED"
    return None


def evidence(candidate: dict, consensus: dict, *, now: datetime) -> dict:
    """Lower of two method medians; a ranking score, never calibrated confidence."""
    clock, kickoff = utc(now), utc(candidate["kickoff_utc"])
    market, fid = candidate["market"], int(candidate["fixture_id"])
    if consensus["fixture_id"] != fid:
        raise ValueError("COMBO_MARKET_FIXTURE_MISMATCH")
    quotes = consensus["quotes"]
    matching = [q for q in quotes if q["provenance_fingerprint"] == candidate["quote_provenance_fingerprint"]]
    if (len(matching) != 1 or matching[0]["market"] != market
            or Decimal(str(matching[0]["decimal_odds"])) != Decimal(candidate["captured_odds"])
            or utc(matching[0]["retrieved_at_utc"]) != utc(candidate["goalvision_retrieved_at_utc"])
            or utc(matching[0]["provider_origin_timestamp_utc"]) != utc(candidate["provider_origin_timestamp_utc"])):
        raise ValueError("COMBO_MARKET_QUOTE_BINDING_INVALID")
    if any(not timedelta(0) <= clock - utc(q["retrieved_at_utc"]) <= timedelta(seconds=900)
           for q in quotes):
        raise ValueError("COMBO_MARKET_COMPARATOR_STALE")
    current = capture(consensus, captured_at=clock, kickoff=kickoff,
                      model_probabilities={}, policy_context={"active_combo_policy": POLICY})
    if current["status"] != "AVAILABLE":
        raise ValueError("COMBO_MARKET_COMPARATOR_UNAVAILABLE")
    books = sorted((b for b in current["bookmakers"] if b["status"] == "AVAILABLE"),
                   key=lambda b: (str(b["bookmaker_id"]), b["bookmaker"]))
    ids = [b["bookmaker_id"] for b in books]
    if any(type(bid) is not int or bid <= 0 for bid in ids) or len(ids) != len(set(ids)):
        raise ValueError("COMBO_MARKET_BOOKMAKER_IDENTITY_INVALID")
    if len(books) < MIN_BOOKMAKERS:
        raise ValueError("COMBO_MARKET_TWO_COMPLETE_BOOKMAKERS_REQUIRED")
    selected = matching[0]
    if not any(b["bookmaker_id"] == selected["bookmaker_id"]
               and b["bookmaker"] == selected["bookmaker_name"] for b in books):
        raise ValueError("COMBO_MARKET_SELECTED_BOOK_INCOMPLETE")
    per_book = []
    for book in books:
        probabilities = {}
        for method in METHODS:
            result = book["methods"][method]
            if result["status"] != "AVAILABLE":
                raise ValueError("COMBO_MARKET_METHOD_UNAVAILABLE")
            probability = Decimal(str(result["probabilities"][market]))
            if not probability.is_finite() or not Decimal(0) < probability < Decimal(1):
                raise ValueError("COMBO_MARKET_PROBABILITY_INVALID")
            probabilities[method] = str(probability)
        per_book.append({"bookmaker_id": book["bookmaker_id"], "bookmaker": book["bookmaker"],
                         "probabilities": probabilities, "quote_fingerprints": book["quote_fingerprints"]})
    medians = {method: median(Decimal(b["probabilities"][method]) for b in per_book) for method in METHODS}
    return seal({"policy": POLICY, "statistics_cohort": COHORT, "selected_at": clock.isoformat(),
                 "candidate_binding": binding(candidate), "consensus": consensus,
                 "bookmakers": per_book, "bookmaker_count": len(per_book),
                 "method_medians": {m: str(p) for m, p in medians.items()},
                 "ranking_score": str(min(medians.values())),
                 "score_is_calibrated_probability": False,
                 "bookmakers_are_independent_observations": False})


def review(value: dict, *, now: datetime) -> None:
    if (value.get("statistics_cohort") != COHORT
            or value.get("score_is_calibrated_probability") is not False):
        raise ValueError("COMBO_MARKET_COHORT_INVALID")
    joint = Decimal(1)
    for leg in value["legs"]:
        frozen = leg["combo_market"]
        verify(frozen)
        if frozen["candidate_binding"] != binding(leg):
            raise ValueError("COMBO_MARKET_CANDIDATE_CHANGED")
        selected = utc(frozen["selected_at"])
        if not selected <= utc(now):
            raise ValueError("COMBO_MARKET_FUTURE_EVIDENCE")
        if evidence(leg, frozen["consensus"], now=selected) != frozen:
            raise ValueError("COMBO_MARKET_REPRODUCTION_FAILED")
        evidence(leg, frozen["consensus"], now=now)
        joint *= Decimal(frozen["ranking_score"])
    if Decimal(value["ranking_score_if_independent"]) != joint:
        raise ValueError("COMBO_MARKET_AGGREGATE_MISMATCH")


def published_selection_blocker(policy: str) -> str | None:
    """Both authorized lanes coexist; rollback blocks new B claims, not results."""
    from .combo_agreement import mode_blocker as agreement_blocker
    if policy == POLICY:
        return mode_blocker(policy)
    return agreement_blocker(policy)
