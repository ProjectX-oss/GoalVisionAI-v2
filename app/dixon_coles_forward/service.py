"""Reuse clock/quote/source guards with explicitly injected prospective algorithms."""
from datetime import datetime
from typing import Callable
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research import service as original, metrics as scores, model as baseline
from app.dixon_coles_research.contracts import seal, utc
from . import model
from .contracts import VERSION, verify_plan, reserved

COMPARATORS = scores.COMPARATORS + ("DIXON_COLES_V1",)

def forecast(item: dict, *, artifact: dict, plan: dict, now: datetime) -> dict:
    verify_plan(plan)
    if item["capture"]["fixture_id"] in reserved(plan):
        raise ValueError("EXCLUDED_FORWARD_FIXTURE")
    value = original.forecast(item, artifact=artifact, plan=plan, now=now,
                              predictor=model.predict, record_version=VERSION)
    value.pop("fingerprint")
    if artifact["baseline_model"] is None:
        value["missing_comparators"]["DIXON_COLES_V1:" + artifact["baseline_unavailable"]] = len(value["comparisons"])
    else:
        first = next(iter(item["candidates"].values()))
        try:
            old = baseline.predict(artifact["baseline_model"], home_team_id=first["home_team_id"],
                away_team_id=first["away_team_id"], league_id=first["league_id"],
                neutral="IS_NEUTRAL_VENUE" in first.get("flags", []),
                as_of=utc(now), kickoff=utc(value["kickoff_utc"]), plan=plan)
            for market, methods in value["comparisons"].items():
                methods["DIXON_COLES_V1"] = old["dixon_coles"]["probabilities"][market]
        except ValueError:
            value["missing_comparators"]["DIXON_COLES_V1:BASELINE_PREDICTION_UNAVAILABLE"] = len(value["comparisons"])
    return seal(value)

def intake(snapshot: dict, store: ResearchStore, *, plan: dict, clock: Callable[[], datetime]) -> dict:
    verify_plan(plan)
    data = {**snapshot, "additional_reserved": sorted(reserved(plan, frozenset(snapshot["additional_reserved"])))}
    return original.intake(data, store, plan=plan, clock=clock, fit_model=model.fit,
                           make_forecast=forecast, record_version=VERSION)

def evaluate(forecasts: list[dict], models: dict, results: list[dict], *, plan: dict,
             now: datetime, additional_reserved: frozenset[int] = frozenset()) -> dict:
    verify_plan(plan)
    for record in forecasts:
        if record["version"] != VERSION:
            raise ValueError("FORWARD_COHORT_MIXING")
        model.verify_artifact(models[record["model_fingerprint"]], plan=plan,
                              additional_reserved=additional_reserved)
    return scores.evaluate(forecasts, models, results, plan=plan, now=now,
                           additional_reserved=reserved(plan, additional_reserved),
                           reproduce=forecast, comparators=COMPARATORS, record_version=VERSION)
