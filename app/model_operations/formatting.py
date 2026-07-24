"""Deterministic, secret-redacted operator output and future Lab previews."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from .models import OperatorResult


_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential", "api_key")


def format_result_json(result: OperatorResult) -> str:
    return json.dumps(
        redact(asdict(result)),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def format_result_human(result: OperatorResult) -> str:
    state = "CHANGED" if result.production_state_changed else "UNCHANGED"
    lines = [
        f"COMMAND: {result.command}",
        f"MODE: {result.mode.value}",
        f"STATUS: {result.status}",
        f"PRODUCTION_STATE: {state}",
    ]
    if result.model_scope:
        lines.append(f"MODEL_SCOPE: {result.model_scope}")
    for key, value in sorted(redact(result.details).items()):
        lines.extend(_human_lines(key.upper(), value))
    for code in result.reason_codes:
        lines.append(f"REASON: {code}")
    for guidance in result.recovery_guidance:
        lines.append(f"RECOVERY: {guidance}")
    return "\n".join(lines)


def format_lab_preview(result: OperatorResult) -> str:
    """Create a safe Lab-only preview; this function never sends Telegram."""
    return "\n".join(
        (
            "🧪 GOALVISION AI LAB — MODEL OPERATIONS PREVIEW",
            "",
            f"Command: {result.command}",
            f"Status: {result.status}",
            f"Scope: {result.model_scope or 'N/A'}",
            "State changed: "
            + ("YES" if result.production_state_changed else "NO"),
            "",
            "Preview only. No Telegram message was sent.",
        )
    )


def redact(value: Any, key: str = "") -> Any:
    if any(part in key.casefold() for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if is_dataclass(value):
        return redact(asdict(value), key)
    if isinstance(value, Mapping):
        return {
            str(item_key): redact(item, str(item_key))
            for item_key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [redact(item, key) for item in value]
    if isinstance(value, (Decimal, datetime)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _human_lines(prefix: str, value: Any) -> list[str]:
    if isinstance(value, Mapping):
        lines: list[str] = []
        for key, item in sorted(value.items()):
            lines.extend(_human_lines(f"{prefix}.{str(key).upper()}", item))
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{prefix}: []"]
        lines = []
        for index, item in enumerate(value, 1):
            lines.extend(_human_lines(f"{prefix}[{index}]", item))
        return lines
    return [f"{prefix}: {value}"]
