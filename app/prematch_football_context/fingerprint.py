"""RFC canonical JSON and domain-separated SHA-256; no I/O."""
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from enum import Enum
import hashlib
import json
import unicodedata
from typing import Mapping

from .policy import decimal_context, feature_range, semantic_manifest


def utc(value: datetime) -> datetime:
    """Require explicit timezone and normalize to UTC microseconds."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('UTC_OFFSET_REQUIRED')
    return value.astimezone(timezone.utc)


def decimal_text(value: Decimal) -> str:
    """Lossless plain intermediate decimal, without ambient-context normalization."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError('NONFINITE_OR_NONDECIMAL')
    if value.is_zero():
        return '0'
    text = format(value, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def feature_text(value: Decimal, index: int) -> str:
    """Validate raw bounds then round once, to six places, preserving supported zero."""
    low, high = feature_range(index)
    if not isinstance(value, Decimal) or not value.is_finite() or not low <= value <= high:
        raise ValueError('CALCULATION_INVARIANT_FAILURE')
    with localcontext(decimal_context()):
        rounded = value.quantize(Decimal('0.000001'))
        return '0.000000' if rounded.is_zero() else format(rounded, '.6f')


def canonical_data(value: object) -> object:
    """Convert typed contracts or explicit JSON trees; reject floats and unsupported types."""
    if isinstance(value, Enum):
        return canonical_data(value.value)
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize('NFC', value)
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, datetime):
        return utc(value).isoformat(timespec='microseconds').replace('+00:00', 'Z')
    if is_dataclass(value) and not isinstance(value, type):
        return canonical_data({field.name: getattr(value, field.name) for field in fields(value)})
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('STRING_KEYS_REQUIRED')
            normalized = unicodedata.normalize('NFC', key)
            if normalized in result:
                raise ValueError('NFC_KEY_COLLISION')
            result[normalized] = canonical_data(item)
        return result
    if isinstance(value, (tuple, list)):
        return [canonical_data(item) for item in value]
    raise ValueError('UNSUPPORTED_CANONICAL_TYPE')


def canonical_bytes(value: object) -> bytes:
    """UTF-8, NFC, compact sorted JSON; array order is semantically significant."""
    return json.dumps(canonical_data(value), sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def fingerprint(domain: str, value: object) -> str:
    """Hash domain + newline + canonical bytes; caller excludes its own hash field."""
    if domain not in ('FC_SEMANTICS_V1', 'FC_SOURCE_BUNDLE_V1', 'FC_PI_STATE_V1',
                      'FC_SNAPSHOT_V1', 'LAB_VECTOR_V2', 'LAB_ARTIFACT_V2'):
        raise ValueError('UNKNOWN_HASH_DOMAIN')
    return hashlib.sha256(domain.encode('ascii') + b'\n' + canonical_bytes(value)).hexdigest()


def semantic_fingerprint() -> str:
    """Content identity of the complete pinned semantic declaration."""
    return fingerprint('FC_SEMANTICS_V1', semantic_manifest())
