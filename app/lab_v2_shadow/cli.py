"""Manual-only LAB_V2_SHADOW commands; no Telegram option exists."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.football.client import FootballClient
from app.real_match_lab_analysis.fingerprint import canonical_json

from .audit import audit_recent_lab, settled_loss_postmortems
from .repository import ShadowEvidenceRepository
from .runner import LabV2ShadowRunner


async def _rehearse(args: argparse.Namespace) -> dict[str, object]:
    client = FootballClient(request_limit=args.max_calls)
    repository = ShadowEvidenceRepository(args.shadow_database)
    try:
        runner = LabV2ShadowRunner(
            client, repository, capability_cache_path=args.capability_cache,
            analysis_path=args.analysis_database, maximum_calls=args.max_calls,
        )
        return await runner.run(now=datetime.now(timezone.utc), horizon_days=args.horizon_days)
    finally:
        await client.close(); repository.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--ledger", type=Path, default=Path("var/lab_combo/ledger.db"))
    audit.add_argument("--analysis-database", type=Path, default=Path("var/lab_combo/analysis.db"))
    rehearse = sub.add_parser("rehearse")
    rehearse.add_argument("--shadow-database", type=Path, default=Path("var/lab_v2/shadow.db"))
    rehearse.add_argument("--analysis-database", type=Path, default=Path("var/lab_combo/analysis.db"))
    rehearse.add_argument("--capability-cache", type=Path, default=Path("var/lab_v2/capabilities.json"))
    rehearse.add_argument("--horizon-days", type=int, default=3)
    rehearse.add_argument("--max-calls", type=int, default=40)
    args = parser.parse_args(argv)
    if args.command == "audit":
        value = {
            "bottleneck_audit": audit_recent_lab(args.ledger, args.analysis_database),
            "settled_loss_postmortems": settled_loss_postmortems(args.ledger, args.analysis_database),
        }
    else:
        value = asyncio.run(_rehearse(args))
    print(canonical_json(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
