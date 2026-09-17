"""Explicit network-inert CLI for forward-test governance."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.database import Database
from app.real_match_lab_analysis.fingerprint import canonical_json

from .controlled import run_controlled_rehearsal
from .reports import build_report, csv_text, markdown, telegram_preview
from .service import GovernanceService


COMMANDS = (
    "evaluate-governance", "inspect-governance", "reproduce-governance",
    "governance-history", "market-governance", "competition-governance",
    "bookmaker-governance", "compare-generations", "retraining-recommendation",
    "recalibration-recommendation", "rollback-review", "governance-report",
    "governance-diagnostics", "controlled-rehearsal",
)


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Manual-only GoalVision AI forward-test governance")
    sub = value.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        item = sub.add_parser(name)
        item.add_argument("--database", required=True, type=Path)
        item.add_argument("--json", action="store_true", dest="json_output")
        item.add_argument("--cutoff")
        item.add_argument("--evaluation-id")
        item.add_argument("--scope")
        item.add_argument("--format", choices=("human", "json", "markdown", "csv", "telegram-preview"), default="human")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evaluation(service: GovernanceService, identifier: str | None):
    value = service.repository.load(identifier) if identifier else service.repository.latest()
    if value is None:
        raise ValueError("Governance evaluation not found.")
    return value


def dispatch(args) -> object:
    database = Database(args.database)
    try:
        service = GovernanceService(database)
        command = args.command
        if command == "evaluate-governance":
            if not args.cutoff:
                raise ValueError("--cutoff is required.")
            return service.evaluate(args.cutoff)
        if command == "controlled-rehearsal":
            return run_controlled_rehearsal(database)
        if command == "governance-history":
            return {"evaluations": service.repository.history(), "network_calls": 0, "telegram_calls": 0}
        if command == "reproduce-governance":
            if not args.evaluation_id:
                raise ValueError("--evaluation-id is required.")
            return service.reproduce(args.evaluation_id, args.cutoff or _now())
        evaluation = _evaluation(service, args.evaluation_id)
        if command == "inspect-governance":
            return evaluation
        if command in {"market-governance", "competition-governance", "bookmaker-governance"}:
            kind = command.split("-")[0].upper()
            rows = [row for row in evaluation["scope_statuses"] if row["scope_type"] == kind and (not args.scope or row["scope_value"] == args.scope)]
            return {"evaluation_id": evaluation["evaluation_id"], "scope_type": kind, "statuses": rows}
        if command == "compare-generations":
            return evaluation["metrics"]["generation_comparison"]
        recommendation = {row["type"]: row for row in evaluation["recommendations"]}
        if command == "retraining-recommendation":
            return recommendation["RETRAINING"]
        if command == "recalibration-recommendation":
            return recommendation["RECALIBRATION"]
        if command == "rollback-review":
            return recommendation["ROLLBACK"]
        if command == "governance-diagnostics":
            return {"schema_version": database.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0], "foreign_key_violations": len(database.connection.execute("PRAGMA foreign_key_check").fetchall()), "latest_evaluation_id": evaluation["evaluation_id"], "network_calls": 0, "telegram_calls": 0, "automatic_execution": False}
        if command == "governance-report":
            return build_report(evaluation)
        raise ValueError("Unsupported command.")
    finally:
        database.close()


def _human(value: object) -> str:
    if isinstance(value, dict) and "decision" in value:
        return "\n".join(("GoalVision AI forward-test governance", f"Decision: {value['decision']['status']}", f"Sample maturity: {value.get('sample_maturity', 'N/A')}", f"Fingerprint: {value.get('evaluation_fingerprint', value.get('report_fingerprint', 'N/A'))}", "Manual-only; no provider or Telegram action occurred."))
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        value = dispatch(args)
        output_format = "json" if args.json_output else args.format
        if args.command == "governance-report" and output_format in {"markdown", "csv", "telegram-preview"}:
            text = {"markdown": markdown, "csv": csv_text, "telegram-preview": telegram_preview}[output_format](value)
        else:
            text = canonical_json(value) if output_format == "json" else _human(value)
        print(text)
        return 0
    except (ValueError, RuntimeError) as exc:
        print(f"GOVERNANCE_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
