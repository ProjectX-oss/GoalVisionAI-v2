"""Natural-cycle hooks; private faults never suppress the existing Lab products."""
from __future__ import annotations
from datetime import datetime, timezone

from app.lab_combo.service import LabComboService, DeliveryFailure
from app.lab_combo.secure_logging import install_lab_secret_redaction
from . import policy, routing
from .repository import PrivateSingleRepository, ledger_path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_outcome(value: dict) -> dict:
    return {k: value.get(k) for k in ("kind", "status", "sent", "stage", "claim_persisted",
        "transport_attempted", "acknowledgement_received", "receipt_persisted",
        "reconciliation_required", "persistence_failure", "reply_status")}


async def deliver(service, pending, config, transport_factory) -> dict:
    outcomes = []
    phase = "INITIALIZATION"
    install_lab_secret_redaction(config.token)
    try:
        transport = transport_factory(config.token)
        async with transport.bot:
            phase = "DELIVERY"
            for kind, identity in pending:
                try:
                    outcome = await service.publish_experimental(kind, identity, config, transport)
                except DeliveryFailure as exc:
                    outcomes.append(safe_outcome(exc.outcome))
                    break
                outcomes.append(safe_outcome({"kind": kind, **outcome}))
            phase = "SHUTDOWN"
    except Exception:
        return {"status": "PRIVATE_DELIVERY_" + phase + "_FAILED", "deliveries": outcomes,
                "transport_constructed": "transport" in locals()}
    return {"status": "COMPLETED" if all(v["receipt_persisted"] for v in outcomes)
            else "PRIVATE_DELIVERY_BLOCKED", "deliveries": outcomes, "transport_constructed": True}


def record_publication(report: dict, outcome: dict) -> None:
    """Count private transport without changing public SINGLE/COMBO cohorts."""
    report["private_single"] = outcome
    deliveries = outcome.get("deliveries", [])
    sent = sum(bool(v.get("receipt_persisted")) for v in deliveries)
    attempts = sum(bool(v.get("transport_attempted")) for v in deliveries)
    constructed = bool(outcome.get("transport_constructed"))
    report["telegram_sends"] = report.get("telegram_sends", 0) + sent
    report["publication_attempt_count"] = report.get("publication_attempt_count", 0) + attempts
    report["telegram_transport_constructed"] = report.get("telegram_transport_constructed", False) or constructed
    report["controlled_publication"].update(private_singles_sent=sent,
        private_publication_attempt_count=attempts, private_transport_constructed=constructed,
        private_single=outcome)


async def publish_natural(report: dict, *, transport_factory, football_context=None, clock=utc_now) -> dict:
    ledger = None
    try:
        if not policy.enabled():
            return {"status": "DISABLED"}
        config = routing.load_config()
        ledger = PrivateSingleRepository(ledger_path())
        prepared = policy.prepare(report, ledger, config.route, now=clock(), football_context=football_context)
        output = {k: v for k, v in prepared.items() if k != "singles"}
        pending = [("single_prediction", v["prediction_id"]) for v in prepared["singles"]]
        if pending:
            output.update(await deliver(LabComboService(ledger, None, clock=clock),
                                        pending, config, transport_factory))
        ledger.append("private_run", clock().isoformat(), output)
        return output
    except Exception as exc:
        return {"status": str(exc) if isinstance(exc, routing.RoutingBlocked)
                else "PRIVATE_SELECTION_FAILED", "provider_calls": 0}
    finally:
        if ledger is not None:
            ledger.close()


def settlement_needed(*, now: datetime) -> bool:
    """Only already published due private picks justify a status preflight."""
    if not ledger_path().is_file():
        return False
    ledger = None
    try:
        from app.lab_combo.cli import _settlement_work_relevant
        ledger = PrivateSingleRepository(ledger_path())
        return _settlement_work_relevant(ledger, now)
    except Exception:
        return False
    finally:
        if ledger is not None:
            ledger.close()


async def settle_natural(client, *, result_cache: dict, maximum_calls: int,
                         transport_factory, send: bool, result_images=None, clock=utc_now) -> dict:
    if not ledger_path().is_file():
        return {"status": "NO_PRIVATE_LEDGER"}
    ledger = None
    try:
        ledger = PrivateSingleRepository(ledger_path())
        service = LabComboService(ledger, None, clock=clock, result_images=result_images)
        output = await service.check_results(client, maximum_calls=maximum_calls,
                                             result_cache=result_cache)
        output["status"] = "COMPLETED"
        pending = [("single_settlement", v["prediction_id"]) for v in ledger.all("single_settlement")
                   if ledger.get("receipt", "single_prediction:" + v["prediction_id"])
                   and not ledger.get("claim", "single_settlement:" + v["prediction_id"])]
        if send and pending:
            config = routing.load_config()
            output.update(await deliver(service, pending, config, transport_factory))
        ledger.append("private_settlement_run", clock().isoformat(), output)
        return output
    except Exception as exc:
        return {"status": str(exc) if isinstance(exc, routing.RoutingBlocked)
                else "PRIVATE_SETTLEMENT_FAILED"}
    finally:
        if ledger is not None:
            ledger.close()
