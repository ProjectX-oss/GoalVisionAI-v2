from decimal import Decimal, localcontext
from typing import Iterable

from .binning import (
    CalibrationBinning,
    EqualWidthBinning,
    ExplicitBoundaryBinning,
    bin_index,
)
from .models import (
    ONE,
    ZERO,
    CalibrationBinReport,
    CalibrationObservation,
    CalibrationReport,
)


class CalibrationReportService:
    """Calculates deterministic binary calibration metrics at precision 50."""

    def __init__(self, binning: CalibrationBinning | None = None) -> None:
        selected = binning or EqualWidthBinning()
        self._boundaries = ExplicitBoundaryBinning(
            tuple(selected.boundaries)
        ).boundaries

    def evaluate(
        self,
        observations: Iterable[CalibrationObservation],
    ) -> CalibrationReport:
        ordered = tuple(sorted(observations, key=self._order_key))
        identifiers = tuple(item.observation_id for item in ordered)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Calibration observation IDs must be unique.")
        with localcontext() as context:
            context.prec = 50
            return self._evaluate(ordered)

    def _evaluate(
        self,
        observations: tuple[CalibrationObservation, ...],
    ) -> CalibrationReport:
        boundaries = self._boundaries
        grouped: list[list[CalibrationObservation]] = [
            [] for _ in range(len(boundaries) - 1)
        ]
        for observation in observations:
            grouped[bin_index(observation.raw_probability, boundaries)].append(
                observation
            )

        bins = tuple(
            self._build_bin(index, boundaries, tuple(values))
            for index, values in enumerate(grouped)
        )
        total = len(observations)
        if not total:
            return CalibrationReport(
                total_observations=0,
                mean_predicted_probability=ZERO,
                observed_success_rate=ZERO,
                brier_score=ZERO,
                log_loss=ZERO,
                expected_calibration_error=ZERO,
                maximum_calibration_error=ZERO,
                bins=bins,
            )

        total_decimal = Decimal(total)
        probabilities = tuple(item.raw_probability for item in observations)
        outcomes = tuple(Decimal(item.binary_outcome) for item in observations)
        ece = sum(
            (
                Decimal(item.observation_count)
                * (item.calibration_gap or ZERO)
            )
            for item in bins
        ) / total_decimal
        non_empty_gaps = tuple(
            item.calibration_gap
            for item in bins
            if item.calibration_gap is not None
        )
        return CalibrationReport(
            total_observations=total,
            mean_predicted_probability=sum(probabilities, ZERO) / total_decimal,
            observed_success_rate=sum(outcomes, ZERO) / total_decimal,
            brier_score=sum(
                (
                    observation.raw_probability
                    - Decimal(observation.binary_outcome)
                )
                ** 2
                for observation in observations
            )
            / total_decimal,
            log_loss=self._log_loss(observations),
            expected_calibration_error=ece,
            maximum_calibration_error=max(non_empty_gaps, default=ZERO),
            bins=bins,
        )

    @staticmethod
    def _build_bin(
        index: int,
        boundaries: tuple[Decimal, ...],
        observations: tuple[CalibrationObservation, ...],
    ) -> CalibrationBinReport:
        count = len(observations)
        if count:
            divisor = Decimal(count)
            mean = sum(
                (item.raw_probability for item in observations),
                ZERO,
            ) / divisor
            rate = sum(
                (Decimal(item.binary_outcome) for item in observations),
                ZERO,
            ) / divisor
            gap: Decimal | None = abs(mean - rate)
        else:
            mean = None
            rate = None
            gap = None
        return CalibrationBinReport(
            index=index,
            lower_bound=boundaries[index],
            upper_bound=boundaries[index + 1],
            includes_upper_bound=(index == len(boundaries) - 2),
            observation_count=count,
            mean_predicted_probability=mean,
            observed_success_rate=rate,
            calibration_gap=gap,
        )

    @staticmethod
    def _log_loss(
        observations: tuple[CalibrationObservation, ...],
    ) -> Decimal:
        losses: list[Decimal] = []
        for observation in observations:
            likelihood = (
                observation.raw_probability
                if observation.binary_outcome == 1
                else ONE - observation.raw_probability
            )
            if likelihood == ZERO:
                return Decimal("Infinity")
            losses.append(-likelihood.ln())
        return sum(losses, ZERO) / Decimal(len(losses))

    @staticmethod
    def _order_key(observation: CalibrationObservation) -> tuple[object, ...]:
        return (
            observation.prediction_timestamp,
            observation.observation_id,
            observation.fixture_id,
            observation.competition,
            observation.market,
            observation.selection,
        )
