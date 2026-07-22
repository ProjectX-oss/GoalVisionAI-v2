"""Deterministic safe-parameter logistic estimators."""

from __future__ import annotations

import math

from app.historical_training_dataset import HistoricalTrainingExample

from .exceptions import EstimatorConvergenceError, InsufficientClassSupportError
from .fingerprint import sha256_fingerprint
from .models import FittedEstimator
from .policy import ModelTrainingPolicy


MATCH_RESULT = "MATCH_RESULT"
TOTAL_GOALS_BUCKET = "TOTAL_GOALS_BUCKET"
BTTS = "BTTS_YES"


def construct_targets(examples: tuple[HistoricalTrainingExample, ...]):
    result, totals, btts = [], [], []
    for example in examples:
        labels = dict(example.labels)
        result.append(0 if labels["HOME_WIN"] else 1 if labels["DRAW"] else 2)
        totals.append(
            3 if labels["OVER_3_5"] else 2 if labels["OVER_2_5"]
            else 1 if labels["OVER_1_5"] else 0
        )
        btts.append(labels["BTTS_YES"])
    return {
        MATCH_RESULT: tuple(result),
        TOTAL_GOALS_BUCKET: tuple(totals),
        BTTS: tuple(btts),
    }


def validate_class_support(targets) -> None:
    requirements = {MATCH_RESULT: set(range(3)), BTTS: {0, 1}}
    for identity, required in requirements.items():
        observed = set(targets[identity])
        if observed != required:
            raise InsufficientClassSupportError(
                f"{identity} requires classes {sorted(required)}; observed {sorted(observed)}."
            )
    totals = targets[TOTAL_GOALS_BUCKET]
    for threshold in (1, 2, 3):
        observed = {int(value >= threshold) for value in totals}
        if observed != {0, 1}:
            raise InsufficientClassSupportError(f"OVER_{threshold}_5 requires both binary classes.")


def fit_estimators(matrix, targets, policy: ModelTrainingPolicy, random_seed: int) -> tuple[FittedEstimator, ...]:
    definitions = (
        (MATCH_RESULT, ("HOME_WIN", "DRAW", "AWAY_WIN")),
        (TOTAL_GOALS_BUCKET, ("UNDER_1_5", "GOALS_2", "GOALS_3", "OVER_3_5")),
        (BTTS, ("BTTS_NO", "BTTS_YES")),
    )
    return tuple(
        _fit_softmax(identity, classes, matrix, targets[identity], policy, random_seed)
        for identity, classes in definitions
    )


def _fit_softmax(identity, classes, matrix, targets, policy, random_seed) -> FittedEstimator:
    row_count, width, class_count = len(matrix), len(matrix[0]), len(classes)
    coefficients = [[0.0] * width for _ in range(class_count)]
    intercepts = [0.0] * class_count
    learning_rate = float(policy.learning_rate)
    regularization = float(policy.regularization)
    tolerance = float(policy.convergence_tolerance)
    final_delta = float("inf")
    converged = False
    iterations = 0
    for iteration in range(1, policy.maximum_iterations + 1):
        gradients = [[0.0] * width for _ in range(class_count)]
        intercept_gradients = [0.0] * class_count
        for row, target in zip(matrix, targets):
            probabilities = _softmax(_scores(row, coefficients, intercepts))
            for class_index in range(class_count):
                error = probabilities[class_index] - (1.0 if target == class_index else 0.0)
                intercept_gradients[class_index] += error
                for feature_index, value in enumerate(row):
                    gradients[class_index][feature_index] += error * value
        final_delta = 0.0
        for class_index in range(class_count):
            delta = learning_rate * intercept_gradients[class_index] / row_count
            intercepts[class_index] -= delta
            final_delta = max(final_delta, abs(delta))
            for feature_index in range(width):
                gradient = gradients[class_index][feature_index] / row_count
                gradient += regularization * coefficients[class_index][feature_index]
                delta = learning_rate * gradient
                coefficients[class_index][feature_index] -= delta
                final_delta = max(final_delta, abs(delta))
        iterations = iteration
        if not math.isfinite(final_delta):
            break
        if final_delta <= tolerance:
            converged = True
            break
    if not converged:
        raise EstimatorConvergenceError(
            f"{identity} did not converge in {policy.maximum_iterations} iterations (delta={final_delta})."
        )
    payload = {
        "identity": identity, "model_type": "MULTINOMIAL_LOGISTIC_REGRESSION",
        "classes": classes, "coefficients": coefficients, "intercepts": intercepts,
        "iterations": iterations, "converged": converged, "final_delta": final_delta,
        "solver": policy.solver, "regularization": policy.regularization,
        "learning_rate": policy.learning_rate, "tolerance": policy.convergence_tolerance,
        "random_seed": random_seed,
    }
    return FittedEstimator(
        estimator_identity=identity, model_type="MULTINOMIAL_LOGISTIC_REGRESSION",
        class_order=classes, coefficients=tuple(tuple(row) for row in coefficients),
        intercepts=tuple(intercepts), iterations=iterations, converged=converged,
        final_delta=final_delta, estimator_fingerprint=sha256_fingerprint(payload),
    )


def predict_estimator(estimator: FittedEstimator, row: tuple[float, ...]) -> tuple[float, ...]:
    if len(row) != len(estimator.coefficients[0]):
        raise ValueError("Estimator input width mismatch.")
    return _softmax(_scores(row, estimator.coefficients, estimator.intercepts))


def _scores(row, coefficients, intercepts):
    return tuple(intercept + math.fsum(weight * value for weight, value in zip(weights, row)) for weights, intercept in zip(coefficients, intercepts))


def _softmax(scores):
    maximum = max(scores)
    exponentials = tuple(math.exp(score - maximum) for score in scores)
    denominator = math.fsum(exponentials)
    return tuple(value / denominator for value in exponentials)
