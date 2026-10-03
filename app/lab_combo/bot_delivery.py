"""Independent bot lifecycles with per-route failures and durable delivery evidence."""
from __future__ import annotations

from .bot_routing import (
    BOT_USERNAME, RoutingBlocked, delivery_route, load_config, validate_delivery,
)
from .secure_logging import install_lab_secret_redaction
from app.real_match_lab_analysis.models import LAB_BOT_USERNAME


async def deliver_batch(service, pending, lab_config, transport_factory):
    """Reuse one client per bot/route; a COMBO setup failure cannot suppress SINGLE."""
    from .service import DeliveryFacts, DeliveryFailure
    from dataclasses import asdict
    groups, deliveries, failure = {}, [], None
    for kind, identity in pending:
        # Do not initialize a new bot or reroute an ambiguous historic claim.
        if service.ledger.get("claim", kind + ":" + identity) is not None:
            facts = DeliveryFacts(kind, identity, stage="NO_TRANSPORT_EXISTING_CLAIM")
            deliveries.append({**asdict(facts), "status": "DELIVERY_ALREADY_CLAIMED", "sent": False})
            continue
        try:
            route = delivery_route(service.ledger, kind, identity)
            config = load_config() if route is not None else lab_config
            if route is not None and config.route != route:
                raise RoutingBlocked("COMBO_CREDENTIAL_ROUTE_MISMATCH")
        except RoutingBlocked as exc:
            facts = DeliveryFacts(kind, identity, stage="REJECTED_BEFORE_TRANSPORT")
            deliveries.append({**asdict(facts), "status": str(exc), "sent": False})
            continue
        key = "COMBO" if route is not None else "LAB"
        groups.setdefault(key, [config, route, []])[2].append((kind, identity))

    for label, (config, route, items) in groups.items():
        install_lab_secret_redaction(config.token)
        phase, transport = "INITIALIZATION", None
        try:
            transport = transport_factory(config.token)
            async with transport.bot:
                phase = "PUBLICATION"
                expected = BOT_USERNAME if route else LAB_BOT_USERNAME
                blocker = validate_delivery(config, transport, route, now=service.clock())
                if "@" + (transport.bot.username or "") != expected:
                    blocker = "COMBO_BOT_IDENTITY_MISMATCH" if route else "LAB_BOT_IDENTITY_MISMATCH"
                if blocker:
                    for kind, identity in items:
                        facts = DeliveryFacts(kind, identity, stage="REJECTED_BEFORE_TRANSPORT")
                        deliveries.append({**asdict(facts), "status": blocker, "sent": False})
                    failure = failure or {"stage": phase, "code": blocker, "product": label}
                else:
                    for kind, identity in items:
                        try:
                            outcome = await service.publish_experimental(kind, identity, config, transport)
                        except DeliveryFailure as exc:
                            deliveries.append(exc.outcome)
                            failure = failure or {"stage": exc.outcome["stage"], "code": exc.outcome["status"],
                                                  "kind": kind, "prediction_id": identity}
                            break
                        deliveries.append({"kind": kind, "prediction_id": identity, **outcome})
                phase = "SHUTDOWN"
        except Exception as exc:
            from telegram.error import TimedOut
            info = {"stage": phase, "code": "LAB_TELEGRAM_" + phase + "_FAILED",
                    "kind": "TIMEOUT" if isinstance(exc, (TimedOut, TimeoutError)) else "ERROR"}
            if failure is None:
                failure = info
            else:
                failure["lifecycle_failure"] = info
            if transport is not None:
                try:
                    await transport.bot.shutdown()
                except Exception:
                    failure["cleanup"] = "FAILED"
                else:
                    failure["cleanup"] = "COMPLETED"
    return deliveries, failure
