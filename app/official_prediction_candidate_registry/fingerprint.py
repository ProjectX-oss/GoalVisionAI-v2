import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal

from .models import OfficialCandidateMarketIdentity, OfficialPredictionReasoningFact


def canonical_decimal(value: Decimal | None) -> str:
    if value is None:
        return "null"
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Canonical decimals must be finite Decimal values.")
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def canonical_timestamp(value: datetime | None) -> str:
    if value is None:
        return "null"
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Canonical timestamps must be timezone-aware.")
    return value.astimezone(timezone.utc).isoformat()


def canonical_items(values: dict[str, object]) -> tuple[tuple[str, str], ...]:
    return tuple(
        (key, _stable(value))
        for key, value in sorted(values.items())
    )


class OfficialCandidateRegistryFingerprint:
    LOGICAL_VERSION = "official-registry-logical-identity-v1"
    CONTENT_VERSION = "official-registry-content-v1"

    def logical_identity(
        self,
        *,
        prediction_id: str,
        match_id: str,
        model_version: str,
        market: OfficialCandidateMarketIdentity,
        bankroll_scope: str,
        destination_scope: str,
    ) -> str:
        return _digest({
            "version": self.LOGICAL_VERSION,
            "prediction_id": prediction_id,
            "match_id": match_id,
            "model_version": model_version,
            "market": market.market.value,
            "selection": market.selection,
            "market_line": canonical_decimal(market.market_line),
            "bankroll_scope": bankroll_scope,
            "destination_scope": destination_scope,
        })

    def content(self, material: dict[str, object]) -> str:
        return _digest({"version": self.CONTENT_VERSION, **material})


def reasoning_material(
    facts: tuple[OfficialPredictionReasoningFact, ...],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (
            fact.fact_type.value,
            fact.text,
            fact.source_reference or "",
        )
        for fact in facts
    )


def _stable(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, datetime):
        return canonical_timestamp(value)
    if isinstance(value, (tuple, list, dict)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def _digest(material: dict[str, object]) -> str:
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
