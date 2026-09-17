"""Platform-independent transcendental operations for fingerprinted model data.

Keep binary64 inputs and outputs, but avoid the host C math library's last-bit
differences. Exact float conversion and a fresh, fixed Decimal context make the
intermediate calculation independent of both the OS and ambient Decimal state.
Fingerprint serialization remains lossless; no artifact values are rounded away.
"""

from decimal import Context, Decimal, ROUND_HALF_EVEN


def deterministic_exp(value: float) -> float:
    """Return exp(value) using a fixed 80-digit decimal calculation."""
    return float(Context(prec=80, rounding=ROUND_HALF_EVEN).exp(Decimal.from_float(value)))


def deterministic_log(value: float) -> float:
    """Return ln(value) using a fixed 80-digit decimal calculation."""
    return float(Context(prec=80, rounding=ROUND_HALF_EVEN).ln(Decimal.from_float(value)))


def deterministic_sqrt(value: float) -> float:
    """Return sqrt(value) using a fixed 80-digit decimal calculation."""
    return float(Context(prec=80, rounding=ROUND_HALF_EVEN).sqrt(Decimal.from_float(value)))


def square(value: float) -> float:
    """Square with binary64 multiplication instead of platform libm pow."""
    return value * value
