"""Inert-by-default operator CLI. Only ``send`` can invoke Telegram."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import dotenv_values

from app.database import Database
from app.services.telegram_service import TelegramService

from .factory import build_real_match_lab_analysis_service
from .fingerprint import canonical_json
from .input import InputValidationError, load_input
from .models import (
    LAB_BOT_USERNAME,
    LAB_CHAT_ID,
    OUTPUT_SCHEMA_VERSION,
    SEND_CONFIRMATION,
)
from .repository import (
    AnalysisConflictError,
    DeliveryConflictError,
    SQLiteRealMatchLabRepository,
    row_as_dict,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goalvision-real-match-lab",
        description="Manual one-match, dry-run-first GoalVision AI Lab analysis.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-input")
    validate.add_argument("--input", type=Path, required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--database", type=Path, required=True)
    analyze.add_argument("--input", type=Path, required=True)
    analyze.add_argument("--output", choices=("human", "json"), default="human")
    for name in ("preview", "inspect", "inspect-markets", "events", "eligible", "delivery"):
        item = sub.add_parser(name)
        item.add_argument("--database", type=Path, required=True)
        item.add_argument("--analysis-id", required=True)
        item.add_argument("--output", choices=("human", "json"), default="human")
    send = sub.add_parser("send")
    send.add_argument("--database", type=Path, required=True)
    send.add_argument("--analysis-id", required=True)
    send.add_argument("--confirmation", required=True)
    send.add_argument("--env-file", type=Path, default=Path(".env"))
    diagnose = sub.add_parser("diagnose")
    diagnose.add_argument("--database", type=Path, required=True)
    diagnose.add_argument("--env-file", type=Path, default=Path(".env"))
    diagnose.add_argument("--output", choices=("human", "json"), default="human")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-input":
            value = load_input(args.input)
            print(
                f"VALID: request={value.request_id} match={value.match_id} "
                f"markets={len(value.odds)} destination={LAB_CHAT_ID}"
            )
            return 0
        if args.command == "analyze":
            database = Database(args.database)
            try:
                record = build_real_match_lab_analysis_service(database).analyze(
                    load_input(args.input)
                )
                _print_record(record, args.output)
                return 0 if record.status.value in {"COMPLETED", "NO_SELECTION"} else 4
            finally:
                database.close()
        if args.command in {
            "preview", "inspect", "inspect-markets", "events", "eligible", "delivery"
        }:
            return _inspect(args)
        if args.command == "send":
            return _send(args)
        if args.command == "diagnose":
            return _diagnose(args)
    except (InputValidationError, AnalysisConflictError, DeliveryConflictError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 3
    raise AssertionError("Unknown command")


def _inspect(args):
    database = Database(args.database)
    try:
        repository = SQLiteRealMatchLabRepository(database, migrate=False)
        row = repository.load_analysis(args.analysis_id)
        if row is None:
            print("NOT FOUND", file=sys.stderr)
            return 2
        if args.command == "inspect-markets":
            value = [json.loads(item[0]) for item in repository.market_evaluations(args.analysis_id)]
        elif args.command == "events":
            value = [json.loads(item[0]) for item in repository.stage_events(args.analysis_id)]
        elif args.command == "delivery":
            value = json.loads(canonical_json(repository.delivery_history(args.analysis_id)))
        elif args.command == "eligible":
            history = repository.delivery_history(args.analysis_id)
            eligible = (
                row["status"] == "COMPLETED"
                and not history
                or bool(history) and history[-1].status.value == "FAILED"
            )
            value = {
                "analysis_id": args.analysis_id,
                "eligible": eligible,
                "destination_chat_id": row["destination_chat_id"],
                "destination_bot": row["destination_bot"],
                "confirmation": SEND_CONFIRMATION,
            }
        elif args.command == "preview":
            value = {
                "analysis_id": args.analysis_id,
                "message_html": row["message_html"],
                "message_fingerprint": row["message_fingerprint"],
                "destination_chat_id": row["destination_chat_id"],
                "destination_bot": row["destination_bot"],
            }
        else:
            value = row_as_dict(row)
        _print_value(value, args.output)
        return 0
    finally:
        database.close()


def _send(args):
    values = dotenv_values(args.env_file)
    token = _clean(values.get("GOALVISION_LAB_TELEGRAM_BOT_TOKEN"))
    chat_id = _clean(values.get("GOALVISION_LAB_TELEGRAM_CHAT_ID"))
    bot = _clean(values.get("GOALVISION_LAB_TELEGRAM_BOT_USERNAME"))
    database = Database(args.database)
    try:
        service = build_real_match_lab_analysis_service(database)
        if not token:
            raise DeliveryConflictError("Lab bot token is missing.")
        result = asyncio.run(service.send(
            args.analysis_id, args.confirmation, token=token,
            configured_chat_id=chat_id, configured_bot=bot,
            transport=TelegramService(token),
        ))
        print(
            f"{result.status.value}: analysis={result.analysis_id} "
            f"destination={result.destination_chat_id} "
            f"message_id={result.telegram_message_id or '-'}"
        )
        return 0 if result.status.value == "SENT" else 5
    finally:
        database.close()


def _diagnose(args):
    values = dotenv_values(args.env_file)
    database = Database(args.database)
    try:
        version = database.connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        result = {
            "schema_version": version,
            "environment": "LAB",
            "destination_chat_id": _clean(values.get("GOALVISION_LAB_TELEGRAM_CHAT_ID")),
            "destination_valid": _clean(values.get("GOALVISION_LAB_TELEGRAM_CHAT_ID")) == LAB_CHAT_ID,
            "bot_username": _clean(values.get("GOALVISION_LAB_TELEGRAM_BOT_USERNAME")),
            "bot_valid": _clean(values.get("GOALVISION_LAB_TELEGRAM_BOT_USERNAME")) == LAB_BOT_USERNAME,
            "token_present": bool(_clean(values.get("GOALVISION_LAB_TELEGRAM_BOT_TOKEN"))),
            "automatic_send": False,
        }
        _print_value(result, args.output)
        return 0
    finally:
        database.close()


def _print_record(record, output):
    if output == "json":
        print(_json_text({
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "analysis": record,
            "send_confirmation": SEND_CONFIRMATION,
        }))
        return
    print(f"Analysis: {record.analysis_id}")
    print(f"Status: {record.status.value}")
    print(f"Match: {record.input.home_team} vs {record.input.away_team}")
    print(f"Destination: {record.destination_bot} / {record.destination_chat_id}")
    print(f"Request fingerprint: {record.request_fingerprint}")
    print(f"Result fingerprint: {record.result_fingerprint}")
    if record.message_html:
        print("\n--- Lab preview (no message sent) ---\n")
        print(record.message_html)
    else:
        print("Rejection reasons: " + ", ".join(record.rejection_reasons or ("NO_SELECTION",)))
    print(f"\nSend confirmation required: {SEND_CONFIRMATION}")


def _print_value(value, output):
    if output == "json":
        print(_json_text(value))
    else:
        if isinstance(value, dict):
            for key, item in value.items():
                print(f"{key}: {item}")
        else:
            print(json.dumps(value, indent=2, ensure_ascii=True))


def _json_text(value):
    """Render deterministic JSON safely through non-UTF-8 operator terminals."""
    normalized = json.loads(canonical_json(value))
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _clean(value):
    if not isinstance(value, str):
        return None
    return value.strip() or None


if __name__ == "__main__":
    sys.exit(main())
