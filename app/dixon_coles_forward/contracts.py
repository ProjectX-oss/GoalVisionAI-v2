"""Pinned prospective declaration independent from the deployed V1 cohort."""
from datetime import datetime
from pathlib import Path
from app.dixon_coles_research.contracts import load_plan as read_plan, verify_plan as base_verify, utc

VERSION = "DC_CONSTRAINED_FORWARD_V1"
FINGERPRINT = "9166353de416c8eeee67fae84c1980f619f8e5ed0c56e6d421df0d0646eaa9f6"

def verify_plan(plan: dict) -> None:
    base_verify(plan)
    if (plan["fingerprint"] != FINGERPRINT or plan["selection_effect"] != "NONE"
            or plan["automatic_promotion"] is not False):
        raise ValueError("FORWARD_PLAN_DRIFT")

def load_plan() -> dict:
    plan = read_plan(Path(__file__).with_name("plan_20261003.json"))
    verify_plan(plan)
    return plan

def reserved(plan: dict, additional: frozenset[int] = frozenset()) -> frozenset[int]:
    return frozenset(int(v) for v in plan["protected_calendar"]["reserved_holdout_fixtures"]) | additional | frozenset(plan["excluded_development_fixtures"])

def input_guard(plan: dict, as_of: datetime) -> None:
    verify_plan(plan)
    if not utc(plan["declared_at"]) <= utc(as_of) < utc(plan["evaluation_end"]):
        raise ValueError("FORWARD_INPUT_OUTSIDE_DECLARATION")
