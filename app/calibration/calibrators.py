from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math
from typing import Protocol, Sequence, runtime_checkable

from .models import (
    CalibrationFitMetadata,
    CalibrationObservation,
    CalibrationScope,
    CalibrationScopeKind,
    CalibrationTrainingWindow,
    validate_aware,
    validate_probability,
)


class CalibrationFittingError(ValueError):
    """Typed failure for unsupported or unsafe calibration fitting."""


class CalibrationNonConvergenceError(CalibrationFittingError):
    pass


class CalibrationFittingNotImplemented(NotImplementedError):
    """Backward-compatible name; production trainers no longer raise this."""


@dataclass(frozen=True, slots=True)
class CalibrationFitRequest:
    fitted_at: datetime
    training_window: CalibrationTrainingWindow
    scope: CalibrationScope
    version: str
    target_prediction_timestamp: datetime | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        validate_aware(self.fitted_at, "Fitted timestamp")
        if self.fitted_at < self.training_window.end:
            raise ValueError("Fitted timestamp must not predate training data.")
        if not self.version.strip():
            raise ValueError("Calibration version must not be empty.")
        if self.model_version is not None and not self.model_version.strip():
            raise ValueError("Model version must not be empty when provided.")
        if self.target_prediction_timestamp is not None:
            validate_aware(self.target_prediction_timestamp, "Target prediction timestamp")
            if self.training_window.end >= self.target_prediction_timestamp:
                raise ValueError("Training cutoff must be strictly earlier than the target.")


@runtime_checkable
class FittedProbabilityCalibrator(Protocol):
    @property
    def metadata(self) -> CalibrationFitMetadata: ...
    def calibrate(self, probability: Decimal) -> Decimal: ...


@runtime_checkable
class ProbabilityCalibratorTrainer(Protocol):
    def fit(
        self,
        observations: Sequence[CalibrationObservation],
        request: CalibrationFitRequest,
    ) -> FittedProbabilityCalibrator: ...


@dataclass(frozen=True, slots=True)
class CalibrationFittingPolicy:
    global_minimum: int = 100
    market_minimum: int = 100
    competition_minimum: int = 100
    competition_market_minimum: int = 100
    odds_band_minimum: int = 100
    minimum_positive: int = 10
    minimum_negative: int = 10
    allow_single_class_isotonic: bool = False

    def __post_init__(self) -> None:
        values = (
            self.global_minimum,
            self.market_minimum,
            self.competition_minimum,
            self.competition_market_minimum,
            self.odds_band_minimum,
            self.minimum_positive,
            self.minimum_negative,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("Calibration fitting minimums must be positive integers.")

    def minimum_for(self, kind: CalibrationScopeKind) -> int:
        return {
            CalibrationScopeKind.GLOBAL: self.global_minimum,
            CalibrationScopeKind.MARKET: self.market_minimum,
            CalibrationScopeKind.COMPETITION: self.competition_minimum,
            CalibrationScopeKind.COMPETITION_MARKET: self.competition_market_minimum,
            CalibrationScopeKind.ODDS_BAND: self.odds_band_minimum,
            CalibrationScopeKind.IDENTITY: 0,
        }[kind]


@dataclass(frozen=True, slots=True)
class PlattFittingConfig:
    epsilon: Decimal = Decimal("0.000001")
    regularization: Decimal = Decimal("0.001")
    maximum_iterations: int = 100
    convergence_tolerance: Decimal = Decimal("0.000000001")

    def __post_init__(self) -> None:
        if not Decimal("0") < self.epsilon < Decimal("0.5"):
            raise ValueError("Platt epsilon must be in (0, 0.5).")
        if self.regularization <= 0 or not self.regularization.is_finite():
            raise ValueError("Platt regularization must be positive and finite.")
        if self.maximum_iterations <= 0:
            raise ValueError("Platt maximum iterations must be positive.")
        if self.convergence_tolerance <= 0:
            raise ValueError("Platt convergence tolerance must be positive.")


@dataclass(frozen=True, slots=True)
class IsotonicFittingConfig:
    output_epsilon: Decimal | None = None
    interpolation_policy: str = "RIGHT_CONTINUOUS_STEP"

    def __post_init__(self) -> None:
        if self.output_epsilon is not None and not (
            Decimal("0") < self.output_epsilon < Decimal("0.5")
        ):
            raise ValueError("Isotonic output epsilon must be in (0, 0.5).")
        if self.interpolation_policy != "RIGHT_CONTINUOUS_STEP":
            raise ValueError("Unsupported isotonic interpolation policy.")


@dataclass(frozen=True, slots=True)
class PlattFitData:
    a: Decimal
    b: Decimal
    clipping_epsilon: Decimal
    regularization: Decimal
    iteration_count: int
    converged: bool
    final_objective: Decimal


@dataclass(frozen=True, slots=True)
class IsotonicFitData:
    breakpoints: tuple[Decimal, ...]
    fitted_values: tuple[Decimal, ...]
    block_observation_counts: tuple[int, ...]
    interpolation_policy: str
    output_epsilon: Decimal | None

    def __post_init__(self) -> None:
        if not self.breakpoints or len(self.breakpoints) != len(self.fitted_values):
            raise ValueError("Isotonic breakpoints and values must be non-empty and aligned.")
        if len(self.block_observation_counts) != len(self.breakpoints):
            raise ValueError("Isotonic block counts must align with breakpoints.")
        if any(a >= b for a, b in zip(self.breakpoints, self.breakpoints[1:])):
            raise ValueError("Isotonic breakpoints must be strictly increasing.")
        if any(a > b for a, b in zip(self.fitted_values, self.fitted_values[1:])):
            raise ValueError("Isotonic fitted values must be non-decreasing.")
        for value in self.breakpoints + self.fitted_values:
            validate_probability(value)
        if any(count <= 0 for count in self.block_observation_counts):
            raise ValueError("Isotonic block counts must be positive.")


@dataclass(frozen=True, slots=True)
class CalibrationFitDiagnostics:
    finite_parameters: bool
    finite_predictions: bool
    outputs_in_range: bool
    monotonic: bool
    converged: bool
    production_eligible: bool
    training_brier_score: Decimal
    training_log_loss: Decimal
    training_expected_calibration_error: Decimal
    training_maximum_calibration_error: Decimal


@dataclass(frozen=True, slots=True)
class IdentityCalibrator:
    metadata: CalibrationFitMetadata

    @classmethod
    def fit(cls, observations, request):
        ordered = _validate_fit_observations(observations, request)
        return cls(_metadata(ordered, request, "identity", 0, "identity"))

    @classmethod
    def fallback(cls, at: datetime, version: str = "identity-v1"):
        validate_aware(at, "Identity fallback timestamp")
        return cls(CalibrationFitMetadata(
            fitted_at=at,
            training_window=CalibrationTrainingWindow(at, at),
            observation_count=0,
            scope=CalibrationScope.identity_scope(),
            method_name="identity",
            version=version,
            configuration_fingerprint="identity",
        ))

    def calibrate(self, probability: Decimal) -> Decimal:
        validate_probability(probability)
        return probability


@dataclass(frozen=True, slots=True)
class FittedPlattCalibrator:
    metadata: CalibrationFitMetadata
    fit_data: PlattFitData
    diagnostics: CalibrationFitDiagnostics

    def calibrate(self, probability: Decimal) -> Decimal:
        validate_probability(probability)
        epsilon = float(self.fit_data.clipping_epsilon)
        p = min(1.0 - epsilon, max(epsilon, float(probability)))
        z = math.log(p / (1.0 - p))
        value = _sigmoid(float(self.fit_data.a) * z + float(self.fit_data.b))
        if not math.isfinite(value):
            raise CalibrationFittingError("Platt prediction is non-finite.")
        return Decimal(str(value))


class PlattCalibrator:
    method_name = "platt"

    def __init__(
        self,
        config: PlattFittingConfig | None = None,
        policy: CalibrationFittingPolicy | None = None,
    ) -> None:
        self.config = config or PlattFittingConfig()
        self.policy = policy or CalibrationFittingPolicy()

    def fit(self, observations, request) -> FittedPlattCalibrator:
        ordered = _validate_fit_observations(observations, request)
        minimum = self.policy.minimum_for(request.scope.kind)
        positives, negatives = _validate_sample(
            ordered, minimum, self.policy.minimum_positive, self.policy.minimum_negative
        )
        epsilon = float(self.config.epsilon)
        regularization = float(self.config.regularization)
        values = [
            (
                math.log(
                    min(1 - epsilon, max(epsilon, float(item.raw_probability)))
                    / (1 - min(1 - epsilon, max(epsilon, float(item.raw_probability))))
                ),
                float(item.binary_outcome),
            )
            for item in ordered
        ]
        a, b = 1.0, 0.0
        converged = False
        iteration = 0
        for iteration in range(1, self.config.maximum_iterations + 1):
            g_a = regularization * a
            g_b = regularization * b
            h_aa = regularization
            h_ab = 0.0
            h_bb = regularization
            for z, outcome in values:
                prediction = _sigmoid(a * z + b)
                residual = prediction - outcome
                weight = max(prediction * (1.0 - prediction), 1e-15)
                g_a += residual * z
                g_b += residual
                h_aa += weight * z * z
                h_ab += weight * z
                h_bb += weight
            determinant = h_aa * h_bb - h_ab * h_ab
            if not math.isfinite(determinant) or determinant <= 1e-18:
                raise CalibrationFittingError("Platt Hessian is singular.")
            delta_a = (h_bb * g_a - h_ab * g_b) / determinant
            delta_b = (-h_ab * g_a + h_aa * g_b) / determinant
            a -= delta_a
            b -= delta_b
            if not math.isfinite(a) or not math.isfinite(b):
                raise CalibrationFittingError("Platt parameters became non-finite.")
            if max(abs(delta_a), abs(delta_b)) <= float(self.config.convergence_tolerance):
                converged = True
                break
        if not converged:
            raise CalibrationNonConvergenceError("Platt fitting did not converge.")
        objective = _platt_objective(values, a, b, regularization)
        fit_data = PlattFitData(
            Decimal(str(a)), Decimal(str(b)), self.config.epsilon,
            self.config.regularization, iteration, True, Decimal(str(objective)),
        )
        fingerprint = _fingerprint("platt", self.config, self.policy)
        metadata = _metadata(ordered, request, "platt", minimum, fingerprint)
        provisional = FittedPlattCalibrator(
            metadata, fit_data, _empty_diagnostics()
        )
        diagnostics = _diagnostics(
            provisional, ordered, monotonic_required=(a >= 0), converged=True
        )
        fitted = FittedPlattCalibrator(metadata, fit_data, diagnostics)
        if not diagnostics.production_eligible:
            raise CalibrationFittingError("Platt diagnostics are not production-eligible.")
        return fitted


@dataclass(frozen=True, slots=True)
class FittedIsotonicCalibrator:
    metadata: CalibrationFitMetadata
    fit_data: IsotonicFitData
    diagnostics: CalibrationFitDiagnostics

    def calibrate(self, probability: Decimal) -> Decimal:
        validate_probability(probability)
        index = bisect_left(self.fit_data.breakpoints, probability)
        if index >= len(self.fit_data.breakpoints):
            index = len(self.fit_data.breakpoints) - 1
        return self.fit_data.fitted_values[index]


class IsotonicCalibrator:
    method_name = "isotonic"

    def __init__(
        self,
        config: IsotonicFittingConfig | None = None,
        policy: CalibrationFittingPolicy | None = None,
    ) -> None:
        self.config = config or IsotonicFittingConfig()
        self.policy = policy or CalibrationFittingPolicy()

    def fit(self, observations, request) -> FittedIsotonicCalibrator:
        ordered = tuple(sorted(
            _validate_fit_observations(observations, request),
            key=lambda item: (
                item.raw_probability, item.prediction_timestamp, item.observation_id
            ),
        ))
        minimum = self.policy.minimum_for(request.scope.kind)
        positives = sum(item.binary_outcome for item in ordered)
        negatives = len(ordered) - positives
        if len(ordered) < minimum:
            raise CalibrationFittingError("Insufficient total calibration sample.")
        if not self.policy.allow_single_class_isotonic:
            if positives < self.policy.minimum_positive:
                raise CalibrationFittingError("Insufficient positive calibration outcomes.")
            if negatives < self.policy.minimum_negative:
                raise CalibrationFittingError("Insufficient negative calibration outcomes.")
        grouped: list[list[object]] = []
        for item in ordered:
            if grouped and grouped[-1][0] == item.raw_probability:
                grouped[-1][1] += item.binary_outcome
                grouped[-1][2] += 1
            else:
                grouped.append([item.raw_probability, item.binary_outcome, 1])
        blocks: list[list[object]] = []
        for breakpoint, successes, count in grouped:
            blocks.append([breakpoint, breakpoint, successes, count])
            while len(blocks) >= 2:
                left, right = blocks[-2], blocks[-1]
                if Decimal(left[2]) / Decimal(left[3]) <= Decimal(right[2]) / Decimal(right[3]):
                    break
                blocks[-2:] = [[left[0], right[1], left[2] + right[2], left[3] + right[3]]]
        breakpoints = []
        values = []
        counts = []
        epsilon = self.config.output_epsilon
        for _, upper, successes, count in blocks:
            value = Decimal(successes) / Decimal(count)
            if epsilon is not None:
                value = min(Decimal("1") - epsilon, max(epsilon, value))
            breakpoints.append(upper)
            values.append(value)
            counts.append(count)
        fit_data = IsotonicFitData(
            tuple(breakpoints), tuple(values), tuple(counts),
            self.config.interpolation_policy, epsilon,
        )
        fingerprint = _fingerprint("isotonic", self.config, self.policy)
        metadata = _metadata(ordered, request, "isotonic", minimum, fingerprint)
        provisional = FittedIsotonicCalibrator(
            metadata, fit_data, _empty_diagnostics()
        )
        diagnostics = _diagnostics(
            provisional, ordered, monotonic_required=True, converged=True
        )
        fitted = FittedIsotonicCalibrator(metadata, fit_data, diagnostics)
        if not diagnostics.production_eligible:
            raise CalibrationFittingError("Isotonic diagnostics are not production-eligible.")
        return fitted


def _metadata(observations, request, method, minimum, fingerprint):
    positives = sum(item.binary_outcome for item in observations)
    return CalibrationFitMetadata(
        fitted_at=request.fitted_at,
        training_window=request.training_window,
        observation_count=len(observations),
        scope=request.scope,
        method_name=method,
        version=request.version,
        model_version=request.model_version,
        positive_outcome_count=positives,
        negative_outcome_count=len(observations) - positives,
        minimum_sample_requirement=minimum,
        configuration_fingerprint=fingerprint,
    )


def _validate_sample(observations, minimum, minimum_positive, minimum_negative):
    positives = sum(item.binary_outcome for item in observations)
    negatives = len(observations) - positives
    if len(observations) < minimum:
        raise CalibrationFittingError("Insufficient total calibration sample.")
    if positives < minimum_positive:
        raise CalibrationFittingError("Insufficient positive calibration outcomes.")
    if negatives < minimum_negative:
        raise CalibrationFittingError("Insufficient negative calibration outcomes.")
    return positives, negatives


def _sigmoid(value: float) -> float:
    if value >= 0:
        exponent = math.exp(-value)
        return 1.0 / (1.0 + exponent)
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _platt_objective(values, a, b, regularization):
    total = regularization * (a * a + b * b) / 2
    for z, outcome in values:
        score = a * z + b
        total += max(score, 0.0) - outcome * score + math.log1p(math.exp(-abs(score)))
    return total


def _fingerprint(method, config, policy):
    def encode(value):
        if isinstance(value, Decimal):
            return str(value)
        if hasattr(value, "__dataclass_fields__"):
            return {name: encode(getattr(value, name)) for name in value.__dataclass_fields__}
        return value
    payload = json.dumps(
        {"method": method, "config": encode(config), "policy": encode(policy)},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _diagnostics(calibrator, observations, monotonic_required, converged):
    from dataclasses import replace
    from .report import CalibrationReportService

    outputs = tuple(calibrator.calibrate(item.raw_probability) for item in observations)
    finite = all(value.is_finite() for value in outputs)
    in_range = all(Decimal("0") <= value <= Decimal("1") for value in outputs)
    pairs = sorted(
        ((item.raw_probability, calibrator.calibrate(item.raw_probability)) for item in observations)
    )
    monotonic = not any(left[1] > right[1] for left, right in zip(pairs, pairs[1:]))
    report = CalibrationReportService().evaluate(tuple(
        replace(item, raw_probability=calibrator.calibrate(item.raw_probability))
        for item in observations
    ))
    finite_parameters = True
    data = getattr(calibrator, "fit_data", None)
    if isinstance(data, PlattFitData):
        finite_parameters = data.a.is_finite() and data.b.is_finite()
    eligible = (
        finite_parameters
        and finite
        and in_range
        and (monotonic or not monotonic_required)
        and converged
    )
    return CalibrationFitDiagnostics(
        finite_parameters,
        finite,
        in_range,
        monotonic,
        converged,
        eligible,
        report.brier_score,
        report.log_loss,
        report.expected_calibration_error,
        report.maximum_calibration_error,
    )


def _empty_diagnostics():
    return CalibrationFitDiagnostics(
        True, True, True, True, True, True,
        Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
    )


def _validate_fit_observations(observations, request):
    ordered = tuple(sorted(
        observations,
        key=lambda item: (item.prediction_timestamp, item.observation_id, item.fixture_id),
    ))
    identifiers = tuple(item.observation_id for item in ordered)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Calibration fit observation IDs must be unique.")
    for observation in ordered:
        if not (
            request.training_window.start
            <= observation.prediction_timestamp
            <= request.training_window.end
        ):
            raise ValueError("Calibration fit contains data outside its training window.")
        if observation.outcome_timestamp > request.training_window.end:
            raise ValueError("Calibration fit contains an outcome unavailable at the cutoff.")
        if request.target_prediction_timestamp is not None and (
            observation.prediction_timestamp >= request.target_prediction_timestamp
            or observation.outcome_timestamp >= request.target_prediction_timestamp
        ):
            raise ValueError("Calibration fit contains future target information.")
        if not observation_matches_scope(observation, request.scope):
            raise ValueError("Calibration observation does not match the fit scope.")
        if request.model_version is not None and observation.model_version != request.model_version:
            raise ValueError("Calibration observation does not match the model version.")
    return ordered


def observation_matches_scope(observation, scope):
    if scope.kind in {CalibrationScopeKind.GLOBAL, CalibrationScopeKind.IDENTITY}:
        return True
    if scope.kind is CalibrationScopeKind.COMPETITION:
        return observation.competition == scope.competition
    if scope.kind is CalibrationScopeKind.MARKET:
        return observation.market == scope.market
    if scope.kind is CalibrationScopeKind.COMPETITION_MARKET:
        return observation.competition == scope.competition and observation.market == scope.market
    if scope.kind is CalibrationScopeKind.ODDS_BAND:
        return observation.odds_band == scope.odds_band
    return False
