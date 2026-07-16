from datetime import datetime
from decimal import Decimal

from .calibrators import (
    FittedIsotonicCalibrator,
    FittedPlattCalibrator,
    CalibrationFitDiagnostics,
    IdentityCalibrator,
    IsotonicFitData,
    PlattFitData,
)
from .models import (
    CalibrationFitMetadata,
    CalibrationScope,
    CalibrationScopeKind,
    CalibrationTrainingWindow,
)


SERIALIZATION_VERSION = "calibrator-json-v1"


class CalibratorSerializer:
    def serialize(self, calibrator) -> dict[str, object]:
        payload: dict[str, object] = {
            "serialization_version": SERIALIZATION_VERSION,
            "method": calibrator.metadata.method_name,
            "metadata": _metadata_to_dict(calibrator.metadata),
        }
        if isinstance(calibrator, FittedPlattCalibrator):
            data = calibrator.fit_data
            payload["parameters"] = {
                "a": str(data.a),
                "b": str(data.b),
                "clipping_epsilon": str(data.clipping_epsilon),
                "regularization": str(data.regularization),
                "iteration_count": data.iteration_count,
                "converged": data.converged,
                "final_objective": str(data.final_objective),
            }
            payload["diagnostics"] = _diagnostics_to_dict(calibrator.diagnostics)
        elif isinstance(calibrator, FittedIsotonicCalibrator):
            data = calibrator.fit_data
            payload["parameters"] = {
                "breakpoints": [str(value) for value in data.breakpoints],
                "fitted_values": [str(value) for value in data.fitted_values],
                "block_observation_counts": list(data.block_observation_counts),
                "interpolation_policy": data.interpolation_policy,
                "output_epsilon": (
                    str(data.output_epsilon)
                    if data.output_epsilon is not None else None
                ),
            }
            payload["diagnostics"] = _diagnostics_to_dict(calibrator.diagnostics)
        elif isinstance(calibrator, IdentityCalibrator):
            payload["parameters"] = {}
        else:
            raise TypeError("Unsupported fitted calibrator.")
        return payload

    def deserialize(self, payload: dict[str, object]):
        if not isinstance(payload, dict):
            raise ValueError("Serialized calibrator must be an object.")
        if payload.get("serialization_version") != SERIALIZATION_VERSION:
            raise ValueError("Unknown serialized calibrator version.")
        method = payload.get("method")
        metadata = _metadata_from_dict(_dict(payload, "metadata"))
        parameters = _dict(payload, "parameters")
        if method != metadata.method_name:
            raise ValueError("Serialized method and metadata disagree.")
        try:
            if method == "identity":
                if parameters:
                    raise ValueError("Identity parameters must be empty.")
                return IdentityCalibrator(metadata)
            if method == "platt":
                return FittedPlattCalibrator(
                    metadata,
                    PlattFitData(
                        Decimal(_string(parameters, "a")),
                        Decimal(_string(parameters, "b")),
                        Decimal(_string(parameters, "clipping_epsilon")),
                        Decimal(_string(parameters, "regularization")),
                        _integer(parameters, "iteration_count"),
                        _boolean(parameters, "converged"),
                        Decimal(_string(parameters, "final_objective")),
                    ),
                    _diagnostics_from_dict(_dict(payload, "diagnostics")),
                )
            if method == "isotonic":
                epsilon = parameters.get("output_epsilon")
                return FittedIsotonicCalibrator(
                    metadata,
                    IsotonicFitData(
                        tuple(Decimal(value) for value in _list(parameters, "breakpoints")),
                        tuple(Decimal(value) for value in _list(parameters, "fitted_values")),
                        tuple(_integer_value(value) for value in _list(parameters, "block_observation_counts")),
                        _string(parameters, "interpolation_policy"),
                        Decimal(epsilon) if isinstance(epsilon, str) else None,
                    ),
                    _diagnostics_from_dict(_dict(payload, "diagnostics")),
                )
        except (ArithmeticError, TypeError, KeyError) as exc:
            raise ValueError("Malformed serialized calibrator.") from exc
        raise ValueError("Unknown calibration method.")


def _metadata_to_dict(value: CalibrationFitMetadata) -> dict[str, object]:
    return {
        "fitted_at": value.fitted_at.isoformat(),
        "training_window": {
            "start": value.training_window.start.isoformat(),
            "end": value.training_window.end.isoformat(),
        },
        "observation_count": value.observation_count,
        "positive_outcome_count": value.positive_outcome_count,
        "negative_outcome_count": value.negative_outcome_count,
        "scope": {
            "kind": value.scope.kind.value,
            "competition": value.scope.competition,
            "market": value.scope.market,
            "odds_band": value.scope.odds_band,
        },
        "method_name": value.method_name,
        "version": value.version,
        "model_version": value.model_version,
        "minimum_sample_requirement": value.minimum_sample_requirement,
        "configuration_fingerprint": value.configuration_fingerprint,
    }


def _diagnostics_to_dict(value: CalibrationFitDiagnostics) -> dict[str, object]:
    return {
        "finite_parameters": value.finite_parameters,
        "finite_predictions": value.finite_predictions,
        "outputs_in_range": value.outputs_in_range,
        "monotonic": value.monotonic,
        "converged": value.converged,
        "production_eligible": value.production_eligible,
        "training_brier_score": str(value.training_brier_score),
        "training_log_loss": str(value.training_log_loss),
        "training_expected_calibration_error": str(
            value.training_expected_calibration_error
        ),
        "training_maximum_calibration_error": str(
            value.training_maximum_calibration_error
        ),
    }


def _diagnostics_from_dict(value: dict[str, object]) -> CalibrationFitDiagnostics:
    return CalibrationFitDiagnostics(
        _boolean(value, "finite_parameters"),
        _boolean(value, "finite_predictions"),
        _boolean(value, "outputs_in_range"),
        _boolean(value, "monotonic"),
        _boolean(value, "converged"),
        _boolean(value, "production_eligible"),
        Decimal(_string(value, "training_brier_score")),
        Decimal(_string(value, "training_log_loss")),
        Decimal(_string(value, "training_expected_calibration_error")),
        Decimal(_string(value, "training_maximum_calibration_error")),
    )


def _metadata_from_dict(value: dict[str, object]) -> CalibrationFitMetadata:
    window = _dict(value, "training_window")
    scope = _dict(value, "scope")
    return CalibrationFitMetadata(
        fitted_at=datetime.fromisoformat(_string(value, "fitted_at")),
        training_window=CalibrationTrainingWindow(
            datetime.fromisoformat(_string(window, "start")),
            datetime.fromisoformat(_string(window, "end")),
        ),
        observation_count=_integer(value, "observation_count"),
        scope=CalibrationScope(
            CalibrationScopeKind(_string(scope, "kind")),
            competition=_optional_string(scope.get("competition")),
            market=_optional_string(scope.get("market")),
            odds_band=_optional_string(scope.get("odds_band")),
        ),
        method_name=_string(value, "method_name"),
        version=_string(value, "version"),
        model_version=_optional_string(value.get("model_version")),
        positive_outcome_count=_integer(value, "positive_outcome_count"),
        negative_outcome_count=_integer(value, "negative_outcome_count"),
        minimum_sample_requirement=_integer(value, "minimum_sample_requirement"),
        configuration_fingerprint=_string(value, "configuration_fingerprint"),
    )


def _dict(value, key):
    result = value.get(key)
    if not isinstance(result, dict):
        raise ValueError(f"Serialized {key} must be an object.")
    return result


def _list(value, key):
    result = value.get(key)
    if not isinstance(result, list):
        raise ValueError(f"Serialized {key} must be a list.")
    return result


def _string(value, key):
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"Serialized {key} must be a non-empty string.")
    return result


def _optional_string(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("Optional serialized string is malformed.")
    return value


def _integer(value, key):
    return _integer_value(value.get(key))


def _integer_value(value):
    if type(value) is not int:
        raise ValueError("Serialized integer is malformed.")
    return value


def _boolean(value, key):
    result = value.get(key)
    if type(result) is not bool:
        raise ValueError(f"Serialized {key} must be boolean.")
    return result
