"""Explicit manual-only operator CLI."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.database import Database
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint

from .engine import MonitoringService
from .exports import export_bundle, markdown, telegram_preview
from .repository import SQLiteMonitoringRepository


def parser() -> argparse.ArgumentParser:
    value=argparse.ArgumentParser(description="GoalVision AI manual forward-test monitoring")
    value.add_argument("--database",required=True); sub=value.add_subparsers(dest="command",required=True)
    for name in ("snapshot","weekly-report","cumulative-report","quality","unresolved","health","incidents"):
        item=sub.add_parser(name); item.add_argument("--cutoff",required=True)
        if name in {"weekly-report","cumulative-report"}: item.add_argument("--output")
    audit=sub.add_parser("audit"); audit.add_argument("observation_id"); audit.add_argument("--cutoff",required=True); audit.add_argument("--persist",action="store_true")
    reproduce=sub.add_parser("reproduce"); reproduce.add_argument("report_id")
    export=sub.add_parser("export"); export.add_argument("report_id"); export.add_argument("--output",required=True); export.add_argument("--overwrite",action="store_true")
    ack=sub.add_parser("acknowledge"); ack.add_argument("incident_id"); ack.add_argument("--operator",required=True); ack.add_argument("--reason",required=True); ack.add_argument("--at",required=True); ack.add_argument("--resolved",action="store_true")
    return value


def main(argv=None) -> int:
    args=parser().parse_args(argv); database=Database(args.database); service=MonitoringService(SQLiteMonitoringRepository(database))
    try:
        if args.command=="snapshot": output=service.snapshot(_time(args.cutoff))
        elif args.command=="weekly-report": output=service.report("WEEKLY",_time(args.cutoff)); output=_render(output,args.output)
        elif args.command=="cumulative-report": output=service.report("CUMULATIVE",_time(args.cutoff)); output=_render(output,args.output)
        elif args.command=="quality": output=service.data_quality(_time(args.cutoff))
        elif args.command=="unresolved": output={"unresolved":service.unresolved(_time(args.cutoff))}
        elif args.command=="health": output=service.health(_time(args.cutoff))
        elif args.command=="incidents": output={"incidents":service.record_incidents(_time(args.cutoff))}
        elif args.command=="audit": output=service.lifecycle_audit(args.observation_id,_time(args.cutoff),persist=args.persist)
        elif args.command=="reproduce": output=service.reproduce(args.report_id)
        elif args.command=="export":
            output=export_bundle(service.repository.report(args.report_id),Path(args.output),overwrite=args.overwrite)
            material={"report_id":args.report_id,"export_format":"CSV_BUNDLE","content_fingerprint":output["manifest_fingerprint"],"relative_path":Path(args.output).name,"created_at_utc":service.repository.report(args.report_id)["generated_at_utc"]}; material["export_fingerprint"]=fingerprint(material); material["export_id"]="forward-test-export-"+material["export_fingerprint"]; service.repository.append_export(material)
        else: output=service.acknowledge_incident(args.incident_id,args.operator,args.reason,_time(args.at),resolved=args.resolved)
        print(output if isinstance(output,str) else canonical_json(output)); return 0
    finally: database.close()


def _time(value): return datetime.fromisoformat(value.replace("Z","+00:00"))
def _render(report,style):
    if style=="markdown":return markdown(report)
    if style=="telegram":return telegram_preview(report)
    return report
