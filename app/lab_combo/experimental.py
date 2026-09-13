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


POLICY_VERSION = "LAB_EXPERIMENTAL_SELECTION_V1"
MIN_SINGLE_ODDS = Decimal("1.70")
MAX_SINGLE_ODDS = Decimal("5.00")
MIN_COMBINED_ODDS = Decimal("2.00")
MAX_COMBINED_ODDS = Decimal("15.00")
MAX_COMBOS_PER_DISCOVERY_CYCLE = 3
MAX_SINGLES_PER_DISCOVERY_CYCLE = 3
SETTLEMENT_RELEVANCE_AFTER_KICKOFF = timedelta(minutes=90)
SUPPORTED_MARKETS = (
    "HOME_WIN", "DRAW", "AWAY_WIN", "OVER_1_5", "UNDER_1_5",
    "OVER_2_5", "UNDER_2_5", "OVER_3_5", "UNDER_3_5",
    "BTTS_YES", "BTTS_NO",
)
MARKET_ORDER = {market: index for index, market in enumerate(SUPPORTED_MARKETS)}
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
    absences = sum(_decimal(values.get(f"feature.{kind}_count_{side}")) or Decimal(0)
                   for side in ("home", "away") for kind in ("injury", "suspension"))
    results = []
    for market in SUPPORTED_MARKETS:
        odds_field = fields.get(f"market.{market}.decimal_odds")
        blockers = list(common)
        odds = _decimal(odds_field.value) if odds_field else None
        signal = probabilities.get(market)
        if odds is None:
            blockers.append("MARKET_ODDS_NOT_AVAILABLE")
        elif odds < MIN_SINGLE_ODDS:
            blockers.append("SINGLE_ODDS_BELOW_1_70")
        elif odds > MAX_SINGLE_ODDS:
            blockers.append("SINGLE_ODDS_ABOVE_EXPERIMENTAL_SAFETY_LIMIT")
        if signal is None:
            blockers.append("EXPERIMENTAL_SIGNAL_UNAVAILABLE")
        elif signal < Decimal("0.05") or signal > Decimal("0.85"):
            blockers.append("UNSUPPORTED_EXTREME_MODEL_SIGNAL")
        implied = Decimal(1) / odds if odds else None
        edge = signal - implied if signal is not None and implied is not None else None
        confidence = _confidence(edge)
        if edge is not None and edge < Decimal("0.05"):
            blockers.append("INSUFFICIENT_MARKET_CONTEXT_AGREEMENT")
        if edge is not None and edge > Decimal("0.15"):
            blockers.append("MODEL_MARKET_DIVERGENCE_TOO_LARGE")
        if confidence == "LOW":
            blockers.append("EXPERIMENTAL_CONFIDENCE_LOW")
        if not lineup_confirmed and absences >= 6 and market in {"HOME_WIN", "AWAY_WIN"}:
            blockers.append("LINEUP_REQUIRED_HIGH_AVAILABILITY_UNCERTAINTY")
        if not lineup_confirmed and market in {"HOME_WIN", "DRAW", "AWAY_WIN"}:
            blockers.append("LINEUP_NOT_YET_PUBLISHED")
        blockers = sorted(set(blockers))
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
            "lineup_status": lineup_state,
            "lineup_context": _lineup_context(values),
            "risk": _risk(values, lineup_confirmed),
            "reasoning": _reasoning(market, values, lineup_state),
            "evidence_fields": source_names, "provenance": evidence,
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


def select_single_predictions(candidates: list[dict], *, existing_keys: set[str], now: datetime) -> list[dict]:
    selected, fixtures = [], set()
    for candidate in rank_candidates([item for item in candidates if item["decision"] == "APPROVED"]):
        key = publication_key(candidate)
        if candidate["fixture_id"] in fixtures or key in existing_keys:
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
                 if item["decision"] == "APPROVED" and publication_key(item) not in used_leg_keys]
    selected = []
    while len(selected) < MAX_COMBOS_PER_DISCOVERY_CYCLE:
        choices = []
        for group in combinations(remaining, 3):
            if not independent(group):
                continue
            combined = _product(_decimal(item["captured_odds"]) for item in group)
            if (any(not MIN_SINGLE_ODDS <= _decimal(item["captured_odds"]) <= MAX_SINGLE_ODDS for item in group)
                    or not combined_odds_eligible(combined)):
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
    return MIN_COMBINED_ODDS <= _decimal(value) <= MAX_COMBINED_ODDS


def single_message(value: dict) -> str:
    reasons = "\n".join(f"- {line}" for line in value["reasoning"])
    return (f"🧪 LAB EXPERIMENTAL SINGLE\n{value['home_team']} vs {value['away_team']} ({value['competition']})\n"
            f"{value['market']} @ {value['captured_odds']} ({value['bookmaker']})\nWhy:\n{reasons}\n"
            f"Lineup: {value['lineup_status']}\nExperimental confidence: {value['experimental_confidence']} "
            f"(uncalibrated signal {value['experimental_signal']})\nRisk/uncertainty: {value['risk']}\n"
            "Lab experiment only. No guaranteed profit.")


def combo_message(value: dict, number: int) -> str:
    lines = [f"🧪 LAB EXPERIMENTAL COMBO #{number}", "Exactly 3 independent Lab-approved legs"]
    for index, leg in enumerate(value["legs"], 1):
        lines.extend((f"{index}. {leg['home_team']} vs {leg['away_team']} — {leg['market']} @ {leg['captured_odds']}",
                      f"   {leg['reasoning'][0]} | lineup: {leg['lineup_status']}"))
    lines.extend((f"Combined odds: {value['combined_odds']}",
                  "Higher variance than singles. Lab experiment only. No guaranteed profit."))
    return "\n".join(lines)


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
