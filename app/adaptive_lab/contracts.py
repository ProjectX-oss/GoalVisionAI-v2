"""Reviewed executable-free contracts shared by the two independent streams."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

STREAMS = frozenset({'PREMATCH', 'LIVE'})
MARKETS = frozenset({'HOME_WIN', 'DRAW', 'AWAY_WIN', 'BTTS_YES', 'BTTS_NO',
                     'OVER_1_5', 'UNDER_1_5', 'OVER_2_5', 'UNDER_2_5', 'OVER_3_5', 'UNDER_3_5'})


def canonical(value: Any) -> str:
    """Reject nonfinite numbers; artifacts are JSON data, never executable objects."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise ValueError('UTC_OFFSET_REQUIRED')
    return parsed.astimezone(timezone.utc)


def number(value: Any, *, low: float = -1e9, high: float = 1e9) -> float:
    if isinstance(value, bool):
        raise ValueError('INVALID_NUMBER')
    result = float(value)
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError('INVALID_NUMBER')
    return result


def stream_name(value: str) -> str:
    if value not in STREAMS:
        raise ValueError('LAB_STREAM_REQUIRED')
    return value


def side(market: str) -> str:
    if market not in MARKETS:
        raise ValueError('UNSUPPORTED_MARKET')
    return market.split('_')[0] if market != 'BTTS_YES' and market != 'BTTS_NO' else market[5:]
