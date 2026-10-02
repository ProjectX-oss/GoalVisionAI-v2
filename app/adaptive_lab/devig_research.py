"""Current quote de-vig research; outputs never enter selection or model training."""
from __future__ import annotations
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from math import isfinite, sqrt
from statistics import mean
from copy import deepcopy
from datetime import datetime
from typing import Callable
from app.adaptive_lab.contracts import digest, utc
from app.adaptive_lab.performance import probability_metrics
from app.current_odds_forward_test.freshness import API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS
from app.lab_v2_shadow.market_consensus import _FAMILIES, remove_margin_multiplicative
from app.real_match_lab_analysis.fingerprint import fingerprint

VERSION = "CURRENT_ODDS_DEVIG_RESEARCH_V2"
METHODS = ("MULTIPLICATIVE", "SHIN", "POWER", "OO_EPC")


def _root(function: Callable[[float], float], lo: float, hi: float) -> float:
    left, right = function(lo), function(hi)
    if not isfinite(left) or not isfinite(right) or left * right > 0:
        raise ValueError("ROOT_NOT_BRACKETED")
    for _ in range(160):
        mid = (lo + hi) / 2
        value = function(mid)
        if not isfinite(value):
            raise ValueError("NON_FINITE_ROOT")
        if abs(value) <= 1e-13:
            return mid
        if value * left > 0:
            lo, left = mid, value
        else:
            hi = mid
    raise ValueError("ROOT_DID_NOT_CONVERGE")


def devig(odds: dict[str, object]) -> dict:
    """Complete mutually exclusive markets only; record inapplicable methods."""
    try:
        prices = {k: Decimal(str(v)) for k, v in sorted(odds.items())}
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("INVALID_CURRENT_ODDS") from exc
    if set(prices) not in [set(v) for v in _FAMILIES.values()]:
        raise ValueError("INCOMPLETE_OR_UNSUPPORTED_MARKET")
    base = remove_margin_multiplicative(prices)
    if base is None:
        raise ValueError("CURRENT_MARKET_ODDS_OR_MARGIN_INVALID")
    fair, margin = base
    keys = list(prices)
    q = [1 / float(prices[k]) for k in keys]
    booksum = sum(q)
    outputs = {"MULTIPLICATIVE": {"status": "AVAILABLE",
               "probabilities": {k: str(fair[k]) for k in keys}, "parameters": {}}}

    def record(name: str, p: list[float], **parameters: float) -> None:
        if any(not isfinite(v) or not 0 < v < 1 for v in p) or abs(sum(p)-1) > 1e-10:
            raise ValueError("RESEARCH_PROBABILITY_CONTRACT")
        outputs[name] = {"status": "AVAILABLE",
                         "probabilities": dict(zip(keys, map(str, p))), "parameters": parameters}

    if booksum < 1 - 1e-12:
        outputs["SHIN"] = {"status": "NOT_APPLICABLE", "reason": "UNDERROUND_NO_NONNEGATIVE_INSIDER_ROOT"}
    else:
        def shin(z: float) -> list[float]:
            # Algebraically equivalent rationalisation avoids cancellation near z=1.
            return [2*x*x/booksum / (sqrt(z*z+4*(1-z)*x*x/booksum)+z) for x in q]
        z = 0.0 if abs(booksum-1) <= 1e-12 else _root(lambda z: sum(shin(z))-1, 0, 1-1e-12)
        record("SHIN", shin(z), insider_fraction=z)
    hi = 2.0
    for _ in range(24):
        if sum(x**hi for x in q) < 1:
            break
        hi *= 2
    exponent = _root(lambda b: sum(x**b for x in q)-1, 0, hi)
    record("POWER", [x**exponent for x in q], exponent=exponent)
    sigma = [sqrt(1-x) for x in q]
    z = (booksum-1) / sum(sigma)
    epc = [x-z*s for x, s in zip(q, sigma)]
    if any(p <= 0 for p in epc):
        outputs["OO_EPC"] = {"status": "FALLBACK_MULTIPLICATIVE",
            "probabilities": {k: str(fair[k]) for k in keys},
            "parameters": {"z": z}, "reason": "OO_EPC_NONPOSITIVE_OUTCOME"}
    else:
        record("OO_EPC", epc, z=z)
    return {"version": VERSION, "margin": str(margin), "methods": outputs,
            "research_only": True, "historical_bookmaker_odds_used": False}


def _book_capture(quotes: list[dict], *, fixture_id: int, family: str,
                  stamp: datetime, source_issues: list[dict]) -> dict:
    """Validate complete simultaneous prices before any conversion."""
    bid, name = quotes[0]["bookmaker_id"], quotes[0]["bookmaker_name"]
    base = {"bookmaker_id": bid, "bookmaker": name}
    reason = None
    if any(i["bookmaker_id"] == bid and i["bookmaker"] == name for i in source_issues):
        reason = "DUPLICATE_PROVIDER_OUTCOME"
    elif len(quotes) != len({q["market"] for q in quotes}):
        reason = "DUPLICATE_BOOKMAKER_OUTCOME"
    elif {q["market"] for q in quotes} != set(_FAMILIES[family]):
        reason = "INCOMPLETE_OR_MISMATCHED_MARKET"
    timestamps = set()
    for quote in quotes:
        if quote["fixture_id"] != fixture_id:
            reason = "FIXTURE_MISMATCH"
            break
        origin = utc(quote["provider_origin_timestamp_utc"])
        retrieved = utc(quote["retrieved_at_utc"])
        timestamps.add((origin, retrieved))
        if not origin <= retrieved <= stamp:
            reason = "FUTURE_OR_REVERSED_QUOTE"
            break
        if (stamp-origin).total_seconds() > API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS:
            reason = "STALE_CURRENT_ODDS"
            break
        odds = Decimal(str(quote["decimal_odds"]))
        if not odds.is_finite() or odds <= 1:
            reason = "INVALID_CURRENT_ODDS"
            break
        identity = dict(provider="API_FOOTBALL", fixture_id=quote["fixture_id"],
                        bookmaker_id=bid, bookmaker=name, market=quote["market"],
                        odds=odds, provider_updated=origin, retrieved_at=retrieved)
        if fingerprint(identity) != quote["provenance_fingerprint"]:
            reason = "CURRENT_QUOTE_FINGERPRINT_MISMATCH"
            break
    if len(timestamps) > 1 and reason is None:
        reason = "INCOMPATIBLE_QUOTE_TIMESTAMPS"
    if reason:
        return {**base, "status": "BLOCKED", "reason": reason}
    try:
        value = devig({q["market"]: q["decimal_odds"] for q in quotes})
    except (ValueError, ArithmeticError, OverflowError):
        return {**base, "status": "BLOCKED", "reason": "CURRENT_MARKET_MATH_INAPPLICABLE"}
    return {**base, "status": "AVAILABLE",
            "quote_fingerprints": sorted(q["provenance_fingerprint"] for q in quotes),
            **value}


def capture_prefix(fixture_id: object, family: object) -> str:
    return f"devig-v2:{fixture_id}:{family}:"


def capture_identity(record: dict) -> str:
    return capture_prefix(record.get("fixture_id"), record.get("market_family")) + digest(record)


def capture(consensus: dict, *, captured_at: str | datetime, kickoff: str | datetime,
            model_probabilities: dict | None = None, policy_context: dict | None = None,
            source_issues: list[dict] | None = None) -> dict:
    """Freeze exact inputs; never enrich an earlier capture using later facts."""
    stamp, start = utc(captured_at), utc(kickoff)
    source = deepcopy(consensus)
    base = {"version": VERSION, "method_version": "ODDS_ONLY_MATH_V1",
            "fixture_id": source.get("fixture_id"), "market_family": source.get("market_family"),
            "captured_at": stamp.isoformat(), "kickoff_utc": start.isoformat(),
            "research_only": True, "historical_bookmaker_odds_used": False,
            "selection_effect": "NONE", "source_consensus": source,
            "source_consensus_fingerprint": digest(source),
            "model_probabilities": deepcopy(model_probabilities or {}),
            "policy_context": deepcopy(policy_context or {}),
            "source_issues": deepcopy(source_issues or [])}
    try:
        family = source["market_family"]
        if family not in _FAMILIES or type(source["fixture_id"]) is not int:
            raise ValueError("UNSUPPORTED_MARKET_IDENTITY")
        if (source.get("source") != "API_FOOTBALL_CURRENT_ODDS"
                or source.get("historical_bookmaker_odds_used") is not False):
            raise ValueError("CURRENT_PREMATCH_SOURCE_REQUIRED")
        if stamp >= start:
            raise ValueError("POST_KICKOFF_CAPTURE")
        if source.get("status") not in {"AVAILABLE", "INSUFFICIENT_COMPARABLE_BOOKMAKERS"}:
            reason = "STALE_CURRENT_ODDS" if source.get("status") == "STALE_CURRENT_ODDS" else "CURRENT_QUOTES_UNAVAILABLE"
            raise ValueError(reason)
        books: dict[tuple, list[dict]] = defaultdict(list)
        for quote in source["quotes"]:
            books[(quote["bookmaker_id"], quote["bookmaker_name"])].append(quote)
        records = [_book_capture(q, fixture_id=source["fixture_id"], family=family,
                                 stamp=stamp, source_issues=base["source_issues"])
                   for _, q in sorted(books.items(), key=lambda i: str(i[0]))]
        base.update(status="AVAILABLE" if any(r["status"] == "AVAILABLE" for r in records) else "BLOCKED",
                    bookmakers=records)
        fatal = next((r["reason"] for r in records if r["status"] == "BLOCKED" and r["reason"] not in
                      {"INCOMPLETE_OR_MISMATCHED_MARKET", "CURRENT_MARKET_MATH_INAPPLICABLE"}), None)
        if fatal:
            base.update(status="BLOCKED", reason=fatal)
        elif base["status"] == "BLOCKED":
            base["reason"] = "NO_COMPLETE_VALID_BOOKMAKER"
    except ValueError as exc:
        allowed = {"UNSUPPORTED_MARKET_IDENTITY", "CURRENT_PREMATCH_SOURCE_REQUIRED",
                   "POST_KICKOFF_CAPTURE", "STALE_CURRENT_ODDS", "CURRENT_QUOTES_UNAVAILABLE"}
        reason = str(exc) if str(exc) in allowed else "INVALID_CURRENT_MARKET"
        base.update(status="BLOCKED", reason=reason, bookmakers=[])
    except (KeyError, TypeError, ArithmeticError, AttributeError):
        base.update(status="BLOCKED", reason="INVALID_CURRENT_MARKET", bookmakers=[])
    base["capture_id"] = capture_identity(base)
    return base


def verify_capture(record: dict) -> None:
    """Verify retained content and reproduce all methods from frozen prices."""
    if (record.get("version") != VERSION or record.get("capture_id") !=
            capture_identity({k: v for k, v in record.items() if k != "capture_id"})):
        raise ValueError("RESEARCH_CAPTURE_REQUIRED")
    reproduced = capture(record["source_consensus"], captured_at=record["captured_at"],
                         kickoff=record["kickoff_utc"], model_probabilities=record["model_probabilities"],
                         policy_context=record["policy_context"], source_issues=record["source_issues"])
    if reproduced != record:
        raise ValueError("RESEARCH_CAPTURE_REPRODUCTION_FAILED")


def forward_metrics(captures: list[dict], results: list[dict], *, now: str | datetime) -> dict:
    """Pure forward evaluation; no training, fetching or activation."""
    from .devig_metrics import evaluate
    return evaluate(captures, results, now=now)
