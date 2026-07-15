from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Protocol, runtime_checkable

from .models import ONE, ZERO, validate_probability


@runtime_checkable
class CalibrationBinning(Protocol):
    @property
    def boundaries(self) -> tuple[Decimal, ...]: ...


@dataclass(frozen=True, slots=True)
class EqualWidthBinning:
    bin_count: int = 10

    def __post_init__(self) -> None:
        if type(self.bin_count) is not int or self.bin_count <= 0:
            raise ValueError("Bin count must be a positive integer.")

    @property
    def boundaries(self) -> tuple[Decimal, ...]:
        with localcontext() as context:
            context.prec = 50
            count = Decimal(self.bin_count)
            return tuple(Decimal(index) / count for index in range(self.bin_count)) + (
                ONE,
            )


@dataclass(frozen=True, slots=True)
class ExplicitBoundaryBinning:
    """Probability edges including 0 and 1, strictly increasing."""

    boundaries: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        if len(self.boundaries) < 2:
            raise ValueError("At least the 0 and 1 boundaries are required.")
        for boundary in self.boundaries:
            validate_probability(boundary, "Calibration boundary")
        if self.boundaries[0] != ZERO or self.boundaries[-1] != ONE:
            raise ValueError("Explicit boundaries must start at 0 and end at 1.")
        if any(
            left >= right
            for left, right in zip(self.boundaries, self.boundaries[1:])
        ):
            raise ValueError(
                "Explicit boundaries must be sorted, unique, and non-overlapping."
            )


def bin_index(probability: Decimal, boundaries: tuple[Decimal, ...]) -> int:
    """Assigns [lower, upper) bins; only the final bin includes probability 1."""

    validate_probability(probability)
    for index, upper in enumerate(boundaries[1:]):
        if probability < upper or index == len(boundaries) - 2:
            return index
    raise AssertionError("Validated probability was not assigned to a bin.")
