"""Versioned data-only research boundaries; no credentials or runtime controls."""
from __future__ import annotations
from datetime import datetime
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from app.adaptive_lab.contracts import canonical, digest, utc, MARKETS
from app.adaptive_lab.calendar_research import CalendarPlan

VERSION = "DIXON_COLES_RESEARCH_V1"
MODEL_VERSION = "REGULARIZED_DIXON_COLES_V1"
POLICY = MappingProxyType({"half_life_days": 180, "ridge": 0.02, "minimum_matches": 40,
          "minimum_target_team_matches": 3, "maximum_matches": 500,
          "maximum_teams": 64, "maximum_iterations": 250,
          "gradient_tolerance": 0.000001, "rho_scale": 0.2,
          "maximum_goal_rate": 8.0, "tail_tolerance": 1e-12,
          "maximum_goals": 80})
PLAN_PATH = Path(__file__).with_name("plan_20261003.json")

def seal(value: dict) -> dict:
    if "fingerprint" in value:
        raise ValueError("ALREADY_SEALED")
    return {**value, "fingerprint": digest(value)}

def verify(value: dict) -> None:
    if value.get("fingerprint") != digest({k:v for k,v in value.items() if k != "fingerprint"}):
        raise ValueError("RESEARCH_INTEGRITY")

def integer(value: object, *, low: int = 1, high: int = 10**9) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError("INVALID_INTEGER")
    return value

def finite(value: object, *, low: float = -1e9, high: float = 1e9) -> float:
    if isinstance(value, bool):
        raise ValueError("INVALID_NUMBER")
    result = float(value)
    if not isfinite(result) or not low <= result <= high:
        raise ValueError("INVALID_NUMBER")
    return result

def load_plan(path: Path = PLAN_PATH) -> dict:
    import json
    plan = json.loads(path.read_text())
    verify_plan(plan)
    return plan

def verify_plan(plan: dict) -> None:
    verify(plan)
    calendar = CalendarPlan.from_document(plan["protected_calendar"])
    if (plan["version"] != VERSION or plan["model_policy"] != POLICY
            or plan["selection_effect"] != "NONE"
            or plan["priority"] != "NORMAL"
            or utc(plan["train_end"]) != calendar.windows()["TRAIN"][1]
            or not utc(plan["train_end"]) < utc(plan["declared_at"]) <= utc(plan["evaluation_start"])
            or not utc(plan["evaluation_start"]) < utc(plan["evaluation_end"])
            or utc(plan["evaluation_end"]) > calendar.windows()["SEALED_HOLDOUT"][0]):
        raise ValueError("RESEARCH_PLAN_INVALID")

def normalize_results(rows: list[dict], *, league_id: int, as_of: datetime,
                      plan: dict, additional_reserved: frozenset[int] = frozenset()) -> tuple[list[dict], dict]:
    """Use observed regulation-time facts only; never infer when a score was known."""
    from collections import Counter
    verify_plan(plan)
    integer(league_id)
    if len(rows) > POLICY["maximum_matches"]:
        raise ValueError("TRAINING_CAPACITY")
    end, cutoff = utc(plan["train_end"]), utc(as_of)
    reserved = {int(v) for v in plan["protected_calendar"]["reserved_holdout_fixtures"]} | set(additional_reserved)
    selected, counts = {}, Counter()
    for row in rows:
        fid = integer(row["fixture_id"])
        kickoff, observed = utc(row["kickoff_utc"]), utc(row["observed_at_utc"])
        if fid in reserved:
            counts["reserved_holdout"] += 1
            continue
        if kickoff >= end:
            counts["outside_frozen_training_window"] += 1
            continue
        if observed > cutoff or not kickoff < observed:
            counts["result_not_known_as_of_input"] += 1
            continue
        if row.get("league_id") != league_id or row.get("status") != "FT":
            counts["wrong_league_or_non_regulation_terminal"] += 1
            continue
        h, a = integer(row["home_team_id"]), integer(row["away_team_id"])
        if h == a or type(row.get("neutral")) is not bool or not row.get("source_fingerprint"):
            raise ValueError("RESULT_PROVENANCE")
        value = {k:row[k] for k in ("fixture_id","league_id","home_team_id","away_team_id",
                                    "source_fingerprint","neutral")}
        value.update(kickoff_utc=kickoff.isoformat(), observed_at_utc=observed.isoformat(),
                     home_goals=integer(row["home_goals"],low=0,high=30),
                     away_goals=integer(row["away_goals"],low=0,high=30), status="FT")
        old = selected.get(fid)
        if old:
            keys = ("home_team_id","away_team_id","home_goals","away_goals","kickoff_utc","neutral")
            if any(old[k] != value[k] for k in keys):
                raise ValueError("CONFLICTING_TRAINING_RESULT")
            counts["duplicate_result"] += 1
            if (old["observed_at_utc"],old["source_fingerprint"]) <= (value["observed_at_utc"],value["source_fingerprint"]):
                continue
        selected[fid] = value
    return sorted(selected.values(),key=lambda r:(r["kickoff_utc"],r["fixture_id"])), dict(counts)
