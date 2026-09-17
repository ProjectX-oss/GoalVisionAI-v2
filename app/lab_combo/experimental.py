"""LAB_EXPERIMENTAL_SELECTION_V1 deterministic selection and accounting.

The score is an explicitly uncalibrated experimental signal.  It is never
used by, or represented as, the production probability/calibration chain.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from itertools import combinations
from math import factorial

from app.current_match_intelligence.canonical import fingerprint
from app.current_match_intelligence.models import CurrentMatchIntelligenceSnapshot
from .presentation import combo_message, single_message


POLICY_VERSION = "LAB_EXPERIMENTAL_SELECTION_V2"
MAX_SINGLE_ODDS = Decimal("5.00")
MAX_COMBINED_ODDS = Decimal("15.00")
MAX_COMBOS_PER_DISCOVERY_CYCLE = 3
MAX_SINGLES_PER_DISCOVERY_CYCLE = 3
SETTLEMENT_RELEVANCE_AFTER_KICKOFF = timedelta(minutes=90)
FINAL_REVIEW_START = timedelta(minutes=60)
FINAL_REVIEW_PREFERRED_END = timedelta(minutes=20)
FINAL_REVIEW_REFRESH_MAX_AGE = timedelta(minutes=5)
SUPPORTED_MARKETS = (
    "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5",
    "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5",
    "BTTS_YES", "BTTS_NO",
)
MARKET_ORDER = {market: index for index, market in enumerate(SUPPORTED_MARKETS)}
LINEUP_SENSITIVE_MARKETS = frozenset(SUPPORTED_MARKETS)
REQUIRED_FRESH_SIGNALS = (
    "fixture_context", "injuries", "team_statistics", "team_history", "odds",
)


def evaluate_snapshot(snapshot: CurrentMatchIntelligenceSnapshot, *, now: datetime) -> list[dict]:
    """Evaluate supported markets using only reproducible snapshot evidence."""
    now = now.astimezone(timezone.utc)
    fields = {field.name: field for field in snapshot.fields}
    values = {name: field.value for name, field in fields.items()}
    freshness = {item.signal: item.status.value for item in snapshot.freshness}
    common: list[str] = []
    if snapshot.kickoff_utc <= now:
        common.append("FIXTURE_ALREADY_STARTED")
    for signal in REQUIRED_FRESH_SIGNALS:
        if freshness.get(signal) != "FRESH":
            common.append(f"{signal.upper()}_NOT_FRESH")
    required_features = (
        "feature.home_form_strength", "feature.away_form_strength",
        "feature.home_recent_goals_for_per_match",
        "feature.home_recent_goals_against_per_match",
        "feature.away_recent_goals_for_per_match",
        "feature.away_recent_goals_against_per_match",
        "feature.rest_days_home", "feature.rest_days_away",
        "feature.schedule_congestion_home", "feature.schedule_congestion_away",
        "feature.injury_count_home", "feature.injury_count_away",
        "feature.suspension_count_home", "feature.suspension_count_away",
    )
    missing = [name for name in required_features if name not in fields]
    if missing:
        common.append("INSUFFICIENT_CURRENT_MATCH_INFORMATION")
    probabilities = _market_probabilities(values) if not missing else {}
    lineup_confirmed = all(values.get(f"{side}.lineup.confirmed") is True for side in ("home", "away"))
    lineup_state = "CONFIRMED" if lineup_confirmed else "NOT_YET_PUBLISHED"
    results = []
    for market in SUPPORTED_MARKETS:
        odds_field = fields.get(f"market.{market}.decimal_odds")
        blockers = list(common)
        odds = _decimal(odds_field.value) if odds_field else None
        signal = probabilities.get(market)
        if odds is None:
            blockers.append("MARKET_ODDS_NOT_AVAILABLE")
        elif not odds.is_finite() or odds <= Decimal(1):
            blockers.append("INVALID_CURRENT_DECIMAL_ODDS")
        elif odds > MAX_SINGLE_ODDS:
            blockers.append("SINGLE_ODDS_ABOVE_EXPERIMENTAL_SAFETY_LIMIT")
        if signal is None:
            blockers.append("EXPERIMENTAL_SIGNAL_UNAVAILABLE")
        elif signal < Decimal("0.05") or signal > Decimal("0.85"):
            blockers.append("UNSUPPORTED_EXTREME_MODEL_SIGNAL")
        valid_odds = odds is not None and odds.is_finite() and odds > Decimal(1)
        implied = Decimal(1) / odds if valid_odds else None
        edge = signal - implied if signal is not None and implied is not None else None
        confidence = _confidence(edge)
        if edge is not None and edge < Decimal("0.05"):
            blockers.append("INSUFFICIENT_MARKET_CONTEXT_AGREEMENT")
        if edge is not None and edge > Decimal("0.15"):
            blockers.append("MODEL_MARKET_DIVERGENCE_TOO_LARGE")
        if confidence == "LOW":
            blockers.append("EXPERIMENTAL_CONFIDENCE_LOW")
        lineup_context = _lineup_context(values)
        blockers.extend(_objective_quality_blockers(market, values))
        stage, stage_reasons, final_blockers = _timing_stage(
            snapshot, market=market, now=now, lineup_confirmed=lineup_confirmed,
            lineup_context=lineup_context,
        )
        blockers.extend(final_blockers)
        blockers = sorted(set(blockers))
        if blockers:
            stage = "REJECTED"
        source_names = _evidence_names(market, fields)
        evidence = _evidence(source_names, fields)
        identity = {
            "policy": POLICY_VERSION, "snapshot_id": snapshot.snapshot_id,
            "fixture_id": snapshot.fixture_id, "market": market,
            "captured_odds": str(odds) if odds is not None else None,
        }
        candidate_id = "lab-single-candidate-" + fingerprint(identity)
        results.append({
            "candidate_id": candidate_id, "observation_id": candidate_id,
            "policy": POLICY_VERSION, "fixture_id": snapshot.fixture_id,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_fingerprint": snapshot.content_fingerprint,
            "home_team": values.get("home.team_name"), "away_team": values.get("away.team_name"),
            "home_team_id": str(values.get("home.team_id")), "away_team_id": str(values.get("away.team_id")),
            "competition": values.get("competition.name"), "competition_id": str(values.get("competition.id")),
            "kickoff_utc": snapshot.kickoff_utc.isoformat(), "market": market,
            "captured_odds": str(odds) if odds is not None else None,
            "bookmaker": values.get(f"market.{market}.bookmaker"),
            "provider_type": "API_FOOTBALL_CURRENT_ODDS",
            "provider_origin_timestamp_utc": _provider_time(odds_field),
            "goalvision_retrieved_at_utc": _retrieved_time(odds_field),
            "experimental_signal": str(signal) if signal is not None else None,
            "implied_market_probability": str(implied) if implied is not None else None,
            "market_context_edge": str(edge) if edge is not None else None,
            "experimental_confidence": confidence,
            "lineup_status": lineup_state, "stage": stage,
            "stage_reasons": stage_reasons,
            "final_review_completed_at_utc": snapshot.evaluated_at.isoformat() if stage == "READY_TO_PUBLISH" else None,
            "lineup_context": lineup_context,
            "risk": _risk(values, lineup_confirmed),
            "reasoning": _reasoning(market, values, lineup_state),
            "evidence_fields": source_names, "provenance": evidence,
            "factors_used": source_names,
            "freshness": {item.signal: item.status.value for item in snapshot.freshness},
            "missing_signals": list(snapshot.missing_data),
            "evidence_completeness": _completeness(required_features, fields, odds_field, lineup_confirmed),
            "approval_reasons": (["OBJECTIVE_EVIDENCE_CONSISTENT", "FRESH_ODDS", "FINAL_REVIEW_COMPLETE"]
                                 if stage == "READY_TO_PUBLISH" else []),
            "decision": "APPROVED" if not blockers else "REJECTED",
            "rejection_reasons": blockers,
            "evaluated_at_utc": now.isoformat(),
        })
    return results


def rank_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=lambda item: (
        -_decimal(item.get("market_context_edge"), Decimal("-99")),
        -_decimal(item.get("experimental_signal"), Decimal(0)),
        MARKET_ORDER.get(item["market"], 999), item["fixture_id"], item["candidate_id"],
    ))


def select_single_predictions(
    candidates: list[dict],
    *,
    existing_keys: set[str],
    now: datetime,
    existing_fixtures: set[str] | None = None,
) -> list[dict]:
    selected, fixtures = [], set()
    existing_fixtures = existing_fixtures or set()
    for candidate in rank_candidates([
        item for item in candidates
        if item["decision"] == "APPROVED" and item.get("stage", "READY_TO_PUBLISH") == "READY_TO_PUBLISH"
    ]):
        key = publication_key(candidate)
        if candidate["fixture_id"] in fixtures or candidate["fixture_id"] in existing_fixtures or key in existing_keys:
            continue
        value = {**candidate, "prediction_id": "lab-single-" + fingerprint((POLICY_VERSION, key, candidate['candidate_id'])),
                 "publication_key": key, "prepared_at_utc": now.astimezone(timezone.utc).isoformat(),
                 "accounting": "LAB_ONLY_HYPOTHETICAL_ONE_UNIT"}
        selected.append(value); fixtures.add(candidate["fixture_id"])
        if len(selected) == MAX_SINGLES_PER_DISCOVERY_CYCLE:
            break
    return selected


def select_combo_batch(candidates: list[dict], *, used_leg_keys: set[str], now: datetime) -> list[dict]:
    """Greedily choose the best deterministic disjoint independent triples."""
    remaining = [item for item in rank_candidates(candidates)
                 if item["decision"] == "APPROVED"
                 and item.get("stage", "READY_TO_PUBLISH") == "READY_TO_PUBLISH"
                 and publication_key(item) not in used_leg_keys]
    selected = []
    while len(selected) < MAX_COMBOS_PER_DISCOVERY_CYCLE:
        choices = []
        for group in combinations(remaining, 3):
            if not independent(group):
                continue
            leg_odds = tuple(_decimal(item["captured_odds"]) for item in group)
            if any(not _valid_leg_odds(value) for value in leg_odds):
                continue
            combined = _product(leg_odds)
            if not combined_odds_eligible(combined):
                continue
            rank = (
                -min(_decimal(item["market_context_edge"]) for item in group),
                -sum((_decimal(item["market_context_edge"]) for item in group), Decimal(0)),
                tuple(publication_key(item) for item in group),
            )
            choices.append((rank, group, combined))
        if not choices:
            break
        _, group, combined = min(choices, key=lambda item: item[0])
        leg_keys = tuple(publication_key(item) for item in group)
        combo = {
            "prediction_id": "lab-combo-" + fingerprint((POLICY_VERSION, leg_keys)),
            "policy": POLICY_VERSION, "created_at_utc": now.astimezone(timezone.utc).isoformat(),
            "legs": [dict(item) for item in group], "combined_odds": str(combined),
            "accounting": "LAB_ONLY_HYPOTHETICAL_ONE_UNIT",
            "correlation_review": "PASSED_DISTINCT_FIXTURES_TEAMS_AND_DISJOINT_BATCH",
        }
        selected.append(combo)
        consumed = set(leg_keys)
        consumed_fixtures = {item["fixture_id"] for item in group}
        consumed_teams = {str(item[key]) for item in group for key in ("home_team_id", "away_team_id")}
        remaining = [item for item in remaining
                     if publication_key(item) not in consumed
                     and item["fixture_id"] not in consumed_fixtures
                     and not consumed_teams.intersection({str(item["home_team_id"]), str(item["away_team_id"])})]
    return selected


def independent(legs) -> bool:
    if len(legs) != 3 or len({leg["fixture_id"] for leg in legs}) != 3:
        return False
    teams = [str(leg[key]) for leg in legs for key in ("home_team_id", "away_team_id")]
    return len(set(teams)) == 6


def publication_key(value: dict) -> str:
    return f"{value['fixture_id']}:{value['market']}"


def combined_odds_eligible(value) -> bool:
    odds = _decimal(value)
    return odds is not None and odds.is_finite() and Decimal(1) < odds <= MAX_COMBINED_ODDS


def _valid_leg_odds(value: Decimal | None) -> bool:
    return (
        value is not None
        and value.is_finite()
        and Decimal(1) < value <= MAX_SINGLE_ODDS
    )


def _timing_stage(
    snapshot: CurrentMatchIntelligenceSnapshot,
    *,
    market: str,
    now: datetime,
    lineup_confirmed: bool,
    lineup_context: dict,
) -> tuple[str, list[str], list[str]]:
    remaining = snapshot.kickoff_utc - now
    if remaining <= timedelta(0):
        return "REJECTED", ["FIXTURE_ALREADY_STARTED"], []
    if market in LINEUP_SENSITIVE_MARKETS and remaining > FINAL_REVIEW_START:
        return "EARLY_CANDIDATE", ["FINAL_REVIEW_WINDOW_NOT_OPEN"], []
    if market in LINEUP_SENSITIVE_MARKETS and not lineup_confirmed:
        return "FINAL_REVIEW_REQUIRED", ["LINEUP_NOT_YET_PUBLISHED"], []
    timing = "PREFERRED_FINAL_REVIEW_WINDOW" if remaining >= FINAL_REVIEW_PREFERRED_END else "LATE_FINAL_REVIEW_WINDOW"
    blockers = _final_review_blockers(snapshot, lineup_context)
    return ("READY_TO_PUBLISH" if not blockers else "REJECTED"), [timing], blockers


def _final_review_blockers(snapshot: CurrentMatchIntelligenceSnapshot, lineup_context: dict) -> list[str]:
    freshness = {item.signal: item for item in snapshot.freshness}
    blockers = []
    threshold = snapshot.evaluated_at - FINAL_REVIEW_REFRESH_MAX_AGE
    for signal in ("fixture_context", "confirmed_lineups", "injuries", "odds"):
        item = freshness.get(signal)
        if item is None or item.status.value != "FRESH":
            blockers.append(f"FINAL_REVIEW_{signal.upper()}_NOT_FRESH")
        elif item.newest_retrieved_at is None or item.newest_retrieved_at < threshold:
            blockers.append(f"FINAL_REVIEW_{signal.upper()}_NOT_REFRESHED")
    for side in ("home", "away"):
        if lineup_context[f"confirmed_starters_{side}"] != 11:
            blockers.append(f"FINAL_REVIEW_{side.upper()}_STARTERS_INCOMPLETE")
        if not lineup_context[f"formation_{side}"]:
            blockers.append(f"FINAL_REVIEW_{side.upper()}_FORMATION_MISSING")
        substitutes = lineup_context[f"substitutes_{side}"]
        if substitutes is None or substitutes < 1:
            blockers.append(f"FINAL_REVIEW_{side.upper()}_SUBSTITUTES_MISSING")
        if (lineup_context[f"availability_overlap_{side}"] or 0) > 0:
            blockers.append(f"CONTRADICTORY_{side.upper()}_STARTER_AVAILABILITY")
        continuity = _decimal(lineup_context[f"continuity_{side}"])
        if continuity is not None and continuity < Decimal("0.40"):
            blockers.append(f"LOW_{side.upper()}_LINEUP_CONTINUITY")
        missing = _decimal(lineup_context[f"missing_recent_starters_{side}"])
        if missing is not None and missing > 4:
            blockers.append(f"MATERIAL_{side.upper()}_STARTING_XI_CHANGE")
    return blockers


def _objective_quality_blockers(market: str, values: dict) -> list[str]:
    """Reject only objective contradictions or material uncertainty."""
    blockers = []
    for side in ("home", "away"):
        rest = _decimal(values.get(f"feature.rest_days_{side}"))
        congestion = _decimal(values.get(f"feature.schedule_congestion_{side}"))
        if rest is not None and congestion is not None and rest < 3 and congestion >= 2:
            blockers.append(f"MATERIAL_{side.upper()}_SCHEDULE_LOAD_UNCERTAINTY")
    home_form = _decimal(values.get("feature.home_form_strength"))
    away_form = _decimal(values.get("feature.away_form_strength"))
    if home_form is not None and away_form is not None:
        if market == "HOME_WIN" and home_form + Decimal("0.20") < away_form:
            blockers.append("HOME_WIN_CONTRADICTED_BY_RECENT_FORM")
        if market == "AWAY_WIN" and away_form + Decimal("0.20") < home_form:
            blockers.append("AWAY_WIN_CONTRADICTED_BY_RECENT_FORM")
    return blockers


def _completeness(required_features, fields, odds_field, lineup_confirmed: bool) -> str:
    total = len(required_features) + 2
    available = sum(name in fields for name in required_features)
    available += int(odds_field is not None) + int(lineup_confirmed)
    return str(Decimal(available) / Decimal(total))


def _market_probabilities(values: dict) -> dict[str, Decimal]:
    home = _expected_goals(values, "home", "away")
    away = _expected_goals(values, "away", "home")
    if home is None or away is None:
        return {}
    with localcontext() as context:
        context.prec = 28
        joint = []
        mass = Decimal(0)
        for h in range(13):
            for a in range(13):
                p = _poisson(home, h) * _poisson(away, a)
                joint.append((h, a, p)); mass += p
        probabilities = {
            "HOME_WIN": sum((p for h, a, p in joint if h > a), Decimal(0)) / mass,
            "DRAW": sum((p for h, a, p in joint if h == a), Decimal(0)) / mass,
            "AWAY_WIN": sum((p for h, a, p in joint if h < a), Decimal(0)) / mass,
            "BTTS_YES": sum((p for h, a, p in joint if h > 0 and a > 0), Decimal(0)) / mass,
        }
        probabilities["BTTS_NO"] = Decimal(1) - probabilities["BTTS_YES"]
        for line in (1, 2, 3):
            over = sum((p for h, a, p in joint if h + a > line), Decimal(0)) / mass
            probabilities[f"OVER_{line}_5"] = over
            probabilities[f"UNDER_{line}_5"] = Decimal(1) - over
        return probabilities


def _expected_goals(values: dict, side: str, opponent: str) -> Decimal | None:
    samples = []
    for first, second in (
        (f"feature.{side}_recent_goals_for_per_match", f"feature.{opponent}_recent_goals_against_per_match"),
        (f"{side}.recent_xg_per_match", f"{opponent}.recent_xg_against_per_match"),
    ):
        a, b = _decimal(values.get(first)), _decimal(values.get(second))
        if a is not None and b is not None:
            samples.append((a + b) / 2)
    venue = "home" if side == "home" else "away"
    opp_venue = "away" if opponent == "away" else "home"
    played = _decimal(values.get(f"{side}.season.{venue}.matches_played"))
    opp_played = _decimal(values.get(f"{opponent}.season.{opp_venue}.matches_played"))
    gf = _decimal(values.get(f"{side}.season.{venue}.goals_for"))
    ga = _decimal(values.get(f"{opponent}.season.{opp_venue}.goals_against"))
    if played and opp_played and gf is not None and ga is not None:
        samples.append((gf / played + ga / opp_played) / 2)
    if not samples:
        return None
    form = _decimal(values.get(f"feature.{side}_form_strength"), Decimal("0.5"))
    result = sum(samples, Decimal(0)) / len(samples)
    result *= Decimal("0.9") + Decimal("0.2") * form
    return min(Decimal("4.5"), max(Decimal("0.15"), result))


def _poisson(rate: Decimal, goals: int) -> Decimal:
    return (-rate).exp() * (rate ** goals) / Decimal(factorial(goals))


def _evidence_names(market: str, fields: dict) -> list[str]:
    names = [
        f"market.{market}.decimal_odds", f"market.{market}.implied_probability",
        "feature.home_form_strength", "feature.away_form_strength",
        "feature.home_recent_goals_for_per_match", "feature.home_recent_goals_against_per_match",
        "feature.away_recent_goals_for_per_match", "feature.away_recent_goals_against_per_match",
        "feature.rest_days_home", "feature.rest_days_away",
        "feature.schedule_congestion_home", "feature.schedule_congestion_away",
        "feature.injury_count_home", "feature.injury_count_away",
        "feature.suspension_count_home", "feature.suspension_count_away",
    ]
    names.extend(name for name in fields if ".recent_xg" in name or ".lineup." in name or ".formation" in name)
    return sorted({name for name in names if name in fields})


def _evidence(names: list[str], fields: dict) -> list[dict]:
    result = []
    for name in names:
        for provenance in fields[name].provenance:
            result.append({"field": name, **asdict(provenance)})
    unique = {fingerprint(item): item for item in result}
    return [unique[key] for key in sorted(unique)]


def _reasoning(market: str, values: dict, lineup: str) -> list[str]:
    context = _lineup_context(values)
    return [
        f"Recent form strength: home {values.get('feature.home_form_strength')} / away {values.get('feature.away_form_strength')}",
        f"Recent goals for/against: home {values.get('feature.home_recent_goals_for_per_match')}/{values.get('feature.home_recent_goals_against_per_match')}; away {values.get('feature.away_recent_goals_for_per_match')}/{values.get('feature.away_recent_goals_against_per_match')}",
        f"Rest days: home {values.get('feature.rest_days_home')} / away {values.get('feature.rest_days_away')}; lineup {lineup.lower()}",
        f"Availability counts: injuries {values.get('feature.injury_count_home')}/{values.get('feature.injury_count_away')}, suspensions {values.get('feature.suspension_count_home')}/{values.get('feature.suspension_count_away')}",
        f"Lineup context: formations {context['formation_home']}/{context['formation_away']}; continuity {context['continuity_home']}/{context['continuity_away']}; missing recent starters {context['missing_recent_starters_home']}/{context['missing_recent_starters_away']}; availability overlap {context['availability_overlap_home']}/{context['availability_overlap_away']}",
        f"Fresh bookmaker price for {market} retained with provider provenance",
    ]


def _risk(values: dict, lineup_confirmed: bool) -> str:
    parts = []
    if not lineup_confirmed:
        parts.append("confirmed lineups not yet published")
    if sum((_decimal(values.get(f"feature.injury_count_{side}"), Decimal(0)) for side in ("home", "away")), Decimal(0)) >= 4:
        parts.append("material availability uncertainty")
    if any((_decimal(values.get(f"feature.rest_days_{side}"), Decimal(99)) < 4 for side in ("home", "away"))):
        parts.append("short rest")
    if any((_decimal(values.get(f"feature.missing_recent_starters_count_{side}"), Decimal(0)) > 0
            for side in ("home", "away"))):
        parts.append("confirmed XI omits recent starters")
    return "; ".join(parts) if parts else "normal experimental uncertainty"


def _lineup_context(values: dict) -> dict:
    result = {}
    for side in ("home", "away"):
        starters = {str(value) for name, value in values.items()
                    if name.startswith(f"{side}.lineup.starters.") and name.endswith(".player_id")}
        unavailable = {name.split(".")[2] for name, value in values.items()
                       if name.startswith(f"{side}.availability.") and name.endswith(".availability")
                       and value == "UNAVAILABLE"}
        substitutes = sum(name.startswith(f"{side}.lineup.substitutes.") and name.endswith(".player_id")
                          for name in values)
        result.update({
            f"formation_{side}": values.get(f"{side}.formation"),
            f"confirmed_starters_{side}": values.get(f"feature.confirmed_starters_count_{side}"),
            f"substitutes_{side}": substitutes if starters else None,
            f"continuity_{side}": values.get(f"feature.lineup_continuity_{side}"),
            f"missing_recent_starters_{side}": values.get(f"feature.missing_recent_starters_count_{side}"),
            f"availability_overlap_{side}": len(starters & unavailable) if starters else None,
        })
    return result


def _provider_time(field) -> str | None:
    if field is None:
        return None
    values = [item.provider_timestamp for item in field.provenance if item.provider_timestamp]
    return max(values).isoformat() if values else None


def _retrieved_time(field) -> str | None:
    return max(item.retrieved_at for item in field.provenance).isoformat() if field else None


def _confidence(edge: Decimal | None) -> str:
    if edge is None: return "UNAVAILABLE"
    if edge >= Decimal("0.12"): return "HIGH"
    if edge >= Decimal("0.08"): return "MEDIUM"
    return "LOW"


def _decimal(value, default=None) -> Decimal | None:
    if value is None: return default
    try: return Decimal(str(value))
    except Exception: return default


def _product(values) -> Decimal:
    result = Decimal(1)
    for value in values: result *= value
    return result
