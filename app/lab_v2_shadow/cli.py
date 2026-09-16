"""Manual Lab V2 audit, no-send validation and controlled Lab-only cycle."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.football.client import FootballClient
from app.lab_combo.presentation import LabTelegramTransport
from app.lab_combo.repository import ComboRepository
from app.lab_combo.service import LabComboService
from app.lab_telegram.service import load_lab_telegram_config, validate_lab_telegram_config
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint
from app.real_match_lab_analysis.models import LAB_BOT_USERNAME

from .audit import audit_recent_lab, settled_loss_postmortems
from .publication import prepare_v2_publications
from .quota import DAILY_SAFETY_RESERVE, MAX_DISCOVERY_CALLS_PER_CYCLE
from .repository import ShadowEvidenceRepository
from .runner import LabV2ShadowRunner
from .summary import latest_cycle_summary


async def _cycle(args: argparse.Namespace) -> dict[str, object]:
    client = FootballClient(request_limit=args.max_calls)
    repository = ShadowEvidenceRepository(args.shadow_database)
    clock = datetime.now(timezone.utc)
    try:
        runner = LabV2ShadowRunner(
            client, repository, capability_cache_path=args.capability_cache,
            analysis_path=args.analysis_database, maximum_calls=args.max_calls,
            daily_safety_reserve=args.daily_reserve,
        )
        report = await runner.run(
            now=clock,
            horizon_days=args.horizon_days,
            publication_requested=bool(args.send),
        )
        report["analysis_mode"] = str(report.get("analysis_mode") or report.get("mode") or "LAB_V2_NO_SEND")
        report["mode"] = "LAB_V2_CONTROLLED_SEND" if args.send else "LAB_V2_NO_SEND"
        report["publication_requested"] = bool(args.send)
        report["publication_enabled"] = bool(args.send)
        report["publication_attempt_count"] = 0
        report["telegram_sends"] = 0
        report["telegram_transport_constructed"] = False
        report["controlled_publication"] = {
            "authorized_destination": "-1003510920417",
            "singles_sent": 0, "combos_sent": 0,
            "send_attempted": False,
            "publication_attempt_count": 0,
            "telegram_transport_constructed": False,
            "reason": "NO_SEND_VALIDATION" if not args.send else None,
        }
        if not args.send:
            return _persist_cycle_evidence(repository, report, clock)
        ready = int(report.get("ready_candidate_count") or 0)
        if ready == 0:
            report["controlled_publication"]["reason"] = "NO_READY_SELECTIONS"
            return _persist_cycle_evidence(repository, report, clock)
        ledger = ComboRepository(args.ledger)
        try:
            prepared = prepare_v2_publications(report, ledger, now=datetime.now(timezone.utc))
            pending = [
                *[("single_prediction", item["prediction_id"]) for item in prepared["singles"]],
                *[("combo_prediction", item["prediction_id"]) for item in prepared["combos"]],
            ]
            if not pending:
                report["controlled_publication"]["reason"] = "EXACTLY_ONCE_NO_NEW_PUBLICATIONS"
                return _persist_cycle_evidence(repository, report, clock)
            config = load_lab_telegram_config()
            blocker = validate_lab_telegram_config(config)
            if blocker is not None:
                report["controlled_publication"]["reason"] = "LAB_CONFIGURATION_REJECTED"
                return _persist_cycle_evidence(repository, report, clock)
            from app.lab_combo.secure_logging import install_lab_secret_redaction
            install_lab_secret_redaction(config.token)
            transport = LabTelegramTransport(config.token)
            report["telegram_transport_constructed"] = True
            report["controlled_publication"]["telegram_transport_constructed"] = True
            service = LabComboService(ledger, None, clock=lambda: datetime.now(timezone.utc))
            deliveries = []
            async with transport.bot:
                if "@" + (transport.bot.username or "") != LAB_BOT_USERNAME:
                    report["controlled_publication"]["reason"] = "LAB_BOT_IDENTITY_MISMATCH"
                    return _persist_cycle_evidence(repository, report, clock)
                for kind, identity in pending:
                    outcome = await service.publish_experimental(kind, identity, config, transport)
                    deliveries.append({"kind": kind, "prediction_id": identity, **outcome})
            attempts = len(deliveries)
            singles_sent = sum(
                item["kind"] == "single_prediction" and bool(item.get("sent"))
                for item in deliveries
            )
            combos_sent = sum(
                item["kind"] == "combo_prediction" and bool(item.get("sent"))
                for item in deliveries
            )
            telegram_sends = singles_sent + combos_sent
            report["publication_attempt_count"] = attempts
            report["telegram_sends"] = telegram_sends
            report["controlled_publication"] = {
                "authorized_destination": "-1003510920417",
                "send_attempted": attempts > 0,
                "publication_attempt_count": attempts,
                "telegram_transport_constructed": True,
                "singles_sent": singles_sent,
                "combos_sent": combos_sent,
                "deliveries": deliveries,
                "reason": None,
            }
            return _persist_cycle_evidence(repository, report, clock)
        finally:
            ledger.close()
    finally:
        await client.close()
        repository.close()


def _persist_cycle_evidence(
    repository: ShadowEvidenceRepository,
    report: dict[str, object],
    started_at: datetime,
) -> dict[str, object]:
    """Append the outer publication-boundary outcome for every controlled cycle."""
    evidence = {
        "schema_version": "goalvision-lab-v2-publication-cycle-v1",
        "analysis_mode": report["analysis_mode"],
        "mode": report["mode"],
        "publication_requested": report["publication_requested"],
        "publication_enabled": report["publication_enabled"],
        "telegram_transport_constructed": report["telegram_transport_constructed"],
        "ready_candidate_count": int(report.get("ready_candidate_count") or 0),
        "publication_attempt_count": report["publication_attempt_count"],
        "telegram_sends": report["telegram_sends"],
        "controlled_publication": report["controlled_publication"],
    }
    identity = "lab-v2-publication-cycle-" + fingerprint((started_at, evidence))
    repository.append(
        "publication_cycle",
        identity,
        evidence,
        created_at=datetime.now(timezone.utc),
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--ledger", type=Path, default=Path("var/lab_combo/ledger.db"))
    audit.add_argument("--analysis-database", type=Path, default=Path("var/lab_combo/analysis.db"))
    summary = sub.add_parser("summary")
    summary.add_argument("--shadow-database", type=Path, default=Path("var/lab_v2/shadow.db"))
    summary.add_argument("--fixture-id", type=int)
    for name in ("rehearse", "controlled-cycle"):
        cycle = sub.add_parser(name)
        cycle.add_argument("--shadow-database", type=Path, default=Path("var/lab_v2/shadow.db"))
        cycle.add_argument("--analysis-database", type=Path, default=Path("var/lab_combo/analysis.db"))
        cycle.add_argument("--ledger", type=Path, default=Path("var/lab_combo/ledger.db"))
        cycle.add_argument("--capability-cache", type=Path, default=Path("var/lab_v2/capabilities.json"))
        cycle.add_argument("--horizon-days", type=int, default=3)
        cycle.add_argument("--max-calls", type=int, default=MAX_DISCOVERY_CALLS_PER_CYCLE)
        cycle.add_argument("--daily-reserve", type=int, default=DAILY_SAFETY_RESERVE)
        cycle.add_argument("--send", action="store_true", help="Explicitly publish genuine READY picks to the fixed Lab chat")
    args = parser.parse_args(argv)
    if args.command == "audit":
        value = {
            "bottleneck_audit": audit_recent_lab(args.ledger, args.analysis_database),
            "settled_loss_postmortems": settled_loss_postmortems(args.ledger, args.analysis_database),
        }
    elif args.command == "summary":
        value = latest_cycle_summary(args.shadow_database, fixture_id=args.fixture_id)
    else:
        if args.command == "rehearse" and args.send:
            parser.error("rehearse is always no-send; use controlled-cycle --send")
        value = asyncio.run(_cycle(args))
    print(canonical_json(value))
    return 1 if value.get("terminal_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
