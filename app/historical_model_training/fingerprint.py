"""Canonical safe serialization for training artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum


def canonical_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("Non-finite floating-point value cannot be serialized.")
    if value == 0:
        return "0"
    return format(value, ".17g")


def _canonical(value):
    if is_dataclass(value):
        value = asdict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite Decimal cannot be serialized.")
        return format(value.normalize(), "f") if value else "0"
    if isinstance(value, float):
        return canonical_float(value)
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def canonical_json(value) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_fingerprint(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
