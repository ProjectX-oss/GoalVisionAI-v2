"""Manual Lab V2 audit, no-send validation and controlled Lab-only cycle."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.football.client import FootballClient
from app.lab_combo.presentation import LabTelegramTransport
from app.lab_combo.repository import ComboRepository
from app.lab_combo.service import DeliveryFailure, LabComboService
from app.lab_telegram.service import load_lab_telegram_config, validate_lab_telegram_config
from app.real_match_lab_analysis.fingerprint import canonical_json, fingerprint
from app.real_match_lab_analysis.models import LAB_BOT_USERNAME

from .audit import audit_recent_lab, settled_loss_postmortems
from .operator_output import operator_cycle_summary
from .publication import prepare_v2_publications
from .quota import DAILY_SAFETY_RESERVE, MAX_DISCOVERY_CALLS_PER_CYCLE, discovery_state
from .repository import ShadowEvidenceRepository
from .runner import LabV2ShadowRunner, night_report
from .summary import latest_cycle_summary


async def _cycle(args: argparse.Namespace, *, football_context: object | None = None) -> dict[str, object]:
    clock = datetime.now(timezone.utc)
    repository = ShadowEvidenceRepository(args.shadow_database)
    if discovery_state(clock) == "NIGHT_DISCOVERY_PAUSED":
        try:
            report = night_report(clock)
            repository.append("rehearsal", "lab-v2-night-" + fingerprint(clock), report, created_at=clock)
            return report
        finally:
            repository.close()
    client = FootballClient(request_limit=args.max_calls, **(
        {'response_observer': football_context.capture} if football_context is not None else {}))
    adaptive_repository = None
    coordinator = None
    if getattr(args, 'adaptive_database', None):
        from app.adaptive_lab.repository import AuditRepository
        from app.adaptive_lab.coordinator import LearningCoordinator
        adaptive_repository = AuditRepository(args.adaptive_database)
        coordinator = LearningCoordinator(adaptive_repository, football_context_observer=football_context)
    try:
        runner = LabV2ShadowRunner(
            client, repository, capability_cache_path=args.capability_cache,
            analysis_path=args.analysis_database, maximum_calls=args.max_calls,
            daily_safety_reserve=args.daily_reserve, adaptive_learning=coordinator, runtime_clock=lambda: datetime.now(timezone.utc),
            football_context_observer=football_context,
        )
        report = await runner.run(
            now=clock,
            horizon_days=args.horizon_days,
            publication_requested=bool(args.send),
        )
        if coordinator is not None:
            from .publication import _leg
            shadow_now=datetime.now(timezone.utc)
            shadow_inputs = [_leg(item, shadow_now)
                             for item in report.get('candidate_markets', [])
                             if item.get('decision') == 'APPROVED' and item.get('quote_provenance_fingerprint') and item.get('ensemble_probability')
                             and item.get('predictive_family_count',0)>0
                             and datetime.fromisoformat(item['kickoff_utc'])>shadow_now
                             and 'ODDS_STALE_WAITING_REFRESH' not in item.get('rejection_reasons',[])]
            coordinator.shadow(shadow_inputs, stream='PREMATCH', now=datetime.now(timezone.utc))
        report["analysis_status"] = "FAILED" if report.get("terminal_error") else "COMPLETED"
        report["delivery_status"] = "NOT_REQUESTED" if not args.send else "NOT_ATTEMPTED"
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
            prepared = prepare_v2_publications(
                report, ledger, now=datetime.now(timezone.utc),
                label_origin=bool(getattr(args, 'label_v2_selections', False)),
                football_context=football_context,
            )
            report['controlled_publication']['publication_blockers']=prepared['publication_blockers']
            report['controlled_publication']['publication_reviews']=prepared['publication_reviews']
            report['controlled_publication']['publication_policy_version']=prepared['publication_policy_version']
            pending = [
                *[("single_prediction", item["prediction_id"]) for item in prepared["singles"]],
                *[("combo_prediction", item["prediction_id"]) for item in prepared["combos"]],
            ]
            if not pending:
                reasons=set(prepared['publication_blockers'].values())
                report["controlled_publication"]["reason"] = (next(iter(reasons)) if len(reasons)==1 else
                    'LAB_PUBLICATION_RULE_BLOCKED' if reasons else 'EXACTLY_ONCE_NO_NEW_PUBLICATIONS')
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
            phase = 'INITIALIZATION'
            failure = None
            try:
                # PTB's context manager shuts requests down if initialize/getMe fails.
                async with transport.bot:
                    phase = 'PUBLICATION'
                    if "@" + (transport.bot.username or "") != LAB_BOT_USERNAME:
                        failure = {'stage': phase, 'code': 'LAB_BOT_IDENTITY_MISMATCH'}
                    else:
                        for kind, identity in pending:
                            try:
                                outcome = await service.publish_experimental(kind, identity, config, transport)
                            except DeliveryFailure as exc:
                                deliveries.append(exc.outcome)
                                failure = {'stage': exc.outcome['stage'], 'code': exc.outcome['status'],
                                           'kind': kind, 'prediction_id': identity}
                                break
                            deliveries.append({"kind": kind, "prediction_id": identity, **outcome})
                    phase = 'SHUTDOWN'
            except Exception as exc:
                # Never persist exception text/URLs/tokens. No batch or send retry.
                from telegram.error import TimedOut
                lifecycle_failure = {'stage': phase, 'code': 'LAB_TELEGRAM_' + phase + '_FAILED',
                                     'kind': 'TIMEOUT' if isinstance(exc, (TimedOut, TimeoutError)) else 'ERROR'}
                if failure is None:
                    failure = lifecycle_failure
                else:
                    failure['lifecycle_failure'] = lifecycle_failure
                # A failed shutdown may leave one request pool open. Closing is
                # idempotent and cannot resend; never retry initialize or publish.
                try:
                    await transport.bot.shutdown()
                except Exception:
                    failure['cleanup'] = 'FAILED'
                else:
                    failure['cleanup'] = 'COMPLETED'
            report['delivery_status'] = ('DEGRADED' if failure and failure['stage'] == 'SHUTDOWN' else
                                         'FAILED' if failure else
                                         'DEGRADED' if any(not d.get('sent') for d in deliveries) else 'COMPLETED')
            attempts = sum(item['transport_attempted'] for item in deliveries)
            singles_sent = sum(
                item["kind"] == "single_prediction" and item['receipt_persisted']
                for item in deliveries
            )
            combos_sent = sum(
                item["kind"] == "combo_prediction" and item['receipt_persisted']
                for item in deliveries
            )
            telegram_sends = singles_sent + combos_sent
            report["publication_attempt_count"] = attempts
            report["telegram_sends"] = telegram_sends
            report["controlled_publication"] = {
                **report["controlled_publication"],
                "status": report["delivery_status"],
                "failure": failure,
                "authorized_destination": "-1003510920417",
                "send_attempted": attempts > 0,
                "publication_attempt_count": attempts,
                "telegram_transport_constructed": True,
                "singles_sent": singles_sent,
                "combos_sent": combos_sent,
                "deliveries": deliveries,
                "reason": failure["code"] if failure else None,
            }
            return _persist_cycle_evidence(repository, report, clock)
        finally:
            ledger.close()
    finally:
        if football_context is not None:
            try:
                football_context.client_diagnostics(client.evidence_capture_failures)
            except Exception:
                pass
        await client.close()
        repository.close()
        if adaptive_repository is not None:
            from app.adaptive_lab.health import persist_health
            import sys
            error=sys.exc_info()[0]
            health_report=locals().get('report',{})
            if error:
                health_report={**health_report,'terminal_error':error.__name__}
            try:
                persist_health(adaptive_repository,health_report,started=clock,completed=datetime.now(timezone.utc))
            finally:
                adaptive_repository.close()


async def configured_cycle(args: argparse.Namespace) -> dict[str, object]:
    """Decorate the existing cycle once; optional observation never starts polling."""
    root = getattr(args, 'football_context_root', None)
    if root is None:
        return await _cycle(args)
    from app.prematch_football_context.readiness.composition import ProspectiveObservation
    import sys
    try:
        observation = ProspectiveObservation(
            root, environment='LAB', clock=lambda: datetime.now(timezone.utc),
            regulation_registry=getattr(args, 'football_context_registry', None),
        )
    except Exception:
        print(canonical_json({'football_context_observation': {'CONSTRUCTION_FAILED': 1}}), file=sys.stderr)
        return await _cycle(args)
    completed = False
    try:
        result = await _cycle(args, football_context=observation)
        completed = not bool(result.get('terminal_error'))
        return result
    finally:
        try:
            diagnostics = observation.finish(completed=completed)
        except Exception:
            diagnostics = {'FINISH_FAILED': 1}
        print(canonical_json({'football_context_observation': diagnostics}), file=sys.stderr)


def _persist_cycle_evidence(
    repository: ShadowEvidenceRepository,
    report: dict[str, object],
    started_at: datetime,
) -> dict[str, object]:
    """Append the outer publication-boundary outcome for every controlled cycle."""
    evidence = {
        "schema_version": "goalvision-lab-v2-publication-cycle-v2",
        "analysis_status": report["analysis_status"],
        "delivery_status": report["delivery_status"],
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
    try:
        repository.append(
            "publication_cycle",
            identity,
            evidence,
            created_at=datetime.now(timezone.utc),
        )
    except Exception:
        # Retain all in-memory delivery facts when the reporting store also fails.
        # No exception text, write retry, or fabricated durable evidence.
        report['publication_cycle_persistence'] = {
            'persisted': False, 'code': 'LAB_PUBLICATION_CYCLE_PERSISTENCE_FAILED',
        }
        if report['delivery_status'] != 'FAILED':
            report['delivery_status'] = 'DEGRADED'
        report['controlled_publication']['status'] = report['delivery_status']
    else:
        report['publication_cycle_persistence'] = {'persisted': True}
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
    summary.add_argument("--human", action="store_true")
    for name in ("rehearse", "controlled-cycle"):
        cycle = sub.add_parser(name)
        cycle.add_argument("--shadow-database", type=Path, default=Path("var/lab_v2/shadow.db"))
        cycle.add_argument("--analysis-database", type=Path, default=Path("var/lab_combo/analysis.db"))
        cycle.add_argument("--ledger", type=Path, default=Path("var/lab_combo/ledger.db"))
        cycle.add_argument("--capability-cache", type=Path, default=Path("var/lab_v2/capabilities.json"))
        cycle.add_argument("--horizon-days", type=int, default=3)
        cycle.add_argument("--max-calls", type=int, default=MAX_DISCOVERY_CALLS_PER_CYCLE)
        cycle.add_argument("--settlement-reserve", "--daily-reserve", dest="daily_reserve", type=int,
                           choices=[DAILY_SAFETY_RESERVE], default=DAILY_SAFETY_RESERVE,
                           help="Result reserve; discovery uses time-aware Riga daytime pacing")
        cycle.add_argument("--adaptive-database", type=Path, help="Opt-in LAB adaptive registry")
        cycle.add_argument('--football-context-root', type=Path,
                           help='Explicit preinitialized isolated observation stores; no extra requests')
        cycle.add_argument('--football-context-registry', type=Path,
                           help='Optional reviewed registry opened read-only and pinned before decisions')
        cycle.add_argument('--label-v2-selections', action='store_true',
                           help='Freeze truthful existing-selector attribution for new singles')
        cycle.add_argument("--send", action="store_true", help="Explicitly publish genuine READY picks to the fixed Lab chat")
    args = parser.parse_args(argv)
    if getattr(args, 'football_context_registry', None) and not getattr(args, 'football_context_root', None):
        parser.error('--football-context-registry requires --football-context-root')
    root = getattr(args, 'football_context_root', None)
    if root is not None and (not root.is_absolute() or Path('/tmp') in root.resolve().parents
                             or not getattr(args, 'adaptive_database', None)):
        parser.error('Observation requires an absolute stable root outside /tmp and --adaptive-database')
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
        value = asyncio.run(configured_cycle(args))
    if args.command == "summary" and args.human:
        from .diagnostics import human_diagnostic
        print(human_diagnostic(value))
    else:
        print(canonical_json(operator_cycle_summary(value)
                             if args.command in {"controlled-cycle", "rehearse"} else value))
    return 1 if value.get("terminal_error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
