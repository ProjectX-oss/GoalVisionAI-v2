"""Inert-by-default operator CLI. Only ``send`` can invoke Telegram."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
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
    analysis_send_eligible,
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
    for name in (
        "preview", "inspect", "inspect-markets", "events", "eligible", "delivery",
        "inspect-calibration-quality", "inspect-target-support",
        "inspect-extreme-probabilities", "inspect-calibration-trace",
        "inspect-live-input-shift", "inspect-market-actionability",
        "inspect-send-eligibility",
    ):
        item = sub.add_parser(name)
        item.add_argument("--database", type=Path, required=True)
        item.add_argument("--analysis-id", required=True)
        item.add_argument("--output", choices=("human", "json"), default="human")
    export = sub.add_parser("export-calibration-quality-evidence")
    export.add_argument("--database", type=Path, required=True)
    export.add_argument("--analysis-id", required=True)
    export.add_argument("--output-path", type=Path, required=True)
    export.add_argument("--source-database", type=Path)
    export.add_argument("--branch", default="UNKNOWN")
    send = sub.add_parser("send")
    send.add_argument("--database", type=Path, required=True)
    send.add_argument("--analysis-id", required=True)
    send.add_argument("--observation-id", required=True)
    send.add_argument("--publication-review-fingerprint", required=True)
    send.add_argument("--message-fingerprint", required=True)
    send.add_argument("--launch-authorization-id", required=True)
    send.add_argument("--reasoning-fingerprint", required=True)
    send.add_argument("--reasoning-audit-fingerprint", required=True)
    send.add_argument("--governance-evaluation-fingerprint", required=True)
    send.add_argument("--observation-governance-fingerprint", required=True)
    send.add_argument("--operator", required=True)
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
            "preview", "inspect", "inspect-markets", "events", "eligible", "delivery",
            "inspect-calibration-quality", "inspect-target-support",
            "inspect-extreme-probabilities", "inspect-calibration-trace",
            "inspect-live-input-shift", "inspect-market-actionability",
            "inspect-send-eligibility", "export-calibration-quality-evidence",
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
        result = json.loads(row["result_snapshot"])
        evidence = result.get("evidence") or {}
        quality = evidence.get("calibration_quality_report") or {}
        if args.command == "inspect-markets":
            value = [json.loads(item[0]) for item in repository.market_evaluations(args.analysis_id)]
        elif args.command == "inspect-calibration-quality":
            value = quality or {"status": "CALIBRATION_QUALITY_NOT_EVALUATED", "send_eligible": False}
        elif args.command == "inspect-target-support":
            value = quality.get("target_evidence", [])
        elif args.command == "inspect-extreme-probabilities":
            value = [item for item in quality.get("traces", []) if item.get("extreme_status") != "NOT_EXTREME"]
        elif args.command == "inspect-calibration-trace":
            value = quality.get("traces", [])
        elif args.command == "inspect-live-input-shift":
            value = quality.get("distribution_shift", {"status": "CALIBRATION_QUALITY_NOT_EVALUATED"})
        elif args.command == "inspect-market-actionability":
            value = [json.loads(item[0]) for item in repository.market_evaluations(args.analysis_id)]
        elif args.command == "inspect-send-eligibility":
            value = {
                "analysis_id": args.analysis_id,
                "send_eligible": analysis_send_eligible(row),
                "quality_status": quality.get("lab_outcome", "CALIBRATION_QUALITY_NOT_EVALUATED"),
                "reason_codes": quality.get("reason_codes", ["CALIBRATION_QUALITY_NOT_EVALUATED"]),
            }
        elif args.command == "export-calibration-quality-evidence":
            request = json.loads(row["request_snapshot"])
            markets = [
                json.loads(item[0])
                for item in repository.market_evaluations(args.analysis_id)
            ]
            counts = {}
            for name in (
                "real_match_lab_deliveries",
                "official_prediction_publication_events",
                "result_publications",
                "bankroll_accounts",
                "bankroll_transactions",
                "model_champion_generations",
            ):
                counts[name] = database.connection.execute(
                    f"SELECT COUNT(*) FROM {name}"
                ).fetchone()[0]
            source_hash = (
                _sha256_file(args.source_database)
                if args.source_database is not None else None
            )
            value = {
                "schema_version": "goalvision-calibration-quality-evidence-export-v1",
                "source_commit": request.get("source_commit"),
                "branch": args.branch,
                "analysis_id": args.analysis_id,
                "analysis_status": row["status"],
                "fixture": {
                    key: request.get(key)
                    for key in (
                        "match_id", "competition", "home_team", "away_team",
                        "kickoff_utc", "collected_at", "source_provider",
                        "source_event_id",
                    )
                },
                "quality": quality or {"status": "CALIBRATION_QUALITY_NOT_EVALUATED"},
                "markets": markets,
                "mathematical_ranking": [
                    item["market"]
                    for item in sorted(
                        (item for item in markets if item.get("mathematical_rank") is not None),
                        key=lambda item: item["mathematical_rank"],
                    )
                ],
                "actionable_result": row["selected_market"] or "NO_SELECTION",
                "send_eligible": analysis_send_eligible(row),
                "rejection_reasons": result.get("rejection_reasons", []),
                "safety": {
                    "telegram_calls": 0,
                    "telegram_sends": 0,
                    "delivery_records": counts["real_match_lab_deliveries"],
                    "official_publications": counts["official_prediction_publication_events"],
                    "official_result_publications": counts["result_publications"],
                    "official_bankroll_accounts": counts["bankroll_accounts"],
                    "official_bankroll_transactions": counts["bankroll_transactions"],
                    "production_activation_mutations": 0,
                    "isolated_generation_count": counts["model_champion_generations"],
                    "foreign_key_violations": len(database.connection.execute("PRAGMA foreign_key_check").fetchall()),
                    "source_database_sha256_before": source_hash,
                    "source_database_sha256_after": source_hash,
                    "isolated_database_sha256": _sha256_file(args.database),
                },
                "limitations": [
                    "Training and calibration evidence is controlled synthetic.",
                    "This does not establish real-world predictive accuracy.",
                    "The result is not betting advice.",
                    "No Lab or Official publication is authorized.",
                ],
            }
            from .fingerprint import fingerprint
            value["evidence_fingerprint"] = fingerprint(value)
            args.output_path.parent.mkdir(parents=True, exist_ok=True)
            args.output_path.write_text(_json_text(value) + "\n", encoding="utf-8")
            print(f"EXPORTED: {args.output_path} fingerprint={value['evidence_fingerprint']}")
            return 0
        elif args.command == "events":
            value = [json.loads(item[0]) for item in repository.stage_events(args.analysis_id)]
        elif args.command == "delivery":
            value = json.loads(canonical_json(repository.delivery_history(args.analysis_id)))
        elif args.command == "eligible":
            history = repository.delivery_history(args.analysis_id)
            eligible = analysis_send_eligible(row) and (
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
        from app.current_odds_forward_test.operations import validate_manual_send_authorization
        from app.current_odds_forward_test.repository import SQLiteForwardTestRepository
        authorization = validate_manual_send_authorization(
            SQLiteForwardTestRepository(database, migrate=False),
            observation_id=args.observation_id,
            review_fingerprint=args.publication_review_fingerprint,
            message_fingerprint=args.message_fingerprint,
            confirmation=args.confirmation,
            environment="LAB", chat_id=chat_id or "", bot=bot or "",
        )
        if authorization["status"] != "LAB_MANUAL_SEND_AUTHORIZED" or authorization["analysis_id"] != args.analysis_id:
            raise DeliveryConflictError("Forward-test publication review did not authorize this exact message.")
        from app.lab_launch_readiness import LabLaunchService
        launch = LabLaunchService(database.connection).validate_send(
            args.launch_authorization_id,
            observation_id=args.observation_id,
            confirmation=args.confirmation,
            environment="LAB", chat_id=chat_id or "", bot=bot or "",
            fingerprints={
                "preview": args.message_fingerprint,
                "reasoning": args.reasoning_fingerprint,
                "reasoning_audit": args.reasoning_audit_fingerprint,
                "governance_evaluation": args.governance_evaluation_fingerprint,
                "observation_governance": args.observation_governance_fingerprint,
                "publication_review": args.publication_review_fingerprint,
            },
            now=datetime.now(timezone.utc),
        )
        if launch["status"] != "LAB_MANUAL_SEND_AUTHORIZED":
            raise DeliveryConflictError("An active first-LAB launch authorization did not authorize this exact message.")
        result = asyncio.run(service.send(
            args.analysis_id, args.confirmation, token=token,
            configured_chat_id=chat_id, configured_bot=bot,
            transport=TelegramService(token),
        ))
        if result.status.value == "SENT":
            LabLaunchService(database.connection).consume(
                args.launch_authorization_id, args.observation_id, args.operator,
                occurred_at_utc=datetime.now(timezone.utc), send_succeeded=True,
            )
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
        _human_print(record.message_html)
    else:
        print("Rejection reasons: " + ", ".join(record.rejection_reasons or ("NO_SELECTION",)))
    print(f"\nSend confirmation required: {SEND_CONFIRMATION}")


def _print_value(value, output):
    if output == "json":
        print(_json_text(value))
    else:
        if isinstance(value, dict):
            for key, item in value.items():
                _human_print(f"{key}: {item}")
        else:
            print(json.dumps(value, indent=2, ensure_ascii=True))


def _human_print(value: object) -> None:
    """Render arbitrary persisted Unicode safely on the active terminal."""
    text = str(value)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe = text.encode(encoding, errors="backslashreplace").decode(encoding)
    print(safe)


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
