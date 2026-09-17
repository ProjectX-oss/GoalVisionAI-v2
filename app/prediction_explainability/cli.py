"""Manual, offline CLI for reasoning creation and inspection."""

import argparse
import json
from pathlib import Path

from app.database import Database
from app.real_match_lab_analysis.fingerprint import canonical_json

from .audit import audit_reasoning
from .controlled import run_controlled_rehearsal
from .repository import SQLiteReasoningRepository
from .service import PredictionExplainabilityService


def build_parser():
    parser=argparse.ArgumentParser(prog="goalvision-prediction-explainability",description="Deterministic offline GoalVision AI reasoning")
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("explain-analysis","explain-observation","inspect-reasoning","reproduce-reasoning","audit-reasoning","list-reasoning","explain-market","compare-markets","feature-contributions","reasoning-diagnostics","controlled-rehearsal"):
        item=sub.add_parser(name);item.add_argument("--database",type=Path,required=True);item.add_argument("--id");item.add_argument("--output",choices=("human","json"),default="human")
    return parser


def main(argv=None):
    args=build_parser().parse_args(argv);database=Database(str(args.database))
    try:
        repo=SQLiteReasoningRepository(database)
        if args.command=="controlled-rehearsal":value=run_controlled_rehearsal(database)
        elif args.command=="list-reasoning":value=[{"reasoning_id":x.reasoning_id,"analysis_id":x.analysis_id,"market":x.selected_market,"status":x.reasoning_status,"fingerprint":x.reasoning_fingerprint} for x in repo.list()]
        elif args.command in {"explain-analysis","explain-observation"}:
            if not args.id:raise ValueError("--id is required.")
            analysis_id=args.id
            observation_id=None
            if args.command=="explain-observation":
                row=database.connection.execute("SELECT analysis_id FROM forward_test_observations WHERE observation_id=?",(args.id,)).fetchone()
                if row is None:raise ValueError("Observation not found.")
                analysis_id=row[0];observation_id=args.id
            result=PredictionExplainabilityService(database).create_for_analysis(analysis_id,created_at_utc=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),observation_id=observation_id);value={"reasoning_id":result["record"].reasoning_id,"audit":result["audit"].status,"fingerprint":result["record"].reasoning_fingerprint,"network_calls":0,"telegram_calls":0}
        else:
            if not args.id:raise ValueError("--id is required.")
            record=repo.load(args.id)
            if record is None:raise ValueError("Reasoning not found.")
            if args.command=="audit-reasoning":value=audit_reasoning(record,checked_at_utc=record.created_at_utc)
            elif args.command=="feature-contributions":value=record.class_attributions
            elif args.command=="explain-market":value=record.market_explanations
            elif args.command=="compare-markets":value={"selected":record.selected_market,"markets":record.market_explanations}
            elif args.command=="reasoning-diagnostics":value={"status":record.reasoning_status,"reproduction":record.contribution_reproduction_status,"stability":record.explanation_stability_status,"audit":repo.audit_for(record.reasoning_id)}
            elif args.command=="reproduce-reasoning":value=PredictionExplainabilityService(database).verify_stored_reproduction(record.reasoning_id)
            else:value=record
        if args.output=="json":print(canonical_json(value).encode("ascii",errors="backslashreplace").decode("ascii"))
        else:
            text=canonical_json(value);print(text.encode("cp1252",errors="replace").decode("cp1252"))
        return 0
    except (ValueError,RuntimeError) as exc:
        print(f"REJECTED: {exc}");return 3
    finally:database.close()
