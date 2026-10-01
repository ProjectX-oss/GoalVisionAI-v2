"""Current quote de-vig research; outputs never enter selection or model training."""
from __future__ import annotations
from collections import Counter, defaultdict
from decimal import Decimal
from math import isfinite, sqrt
from statistics import mean
from app.adaptive_lab.contracts import digest, utc
from app.adaptive_lab.performance import probability_metrics
from app.current_odds_forward_test.freshness import API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS
from app.lab_v2_shadow.market_consensus import _FAMILIES, remove_margin_multiplicative
from app.real_match_lab_analysis.fingerprint import fingerprint

VERSION = "CURRENT_ODDS_DEVIG_RESEARCH_V1"
METHODS = ("MULTIPLICATIVE", "SHIN", "POWER", "OO_EPC")


def _root(function, lo, hi):
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
    prices = {k: Decimal(str(v)) for k, v in sorted(odds.items())}
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

    def record(name, p, **parameters):
        if any(not isfinite(v) or not 0 < v < 1 for v in p) or abs(sum(p)-1) > 1e-10:
            raise ValueError("RESEARCH_PROBABILITY_CONTRACT")
        outputs[name] = {"status": "AVAILABLE",
                         "probabilities": dict(zip(keys, map(str, p))), "parameters": parameters}

    if booksum < 1 - 1e-12:
        outputs["SHIN"] = {"status": "NOT_APPLICABLE", "reason": "UNDERROUND_NO_NONNEGATIVE_INSIDER_ROOT"}
    else:
        def shin(z):
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


def capture(consensus: dict, *, captured_at, kickoff, model_probabilities: dict | None = None) -> dict:
    """Sibling evidence from the same fresh complete current quote records."""
    stamp = utc(captured_at)
    base = {"version": VERSION, "fixture_id": consensus.get("fixture_id"),
            "market_family": consensus.get("market_family"), "captured_at": stamp.isoformat(),
            "kickoff_utc": utc(kickoff).isoformat(), "research_only": True,
            "historical_bookmaker_odds_used": False, "selection_effect": "NONE",
            "source_consensus_fingerprint": digest(consensus),
            "model_probabilities": model_probabilities or {}}
    try:
        if (consensus.get("source") != "API_FOOTBALL_CURRENT_ODDS"
                or consensus.get("historical_bookmaker_odds_used") is not False
                or consensus.get("status") != "AVAILABLE" or stamp >= utc(kickoff)):
            raise ValueError("CURRENT_PREMATCH_SOURCE_REQUIRED")
        family = consensus["market_family"]
        outcomes = set(_FAMILIES[family])
        books = defaultdict(dict)
        for quote in consensus["quotes"]:
            if quote["market"] not in outcomes:
                continue
            origin, retrieved = utc(quote["provider_origin_timestamp_utc"]), utc(quote["retrieved_at_utc"])
            odds = Decimal(str(quote["decimal_odds"]))
            if (quote["fixture_id"] != consensus["fixture_id"] or not origin <= retrieved <= stamp
                    or (stamp-origin).total_seconds() > API_FOOTBALL_PREMATCH_MAX_AGE_SECONDS):
                raise ValueError("STALE_OR_MISMATCHED_CURRENT_QUOTE")
            identity = dict(provider="API_FOOTBALL", fixture_id=quote["fixture_id"],
                bookmaker_id=quote["bookmaker_id"], bookmaker=quote["bookmaker_name"],
                market=quote["market"], odds=odds, provider_updated=origin, retrieved_at=retrieved)
            if fingerprint(identity) != quote["provenance_fingerprint"]:
                raise ValueError("CURRENT_QUOTE_FINGERPRINT_MISMATCH")
            key = (quote["bookmaker_id"], quote["bookmaker_name"])
            if quote["market"] in books[key]:
                raise ValueError("DUPLICATE_BOOKMAKER_OUTCOME")
            books[key][quote["market"]] = quote
        results = []
        for (bid, name), quotes in sorted(books.items(), key=lambda item: str(item[0])):
            if set(quotes) != outcomes:
                continue
            try:
                value = devig({k: q["decimal_odds"] for k, q in quotes.items()})
            except ValueError as exc:
                results.append({"bookmaker_id": bid, "bookmaker": name, "status": "BLOCKED", "reason": str(exc)})
                continue
            results.append({"bookmaker_id": bid, "bookmaker": name, "status": "AVAILABLE",
                            "quote_fingerprints": sorted(q["provenance_fingerprint"] for q in quotes.values()), **value})
        base.update(status="AVAILABLE" if any(r["status"] == "AVAILABLE" for r in results) else "BLOCKED",
                    bookmakers=results)
    except (ValueError, KeyError, TypeError, ArithmeticError):
        base.update(status="BLOCKED", reason="INVALID_OR_STALE_CURRENT_MARKET", bookmakers=[])
    base["capture_id"] = "devig-" + digest(base)
    return base


def forward_metrics(captures: list[dict], results: list[dict], *, now) -> dict:
    """First forward capture per fixture/book/family; only later resolved scores."""
    from app.current_odds_forward_test.service import _won
    resolved = {}
    for result in results:
        fid = result["fixture_id"]
        if fid in resolved and resolved[fid] != result:
            raise ValueError("CONFLICTING_FORWARD_RESULT")
        resolved[fid] = result
    first = {}
    for record in sorted(captures, key=lambda r: (r["captured_at"], r["capture_id"])):
        if record.get("version") != VERSION or record.get("research_only") is not True:
            raise ValueError("RESEARCH_CAPTURE_REQUIRED")
        if utc(record["captured_at"]) >= utc(record["kickoff_utc"]) or utc(record["captured_at"]) > utc(now):
            continue
        for book in record.get("bookmakers", []):
            if book["status"] == "AVAILABLE":
                first.setdefault((record["fixture_id"], book["bookmaker_id"], book["bookmaker"], record["market_family"]),
                                 (record, book))
    pairs, bias, disagreements = defaultdict(list), defaultdict(list), defaultdict(list)
    model_gaps, model_pairs = defaultdict(list), defaultdict(list)
    fixture_ids, samples = set(), Counter()
    for (fid, _, _, _), (record, book) in first.items():
        result = resolved.get(fid)
        if not result or result.get("status") != "RESOLVED":
            continue
        if not utc(record["kickoff_utc"]) < utc(result["settled_at"]) <= utc(now):
            continue
        home, away = result["home_goals"], result["away_goals"]
        if any(type(v) is not int or not 0 <= v <= 30 for v in (home, away)):
            raise ValueError("INVALID_FORWARD_SCORE")
        fixture_ids.add(fid)
        for method, output in book["methods"].items():
            if "probabilities" not in output:
                continue
            samples[method] += 1
            probs = {k: float(v) for k, v in output["probabilities"].items()}
            favourite = max(probs.values())
            for market, p in probs.items():
                y = int(_won(market, home, away))
                pairs[method].append((p, y))
                bias[(method, "FAVOURITE" if p == favourite else "OTHER")].append((p, y))
                baseline = float(book["methods"]["MULTIPLICATIVE"]["probabilities"][market])
                disagreements[method].append(abs(p-baseline))
                ref = record.get("model_probabilities", {}).get(market, {})
                try:
                    model_p = float(ref["probability"])
                except (ValueError, TypeError, KeyError):
                    continue
                if isfinite(model_p) and 0 < model_p < 1:
                    model_gaps[method].append(abs(p-model_p))
                    model_pairs[method].append((model_p,y))
    return {"version": VERSION, "status": "AVAILABLE" if fixture_ids else "NEEDS_MORE_EVIDENCE",
            "fixture_count": len(fixture_ids), "sampling": "FIRST_FORWARD_FIXTURE_BOOK_FAMILY",
            "methods": {m: {**probability_metrics(pairs[m]), "book_market_samples": samples[m],
                "mean_difference_from_multiplicative": mean(disagreements[m]) if disagreements[m] else None,
                "mean_model_market_disagreement": mean(model_gaps[m]) if model_gaps[m] else None,
                "paired_model_metrics": probability_metrics(model_pairs[m]),
                "bias": {b: probability_metrics(bias[(m,b)]) for b in ("FAVOURITE", "OTHER")}} for m in METHODS},
            "model_learning_observations": 0, "selection_effect": "NONE"}
