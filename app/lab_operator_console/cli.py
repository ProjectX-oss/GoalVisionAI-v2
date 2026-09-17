"""Explicit launcher for the local-only Lab operator console."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.database import Database
from app.real_match_lab_analysis.fingerprint import canonical_json

from .config import ConsoleConfig
from .demo import build_demo
from .web import ConsoleApplication


def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(prog="goalvision-lab-console",description="Local manual-only GoalVision AI Lab operator console")
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("run","config-check"):
        item=sub.add_parser(name);_common(item);item.add_argument("--enable-actions",action="store_true");item.add_argument("--output",choices=("human","json"),default="human")
    demo=sub.add_parser("demo");_common(demo);demo.add_argument("--enable-actions",action="store_true");demo.add_argument("--output",choices=("human","json"),default="human");demo.add_argument("--no-serve",action="store_true")
    return parser


def _common(parser):
    parser.add_argument("--database",type=Path,required=True);parser.add_argument("--allowed-root",type=Path,action="append");parser.add_argument("--host",default="127.0.0.1");parser.add_argument("--port",type=int,default=8765);parser.add_argument("--operator",default="local-operator")


def main(argv=None) -> int:
    args=build_parser().parse_args(argv)
    try:
        demo=args.command=="demo"
        if demo:
            args.database.parent.mkdir(parents=True,exist_ok=True);database=Database(str(args.database));manifest=build_demo(database);database.close()
        config=ConsoleConfig.build(args.database,allowed_database_roots=tuple(args.allowed_root or (Path.cwd(),)),host=args.host,port=args.port,read_only=not args.enable_actions,operator_identifier=args.operator,controlled_demo=demo)
        public=config.public_view();public.update({"status":"CONFIGURATION_VALID","session_secret":"EPHEMERAL_NOT_PRINTED","csrf_enabled":True,"external_binding":False,"network_calls":0,"telegram_calls":0})
        if demo:public["demo_manifest"]=manifest
        if args.output=="json":print(canonical_json(public))
        else:
            print("GoalVision AI Lab Operator Console")
            print("LOCAL OPERATOR CONSOLE - NOT PUBLICLY EXPOSED")
            print(f"URL: http://{config.host}:{config.port}")
            print(f"Database: {config.database}")
            print(f"Mode: {'READ_ONLY' if config.read_only else 'ACTIONS_ENABLED_WITH_CONFIRMATION'}")
            print("Scheduler: DISABLED | Automatic publication: DISABLED | Startup actions: ZERO")
            if demo:print("CONTROLLED FICTIONAL DEMO DATA")
        if args.command=="config-check" or demo and args.no_serve:return 0
        ConsoleApplication(config).serve();return 0
    except (ValueError,OSError) as exc:
        print(f"REJECTED: {exc}",file=sys.stderr);return 3


if __name__=="__main__":raise SystemExit(main())
