"""Reply-to-original result notifications without another lookup or send retry."""
from __future__ import annotations

from dataclasses import dataclass
import os

from app.services.telegram_service import TelegramMessageReceipt

FLAG = "GOALVISION_LAB_SETTLEMENT_REPLIES"
VERSION = "LAB_SETTLEMENT_REPLY_V1"


def settlement_reply(ledger: object, kind: str, prediction_id: str,
                     destination: str) -> dict | None:
    """Bind only result notifications to their confirmed original publication."""
    prefixes = {"single_settlement": "single_prediction:",
                "combo_settlement": "combo_prediction:", "settlement": "prediction:"}
    if kind not in prefixes:
        return None
    enabled = os.environ.get(FLAG, "0")
    if enabled not in {"0", "1"}:
        raise ValueError("SETTLEMENT_REPLY_CONFIGURATION_INVALID")
    if enabled == "0":
        return None
    identity = prefixes[kind] + prediction_id
    receipt = ledger.get("receipt", identity)
    if (not isinstance(receipt, dict) or receipt.get("status") != "SENT"
            or receipt.get("sent") is not True
            or str(receipt.get("chat_id")) != str(destination)
            or type(receipt.get("message_id")) is not int or receipt["message_id"] <= 0):
        raise ValueError("SETTLEMENT_REPLY_ORIGINAL_RECEIPT_REQUIRED")
    return {"version": VERSION, "publication_identity": identity,
            "chat_id": str(destination), "message_id": receipt["message_id"],
            "allow_sending_without_reply": True}


@dataclass(frozen=True)
class ReplyMessageReceipt(TelegramMessageReceipt):
    """A confirmed parent is distinct from a successfully sent unthreaded result."""
    reply_to_message_id: int | None = None


def telegram_receipt(message: object, *, destination: str,
                     reply_to_message_id: int | None) -> TelegramMessageReceipt:
    message_id = getattr(message, "message_id", None)
    chat_id = getattr(message, "chat_id", None)
    if chat_id is None:
        chat_id = getattr(getattr(message, "chat", None), "id", None)
    if type(message_id) is not int or message_id <= 0 or str(chat_id) != str(destination):
        raise ValueError("INVALID_RESULT_MESSAGE_RECEIPT")
    if reply_to_message_id is None:
        return TelegramMessageReceipt(message_id, str(chat_id))
    parent = getattr(message, "reply_to_message", None)
    parent_id = None
    if parent is not None:
        parent_id = getattr(parent, "message_id", None)
        parent_chat = getattr(parent, "chat_id", None)
        if parent_chat is None:
            parent_chat = getattr(getattr(parent, "chat", None), "id", None)
        if (type(parent_id) is not int or parent_id != reply_to_message_id
                or str(parent_chat) != str(destination)):
            raise ValueError("RESULT_REPLY_RECEIPT_MISMATCH")
    return ReplyMessageReceipt(message_id, str(chat_id), parent_id)


def reply_confirmation(receipt: object, binding: dict | None) -> dict:
    if binding is None:
        return {}
    actual = getattr(receipt, "reply_to_message_id", None)
    if actual is not None and (type(actual) is not int or actual != binding["message_id"]):
        raise ValueError("RESULT_REPLY_RECEIPT_MISMATCH")
    return {"reply_to": binding,
            "reply_status": "CONFIRMED" if actual is not None else "NOT_CONFIRMED"}
