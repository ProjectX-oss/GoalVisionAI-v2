import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from .models import OfficialCandidateAssembly


def stable_value(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return value.isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value)
        normalized = value.normalize()
        return "0" if normalized == 0 else format(normalized, "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def canonical_items(values: dict[str, object]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (key, stable_value(value)) for key, value in sorted(values.items())
    )


def fingerprint_items(items: tuple[tuple[str, str], ...]) -> str:
    payload = json.dumps(
        {"facts": items},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OfficialCandidateFingerprint:
    """Canonical SHA-256 identity for every material assembled fact."""

    VERSION = "official-candidate-fingerprint-v1"

    def generate(self, assembly: OfficialCandidateAssembly) -> str:
        payload = json.dumps(
            {
                "version": self.VERSION,
                "facts": assembly.normalized_input,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
