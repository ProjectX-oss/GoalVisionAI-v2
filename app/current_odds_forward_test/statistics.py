"""Transparent aggregate statistics isolated from every production ledger."""

from __future__ import annotations

import json
import math
from collections import Counter
from decimal import Decimal

from app.real_match_lab_analysis.fingerprint import fingerprint

from .models import ForwardTestSampleStatus, ForwardTestStatistics
from .repository import SQLiteForwardTestRepository


EARLY_EVIDENCE_MIN_SETTLED = 30
REVIEWABLE_MIN_SETTLED = 100
STATISTICALLY_MEANINGFUL_MIN_SETTLED = 300


def build_statistics(repository: SQLiteForwardTestRepository) -> ForwardTestStatistics:
    rows = repository.observations(); observations = [json.loads(row["observation_json"]) for row in rows]
    settlements = [json.loads(row[0]) for row in repository.connection.execute("SELECT settlement_json FROM forward_test_settlements ORDER BY settled_at_utc,settlement_id")]
    results = {row[0]: json.loads(row[1]) for row in repository.connection.execute("SELECT observation_id,result_json FROM forward_test_results")}
    selected = [item for item in observations if item.get("actionable_market")]
    decisive = [item for item in settlements if item["outcome"] in {"WON", "LOST"}]
    wins = sum(item["outcome"] == "WON" for item in decisive); losses = len(decisive) - wins
    count = len(decisive)
    status = (ForwardTestSampleStatus.FORWARD_TEST_STATISTICALLY_MEANINGFUL if count >= STATISTICALLY_MEANINGFUL_MIN_SETTLED else ForwardTestSampleStatus.FORWARD_TEST_REVIEWABLE if count >= REVIEWABLE_MIN_SETTLED else ForwardTestSampleStatus.FORWARD_TEST_EARLY_EVIDENCE if count >= EARLY_EVIDENCE_MIN_SETTLED else ForwardTestSampleStatus.FORWARD_TEST_SAMPLE_INSUFFICIENT)
    odds = [Decimal(str(item["quoted_odds"])) for item in decisive if item.get("quoted_odds") is not None]
    selected_evaluations = []
    for item in selected:
        selected_evaluations.extend(evaluation for evaluation in item.get("market_evaluations", []) if evaluation.get("market") == item.get("actionable_market"))
    probabilities = [Decimal(str(item["calibrated_probability"])) for item in selected_evaluations]
    evs = [Decimal(str(item["expected_value"])) for item in selected_evaluations]
    returns = [Decimal(str(item["hypothetical_net_return"])) for item in decisive]
    cumulative = Decimal(0); peak = Decimal(0); drawdown = Decimal(0)
    for value in returns:
        cumulative += value; peak = max(peak, cumulative); drawdown = max(drawdown, peak - cumulative)
    market_counts = Counter(item.get("actionable_market") or "NO_SELECTION" for item in observations)
    source_counts = Counter(_source(repository, row["odds_snapshot_id"]) for row in rows)
    competition_counts = Counter(_competition(repository, row["analysis_id"]) for row in rows)
    month_counts = Counter((item["created_at_utc"][:7], settlement["outcome"]) for item in observations for settlement in settlements if settlement["observation_id"] == item["observation_id"] and settlement["outcome"] in {"WON", "LOST"})
    probability_rows = []
    per_market = {}
    result_correct = []
    for observation in observations:
        result = results.get(observation["observation_id"])
        if not result: continue
        home, away = result["final_home_score"], result["final_away_score"]
        evaluations = observation.get("market_evaluations", [])
        for evaluation in evaluations:
            market = evaluation["market"]
            actual = Decimal(1 if _market_won(market, home, away) else 0)
            raw_probability = Decimal(str(evaluation["raw_probability"])); calibrated = Decimal(str(evaluation["calibrated_probability"]))
            probability_rows.append((market, raw_probability, calibrated, actual))
            values = per_market.setdefault(market, [0, 0]); values[0] += int((calibrated >= Decimal("0.5")) == bool(actual)); values[1] += 1
        match_values = [item for item in evaluations if item["market"] in {"HOME_WIN", "DRAW", "AWAY_WIN"}]
        if len(match_values) == 3:
            predicted = max(match_values, key=lambda item: Decimal(str(item["calibrated_probability"]))) ["market"]
            actual_market = "HOME_WIN" if home > away else "DRAW" if home == away else "AWAY_WIN"
            result_correct.append(predicted == actual_market)
    raw_brier = _average([(raw - actual) ** 2 for _, raw, _, actual in probability_rows])
    calibrated_brier = _average([(calibrated - actual) ** 2 for _, _, calibrated, actual in probability_rows])
    raw_log = _log_loss([(raw, actual) for _, raw, _, actual in probability_rows])
    calibrated_log = _log_loss([(calibrated, actual) for _, _, calibrated, actual in probability_rows])
    calibration_buckets = _buckets([(calibrated, actual) for _, _, calibrated, actual in probability_rows])
    quality_counts = Counter(_quality_status(item) for item in observations); shift_counts = Counter((item.get("distribution_shift") or {}).get("status", "NOT_EVALUATED") for item in observations)
    rejection_counts = Counter(row[0] for row in repository.connection.execute("SELECT reason_code FROM forward_test_rejections"))
    lineup_counts = Counter("AVAILABLE" if any(evaluation.get("lineup_freshness_status") == "FRESH" for evaluation in item.get("market_evaluations", [])) else "NOT_RECORDED" for item in observations)
    raw = dict(
        sample_status=status, total_analyses=len(observations), blocked_analyses=sum(item.get("status") == "BLOCKED" for item in observations), selected=len(selected), no_selection=sum(item.get("status") == "NO_SELECTION" for item in observations),
        actionable=sum(bool(item.get("actionable")) for item in observations), non_actionable=sum(not bool(item.get("actionable")) for item in observations),
        preview_available=sum(bool(item.get("preview_available")) for item in observations), published=0, unpublished=len(observations),
        settled=len(settlements), unsettled=len(observations)-len(settlements), wins=wins, losses=losses,
        voids=sum(item["outcome"] == "VOID" for item in settlements), hit_rate=_average([Decimal(wins) / Decimal(count)]) if count else None,
        average_quoted_odds=_average(odds), average_calibrated_probability=_average(probabilities), average_ev_at_capture=_average(evs),
        hypothetical_flat_stake_roi=_average(returns), maximum_simulated_drawdown=drawdown if returns else None,
        longest_winning_run=_run(decisive, "WON"), longest_losing_run=_run(decisive, "LOST"), brier_score=calibrated_brier, log_loss=calibrated_log,
        raw_brier_score=raw_brier, raw_log_loss=raw_log,
        match_result_accuracy=(Decimal(sum(result_correct)) / Decimal(len(result_correct))) if result_correct else None,
        per_market_accuracy=tuple((market, Decimal(correct) / Decimal(total)) for market, (correct, total) in sorted(per_market.items())),
        calibration_buckets=calibration_buckets,
        confidence_buckets=tuple((label, count, correct) for label, (count, correct) in _confidence(probability_rows).items()),
        market_distribution=tuple(sorted(market_counts.items())), competition_distribution=tuple(sorted(competition_counts.items())),
        source_distribution=tuple(sorted(source_counts.items())), bookmaker_distribution=tuple(sorted(Counter(key.split(":", 1)[-1] for key in source_counts.elements()).items())), monthly_results=tuple((month, month_counts[(month, "WON")], month_counts[(month, "LOST")]) for month in sorted({key[0] for key in month_counts})),
        average_feature_completeness=None, required_missing_count=0,
        distribution_shift_counts=tuple(sorted(shift_counts.items())), calibration_quality_outcomes=tuple(sorted(quality_counts.items())),
        lineup_availability=tuple(sorted(lineup_counts.items())),
        rejection_counts=tuple(sorted(rejection_counts.items())),
        limitations=("All ROI and drawdown values are hypothetical flat-stake simulations; no bankroll was mutated.", "Profitability is not reportable before the centralized settled-sample threshold is reached.", "Feature completeness is unavailable when the linked legacy Lab analysis did not persist that aggregate."),
    )
    return ForwardTestStatistics(**raw, statistics_fingerprint=fingerprint(raw))


def _average(values): return (sum(values, Decimal(0)) / Decimal(len(values))) if values else None
def _log_loss(values):
    if not values: return None
    epsilon = Decimal("0.000000001"); total = 0.0
    for probability, actual in values:
        p = float(min(Decimal(1)-epsilon, max(epsilon, probability))); y = float(actual); total += -(y * math.log(p) + (1-y) * math.log(1-p))
    return Decimal(str(total / len(values)))
def _buckets(values):
    buckets = []
    for lower in range(0, 10):
        selected = [(p, y) for p, y in values if Decimal(lower)/10 <= p < Decimal(lower+1)/10 or lower == 9 and p == 1]
        if selected: buckets.append((f"{lower/10:.1f}-{(lower+1)/10:.1f}", len(selected), _average([p for p, _ in selected]), _average([y for _, y in selected])))
    return tuple(buckets)
def _confidence(rows):
    output = {"LOW": [0, 0], "MEDIUM": [0, 0], "HIGH": [0, 0]}
    for _, _, probability, actual in rows:
        label = "HIGH" if probability >= Decimal("0.70") else "MEDIUM" if probability >= Decimal("0.55") else "LOW"; output[label][0] += 1; output[label][1] += int((probability >= Decimal("0.5")) == bool(actual))
    return {key: tuple(value) for key, value in output.items() if value[0]}
def _run(items, status):
    best = current = 0
    for item in items:
        current = current + 1 if item["outcome"] == status else 0; best = max(best, current)
    return best
def _source(repository, identifier):
    row = repository.load_odds(identifier); return f"{row['provider_source_id']}:{row['bookmaker_name']}"
def _competition(repository, analysis_id):
    row = repository.connection.execute("SELECT request_snapshot FROM real_match_lab_analyses WHERE analysis_id=?", (analysis_id,)).fetchone(); return json.loads(row[0]).get("competition", "UNKNOWN")
def _quality_status(item):
    value = item.get("calibration_quality") or {}; return value.get("lab_outcome") or value.get("status") or "NOT_EVALUATED"
def _market_won(market, home, away):
    total = home + away
    return {"HOME_WIN": home > away, "DRAW": home == away, "AWAY_WIN": away > home, "OVER_1_5": total > 1, "UNDER_1_5": total < 2, "OVER_2_5": total > 2, "UNDER_2_5": total < 3, "OVER_3_5": total > 3, "UNDER_3_5": total < 4, "BTTS_YES": home > 0 and away > 0, "BTTS_NO": home == 0 or away == 0}[market]
