"""Verified Lab-bot private route; never falls back to a group or other bot."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import pwd
import re
import stat

from app.lab_combo.bot_routing import RoutingBlocked
from app.lab_telegram.service import load_lab_telegram_config, validate_lab_telegram_config
from app.real_match_lab_analysis.models import LAB_BOT_USERNAME

CONFIG_PATH = Path("/home/arvis/goalvision-private/lab-single-telegram.json")
VERSION = "GOALVISION_PRIVATE_LAB_SINGLE_ROUTE_V1"
PERIOD = "PRIVATE_SINGLE_170_20261004_V1"


@dataclass(frozen=True)
class PrivateLabConfig:
    token: str = field(repr=False)
    route: dict


def validate_route(route: object) -> dict:
    keys = {"version", "product", "bot_username", "bot_id", "chat_id", "chat_type",
            "statistics_period", "period_started_at"}
    try:
        if not isinstance(route, dict) or set(route) != keys:
            raise ValueError
        stamp = datetime.fromisoformat(route["period_started_at"])
        if (route["version"] != VERSION or route["product"] != "PRIVATE_SINGLE"
                or route["bot_username"] != LAB_BOT_USERNAME or route["chat_type"] != "private"
                or route["statistics_period"] != PERIOD
                or stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0
                or any(not isinstance(route[k], str) or not re.fullmatch(r"[1-9][0-9]{0,18}", route[k])
                       for k in ("bot_id", "chat_id"))):
            raise ValueError
        return dict(route)
    except (KeyError, ValueError, TypeError, AttributeError):
        raise RoutingBlocked("PRIVATE_LAB_ROUTE_INVALID") from None


def load_config(path: Path | None = None) -> PrivateLabConfig:
    path = CONFIG_PATH if path is None else path
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != pwd.getpwnam("arvis").pw_uid or info.st_size > 8192):
            raise ValueError
        data = json.loads(path.read_text())
        if set(data) != {"route", "verified_at", "start_update_id", "recipient_anchor_fingerprint"}:
            raise ValueError
        route = validate_route(data["route"])
        if (data["verified_at"] != route["period_started_at"]
                or type(data["start_update_id"]) is not int or data["start_update_id"] < 0
                or not re.fullmatch(r"[a-f0-9]{64}", data["recipient_anchor_fingerprint"])):
            raise ValueError
        lab = load_lab_telegram_config(Path("/home/arvis/GoalVisionAI/.env"))
        if (validate_lab_telegram_config(lab) is not None or not isinstance(lab.token, str)
                or not re.fullmatch(re.escape(route["bot_id"]) + r":[A-Za-z0-9_-]{20,100}", lab.token)):
            raise ValueError
        return PrivateLabConfig(lab.token, route)
    except (OSError, ValueError, KeyError, TypeError):
        raise RoutingBlocked("PRIVATE_LAB_RECIPIENT_NOT_CONFIGURED") from None


def delivery_route(ledger, kind: str, prediction_id: str) -> dict:
    from .policy import enabled
    if kind not in {"single_prediction", "single_settlement"}:
        raise RoutingBlocked("PRIVATE_SINGLE_ONLY")
    prediction = ledger.get("single_prediction", prediction_id)
    route = validate_route((prediction or {}).get("private_delivery_route"))
    if kind == "single_prediction":
        if not enabled():
            raise RoutingBlocked("PRIVATE_NEW_PUBLICATIONS_PAUSED")
        return route
    receipt = ledger.get("receipt", "single_prediction:" + prediction_id)
    claim = ledger.get("claim", "single_prediction:" + prediction_id)
    if (not receipt or not claim or receipt.get("status") != "SENT" or receipt.get("sent") is not True
            or receipt.get("delivery_route") != route or claim.get("delivery_route") != route
            or str(receipt.get("chat_id")) != route["chat_id"]
            or str(claim.get("chat_id")) != route["chat_id"]
            or type(receipt.get("message_id")) is not int or receipt["message_id"] <= 0):
        raise RoutingBlocked("PRIVATE_PUBLICATION_ROUTE_CONFLICT")
    return route


def validate_delivery(config, transport, route: dict, *, now: datetime) -> str | None:
    if not isinstance(config, PrivateLabConfig) or config.route != route:
        return "PRIVATE_LAB_CREDENTIAL_ROUTE_MISMATCH"
    if now < datetime.fromisoformat(route["period_started_at"]):
        return "PRIVATE_LAB_PERIOD_NOT_STARTED"
    bot = getattr(transport, "bot", None)
    if ("@" + (getattr(bot, "username", None) or "") != LAB_BOT_USERNAME
            or str(getattr(bot, "id", "")) != route["bot_id"]):
        return "PRIVATE_LAB_BOT_IDENTITY_MISMATCH"
    return None


def route_message(message: str, route: dict) -> str:
    validate_route(route)
    if message.startswith("🧪 GoalVision AI Lab • Privātā atlase"):
        return message
    return "🧪 Privātās atlases rezultāts · koef. ≥1.70\n" + message
