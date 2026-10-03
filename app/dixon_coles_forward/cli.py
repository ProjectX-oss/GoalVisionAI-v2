"""Dedicated source readers and append-only output; no transport/provider imports."""
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Callable
from app.dixon_coles_research.repository import ResearchStore
from app.dixon_coles_research import sources
from app.dixon_coles_research.contracts import seal, utc
from .contracts import load_plan, reserved
from . import service, combo

ORIGINAL_RESEARCH = Path("/var/lib/goalvision-dixon-coles/research.db")

def run_report(args: Namespace, clock: Callable[[], datetime]) -> dict:
    plan = load_plan()
    protected = (args.shadow_database, args.audit_database, args.ledger_database, ORIGINAL_RESEARCH)
    # Reject the original cohort and production aliases before reading sources or creating output.
    store = ResearchStore(args.research_database, protected_paths=protected)
    try:
        store.append("plan", plan["fingerprint"], plan)
        if args.command == "capture":
            data = sources.snapshot(args.shadow_database, args.audit_database, plan=plan,
                                    now=clock(), limit=args.limit)
            report = service.intake(data, store, plan=plan, clock=clock)
            now = clock()
            # First prospective family forecasts only. Reused/stale inputs cannot produce another bet.
            forecasts = [r for r in store.all("forecast")
                         if 0 <= (utc(now)-utc(r["forecast_at"])).total_seconds() <= 900]
            batch = combo.capture(forecasts, store, plan=plan, now=now)
            report.pop("fingerprint")
            report["combo_shadow"] = {"eligible_fixtures": batch["eligible_fixtures"],
                "selections": {k: len(v) for k,v in batch["selections"].items()},
                "rejection_counts": batch["rejection_counts"], "fingerprint": batch["fingerprint"]}
            return seal(report)
        if args.command != "evaluate":
            raise ValueError("UNKNOWN_FORWARD_OPERATION")
        forecasts = store.all("forecast"); models = {m["fingerprint"]: m for m in store.all("model")}
        now = clock()
        facts = sources.results(args.ledger_database, args.audit_database,
                                fixture_ids={r["fixture_id"] for r in forecasts}, now=now)
        exclusions = reserved(plan, sources.consumed_holdout_fixtures(args.audit_database))
        report = service.evaluate(forecasts, models, facts, plan=plan, now=now, additional_reserved=exclusions)
        combos = combo.evaluate(store.all("combo_batch"), forecasts, facts, plan=plan, now=now,
                                additional_reserved=exclusions)
        store.append("combo_metrics", combos["fingerprint"], combos)
        report.pop("fingerprint")
        report["combo_shadow"] = {"fingerprint": combos["fingerprint"],
            "policies": {k: {a:b for a,b in v.items() if a != "rows"} for k,v in combos["policies"].items()}}
        report = seal(report)
        store.append("metrics", report["fingerprint"], report)
        return report
    finally:
        store.close()
