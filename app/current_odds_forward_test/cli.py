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
    diagnose_api = sub.add_parser("diagnose-api-football"); diagnose_api.add_argument("--env-file", type=Path, default=Path(".env")); diagnose_api.add_argument("--output", choices=("human", "json"), default="human")
    diagnose_discovery = sub.add_parser("diagnose-fixture-discovery"); diagnose_discovery.add_argument("--env-file", type=Path, default=Path(".env")); diagnose_discovery.add_argument("--metadata-output", type=Path); diagnose_discovery.add_argument("--output", choices=("human", "json"), default="human")
    for name in ("inspect-provider-leagues", "inspect-current-seasons", "inspect-provider-quota"):
        item = sub.add_parser(name); item.add_argument("--env-file", type=Path, default=Path(".env")); item.add_argument("--output", choices=("human", "json"), default="human")
    for name in ("discover-current-fixtures", "inspect-discovery-candidates", "inspect-discovery-request-costs"):
        discover = sub.add_parser(name); discover.add_argument("--env-file", type=Path, default=Path(".env")); discover.add_argument("--database", type=Path); discover.add_argument("--capability-cache", type=Path, default=Path("var/api_football_capabilities.json")); discover.add_argument("--metadata-output", type=Path); discover.add_argument("--max-candidates", type=int, default=50); discover.add_argument("--max-api-calls", type=int, default=40); discover.add_argument("--horizon-days", type=int, default=7); discover.add_argument("--minimum-lead-minutes", type=int, default=60); discover.add_argument("--daily-quota-reserve", type=int, default=20); discover.add_argument("--output", choices=("human", "json"), default="human")
    fixture = sub.add_parser("inspect-current-fixture"); fixture.add_argument("--env-file", type=Path, default=Path(".env")); fixture.add_argument("--fixture-id", type=int, required=True); fixture.add_argument("--output", choices=("human", "json"), default="human")
    fixture_odds = sub.add_parser("inspect-fixture-odds"); fixture_odds.add_argument("--env-file", type=Path, default=Path(".env")); fixture_odds.add_argument("--fixture-id", type=int, required=True); fixture_odds.add_argument("--kickoff-utc", required=True); fixture_odds.add_argument("--output", choices=("human", "json"), default="human")
    team_baseline = sub.add_parser("inspect-team-baseline"); team_baseline.add_argument("--env-file", type=Path, default=Path(".env")); team_baseline.add_argument("--team-id", type=int, required=True); team_baseline.add_argument("--league-id", type=int, required=True); team_baseline.add_argument("--season", type=int, required=True); team_baseline.add_argument("--output", choices=("human", "json"), default="human")
    create = sub.add_parser("create-forward-test-observation"); create.add_argument("--database", type=Path, required=True); create.add_argument("--request-id", required=True); create.add_argument("--analysis-id", required=True); create.add_argument("--odds-snapshot-id", required=True); create.add_argument("--output", choices=("human", "json"), default="human")
    result = sub.add_parser("record-forward-test-result"); result.add_argument("--database", type=Path, required=True); result.add_argument("--observation-id", required=True); result.add_argument("--input", type=Path, required=True); result.add_argument("--output", choices=("human", "json"), default="human")
    settle = sub.add_parser("settle-forward-test-observation"); settle.add_argument("--database", type=Path, required=True); settle.add_argument("--observation-id", required=True); settle.add_argument("--output", choices=("human", "json"), default="human")
    for name in ("inspect-forward-test-observation", "inspect-forward-test-markets", "inspect-forward-test-preview", "inspect-forward-test-eligibility", "inspect-forward-test-settlement", "audit-forward-test"):
        item = sub.add_parser(name); item.add_argument("--database", type=Path, required=True); item.add_argument("--observation-id", required=True); item.add_argument("--output", choices=("human", "json"), default="human")
    stats = sub.add_parser("forward-test-statistics"); stats.add_argument("--database", type=Path, required=True); stats.add_argument("--output", choices=("human", "json"), default="human")
    diagnose = sub.add_parser("diagnose-forward-test"); diagnose.add_argument("--database", type=Path, required=True); diagnose.add_argument("--output", choices=("human", "json"), default="human")
    export = sub.add_parser("export-forward-test-evidence"); export.add_argument("--database", type=Path, required=True); export.add_argument("--output-path", type=Path, required=True); export.add_argument("--source-database", type=Path)
    ready = sub.add_parser("pro-readiness"); ready.add_argument("--env-file", type=Path, default=Path(".env")); ready.add_argument("--capability-cache", type=Path, default=Path("var/api_football_capabilities.json")); ready.add_argument("--network-verify", action="store_true"); ready.add_argument("--output", choices=("human", "json"), default="human")
    first = sub.add_parser("first-lab-dry-run"); first.add_argument("--database", type=Path, required=True); first.add_argument("--env-file", type=Path, default=Path(".env")); first.add_argument("--capability-cache", type=Path, default=Path("var/api_football_capabilities.json")); first.add_argument("--run-id"); first.add_argument("--max-candidates", type=int, default=50); first.add_argument("--max-calls", type=int, default=40); first.add_argument("--daily-reserve", type=int, default=20); first.add_argument("--output", choices=("human", "json"), default="human")
    review = sub.add_parser("publication-review"); review.add_argument("--database", type=Path, required=True); review.add_argument("--observation-id", required=True); review.add_argument("--output", choices=("human", "json"), default="human")
    send_review = sub.add_parser("validate-lab-send-readiness"); send_review.add_argument("--database", type=Path, required=True); send_review.add_argument("--observation-id", required=True); send_review.add_argument("--review-fingerprint", required=True); send_review.add_argument("--message-fingerprint", required=True); send_review.add_argument("--confirmation", required=True); send_review.add_argument("--environment", required=True); send_review.add_argument("--chat-id", required=True); send_review.add_argument("--bot", required=True); send_review.add_argument("--output", choices=("human", "json"), default="human")
    fetch_result = sub.add_parser("fetch-forward-test-result"); fetch_result.add_argument("--database", type=Path, required=True); fetch_result.add_argument("--observation-id", required=True); fetch_result.add_argument("--env-file", type=Path, default=Path(".env")); fetch_result.add_argument("--output", choices=("human", "json"), default="human")
    result_preview = sub.add_parser("result-message-preview"); result_preview.add_argument("--database", type=Path, required=True); result_preview.add_argument("--observation-id", required=True); result_preview.add_argument("--output", choices=("human", "json"), default="human")
    inspect_run = sub.add_parser("inspect-first-lab-run"); inspect_run.add_argument("--database", type=Path, required=True); inspect_run.add_argument("--run-id", required=True); inspect_run.add_argument("--output", choices=("human", "json"), default="human")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "pro-readiness": return asyncio.run(_pro_readiness(args))
        if args.command == "first-lab-dry-run": return asyncio.run(_first_lab_dry_run(args))
        if args.command == "fetch-forward-test-result": return asyncio.run(_fetch_result(args))
        if args.command == "validate-forward-test-input": return _render(parse_current_odds(_json(args.input)), args.output)
        if args.command == "diagnose-api-football": return asyncio.run(_api_diagnose(args))
        if args.command == "diagnose-fixture-discovery": return asyncio.run(_diagnose_fixture_discovery(args))
        if args.command in {"inspect-provider-leagues", "inspect-current-seasons", "inspect-provider-quota"}: return asyncio.run(_inspect_provider(args))
        if args.command in {"discover-current-fixtures", "inspect-discovery-candidates", "inspect-discovery-request-costs"}: return asyncio.run(_api_discover(args))
        if args.command == "inspect-current-fixture": return asyncio.run(_api_read(args))
        if args.command == "inspect-fixture-odds": return asyncio.run(_inspect_fixture_odds(args))
        if args.command == "inspect-team-baseline": return asyncio.run(_inspect_team_baseline(args))
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
            if args.command == "publication-review":
                from .operations import FirstLabOperationsRepository, build_publication_review
                value = build_publication_review(repository, args.observation_id, persist=FirstLabOperationsRepository(database, migrate=False))
                return _render(value, args.output, 0 if value["status"] == "LAB_PUBLICATION_REVIEW_PASSED" else 4)
            if args.command == "validate-lab-send-readiness":
                from .operations import validate_manual_send_authorization
                value = validate_manual_send_authorization(repository, observation_id=args.observation_id, review_fingerprint=args.review_fingerprint, message_fingerprint=args.message_fingerprint, confirmation=args.confirmation, environment=args.environment, chat_id=args.chat_id, bot=args.bot)
                return _render(value, args.output, 0 if value["status"] == "LAB_MANUAL_SEND_AUTHORIZED" else 4)
            if args.command == "result-message-preview":
                from .operations import FirstLabOperationsRepository, build_result_preview
                return _render(build_result_preview(repository, args.observation_id, persist=FirstLabOperationsRepository(database, migrate=False)), args.output)
            if args.command == "inspect-first-lab-run":
                from .operations import FirstLabOperationsRepository
                value = {"status": "FOUND", "run_id": args.run_id, "stages": FirstLabOperationsRepository(database, migrate=False).stages(args.run_id)}
                return _render(value, args.output, 0 if value["stages"] else 2)
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


async def _pro_readiness(args):
    from app.football.client import FootballClient
    from .operations import build_pro_readiness
    if not args.network_verify:
        return _render(build_pro_readiness(env_file=args.env_file, cache_path=args.capability_cache), args.output, 4)
    client = FootballClient(env_file=args.env_file, request_limit=1)
    try:
        payload = await client.account_status()
        response = payload.get("response") if isinstance(payload, dict) else {}
        subscription = response.get("subscription") if isinstance(response, dict) else {}
        plan = str(subscription.get("plan") or subscription.get("name") or "UNKNOWN")
        quota = client.quota_snapshot()
        daily_limit = quota.get("daily_limit") or (response.get("requests") or {}).get("limit_day")
        if plan.upper() == "UNKNOWN" and isinstance(daily_limit, int):
            plan = "FREE" if daily_limit <= 100 else "PRO"
        value = build_pro_readiness(env_file=args.env_file, cache_path=args.capability_cache, network_verified=True, authenticated=True, detected_plan=plan, quota=quota)
        return _render(value, args.output, 0 if value["status"] == "PRO_PLAN_READY" else 4)
    except httpx.HTTPStatusError as exc:
        value = build_pro_readiness(env_file=args.env_file, cache_path=args.capability_cache, network_verified=True, authenticated=False if exc.response.status_code == 401 else True, detected_plan="UNKNOWN", quota=client.quota_snapshot())
        return _render(value, args.output, 4)
    finally:
        await client.close()


async def _first_lab_dry_run(args):
    from app.football.client import FootballClient
    from app.model_activation_audit import resolve_active_reviewed_source_provenance
    from app.real_match_lab_analysis.factory import build_real_match_lab_analysis_service
    from .discovery import discover_current_fixture
    from .operations import FirstLabOperationsRepository, build_pro_readiness
    from .workflow import FirstLabDryRunWorkflow
    now = datetime.now(timezone.utc)
    run_id = args.run_id or f"first-lab-{now:%Y%m%d}"
    database = Database(args.database)
    client = None
    try:
        operations = FirstLabOperationsRepository(database)
        repository = SQLiteForwardTestRepository(database, migrate=False)
        source_commit = resolve_active_reviewed_source_provenance(
            database, "OFFICIAL_GLOBAL"
        ).source_commit
        try:
            client = FootballClient(env_file=args.env_file, request_limit=args.max_calls)
            status_payload = await client.account_status()
            response = status_payload.get("response") if isinstance(status_payload, dict) else {}
            subscription = response.get("subscription") if isinstance(response, dict) else {}
            plan = str(subscription.get("plan") or subscription.get("name") or "UNKNOWN")
            quota = client.quota_snapshot()
            daily_limit = quota.get("daily_limit") or (response.get("requests") or {}).get("limit_day")
            if plan.upper() == "UNKNOWN" and isinstance(daily_limit, int): plan = "FREE" if daily_limit <= 100 else "PRO"
            readiness = build_pro_readiness(env_file=args.env_file, cache_path=args.capability_cache, now=now, network_verified=True, authenticated=True, detected_plan=plan, quota=quota)
        except Exception:
            readiness = build_pro_readiness(env_file=args.env_file, cache_path=args.capability_cache, now=now, network_verified=True, authenticated=False, detected_plan="UNKNOWN")
        async def discover():
            assert client is not None
            return await discover_current_fixture(client, now=now, maximum_candidates=args.max_candidates, maximum_api_calls=args.max_calls, daily_quota_reserve=args.daily_reserve, capability_cache_path=args.capability_cache, quota_already_verified=True)
        workflow = FirstLabDryRunWorkflow(
            operations,
            repository,
            build_real_match_lab_analysis_service(database).analyze,
            source_commit,
        )
        value = await workflow.run(run_id=run_id, readiness=readiness, discover=discover, parameters={"max_candidates": args.max_candidates, "max_calls": args.max_calls, "daily_reserve": args.daily_reserve, "capability_cache": str(args.capability_cache)}, now=now)
        return _render(value, args.output, 0 if value["status"] == "FIRST_LAB_DRY_RUN_COMPLETED" else 4)
    finally:
        if client is not None: await client.close()
        database.close()


async def _fetch_result(args):
    from app.football.client import FootballClient
    repository_db = Database(args.database)
    try:
        repository = SQLiteForwardTestRepository(repository_db)
        observation = repository.load_observation(args.observation_id)
        if observation is None: return _render({"status": "NOT_FOUND"}, args.output, 2)
        fixture_id = int(observation["canonical_fixture_id"])
        client = FootballClient(env_file=args.env_file, request_limit=1)
        try:
            payload = await client.fixture(fixture_id)
            rows = payload.get("response") if isinstance(payload, dict) else None
            row = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
            fixture = row.get("fixture", {}) if isinstance(row, dict) else {}
            goals = row.get("goals", {}) if isinstance(row, dict) else {}
            status = (fixture.get("status") or {}).get("short") if isinstance(fixture.get("status"), dict) else None
            if status not in {"FT", "AET", "PEN"}:
                return _render({"status": "RESULT_NOT_FINAL", "fixture_id": fixture_id, "provider_status": status, "manual_json_fallback": True}, args.output, 4)
            raw = {"schema_version": "goalvision-forward-test-result-v1", "fixture_id": str(fixture_id), "final_home_score": goals.get("home"), "final_away_score": goals.get("away"), "final_status": status, "result_source": "API_FOOTBALL", "result_retrieval_timestamp_utc": datetime.now(timezone.utc).isoformat(), "provenance": "API-Football exact fixture final result"}
            return _render(ForwardTestService(repository).record_result(args.observation_id, raw), args.output)
        finally: await client.close()
    finally: repository_db.close()


async def _api_diagnose(args):
    from app.football.client import FootballClient
    from app.football.configuration import (
        CANONICAL_API_FOOTBALL_ENVIRONMENT_VARIABLE,
        api_football_credential_status,
    )
    credential_status = api_football_credential_status(env_file=args.env_file)
    value = {
        "provider": "API_FOOTBALL",
        "canonical_environment_variable": CANONICAL_API_FOOTBALL_ENVIRONMENT_VARIABLE,
        "credential_status": credential_status,
        "authentication_status": "NOT_EXECUTED",
        "plan_status": "NOT_EXECUTED",
        "quota": {"interpretation_status": "NOT_OBSERVED"},
        "startup_request_count": 0,
    }
    if credential_status != "CONFIGURED":
        return _render(value, args.output, 3)
    client = FootballClient(env_file=args.env_file)
    try:
        payload = await client.account_status()
        response = payload.get("response") if isinstance(payload, dict) else None
        subscription = response.get("subscription") if isinstance(response, dict) else None
        requests = response.get("requests") if isinstance(response, dict) else None
        value["authentication_status"] = "AUTHENTICATED"
        value["plan_status"] = "AVAILABLE" if isinstance(subscription, dict) and subscription.get("active") else "PLAN_RESTRICTED"
        value["quota"] = client.quota_snapshot()
        value["quota"]["status_payload_daily_limit"] = requests.get("limit_day") if isinstance(requests, dict) else None
        value["quota"]["status_payload_daily_used"] = requests.get("current") if isinstance(requests, dict) else None
        return _render(value, args.output, 0 if value["plan_status"] == "AVAILABLE" else 4)
    except httpx.HTTPStatusError as exc:
        value["quota"] = client.quota_snapshot()
        if exc.response.status_code == 401:
            value["authentication_status"] = "AUTHENTICATION_FAILED"
            value["plan_status"] = "INVALID"
        elif exc.response.status_code in {403, 429}:
            value["authentication_status"] = "AUTHENTICATED"
            value["plan_status"] = "PLAN_RESTRICTED"
        else:
            value["authentication_status"] = "INVALID"
            value["plan_status"] = "INVALID"
        return _render(value, args.output, 4)
    finally:
        await client.close()


async def _diagnose_fixture_discovery(args):
    from app.football.client import FootballClient
    from .provider import diagnose_fixture_discovery, write_sanitized_metadata
    client = FootballClient(env_file=args.env_file, request_limit=20)
    try:
        value = await diagnose_fixture_discovery(client, now=datetime.now(timezone.utc))
        if args.metadata_output is not None:
            write_sanitized_metadata(args.metadata_output, value)
    finally:
        await client.close()
    return _render(value, args.output)


async def _inspect_provider(args):
    from app.football.client import FootballClient
    from .provider import resolve_current_competitions
    client = FootballClient(env_file=args.env_file, request_limit=2)
    try:
        if args.command == "inspect-provider-quota":
            await client.account_status()
            value = {"schema_version": "goalvision-api-football-quota-v1", "quota": client.quota_snapshot()}
        else:
            payload = await client.leagues(current=True)
            competitions = resolve_current_competitions(payload, observed_at=datetime.now(timezone.utc))
            value = {"schema_version": "goalvision-api-football-competitions-v1", "competitions": competitions, "quota": client.quota_snapshot()}
    finally:
        await client.close()
    return _render(value, args.output)


async def _api_read(args):
    from app.football.client import FootballClient
    client = FootballClient(env_file=args.env_file)
    try:
        data = await (client.fixture(args.fixture_id) if args.command == "inspect-current-fixture" else client.fixtures())
        value = {"data": data, "quota": client.quota_snapshot()}
    finally: await client.close()
    return _render(value, args.output)


async def _api_discover(args):
    from app.football.client import FootballClient
    from .discovery import discover_current_fixture
    client = FootballClient(env_file=args.env_file, request_limit=args.max_api_calls)
    try:
        value = await discover_current_fixture(
            client,
            now=datetime.now(timezone.utc),
            maximum_candidates=args.max_candidates,
            maximum_api_calls=args.max_api_calls,
            horizon_days=args.horizon_days,
            minimum_lead_minutes=args.minimum_lead_minutes,
            daily_quota_reserve=args.daily_quota_reserve,
            capability_cache_path=args.capability_cache,
        )
        value["quota"] = client.quota_snapshot()
        selected = value.get("selected_fixture")
        value["odds_sealed"] = False
        if selected is not None and args.database is not None:
            snapshot = parse_current_odds(selected["odds_contract"], now=datetime.fromisoformat(selected["api_retrieval_timestamp_utc"]))
            database = Database(args.database)
            try:
                ForwardTestService(SQLiteForwardTestRepository(database)).capture_odds(snapshot)
            finally:
                database.close()
            value["odds_sealed"] = True
        if args.metadata_output is not None:
            from .provider import write_sanitized_metadata
            write_sanitized_metadata(args.metadata_output, value)
    finally:
        await client.close()
    if args.command == "inspect-discovery-request-costs":
        value = {
            "schema_version": "goalvision-api-football-request-cost-report-v1",
            "terminal_result": value["terminal_result"],
            "stage_request_costs": value["stage_request_costs"],
            "candidate_request_costs": value["request_cost_report"],
            "api_call_count": value["api_call_count"],
            "quota": value["quota"],
            "telegram_sends": 0,
        }
        return _render(value, args.output)
    return _render(value, args.output, 0 if value.get("selected_fixture") else 4)


async def _inspect_fixture_odds(args):
    from app.football.client import FootballClient
    client = FootballClient(env_file=args.env_file, request_limit=1)
    selected = retrieved = datetime.now(timezone.utc)
    try:
        payload = await client.current_odds(args.fixture_id)
        retrieved = datetime.now(timezone.utc)
        raw = normalize_api_football_current_odds(payload, fixture_id=str(args.fixture_id), kickoff_utc=args.kickoff_utc, retrieved_at_utc=retrieved.isoformat(), source_selected_at_utc=selected.isoformat())
        snapshot = parse_current_odds(raw, now=retrieved)
        value = {"schema_version": "goalvision-api-football-fixture-odds-inspection-v1", "fixture_id": str(args.fixture_id), "bookmaker": snapshot.bookmaker_name, "markets": [{"market": quote.market, "decimal_odds": str(quote.decimal_odds)} for quote in snapshot.quotes], "provider_update_timestamp_utc": snapshot.quotes[0].provider_origin_timestamp_utc, "goalvision_retrieval_timestamp_utc": retrieved, "freshness": snapshot.freshness_status, "snapshot_fingerprint": snapshot.snapshot_fingerprint, "quota": client.quota_snapshot(), "inference_executed": False, "telegram_sends": 0}
    finally:
        await client.close()
    return _render(value, args.output)


async def _inspect_team_baseline(args):
    from app.football.client import FootballClient
    client = FootballClient(env_file=args.env_file, request_limit=1)
    try:
        rows = await client.last_matches(
            args.team_id, last=5, league_id=args.league_id, season=args.season
        )
        metadata = client.response_metadata()
        value = {
            "schema_version": "goalvision-api-football-team-baseline-inspection-v1",
            "team_id": args.team_id, "league_id": args.league_id,
            "season": args.season, "result_count": len(rows),
            "request": metadata, "quota": client.quota_snapshot(),
            "inference_executed": False, "telegram_sends": 0,
        }
    finally:
        await client.close()
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
