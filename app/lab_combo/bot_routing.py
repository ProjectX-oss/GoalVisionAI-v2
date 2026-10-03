"""Pinned COMBO bot routing; immutable publication routes and prospective cohorts."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import pwd
from pathlib import Path
import re
import stat

from app.real_match_lab_analysis.models import LAB_CHAT_ID, LAB_BOT_USERNAME
from app.lab_telegram.service import validate_lab_telegram_config

FLAG = "GOALVISION_COMBO_BOT_ROUTING"
CONFIG_PATH = Path("/home/arvis/goalvision-private/combo-telegram.json")
BOT_USERNAME = "@GoalVision_AI_Combo_Bot"
VERSION = "GOALVISION_COMBO_PRIVATE_ROUTE_V1"
PERIOD = "COMBO_BOT_20261003_V1"


class RoutingBlocked(ValueError):
    """Only a fixed, secret-free reason may leave the routing boundary."""


@dataclass(frozen=True)
class ComboBotConfig:
    token: str = field(repr=False)
    route: dict
    verified_at: str
    start_update_id: int

    @property
    def chat_id(self) -> str:
        return self.route["chat_id"]


def validate_route(route: object) -> dict:
    keys = {"version", "product", "bot_username", "bot_id", "chat_id",
            "chat_type", "statistics_period", "period_started_at"}
    if not isinstance(route, dict) or set(route) != keys:
        raise RoutingBlocked("COMBO_ROUTE_INVALID")
    if (route["version"] != VERSION or route["product"] != "COMBO"
            or route["bot_username"] != BOT_USERNAME
            or route["chat_type"] != "private" or route["statistics_period"] != PERIOD
            or any(not isinstance(route[k], str) or not re.fullmatch(r"[1-9][0-9]{0,18}", route[k])
                   for k in ("bot_id", "chat_id"))):
        raise RoutingBlocked("COMBO_ROUTE_INVALID")
    try:
        stamp = datetime.fromisoformat(route["period_started_at"])
        if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise RoutingBlocked("COMBO_ROUTE_INVALID") from None
    return dict(route)


def load_config(path: Path | None = None) -> ComboBotConfig:
    """No network, no credential logging; secrets live outside Git in a 0600 file."""
    path = CONFIG_PATH if path is None else path
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != pwd.getpwnam('arvis').pw_uid or info.st_size > 8192):
            raise ValueError
        data = json.loads(path.read_text())
        if set(data) != {"token", "route", "verified_at", "start_update_id"}:
            raise ValueError
        route = validate_route(data["route"])
        token = data["token"]
        if not isinstance(token, str) or not re.fullmatch(
                re.escape(route["bot_id"]) + r":[A-Za-z0-9_-]{20,100}", token):
            raise ValueError
        verified = datetime.fromisoformat(data["verified_at"])
        if verified.tzinfo is None or verified != datetime.fromisoformat(route["period_started_at"]):
            raise ValueError
        if type(data["start_update_id"]) is not int or data["start_update_id"] < 0:
            raise ValueError
        return ComboBotConfig(token, route, data["verified_at"], data["start_update_id"])
    except (OSError, ValueError, KeyError, TypeError):
        raise RoutingBlocked("COMBO_CREDENTIAL_OR_RECIPIENT_NOT_CONFIGURED") from None


def frozen_route(ledger: object, prediction_id: str, *, legacy: bool = False) -> dict | None:
    """A settled bet belongs to the original confirmed publication, never today's config."""
    identity = ("prediction:" if legacy else "combo_prediction:") + prediction_id
    receipt = ledger.get("receipt", identity)
    if not receipt or "delivery_route" not in receipt:
        if receipt and receipt.get("chat_id") is not None and str(receipt["chat_id"]) != LAB_CHAT_ID:
            raise RoutingBlocked("COMBO_UNBOUND_PUBLICATION_DESTINATION")
        claim = ledger.get("claim", identity)
        if claim and "delivery_route" in claim:
            raise RoutingBlocked("COMBO_PUBLICATION_ROUTE_CONFLICT")
        return None
    route = validate_route(receipt["delivery_route"])
    claim = ledger.get("claim", identity)
    if (not claim or claim.get("delivery_route") != route
            or str(claim.get("chat_id")) != route["chat_id"]
            or str(receipt.get("chat_id")) != route["chat_id"]
            or receipt.get("status") != "SENT" or receipt.get("sent") is not True
            or type(receipt.get("message_id")) is not int or receipt["message_id"] <= 0):
        raise RoutingBlocked("COMBO_PUBLICATION_ROUTE_CONFLICT")
    return route


def delivery_route(ledger: object, kind: str, prediction_id: str) -> dict | None:
    if kind == "combo_settlement":
        return frozen_route(ledger, prediction_id)
    if kind == "settlement":
        return frozen_route(ledger, prediction_id, legacy=True)
    if kind not in {"combo_prediction", "prediction"}:
        return None
    mode = os.environ.get(FLAG)
    if mode is None:
        return None
    if mode == "0":
        raise RoutingBlocked("COMBO_NEW_PUBLICATIONS_PAUSED")
    if mode != "1":
        raise RoutingBlocked("COMBO_ROUTING_CONFIGURATION_INVALID")
    return dict(load_config().route)


def validate_delivery(config: object, transport: object, route: dict | None,
                      *, now: datetime) -> str | None:
    if route is None:
        return "LAB_CONFIGURATION_REJECTED" if (
            isinstance(config, ComboBotConfig) or validate_lab_telegram_config(config) is not None) else None
    if not isinstance(config, ComboBotConfig) or config.route != route:
        return "COMBO_CREDENTIAL_ROUTE_MISMATCH"
    if now < datetime.fromisoformat(route["period_started_at"]):
        return "COMBO_PERIOD_NOT_STARTED"
    bot = getattr(transport, "bot", None)
    if ("@" + (getattr(bot, "username", None) or "") != BOT_USERNAME
            or str(getattr(bot, "id", "")) != route["bot_id"]):
        return "COMBO_BOT_IDENTITY_MISMATCH"
    return None


def route_message(message: str, route: dict | None) -> str:
    if route is None:
        return message
    lines = message.splitlines()
    # Only the product heading changes; all frozen odds/reasoning/results survive.
    if lines:
        suffix = (" #" + lines[0].split("#", 1)[1]) if "#" in lines[0] else ""
        lines[0] = "⚽ GoalVision AI COMBO" + suffix
    stamp = datetime.fromisoformat(route["period_started_at"])
    from zoneinfo import ZoneInfo
    lines.append("📅 COMBO uzskaite no " + stamp.astimezone(ZoneInfo("Europe/Riga")).strftime("%d.%m.%Y %H:%M"))
    return "\n".join(lines)


def cohort_statistics(ledger: object, route: dict | None) -> dict:
    """Filter by frozen publication membership, never by settlement date."""
    from .settlement import statistics

    class Cohort:
        def get(self, kind: str, identity: str):
            return ledger.get(kind, identity)

        def all(self, kind: str):
            if kind != "prediction":
                return ledger.all(kind)
            selected = []
            for value in ledger.all("prediction"):
                pid = value["prediction_id"]
                legacy = ledger.get("receipt", "combo_prediction:" + pid) is None
                if frozen_route(ledger, pid, legacy=legacy) == route:
                    selected.append(value)
            return selected

    result = statistics(Cohort(), published_only=True)
    if route is not None:
        result = {**result, "statistics_period": route["statistics_period"],
                  "period_started_at": route["period_started_at"]}
    return result
