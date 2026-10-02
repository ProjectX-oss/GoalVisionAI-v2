"""Paired descriptive scores from immutable forward de-vig captures only."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from math import isfinite
from statistics import mean

from app.current_odds_forward_test.service import _won
from .contracts import digest, utc
from .devig_research import METHODS, VERSION, verify_capture
from .performance import probability_metrics


def _scores(samples: list[tuple[dict, dict, dict]], method: str) -> dict:
    pairs, baseline_pairs, model_pairs, model_market_pairs = [], [], [], []
    bias: dict[str, list] = defaultdict(list)
    gaps, model_gaps, fixtures = [], [], set()
    model_missing = fallback = 0
    for record, book, result in samples:
        output = book["methods"][method]
        probs = {k: float(v) for k, v in output["probabilities"].items()}
        fixtures.add(record["fixture_id"])
        fallback += output["status"] == "FALLBACK_MULTIPLICATIVE"
        favourite = max(float(v) for v in book["methods"]["MULTIPLICATIVE"]["probabilities"].values())
        for market, p in probs.items():
            y = int(_won(market, result["home_goals"], result["away_goals"]))
            base = float(book["methods"]["MULTIPLICATIVE"]["probabilities"][market])
            pairs.append((p, y)); baseline_pairs.append((base, y)); gaps.append(abs(p-base))
            # Same favourite classification for all comparators, including ties.
            bias["FAVOURITE" if base == favourite else "OTHER"].append((p, y))
            ref = record["model_probabilities"].get(market, {})
            try:
                model = float(ref["probability"])
            except (KeyError, ValueError, TypeError):
                model = float("nan")
            if not isfinite(model) or not 0 < model < 1:
                model_missing += 1
                continue
            model_pairs.append((model, y)); model_market_pairs.append((p, y))
            model_gaps.append(abs(p-model))
    return {**probability_metrics(pairs), "book_market_samples": len(samples),
            "fixture_count": len(fixtures), "fallback_samples": fallback,
            "paired_multiplicative_metrics": probability_metrics(baseline_pairs),
            "paired_model_metrics": probability_metrics(model_pairs),
            "model_paired_market_metrics": probability_metrics(model_market_pairs),
            "missing_or_invalid_model_references": model_missing,
            "mean_difference_from_multiplicative": mean(gaps) if gaps else None,
            "mean_model_market_disagreement": mean(model_gaps) if model_gaps else None,
            "bias": {key: {**probability_metrics(bias[key]),
                          "mean_signed_error": mean(p-y for p,y in bias[key]) if bias[key] else None}
                     for key in ("FAVOURITE", "OTHER")}}


def evaluate(captures: list[dict], results: list[dict], *, now: str | datetime) -> dict:
    """Score first complete capture per book/family, with explicit missingness.

    The common cohort compares all methods on the same events. Per-method scores
    always include the multiplicative score on that exact method's event subset.
    Outcomes and bookmaker rows are correlated; unique fixtures are reported.
    """
    cutoff = utc(now)
    resolved: dict[int, dict] = {}
    result_counts: Counter = Counter()
    for result in results:
        if result.get("source_product") in {"COMBO", "COMBO_LEG"}:
            result_counts["excluded_combo_results"] += 1
            continue
        try:
            # A future correction cannot invalidate an earlier as-of snapshot.
            if utc(result["settled_at"]) > cutoff:
                result_counts["future_results"] += 1
                continue
            fid = result["fixture_id"]
            if type(fid) is not int or not result.get("source_fingerprint"):
                raise ValueError("INVALID_RESULT_PROVENANCE")
            status = result.get("status")
            if status not in {"RESOLVED", "VOID"}:
                raise ValueError("NONTERMINAL_RESULT")
            if status == "RESOLVED" and any(type(v) is not int or not 0 <= v <= 30
                                             for v in (result["home_goals"], result["away_goals"])):
                raise ValueError("INVALID_FORWARD_SCORE")
        except (ValueError, KeyError, TypeError, AttributeError):
            result_counts["invalid_results"] += 1
            continue
        if fid in resolved:
            previous = resolved[fid]
            keys = ("status", "home_goals", "away_goals")
            if any(previous.get(k) != result.get(k) for k in keys):
                raise ValueError("CONFLICTING_FORWARD_RESULT")
            result_counts["duplicate_results"] += 1
            if utc(previous["settled_at"]) <= utc(result["settled_at"]):
                continue
        resolved[fid] = result
    first: dict[tuple, tuple[dict, dict]] = {}
    counts: Counter = Counter()
    reasons: Counter = Counter()
    seen: set[str] = set()
    for record in sorted(captures, key=lambda r: (utc(r["captured_at"]), r["capture_id"])):
        if utc(record["captured_at"]) > cutoff:
            counts["future_captures"] += 1
            continue
        verify_capture(record)
        if record["capture_id"] in seen:
            counts["duplicate_captures"] += 1
            continue
        seen.add(record["capture_id"])
        counts["captures"] += 1
        if record["status"] != "AVAILABLE":
            counts["blocked_captures"] += 1
            reasons[record.get("reason", "INVALID_CURRENT_MARKET")] += 1
            counts["blocked_book_markets"] += len(record["bookmakers"])
            continue
        for book in record["bookmakers"]:
            if book["status"] != "AVAILABLE":
                counts["blocked_book_markets"] += 1
                reasons[book["reason"]] += 1
                continue
            key = (record["fixture_id"], book["bookmaker_id"], book["bookmaker"], record["market_family"])
            if key in first:
                if utc(first[key][0]["captured_at"]) == utc(record["captured_at"]):
                    raise ValueError("AMBIGUOUS_FIRST_FORWARD_CAPTURE")
                counts["repeat_book_markets"] += 1
            first.setdefault(key, (record, book))
    samples: list[tuple[dict, dict, dict]] = []
    result_links = []
    for record, book in first.values():
        result = resolved.get(record["fixture_id"])
        if result is None:
            counts["pending_book_markets"] += 1
        elif utc(result["settled_at"]) <= utc(record["kickoff_utc"]):
            counts["invalid_result_chronology_book_markets"] += 1
        elif result["status"] == "VOID":
            counts["void_book_markets"] += 1
        else:
            samples.append((record, book, result))
            result_links.append({"capture_id": record["capture_id"], "bookmaker_id": book["bookmaker_id"],
                                 "bookmaker": book["bookmaker"], "result_fingerprint": digest(result)})
    available = lambda book, method: book["methods"][method]["status"] in {"AVAILABLE", "FALLBACK_MULTIPLICATIVE"}
    common = [s for s in samples if all(available(s[1], m) for m in METHODS)]
    methods = {}
    for method in METHODS:
        eligible = [s for s in samples if available(s[1], method)]
        statuses = Counter(book["methods"][method]["status"] for _, book in first.values())
        methods[method] = {**_scores(eligible, method), "capture_method_statuses": dict(statuses),
                           "common_cohort": _scores(common, method)}
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for sample in samples:
        record = sample[0]
        policy = str(record["policy_context"].get("single_policy", "UNSPECIFIED"))
        groups[(policy, record["market_family"])].append(sample)
    count_names = ("captures", "blocked_captures", "blocked_book_markets", "future_captures",
                   "duplicate_captures", "repeat_book_markets", "pending_book_markets",
                   "void_book_markets", "invalid_result_chronology_book_markets")
    value = {"version": VERSION, "as_of": cutoff.isoformat(),
             "status": "AVAILABLE" if samples else "NEEDS_MORE_EVIDENCE",
             "quality_verdict": "NEEDS_MORE_EVIDENCE", "promotion_eligible": False,
             "sampling": "FIRST_FORWARD_FIXTURE_BOOK_FAMILY",
             "fixture_count": len({r["fixture_id"] for r,_,_ in samples}),
             "captured_fixture_count": len({r["fixture_id"] for r,_ in first.values()}),
             "first_book_market_samples": len(first), "resolved_book_market_samples": len(samples),
             "common_book_market_samples": len(common),
             "counts": {k: counts[k] for k in count_names}, "blocked_reasons": dict(sorted(reasons.items())),
             "result_counts": {k: result_counts[k] for k in
                               ("future_results", "invalid_results", "duplicate_results", "excluded_combo_results")},
             "methods": methods,
             "segments": [{"single_policy": p, "market_family": f,
                           "methods": {m: _scores([s for s in rows if available(s[1],m)],m) for m in METHODS}}
                          for (p,f),rows in sorted(groups.items())],
             "capture_ids": sorted(seen), "result_links": result_links,
             "sampling_limitations": ["RESULT_COVERAGE_DEPENDS_ON_EXISTING_SINGLE_AND_SHADOW_TRACKING",
                                     "BOOKMAKERS_AND_OUTCOMES_ARE_CORRELATED_NOT_INDEPENDENT_SAMPLES",
                                     "DESCRIPTIVE_FORWARD_EVIDENCE_NOT_A_NEW_HOLDOUT"],
             "model_learning_observations": 0, "selection_effect": "NONE",
             "historical_bookmaker_odds_used": False}
    value["snapshot_fingerprint"] = digest(value)
    return value


def operator_summary(snapshot: dict) -> dict:
    """Fixed-size scheduled stdout; full evidence remains in observer_runs."""
    return {k: snapshot.get(k) for k in ("version", "status", "reason", "quality_verdict",
            "snapshot_fingerprint", "fixture_count", "first_book_market_samples",
            "resolved_book_market_samples", "common_book_market_samples",
            "counts", "model_learning_observations", "selection_effect")}
