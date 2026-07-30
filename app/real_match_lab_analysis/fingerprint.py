from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


def canonical_json(value: object) -> str:
    def encode(item: object) -> object:
        if is_dataclass(item):
            return encode(asdict(item))
        if isinstance(item, dict):
            return {str(key): encode(val) for key, val in sorted(item.items())}
        if isinstance(item, (tuple, list)):
            return [encode(val) for val in item]
        if isinstance(item, Decimal):
            return format(item.normalize(), "f")
        if isinstance(item, datetime):
            return item.isoformat()
        if isinstance(item, Enum):
            return item.value
        return item
    return json.dumps(encode(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
