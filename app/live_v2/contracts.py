"""Pure LIVE evidence contracts; no environment or network side effects."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any


def utc(value: datetime | str) -> datetime:
    """Require an offset and return a UTC instant."""
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('OFFSET_REQUIRED')
    return result.astimezone(timezone.utc)


def canonical(value: Any) -> str:
    """Stable, finite JSON suitable for immutable replay."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return sha256(canonical(value).encode()).hexdigest()


def fresh(value: str | None, now: datetime, seconds: int) -> bool:
    try:
        return value is not None and 0 <= (utc(now) - utc(value)).total_seconds() <= seconds
    except (ValueError, TypeError, AttributeError):
        return False


def integer(value: object, low: int = 0, high: int = 10000000) -> bool:
    return type(value) is int and low <= value <= high
