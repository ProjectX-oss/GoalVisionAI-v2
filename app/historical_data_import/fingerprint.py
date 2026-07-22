"""Canonical serialization and SHA-256 identities for historical data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any


def canonical_json(value: object) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("Decimal values must be finite.")
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f")


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value):
        return _canonical_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime values must be timezone-aware.")
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    raise TypeError(f"Unsupported canonical value: {type(value).__name__}.")
