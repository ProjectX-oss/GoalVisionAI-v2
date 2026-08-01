"""Inert operator CLI; every command is read-only or isolated forward-test storage."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import httpx
from datetime import datetime, timezone
from pathlib import Path

from app.database import Database, MigrationManager
from app.real_match_lab_analysis.fingerprint import canonical_json

from .audit import audit_observation
from .input import CurrentOddsValidationError, normalize_api_football_current_odds, parse_current_odds
from .repository import ForwardTestConflictError, SQLiteForwardTestRepository, decode
from .service import ForwardTestService, ForwardTestValidationError
from .statistics import build_statistics


def build_parser():
    parser = argparse.ArgumentParser(prog="goalvision-forward-test", description="Manual current-odds and Lab-only forward-test evidence.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate-forward-test-input",):
        item = sub.add_parser(name); item.add_argument("--input", type=Path, required=True); item.add_argument("--output", choices=("human", "json"), default="human")
    capture = sub.add_parser("capture-current-odds"); capture.add_argument("--database", type=Path, required=True); capture.add_argument("--input", type=Path, required=True); capture.add_argument("--output", choices=("human", "json"), default="human")
    api = sub.add_parser("capture-api-football-odds"); api.add_argument("--database", type=Path, required=True); api.add_argument("--fixture-id", type=int, required=True); api.add_argument("--kickoff-utc", required=True); api.add_argument("--source-selected-at-utc", required=True); api.add_argument("--output", choices=("human", "json"), default="human")
    discover = sub.add_parser("discover-current-fixtures"); discover.add_argument("--output", choices=("human", "json"), default="human")
    fixture = sub.add_parser("inspect-current-fixture"); fixture.add_argument("--fixture-id", type=int, required=True); fixture.add_argument("--output", choices=("human", "json"), default="human")
    create = sub.add_parser("create-forward-test-observation"); create.add_argument("--database", type=Path, required=True); create.add_argument("--request-id", required=True); create.add_argument("--analysis-id", required=True); create.add_argument("--odds-snapshot-id", required=True); create.add_argument("--output", choices=("human", "json"), default="human")
    result = sub.add_parser("record-forward-test-result"); result.add_argument("--database", type=Path, required=True); result.add_argument("--observation-id", required=True); result.add_argument("--input", type=Path, required=True); result.add_argument("--output", choices=("human", "json"), default="human")
    settle = sub.add_parser("settle-forward-test-observation"); settle.add_argument("--database", type=Path, required=True); settle.add_argument("--observation-id", required=True); settle.add_argument("--output", choices=("human", "json"), default="human")
    for name in ("inspect-forward-test-observation", "inspect-forward-test-markets", "inspect-forward-test-preview", "inspect-forward-test-eligibility", "inspect-forward-test-settlement", "audit-forward-test"):
        item = sub.add_parser(name); item.add_argument("--database", type=Path, required=True); item.add_argument("--observation-id", required=True); item.add_argument("--output", choices=("human", "json"), default="human")
    stats = sub.add_parser("forward-test-statistics"); stats.add_argument("--database", type=Path, required=True); stats.add_argument("--output", choices=("human", "json"), default="human")
    diagnose = sub.add_parser("diagnose-forward-test"); diagnose.add_argument("--database", type=Path, required=True); diagnose.add_argument("--output", choices=("human", "json"), default="human")
    export = sub.add_parser("export-forward-test-evidence"); export.add_argument("--database", type=Path, required=True); export.add_argument("--output-path", type=Path, required=True); export.add_argument("--source-database", type=Path)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-forward-test-input": return _render(parse_current_odds(_json(args.input)), args.output)
        if args.command in {"discover-current-fixtures", "inspect-current-fixture"}: return asyncio.run(_api_read(args))
        if args.command == "capture-api-football-odds": return asyncio.run(_api_capture(args))
        database = Database(args.database)
        try:
            repository = SQLiteForwardTestRepository(database); service = ForwardTestService(repository)
            if args.command == "capture-current-odds":
                raw = _json(args.input)
                try: value = parse_current_odds(raw)
                except CurrentOddsValidationError as exc:
                    from app.real_match_lab_analysis.fingerprint import fingerprint
                    repository.append_rejection(fingerprint(raw), "ODDS_CAPTURE", str(exc), datetime.now(timezone.utc).isoformat()); raise
                service.capture_odds(value); return _render(value, args.output)
            if args.command == "create-forward-test-observation": return _render(service.create_observation(args.request_id, args.analysis_id, args.odds_snapshot_id), args.output)
            if args.command == "record-forward-test-result": return _render(service.record_result(args.observation_id, _json(args.input)), args.output)
            if args.command == "settle-forward-test-observation": return _render(service.settle(args.observation_id), args.output)
            if args.command == "forward-test-statistics": return _render(build_statistics(repository), args.output)
            if args.command == "audit-forward-test": return _render(audit_observation(repository, args.observation_id), args.output)
            if args.command == "diagnose-forward-test":
                version = database.connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                value = {"status": "HEALTHY", "schema_version": version, "evidence_tier": "FORWARD_TEST_REAL_TIME", "startup_execution": False, "scheduling_enabled": False, "telegram_transport_constructed": False, "foreign_key_violations": len(database.connection.execute("PRAGMA foreign_key_check").fetchall())}
                return _render(value, args.output)
            if args.command == "export-forward-test-evidence":
                from .evidence import build_foundation_evidence
                source_hash = _sha256(args.source_database) if args.source_database else "NOT_SUPPLIED"
                value = build_foundation_evidence(source_hash_before=source_hash, source_hash_after=source_hash, isolated_database_hash=_sha256(args.database))
                args.output_path.write_text(canonical_json(value) + "\n", encoding="utf-8")
                print(f"EXPORTED: {args.output_path} fingerprint={value['evidence_fingerprint']}"); return 0
            row = repository.load_observation(args.observation_id)
            if row is None: return _render({"status": "NOT_FOUND"}, args.output, 2)
            value = decode(row, "observation_json")
            if args.command == "inspect-forward-test-markets": value = value["market_evaluations"]
            elif args.command == "inspect-forward-test-preview": value = {"observation_id": args.observation_id, "preview": value["message_preview"], "message_fingerprint": value["message_fingerprint"]}
            elif args.command == "inspect-forward-test-eligibility": value = {key: value[key] for key in ("analysis_completed", "actionable", "forward_test_recorded", "preview_available", "lab_send_eligible", "official_eligible", "rejection_reasons")}
            elif args.command == "inspect-forward-test-settlement": value = decode(repository.load_settlement(args.observation_id), "settlement_json") or {"status": "UNSETTLED"}
            return _render(value, args.output)
        finally: database.close()
    except (CurrentOddsValidationError, ForwardTestValidationError, ForwardTestConflictError, OSError, json.JSONDecodeError) as exc:
        print(f"REJECTED: {exc}", file=sys.stderr); return 3
    except (RuntimeError, httpx.HTTPError):
        print("REJECTED: API_FOOTBALL_UNAVAILABLE", file=sys.stderr); return 3


async def _api_read(args):
    from app.football.client import FootballClient
    client = FootballClient()
    try:
        data = await (client.fixture(args.fixture_id) if args.command == "inspect-current-fixture" else client.fixtures())
        value = {"data": data, "quota": client.quota_snapshot()}
    finally: await client.close()
    return _render(value, args.output)


async def _api_capture(args):
    from app.football.client import FootballClient
    retrieved = datetime.now(timezone.utc).isoformat(); client = FootballClient()
    try: payload = await client.current_odds(args.fixture_id)
    finally: await client.close()
    raw = normalize_api_football_current_odds(payload, fixture_id=str(args.fixture_id), kickoff_utc=args.kickoff_utc, retrieved_at_utc=retrieved, source_selected_at_utc=args.source_selected_at_utc)
    value = parse_current_odds(raw, now=datetime.fromisoformat(retrieved)); database = Database(args.database)
    try: ForwardTestService(SQLiteForwardTestRepository(database)).capture_odds(value)
    finally: database.close()
    return _render(value, args.output)


def _json(path): return json.loads(path.read_text(encoding="utf-8"))
def _sha256(path):
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()
def _render(value, output, code=0):
    document = json.loads(canonical_json(value))
    if output == "json": print(json.dumps(document, sort_keys=True, separators=(",", ":")))
    else: print(f"status: {document.get('status', 'OK') if isinstance(document, dict) else 'OK'}\n" + json.dumps(document, indent=2, sort_keys=True))
    return code
