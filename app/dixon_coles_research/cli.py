"""Explicit manual research CLI. No timer, provider, transport or credential setup."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
import sqlite3
from pathlib import Path
from .contracts import load_plan,seal
from .repository import ResearchStore
from .sources import snapshot,results,consumed_holdout_fixtures
from .service import intake
from .metrics import evaluate

def run_report(args: argparse.Namespace, clock) -> dict:
    """Run one data operation; callers provide the real clock or an isolated test clock."""
    plan=load_plan(); store=None
    try:
        protected=tuple(p for p in (args.shadow_database,args.audit_database,args.ledger_database) if p)
        if args.command in {"readiness","capture"}:
            data=snapshot(args.shadow_database,args.audit_database,plan=plan,now=clock(),limit=args.limit)
            if args.command=="readiness":
                report=seal({"eligible_fixture_families":len(data["items"]),
                             "diagnostics":data["diagnostics"],"read_only":True,
                             "provider_calls":0,"telegram_sends":0,"priority":"NORMAL"})
            else:
                store=ResearchStore(args.research_database,protected_paths=protected)
                report=intake(data,store,plan=plan,clock=clock)
        else:
            store=ResearchStore(args.research_database,protected_paths=protected)
            if store.get("plan",plan["fingerprint"])!=plan: raise ValueError("RESEARCH_PLAN_NOT_ENROLLED")
            forecasts=store.all("forecast"); models={m["fingerprint"]:m for m in store.all("model")}
            now=clock()
            facts=results(args.ledger_database,args.audit_database,
                          fixture_ids={r["fixture_id"] for r in forecasts},now=now)
            report=evaluate(forecasts,models,facts,plan=plan,now=now,
                            additional_reserved=consumed_holdout_fixtures(args.audit_database))
            store.append("metrics",report["fingerprint"],report)
        return report
    finally:
        if store is not None: store.close()

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("readiness","capture","evaluate"))
    parser.add_argument("--shadow-database",type=Path,required=True)
    parser.add_argument("--audit-database",type=Path,required=True)
    parser.add_argument("--ledger-database",type=Path)
    parser.add_argument("--research-database",type=Path)
    parser.add_argument("--limit",type=int,default=20)
    args=parser.parse_args(argv)
    if args.command!="readiness" and args.research_database is None:
        parser.error("--research-database is required")
    if args.command=="evaluate" and args.ledger_database is None:
        parser.error("--ledger-database is required")
    if hasattr(os,"getpriority"):
        current=os.getpriority(os.PRIO_PROCESS,0)
        if current<10: os.nice(10-current)
    try:
        report=run_report(args,lambda:datetime.now(timezone.utc))
        print(json.dumps(report,sort_keys=True,allow_nan=False))
        return 0
    except (ValueError,KeyError,TypeError,ArithmeticError,OSError,sqlite3.Error) as exc:
        reason=str(exc) if isinstance(exc,ValueError) and str(exc).isupper() else "RESEARCH_INPUT_UNAVAILABLE"
        print(json.dumps({"status":"BLOCKED","reason":reason,"selection_effect":"NONE"}))
        return 2
