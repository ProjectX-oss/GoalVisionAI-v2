from decimal import Decimal


def normalize_text(value: object, label: str) -> str:
    normalized = " ".join(str(value).strip().split())
    if not normalized:
        raise ValueError(f"{label} must not be empty.")
    return normalized


def normalize_identifier(value: object, label: str) -> str:
    return normalize_text(value, label).lower()


def normalize_source(value: object) -> str:
    return normalize_text(value, "Source name").upper()


def decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Numeric evidence must be finite and non-negative.")
    return result
