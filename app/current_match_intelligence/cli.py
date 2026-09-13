"""One-fixture diagnostic CLI; it never runs inference or Telegram."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.database import Database
from app.football.client import FootballClient

from .canonical import canonical_json
from .features import future_feature_vector
from .models import CurrentMatchIntelligenceSnapshot
from .policy import IntelligenceBudgetPolicy
from .provider import ApiFootballCurrentMatchProvider
from .repository import SQLiteCurrentMatchIntelligenceRepository
from .service import CurrentMatchIntelligenceService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="goalvision-current-match-intelligence",
        description="Collect or inspect one immutable pre-match intelligence snapshot.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--fixture-id", type=int, required=True)
    collect.add_argument("--database", type=Path, required=True)
    collect.add_argument("--env-file", type=Path, default=Path(".env"))
    collect.add_argument("--max-api-calls", type=int, default=40)
    collect.add_argument("--output", choices=("human", "json"), default="human")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--snapshot-id", required=True)
    inspect.add_argument("--database", type=Path, required=True)
    inspect.add_argument("--output", choices=("human", "json"), default="human")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "collect":
            return asyncio.run(_collect(args))
        database = Database(args.database)
        try:
            snapshot = SQLiteCurrentMatchIntelligenceRepository(database).load(args.snapshot_id)
            if snapshot is None:
                return _render({"status": "NOT_FOUND", "snapshot_id": args.snapshot_id}, args.output, 2)
            return _render(_diagnostic(snapshot), args.output)
        finally:
            database.close()
    except (ValueError, RuntimeError) as exc:
        return _render({"status": "FAILED", "reason": str(exc)}, getattr(args, "output", "human"), 4)


async def _collect(args) -> int:
    database = Database(args.database)
    client = FootballClient(env_file=args.env_file, request_limit=args.max_api_calls)
    try:
        repository = SQLiteCurrentMatchIntelligenceRepository(database)
        service = CurrentMatchIntelligenceService(
            repository, ApiFootballCurrentMatchProvider(client),
            budget=IntelligenceBudgetPolicy(maximum_api_calls=args.max_api_calls),
        )
        result = await service.collect(args.fixture_id, evaluated_at=datetime.now(timezone.utc))
        return _render(_diagnostic(result.snapshot), args.output)
    finally:
        await client.close()
        database.close()


def _diagnostic(snapshot: CurrentMatchIntelligenceSnapshot) -> dict[str, object]:
    fields = {item.name: item.value for item in snapshot.fields}
    fixture = {key: value for key, value in fields.items()
               if key.startswith("fixture.") or key.startswith("competition.")
               or key in {"home.team_id", "home.team_name", "away.team_id", "away.team_name"}}
    provenance = {
        item.name: [asdict(value) for value in item.provenance]
        for item in snapshot.fields
    }
    return {
        "schema_version": snapshot.schema_version,
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_version": snapshot.version,
        "content_fingerprint": snapshot.content_fingerprint,
        "fixture": fixture,
        "retrieved_context": fields,
        "missing_data": snapshot.missing_data,
        "freshness": [asdict(item) for item in snapshot.freshness],
        "api_calls": [asdict(item) for item in snapshot.api_calls],
        "normalized_features": asdict(future_feature_vector(snapshot)),
        "blockers": snapshot.blockers,
        "provenance": provenance,
        "inference_executed": False,
        "telegram_sends": 0,
        "official_state_mutations": 0,
    }


def _render(value: object, output: str, code: int = 0) -> int:
    if output == "json":
        print(canonical_json(value))
    else:
        data = json.loads(canonical_json(value))
        print(f"status: {data.get('status', 'AVAILABLE')}")
        for key in ("snapshot_id", "snapshot_version", "fixture", "missing_data",
                    "freshness", "api_calls", "normalized_features", "blockers", "provenance"):
            if key in data:
                print(f"{key}: {json.dumps(data[key], ensure_ascii=False, sort_keys=True)}")
    return code
